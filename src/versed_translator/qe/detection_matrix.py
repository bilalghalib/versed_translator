"""C4 detection matrix — does existing QE catch our 15 corruption types?

Method: take clean translations produced in C2, corrupt each one in every
applicable way (`qe.injectors`), then score BOTH the clean and the corrupted
version with a reference-free QE system. The signal we care about is the
*drop*:

    delta = score(clean) - score(corrupted)

A QE system that detects an error scores the corrupted version materially
lower. One that doesn't is blind to that failure mode — which is exactly what
the master plan wants measured before anyone trains a custom QE model.

Two properties this module is careful about:

* **Paired comparison.** Clean and corrupted are scored in the same batch
  against the same source segment, so the delta isn't confounded by passage
  difficulty. An absolute score tells you little; the paired delta is the
  measurement.
* **Detection is a threshold question, not a binary.** We report the delta
  distribution per error type, plus the fraction exceeding a stated
  threshold, rather than declaring "detected/missed" from one arbitrary cut.
  The threshold belongs to C5's routing decision, not to this study.

COMETKiwi is CC-BY-NC-SA: fine for this internal study, but it must not be
required by anything Versed ships commercially (see roadmap D4b).
"""

from __future__ import annotations

import json
import statistics
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

from versed_translator.qe.injectors import Injection, inject_all

DEFAULT_QE_MODEL = "Unbabel/wmt22-cometkiwi-da"


@dataclass(frozen=True)
class ScoredPair:
    item_id: str
    injector: str
    taxonomy: str
    severity: str
    clean_score: float
    corrupted_score: float

    @property
    def delta(self) -> float:
        """Positive means the QE system scored the corruption lower, i.e.
        it noticed something. Near-zero or negative means it did not."""
        return self.clean_score - self.corrupted_score


def build_pairs(
    items: dict[str, str],
    translations: dict[str, str],
    seed: int = 0,
    limit: int | None = None,
) -> list[tuple[str, str, Injection]]:
    """(item_id, source_arabic, injection) for every applicable corruption.

    `items` maps item_id -> Arabic source; `translations` maps item_id ->
    clean English translation.
    """
    pairs: list[tuple[str, str, Injection]] = []
    for item_id, source in items.items():
        translation = translations.get(item_id)
        if not translation or not source:
            continue
        for injection in inject_all(translation, seed=seed):
            pairs.append((item_id, source, injection))
        if limit is not None and len({p[0] for p in pairs}) >= limit:
            break
    return pairs


def score_pairs(
    pairs: list[tuple[str, str, Injection]],
    scorer: Callable[[list[str], list[str]], list[float]],
    batch_size: int = 32,
) -> list[ScoredPair]:
    """Score clean and corrupted sides of every pair with `scorer`.

    `scorer(sources, hypotheses) -> list[float]` keeps this module testable
    without loading a 2GB model: unit tests pass a stub, production passes
    the COMETKiwi wrapper below.
    """
    if not pairs:
        return []

    sources: list[str] = []
    hyps: list[str] = []
    for _item_id, source, injection in pairs:
        sources.extend([source, source])
        hyps.extend([injection.original, injection.corrupted])

    scores = scorer(sources, hyps)
    if len(scores) != len(hyps):
        raise ValueError(
            f"scorer returned {len(scores)} scores for {len(hyps)} inputs — "
            "clean/corrupted pairing would be misaligned"
        )

    out: list[ScoredPair] = []
    for i, (item_id, _source, injection) in enumerate(pairs):
        out.append(
            ScoredPair(
                item_id=item_id,
                injector=injection.injector,
                taxonomy=injection.taxonomy,
                severity=injection.severity,
                clean_score=scores[2 * i],
                corrupted_score=scores[2 * i + 1],
            )
        )
    return out


def summarize(scored: Iterable[ScoredPair], threshold: float = 0.02) -> dict:
    """Per-injector delta distribution + fraction exceeding `threshold`.

    `threshold` is deliberately a parameter, not a constant: what counts as
    "detected" is a routing decision for C5, calibrated against human
    judgments. Here it only labels the summary.
    """
    scored = list(scored)
    by_injector: dict[str, list[ScoredPair]] = {}
    for s in scored:
        by_injector.setdefault(s.injector, []).append(s)

    rows = []
    for injector, group in sorted(by_injector.items()):
        deltas = [g.delta for g in group]
        detected = [d for d in deltas if d >= threshold]
        rows.append(
            {
                "injector": injector,
                "taxonomy": group[0].taxonomy,
                "severity": group[0].severity,
                "n": len(deltas),
                "mean_delta": round(statistics.fmean(deltas), 5),
                "median_delta": round(statistics.median(deltas), 5),
                "min_delta": round(min(deltas), 5),
                "max_delta": round(max(deltas), 5),
                "detection_rate": round(len(detected) / len(deltas), 4),
            }
        )

    rows.sort(key=lambda r: r["detection_rate"])
    return {
        "threshold": threshold,
        "total_pairs": len(scored),
        "n_injectors": len(rows),
        "overall_detection_rate": (
            round(sum(r["detection_rate"] * r["n"] for r in rows) / len(scored), 4)
            if scored else None
        ),
        "by_injector": rows,
    }


def render_markdown(summary: dict, title: str = "QE Detection Matrix") -> str:
    lines = [
        f"# {title}",
        "",
        f"- Pairs scored: **{summary['total_pairs']}**",
        f"- Error types covered: **{summary['n_injectors']}/15**",
        f"- Detection threshold (delta >=): **{summary['threshold']}**",
        f"- Overall detection rate: **{summary['overall_detection_rate']}**",
        "",
        "Sorted worst-detected first — the top rows are the blind spots.",
        "",
        "| injector | taxonomy | severity | n | mean delta | median | detection rate |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for r in summary["by_injector"]:
        lines.append(
            f"| {r['injector']} | {r['taxonomy']} | {r['severity']} | {r['n']} | "
            f"{r['mean_delta']} | {r['median_delta']} | {r['detection_rate']} |"
        )
    reading = (
        "**Reading this:** delta = clean score - corrupted score. A high mean "
        "delta means the QE system reliably notices that corruption; a delta "
        "near zero means it is blind to it. Severity is what the error would "
        "cost a reader at corpus scale, so a `critical` row with a low "
        "detection rate is the finding that matters most."
    )
    lines += ["", reading]
    return "\n".join(lines)


def load_cometkiwi(model_name: str = DEFAULT_QE_MODEL, batch_size: int = 8, gpus: int = 0):
    """Return a `scorer(sources, hypotheses) -> list[float]` backed by COMETKiwi.

    Imported lazily so the rest of this module (and its tests) stay usable
    without the 2GB model or the comet dependency.
    """
    from comet import download_model, load_from_checkpoint

    path = download_model(model_name)
    model = load_from_checkpoint(path)

    def scorer(sources: list[str], hypotheses: list[str]) -> list[float]:
        data = [{"src": s, "mt": h} for s, h in zip(sources, hypotheses)]
        out = model.predict(data, batch_size=batch_size, gpus=gpus, progress_bar=False)
        return list(out["scores"])

    return scorer


def write_reports(summary: dict, out_dir: Path, title: str = "QE Detection Matrix") -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "detection_matrix.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    (out_dir / "detection_matrix.md").write_text(
        render_markdown(summary, title=title), encoding="utf-8"
    )


def write_scored_pairs(scored: Iterable[ScoredPair], path: Path) -> None:
    """Raw per-pair scores, for re-analysis at a different threshold."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for s in scored:
            row = asdict(s)
            row["delta"] = s.delta
            f.write(json.dumps(row) + "\n")
