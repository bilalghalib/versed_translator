"""Build the Hariri / Chenery–Steingass maqama-anchored alignment slice.

`sources/hariri.py:extract()` pairs the fifty maqamat by sequence, then
proposes interior cuts. Those cuts are not passages: a maqama has no second
structural bracket inside it, so every item is adjudicated for content
before it can be selected.

Run:

    uv run python -m versed_translator.benchmark.hariri_alignment \\
        --arabic  ~/versed-translator-data/openiti/0516IbnCaliHariri.Maqamat.txt \\
        --english ~/versed-translator-data/pd-english/The_Assembly_of_Al_Hariri_All_50_djvu.txt \\
        --adjudicate
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

from versed_translator.benchmark import alignment_review, pd_alignment
from versed_translator.benchmark.sources import hariri, llm_adjudicator
from versed_translator.benchmark.sources.schema import length_band, make_pair

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA_DIR = (
    Path.home() / "versed-translator-data" / "benchmark-alignment" / "hariri_assemblies"
)
DEFAULT_REPO_OUT = REPO_ROOT / "benchmark" / "alignment" / "hariri_assemblies"
DEFAULT_SEED = 20260815
DEFAULT_TARGET = 40
TARGET_BANDS = ("100-250", "250-600")
SELECT_MIN_CONFIDENCE = 0.6
RATIO_MIN = 0.75
RATIO_MAX = 3.2
ADJUDICATE_CONTEXT = (
    "The Arabic is from al-Hariri's Maqamat. The English is Chenery (1867) "
    "and Steingass (1898), The Assemblies of Al Hariri. Each maqama is a "
    "real bilateral unit, but cuts inside a maqama are proposals: the "
    "English running head can leak, and rhymed-prose verse insertions may "
    "sit a paragraph early or late. Judge whether this English span "
    "translates this Arabic span."
)


def eligible_for_adjudication(passage: hariri.Passage) -> bool:
    return (
        length_band(passage.arabic_word_count) in TARGET_BANDS
        and RATIO_MIN <= passage.word_ratio <= RATIO_MAX
    )


def adjudication_pool(
    passages: list[hariri.Passage],
    limit: int | None,
    seed: int,
) -> list[hariri.Passage]:
    candidates = [p for p in passages if eligible_for_adjudication(p)]
    if limit is None or limit >= len(candidates):
        return candidates
    rng = random.Random(seed)
    by_maqama: dict[int, list[hariri.Passage]] = {}
    for passage in candidates:
        by_maqama.setdefault(passage.maqama_number, []).append(passage)
    for items in by_maqama.values():
        rng.shuffle(items)
        items.sort(key=lambda p: -p.structural_confidence)
    order = sorted(by_maqama)
    rng.shuffle(order)
    taken: list[hariri.Passage] = []
    cursor = 0
    while len(taken) < limit and any(by_maqama[n] for n in order):
        number = order[cursor % len(order)]
        if by_maqama[number]:
            taken.append(by_maqama[number].pop(0))
        cursor += 1
    return taken


def select(
    passages: list[hariri.Passage],
    target: int = DEFAULT_TARGET,
    seed: int = DEFAULT_SEED,
    min_confidence: float = SELECT_MIN_CONFIDENCE,
) -> list[hariri.Passage]:
    eligible = [
        passage
        for passage in passages
        if passage.confidence >= min_confidence
        and length_band(passage.arabic_word_count) in TARGET_BANDS
        and passage.llm_verdict
        and passage.llm_verdict.get("verdict") == "aligned"
    ]
    rng = random.Random(seed)
    per_band = max(1, target // len(TARGET_BANDS))
    chosen: list[hariri.Passage] = []
    for band in TARGET_BANDS:
        pool = [p for p in eligible if length_band(p.arabic_word_count) == band]
        by_maqama: dict[int, list[hariri.Passage]] = {}
        for passage in pool:
            by_maqama.setdefault(passage.maqama_number, []).append(passage)
        for items in by_maqama.values():
            rng.shuffle(items)
            items.sort(key=lambda p: -p.confidence)
        order = sorted(by_maqama)
        rng.shuffle(order)
        taken: list[hariri.Passage] = []
        cursor = 0
        while len(taken) < per_band and any(by_maqama[n] for n in order):
            number = order[cursor % len(order)]
            if by_maqama[number]:
                taken.append(by_maqama[number].pop(0))
            cursor += 1
        chosen.extend(taken)
    return sorted(chosen, key=lambda p: (p.maqama_number, p.arabic_range[0]))


def to_record(passage: hariri.Passage, metadata: Any) -> dict:
    pair = make_pair(
        source="hariri_assemblies",
        source_native_id=passage.native_id,
        work_id=hariri.WORK_ID,
        author=metadata.author_name,
        genre=metadata.book_subject,
        date_or_century=(
            f"{metadata.author_died} AH" if metadata.author_died else None
        ),
        arabic=passage.arabic,
        reference_english=passage.english,
        translator=hariri.TRANSLATOR,
        english_source=hariri.ENGLISH_SOURCE,
        rights_status=hariri.RIGHTS_STATUS,
        source_split=None,
        notes=None,
    )
    record = dict(pair)
    record.update(
        {
            "id": f"hariri_assemblies:{passage.native_id}",
            "english": passage.english,
            "sha256_arabic": pd_alignment.sha256_hex(passage.arabic),
            "sha256_english": pd_alignment.sha256_hex(passage.english),
            "band": length_band(passage.arabic_word_count),
            "arabic_word_count": passage.arabic_word_count,
            "english_word_count": passage.english_word_count,
            "word_ratio": round(passage.word_ratio, 3),
            "method": passage.method,
            "confidence": passage.confidence,
            "structural_confidence": passage.structural_confidence,
            "anchors_open": [f"maqama {passage.maqama_number}"],
            "anchors_close": [f"maqama {passage.maqama_number}"],
            "section_index": passage.maqama_number,
            "section_title": "",
            "chapter_label": f"maqama {passage.maqama_number}",
            "chapter_title": "",
            "arabic_range": list(passage.arabic_range),
            "english_range": list(passage.english_range),
            "headings_stripped": [],
            "flags": list(passage.flags),
            "rights_evidence": hariri.RIGHTS_EVIDENCE,
            "llm_verdict": passage.llm_verdict,
            "reference_fidelity": "pending_human_audit",
            "maqama_number": passage.maqama_number,
            "maqama_complete": passage.maqama_complete,
        }
    )
    return record


def to_manifest_record(record: dict) -> dict:
    verdict = record.get("llm_verdict") or {}
    return {
        "id": record["id"],
        "source": record["source"],
        "source_native_id": record["source_native_id"],
        "work_id": record["work_id"],
        "date_or_century": record["date_or_century"],
        "sha256_arabic": record["sha256_arabic"],
        "sha256_english": record["sha256_english"],
        "band": record["band"],
        "arabic_word_count": record["arabic_word_count"],
        "english_word_count": record["english_word_count"],
        "word_ratio": record["word_ratio"],
        "method": record["method"],
        "confidence": record["confidence"],
        "structural_confidence": record["structural_confidence"],
        "n_anchor_names_open": len(record["anchors_open"]),
        "n_anchor_names_close": len(record["anchors_close"]),
        "section_index": record["section_index"],
        "chapter_label": record["chapter_label"],
        "arabic_range": record["arabic_range"],
        "english_range": record["english_range"],
        "flags": record["flags"],
        "llm_verdict": verdict.get("verdict"),
        "llm_confidence": verdict.get("confidence"),
        "reference_fidelity": record["reference_fidelity"],
        "rights_status": record["rights_status"],
        "maqama_number": record["maqama_number"],
        "maqama_complete": record["maqama_complete"],
    }


def build_report(
    report: hariri.ExtractionReport,
    selected: list[dict],
    all_records: list[dict],
    seed: int,
) -> str:
    bands = Counter(record["band"] for record in selected)
    methods = Counter(record["method"] for record in selected)
    return "\n".join(
        [
            "# PD alignment slice -- al-Hariri / Chenery and Steingass",
            "",
            (
                "Maqama-anchored proposals from the *Maqamat* against *The "
                "Assemblies of Al Hariri* (1867/1898). Corpus text lives off-repo."
            ),
            "",
            f"- Arabic: OpenITI `{hariri.WORK_ID}`",
            f"- English: {hariri.ENGLISH_SOURCE}",
            f"- Rights: `{hariri.RIGHTS_STATUS}` -- {hariri.RIGHTS_EVIDENCE}",
            f"- Selection seed: `{seed}`",
            "",
            "## Pipeline yield",
            "",
            "| stage | count |",
            "|---|---|",
            f"| Arabic maqamat parsed | {report.arabic_maqamat} |",
            f"| English assemblies parsed | {report.english_maqamat} |",
            f"| paired by sequence | {report.paired} |",
            f"| maqamat used | {len(report.used)} |",
            f"| maqamat rejected | {len(report.rejected)} |",
            f"| proposals assembled | {len(all_records)} |",
            f"| selected after aligned verdict | {len(selected)} |",
            "",
            "## Selected passages",
            "",
            "| band | count |",
            "|---|---|",
            *[f"| {band} | {bands.get(band, 0)} |" for band in TARGET_BANDS],
            "",
            "| method | count |",
            "|---|---|",
            *[f"| {method} | {count} |" for method, count in sorted(methods.items())],
            "",
            "## Evidence and limits",
            "",
            (
                "The maqama is a real bilateral anchor (Arabic maqama headings; "
                "English THE NTH ASSEMBLY headings). Printed Arabic numerals in "
                "this witness are dirty, so pairing is by document order, not "
                "by those labels. Cuts *inside* a maqama are name-refined "
                "proportional proposals. Every selected item has an explicit "
                "`aligned` content verdict; `reference_fidelity` remains "
                "`pending_human_audit`."
            ),
            "",
            (
                "Review pages (corpus text, off-repo): "
                "`~/versed-translator-data/benchmark-alignment/hariri_assemblies/"
                "review.html` (triage, worst first) and `review_shipping.html` "
                f"(selected only, best first). {len(all_records)} proposals "
                f"rendered; {len(selected)} selected."
            ),
            "",
            f"Rejected maqamat: {len(report.rejected)} of {report.paired}.",
            "",
        ]
    )


def _apply_verdict(passage: hariri.Passage, verdict: llm_adjudicator.Verdict) -> None:
    passage.llm_verdict = asdict(verdict)
    if not verdict.ok:
        return
    passage.confidence = llm_adjudicator.combined_confidence(
        passage.structural_confidence, verdict
    )
    passage.method = "llm_proposed"
    if verdict.verdict == "aligned":
        passage.flags = [flag for flag in passage.flags if flag != "llm_required"]


def _passage_key(passage: hariri.Passage, model: str) -> str:
    return pd_alignment.sha256_hex(f"{model}\n{passage.arabic}\n{passage.english}")


def apply_cached_verdicts(
    passages: list[hariri.Passage],
    cache: dict[str, dict],
    model: str,
) -> int:
    applied = 0
    for passage in passages:
        payload = cache.get(_passage_key(passage, model))
        if payload is None:
            continue
        _apply_verdict(passage, llm_adjudicator.Verdict(**payload))
        applied += 1
    return applied


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arabic", type=Path, required=True)
    parser.add_argument("--english", type=Path, required=True)
    parser.add_argument("--data-out", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--repo-out", type=Path, default=DEFAULT_REPO_OUT)
    parser.add_argument("--target", type=int, default=DEFAULT_TARGET)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--adjudicate", action="store_true")
    parser.add_argument("--adjudicate-limit", type=int, default=None)
    parser.add_argument("--model", default=llm_adjudicator.DEFAULT_MODEL)
    args = parser.parse_args(argv)

    data_out = pd_alignment._assert_outside_repo(args.data_out)
    data_out.mkdir(parents=True, exist_ok=True)

    metadata, report = hariri.extract(args.arabic, args.english)
    print(
        f"parsed: {report.arabic_maqamat} Arabic maqamat, "
        f"{report.english_maqamat} English assemblies -> "
        f"{report.paired} paired, {len(report.used)} used, "
        f"{len(report.passages)} proposals",
        file=sys.stderr,
    )

    cache_path = data_out / "llm_verdicts.json"
    cache = (
        json.loads(cache_path.read_text(encoding="utf-8"))
        if cache_path.exists()
        else {}
    )
    cached_hits = apply_cached_verdicts(report.passages, cache, args.model)
    uncached = [
        passage
        for passage in report.passages
        if passage.llm_verdict is None and eligible_for_adjudication(passage)
    ]
    pending = adjudication_pool(uncached, args.adjudicate_limit, args.seed)
    if args.adjudicate:
        print(
            f"adjudicating {len(pending)} uncached of "
            f"{sum(1 for p in report.passages if eligible_for_adjudication(p))} "
            f"eligible ({cached_hits} replayed from cache) with {args.model}...",
            file=sys.stderr,
        )
        client = None
        for index, passage in enumerate(pending, 1):
            key = _passage_key(passage, args.model)
            client = client or llm_adjudicator._get_client()
            verdict = llm_adjudicator.adjudicate(
                passage.arabic,
                passage.english,
                model=args.model,
                client=client,
                context=ADJUDICATE_CONTEXT,
            )
            cache[key] = asdict(verdict)
            cache_path.write_text(
                json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            _apply_verdict(passage, verdict)
            print(
                f"  [{index}/{len(pending)}] {passage.native_id}: "
                f"{verdict.verdict or verdict.error} (fresh)",
                file=sys.stderr,
            )
    elif cached_hits:
        print(f"replayed {cached_hits} cached verdicts", file=sys.stderr)

    selected = select(report.passages, target=args.target, seed=args.seed)
    selected_ids = {passage.native_id for passage in selected}
    all_records = [to_record(passage, metadata) for passage in report.passages]
    for record in all_records:
        record["selected"] = record["source_native_id"] in selected_ids
    selected_records = [record for record in all_records if record["selected"]]

    for name, records in (
        ("passages.jsonl", selected_records),
        ("passages_all.jsonl", all_records),
    ):
        with (data_out / name).open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    summary = {
        "work_title": "al-Hariri, Maqamat / Chenery and Steingass",
        "subtitle": (
            f"{len(selected_records)} selected of {len(all_records)} proposals "
            f"· genre {metadata.book_subject} · author d. {metadata.author_died} AH"
        ),
        "work_id": hariri.WORK_ID,
        "english_source": hariri.ENGLISH_SOURCE,
        "rights": hariri.RIGHTS_STATUS,
        "stats": {
            "proposed": len(all_records),
            "maqamat used": len(report.used),
            "adjudicated": sum(bool(r.get("llm_verdict")) for r in all_records),
            "selected": len(selected_records),
        },
    }
    (data_out / "review.html").write_text(
        alignment_review.render_page(all_records, summary), encoding="utf-8"
    )
    (data_out / "review_shipping.html").write_text(
        alignment_review.render_shipping_page(selected_records, summary),
        encoding="utf-8",
    )

    repo_out = args.repo_out.expanduser().resolve()
    repo_out.mkdir(parents=True, exist_ok=True)
    items = [to_manifest_record(record) for record in selected_records]
    pd_alignment._assert_textfree(items, "manifest")
    manifest = {
        "slice": "hariri_assemblies",
        "work_id": hariri.WORK_ID,
        "translator": hariri.TRANSLATOR,
        "english_source": hariri.ENGLISH_SOURCE,
        "rights_status": hariri.RIGHTS_STATUS,
        "rights_evidence": hariri.RIGHTS_EVIDENCE,
        "genre_openiti_021_booksubj": metadata.book_subject,
        "author_died_ah": metadata.author_died,
        "seed": args.seed,
        "counts": {
            "proposed": len(all_records),
            "eligible_for_adjudication": sum(
                1 for p in report.passages if eligible_for_adjudication(p)
            ),
            "selected": len(selected_records),
            "by_band": dict(Counter(r["band"] for r in selected_records)),
            "by_method": dict(Counter(r["method"] for r in selected_records)),
        },
        "items": items,
    }
    (repo_out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (repo_out / "report.md").write_text(
        build_report(report, selected_records, all_records, args.seed),
        encoding="utf-8",
    )
    print(f"passages (with text) -> {data_out / 'passages.jsonl'}", file=sys.stderr)
    print(f"all passages         -> {data_out / 'passages_all.jsonl'}", file=sys.stderr)
    print(f"review (triage)      -> {data_out / 'review.html'}", file=sys.stderr)
    print(
        f"review (shipping)    -> {data_out / 'review_shipping.html'}", file=sys.stderr
    )
    print(f"manifest + report    -> {repo_out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
