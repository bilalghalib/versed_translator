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

Two QE backends are wired up here, both reference-free:

* **COMETKiwi** (`load_cometkiwi`) — CC-BY-NC-SA. Fine for this internal
  study, but it must not be required by anything Versed ships commercially
  (see roadmap D4b).
* **MetricX-24-Hybrid** (`load_metricx`) — Apache-2.0 and ungated, so it is
  the shippable candidate. Its native output is an *error* score on [0, 25]
  where lower is better; `load_metricx` negates it so both backends satisfy
  the same higher-is-better contract everything downstream assumes.

Both are exposed as the same duck-typed callable,
`scorer(sources, hypotheses) -> list[float]`, which must be order- and
length-preserving because `score_pairs` interleaves clean/corrupted.
"""

from __future__ import annotations

import json
import statistics
import sys
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

from versed_translator.qe.injectors import Injection, inject_all

DEFAULT_QE_MODEL = "Unbabel/wmt22-cometkiwi-da"

DEFAULT_METRICX_MODEL = "google/metricx-24-hybrid-large-v2p6"
# MetricX ships no tokenizer of its own; it is mT5 underneath, and the model
# size must match (Large -> mt5-large).
DEFAULT_METRICX_TOKENIZER = "google/mt5-large"
# Upstream's documented value for MetricX-24. The README warns that raising it
# leads to "unpredictable behavior" — the model never saw longer inputs.
METRICX_MAX_INPUT_LENGTH = 1536

# What counts as "the QE system noticed something" is scale-dependent, so the
# default threshold has to be per-model. It is NOT a quality judgment shared
# across backends — do not compare a COMETKiwi delta to a MetricX delta.
#
#   cometkiwi: scores live on [0, 1]. 0.02 = 2% of the range (the C4 default,
#             kept unchanged so the existing tg27b-full baseline stays
#             comparable).
#   metricx:  scores live on [0, 25]. The same 2%-of-range proportion gives
#             0.5. That lands on the same number from a second, independent
#             direction: MetricX-24 regresses MQM, whose penalty weights are
#             minor=1 / major=5 / critical=10 on this scale, so 0.5 is half a
#             minor error — the smallest movement that is plausibly a judgment
#             rather than regression noise. Both arguments agree on 0.5, which
#             is why it is the default rather than a tuned value; C5 should
#             recalibrate it against human judgments.
DEFAULT_THRESHOLDS: dict[str, float] = {"cometkiwi": 0.02, "metricx": 0.5}

QE_MODEL_IDS: dict[str, str] = {
    "cometkiwi": DEFAULT_QE_MODEL,
    "metricx": DEFAULT_METRICX_MODEL,
}


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
    ]
    if summary.get("qe_model"):
        lines.append(f"- QE model: **{summary['qe_model']}**")
    if summary.get("score_note"):
        lines.append(f"- Score scale: {summary['score_note']}")
    lines += [
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
        # num_workers=1: comet 2.2.x passes a multiprocessing_context to its
        # DataLoader unconditionally, which newer torch rejects when
        # num_workers=0 ("multiprocessing_context can only be used with
        # multi-process loading"). One worker satisfies torch without
        # meaningfully changing throughput at this batch size.
        out = model.predict(
            data,
            batch_size=batch_size,
            gpus=gpus,
            progress_bar=False,
            num_workers=1,
        )
        return list(out["scores"])

    return scorer


def metricx_qe_input(source: str, hypothesis: str) -> str:
    """The exact QE input string MetricX-24 was trained on.

    Verbatim from `metricx24/predict.py`'s `_make_input` (qe branch):
    `"source: " + source + " candidate: " + hypothesis`. MetricX-24 is a
    hybrid model — the reference-based form appends `" reference: " + ref`,
    and reference-free means that segment is simply absent, NOT an empty
    `reference:` marker. Spacing and the lowercase markers are part of the
    learned format; changing them silently degrades the score.
    """
    return f"source: {source} candidate: {hypothesis}"


def metricx_encode(tokenizer, texts: list[str], max_input_length: int):
    """Tokenize for MetricX. Returns `(batch, n_truncated)`.

    Truncate, drop the trailing EOS, then pad — in that order.

    The EOS strip is the detail that is easy to get wrong. MetricX was trained
    in T5X, whose inputs carry no EOS, but the HF mT5 tokenizer appends one.
    Upstream drops the final token unconditionally, and crucially does so
    *after truncation and before padding* — strip after padding and you remove
    a pad token while leaving the EOS in place, which shifts every score with
    no error and no obvious symptom.

    `n_truncated` counts sequences that hit `max_input_length`. This is not
    cosmetic: the input is `source: ... candidate: ...`, so truncation eats
    the *candidate* first — the very text being judged. A truncated QE score
    is not a QE score, and callers must be told.

    Split out from `load_metricx` so a stub tokenizer can pin this in tests
    without the 4.9GB checkpoint.
    """
    enc = tokenizer(
        texts,
        max_length=max_input_length,
        truncation=True,
        padding=False,
    )
    n_truncated = sum(1 for row in enc["input_ids"] if len(row) >= max_input_length)
    batch = tokenizer.pad(
        {
            "input_ids": [row[:-1] for row in enc["input_ids"]],
            "attention_mask": [row[:-1] for row in enc["attention_mask"]],
        },
        return_tensors="pt",
    )
    return batch, n_truncated


def load_metricx(
    model_name: str = DEFAULT_METRICX_MODEL,
    tokenizer_name: str = DEFAULT_METRICX_TOKENIZER,
    batch_size: int = 8,
    max_input_length: int = METRICX_MAX_INPUT_LENGTH,
    device: str | None = None,
    progress_every: int = 0,
):
    """Return a `scorer(sources, hypotheses) -> list[float]` backed by MetricX-24.

    ============================ POLARITY WARNING ============================
    MetricX natively emits an **error** score on [0, 25] where **lower is
    better** (0 = flawless, 25 = worst). Everything downstream of this
    module — `ScoredPair.delta = clean - corrupted`, `summarize`'s
    `d >= threshold`, the "worst-detected first" sort in `render_markdown` —
    assumes higher-is-better.

    So this closure returns **-raw**, i.e. scores on [-25, 0], higher-is-
    better. That single negation is the entire adaptation; nothing else in
    this module knows or cares which backend produced the numbers.

    DO NOT NEGATE AGAIN downstream. If you are reading a `scored_pairs.jsonl`
    from a MetricX run, `clean_score = -0.8` means "0.8 MetricX error points",
    and a positive delta still means the corruption was scored worse. Flipping
    the sign a second time turns a working detector into a ~0% detection rate
    that looks like a finding.
    ==========================================================================

    Heavy deps are imported lazily so this module and its tests stay usable
    without the ~4.9GB checkpoint, matching `load_cometkiwi`.

    Input format is taken verbatim from `metricx24/predict.py` (QE branch);
    the two easy-to-get-wrong details live in `metricx_qe_input` and
    `metricx_encode`, which are unit-tested.
    """
    import torch
    import transformers

    from versed_translator.qe.metricx_model import MT5ForRegression

    tokenizer = transformers.AutoTokenizer.from_pretrained(tokenizer_name)
    model = MT5ForRegression.from_pretrained(model_name, torch_dtype="auto")

    dev = torch.device(device) if device else torch.device(
        "cuda" if torch.cuda.is_available() else "cpu"
    )
    model.to(dev)
    model.eval()

    def scorer(sources: list[str], hypotheses: list[str]) -> list[float]:
        if len(sources) != len(hypotheses):
            raise ValueError(
                f"{len(sources)} sources vs {len(hypotheses)} hypotheses"
            )

        out: list[float] = []
        truncated = 0
        # Strictly sequential over the input order — no length-bucketing, no
        # sorting. `score_pairs` indexes scores[2*i]/scores[2*i+1], so any
        # reordering here silently mispairs clean with corrupted.
        for start in range(0, len(sources), batch_size):
            src = sources[start : start + batch_size]
            hyp = hypotheses[start : start + batch_size]

            texts = [metricx_qe_input(s, h) for s, h in zip(src, hyp)]
            batch, n_trunc = metricx_encode(tokenizer, texts, max_input_length)
            truncated += n_trunc
            batch = batch.to(dev)

            with torch.no_grad():
                preds = model(
                    input_ids=batch["input_ids"],
                    attention_mask=batch["attention_mask"],
                ).predictions

            # The negation. See POLARITY WARNING above.
            out.extend(-float(p) for p in preds.detach().float().cpu())

            if progress_every and len(out) % progress_every < batch_size:
                # CPU inference on a 1.2B model takes hours for a full run;
                # without this a detached job is indistinguishable from a hang.
                print(
                    f"[metricx] {len(out)}/{len(sources)} segments",
                    file=sys.stderr,
                    flush=True,
                )

        scorer.truncated += truncated
        scorer.scored += len(sources)
        if truncated:
            print(
                f"[metricx] WARNING: {truncated}/{len(sources)} inputs hit the "
                f"{max_input_length}-token cap. Truncation removes the END of "
                "'source: ... candidate: ...', i.e. the candidate translation "
                "being judged — those scores are unreliable.",
                file=sys.stderr,
                flush=True,
            )
        return out

    # Counters live on the callable so a caller holding only the duck-typed
    # scorer can still report truncation. This matters more than it looks:
    # several injectors LENGTHEN the candidate (duplicate_sentence,
    # hallucinate_prose), so truncation hits the corrupted side harder than the
    # clean side and biases the paired delta toward zero — or negative. A
    # detection rate computed over a heavily truncated batch is not a fact
    # about MetricX, it is a fact about the token cap.
    scorer.truncated = 0
    scorer.scored = 0
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
