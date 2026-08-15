"""Build the Miskawayh / Margoliouth year-anchored alignment slice.

`sources/miskawayh.py:extract()` proposes passages inside hijri-year blocks.
Those proposals are not passages: within-year cuts can lag a page, so every
item is adjudicated for content before it can be selected. This module is
the extract → adjudicate → select → write CLI.

Corpus-bearing JSONL and both review pages are written outside the
repository. The repository receives only hashes, counts, confidence
evidence, and a text-free report.

Run:

    uv run python -m versed_translator.benchmark.miskawayh_alignment \\
        --arabic  ~/versed-translator-data/openiti/0421Miskawayh.Tajarib.txt \\
        --english ~/versed-translator-data/pd-english/eclipse_04ameduoft_djvu.txt \\
        --english ~/versed-translator-data/pd-english/eclipse_05ameduoft_djvu.txt \\
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
from versed_translator.benchmark.sources import llm_adjudicator, miskawayh
from versed_translator.benchmark.sources.schema import length_band, make_pair

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA_DIR = (
    Path.home() / "versed-translator-data" / "benchmark-alignment" / "miskawayh_eclipse"
)
DEFAULT_REPO_OUT = REPO_ROOT / "benchmark" / "alignment" / "miskawayh_eclipse"
DEFAULT_SEED = 20260815
DEFAULT_TARGET = 40
TARGET_BANDS = ("100-250", "250-600")
SELECT_MIN_CONFIDENCE = 0.6
# Word-ratio window around Miskawayh's measured work-level ~1.68. Wider than
# the year-drop tolerance: a passage can be a bit short/long without meaning
# a year heading was missed.
RATIO_MIN = 0.75
RATIO_MAX = 3.2
# Hard flags disqualify; `llm_required` is the standing gate, not a defect.
HARD_FLAGS = ("page_markers_nonmonotone",)
ADJUDICATE_CONTEXT = (
    "The Arabic is from Miskawayh's Tajarib al-Umam. The English is "
    "Margoliouth and Amedroz's 1921 Eclipse of the 'Abbasid Caliphate. "
    "Year headings independently anchor both sides, but cuts inside a year "
    "are proposals: the English running head can lag by a page, so a "
    "passage may start or end a paragraph early or late."
)


def _hard_flagged(passage: miskawayh.Passage) -> bool:
    return any(flag.startswith(HARD_FLAGS) for flag in passage.flags)


def eligible_for_adjudication(passage: miskawayh.Passage) -> bool:
    """Band, ratio, and text-defect filter. A proposal is not a passage."""
    return (
        length_band(passage.arabic_word_count) in TARGET_BANDS
        and RATIO_MIN <= passage.word_ratio <= RATIO_MAX
        and not _hard_flagged(passage)
    )


def adjudication_pool(
    passages: list[miskawayh.Passage],
    limit: int | None,
    seed: int,
) -> list[miskawayh.Passage]:
    """Year-spread, band-balanced pool so a cap does not drain early years.

    Adjudicating all ~500 proposals would spend API budget on a history
    source that is already over the freeze-bar 40% genre cap. A 3x-target
    pool is enough to fill a 40-item slice after the expected 25-40% yield.
    """
    candidates = [p for p in passages if eligible_for_adjudication(p)]
    if limit is None or limit >= len(candidates):
        return candidates
    rng = random.Random(seed)
    by_year: dict[int, list[miskawayh.Passage]] = {}
    for passage in candidates:
        by_year.setdefault(passage.ah_year, []).append(passage)
    for items in by_year.values():
        rng.shuffle(items)
        items.sort(key=lambda p: -p.structural_confidence)
    order = sorted(by_year)
    rng.shuffle(order)
    taken: list[miskawayh.Passage] = []
    cursor = 0
    while len(taken) < limit and any(by_year[year] for year in order):
        year = order[cursor % len(order)]
        if by_year[year]:
            taken.append(by_year[year].pop(0))
        cursor += 1
    return taken


def select(
    passages: list[miskawayh.Passage],
    target: int = DEFAULT_TARGET,
    seed: int = DEFAULT_SEED,
    min_confidence: float = SELECT_MIN_CONFIDENCE,
) -> list[miskawayh.Passage]:
    """Band-balanced, year-spread subset of aligned, adjudicated passages."""
    eligible = [
        passage
        for passage in passages
        if passage.confidence >= min_confidence
        and not _hard_flagged(passage)
        and length_band(passage.arabic_word_count) in TARGET_BANDS
        and passage.llm_verdict
        and passage.llm_verdict.get("verdict") == "aligned"
    ]
    rng = random.Random(seed)
    per_band = max(1, target // len(TARGET_BANDS))
    chosen: list[miskawayh.Passage] = []
    for band in TARGET_BANDS:
        pool = [p for p in eligible if length_band(p.arabic_word_count) == band]
        by_year: dict[int, list[miskawayh.Passage]] = {}
        for passage in pool:
            by_year.setdefault(passage.ah_year, []).append(passage)
        for items in by_year.values():
            rng.shuffle(items)
            items.sort(key=lambda p: -p.confidence)
        order = sorted(by_year)
        rng.shuffle(order)
        taken: list[miskawayh.Passage] = []
        cursor = 0
        while len(taken) < per_band and any(by_year[year] for year in order):
            year = order[cursor % len(order)]
            if by_year[year]:
                taken.append(by_year[year].pop(0))
            cursor += 1
        chosen.extend(taken)
    return sorted(chosen, key=lambda p: (p.ah_year, p.arabic_range[0]))


def to_record(passage: miskawayh.Passage, metadata: Any) -> dict:
    pair = make_pair(
        source="miskawayh_eclipse",
        source_native_id=passage.native_id,
        work_id=miskawayh.WORK_ID,
        author=metadata.author_name,
        genre=metadata.book_subject,
        date_or_century=(
            f"{metadata.author_died} AH" if metadata.author_died else None
        ),
        arabic=passage.arabic,
        reference_english=passage.english,
        translator=miskawayh.TRANSLATOR,
        english_source=miskawayh.ENGLISH_SOURCE,
        rights_status=miskawayh.RIGHTS_STATUS,
        source_split=None,
        notes=None,
    )
    record = dict(pair)
    record.update(
        {
            "id": f"miskawayh_eclipse:{passage.native_id}",
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
            "anchors_open": [f"AH {passage.ah_year}"],
            "anchors_close": [f"AH {passage.ah_year}"],
            "section_index": passage.ah_year,
            "section_title": "",
            "chapter_label": f"AH {passage.ah_year}",
            "chapter_title": "",
            "arabic_range": list(passage.arabic_range),
            "english_range": list(passage.english_range),
            "headings_stripped": [],
            "flags": list(passage.flags),
            "rights_evidence": miskawayh.RIGHTS_EVIDENCE,
            "llm_verdict": passage.llm_verdict,
            "reference_fidelity": "pending_human_audit",
            "ah_year": passage.ah_year,
            "year_complete": passage.year_complete,
            "arabic_pages": list(passage.arabic_pages),
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
        "ah_year": record["ah_year"],
        "year_complete": record["year_complete"],
        "n_arabic_pages": len(record.get("arabic_pages") or []),
    }


def build_report(
    report: miskawayh.ExtractionReport,
    selected: list[dict],
    all_records: list[dict],
    seed: int,
) -> str:
    bands = Counter(record["band"] for record in selected)
    methods = Counter(record["method"] for record in selected)
    return "\n".join(
        [
            "# PD alignment slice -- Miskawayh / Margoliouth & Amedroz",
            "",
            (
                "Year-anchored proposals from *Tajarib al-Umam* against *The Eclipse "
                "of the 'Abbasid Caliphate* (1921). Corpus text lives off-repo."
            ),
            "",
            f"- Arabic: OpenITI `{miskawayh.WORK_ID}`",
            f"- English: {miskawayh.ENGLISH_SOURCE}",
            f"- Rights: `{miskawayh.RIGHTS_STATUS}` -- {miskawayh.RIGHTS_EVIDENCE}",
            f"- Selection seed: `{seed}`",
            "",
            "## Pipeline yield",
            "",
            "| stage | count |",
            "|---|---|",
            f"| Arabic hijri years parsed | {report.arabic_years} |",
            f"| English hijri years parsed | {report.english_years} |",
            f"| shared year-blocks | {report.shared_years} |",
            f"| years used | {len(report.used_years)} |",
            f"| years rejected | {len(report.rejected_years)} |",
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
                "The hijri year is a real bilateral anchor (Arabic year "
                "headings; English `A.H. NNN` running heads). Cuts *inside* a "
                "year are name-refined proportional proposals, not structural "
                "brackets. Every selected item has an explicit `aligned` content "
                "verdict; `reference_fidelity` remains `pending_human_audit`."
            ),
            "",
            (
                "A missed year heading on either side is dropped via word-ratio "
                "tolerance, not quietly merged. The English running head can lag "
                "a page, so within-year offset is expected; that is why "
                "adjudication is mandatory and why a proposal is not a passage."
            ),
            "",
            (
                "Review pages (corpus text, off-repo): "
                "`~/versed-translator-data/benchmark-alignment/miskawayh_eclipse/"
                "review.html` (triage, worst first) and `review_shipping.html` "
                f"(selected only, best first). {len(all_records)} proposals "
                f"rendered; {len(selected)} selected."
            ),
            "",
            f"Rejected years: {len(report.rejected_years)} of {report.shared_years}.",
            "",
        ]
    )


def _apply_verdict(
    passage: miskawayh.Passage, verdict: llm_adjudicator.Verdict
) -> None:
    passage.llm_verdict = asdict(verdict)
    if not verdict.ok:
        return
    passage.confidence = llm_adjudicator.combined_confidence(
        passage.structural_confidence, verdict
    )
    passage.method = "llm_proposed"
    if verdict.verdict == "aligned":
        passage.flags = [flag for flag in passage.flags if flag != "llm_required"]


def _passage_key(passage: miskawayh.Passage, model: str) -> str:
    return pd_alignment.sha256_hex(f"{model}\n{passage.arabic}\n{passage.english}")


def apply_cached_verdicts(
    passages: list[miskawayh.Passage],
    cache: dict[str, dict],
    model: str,
) -> int:
    """Replay paid-for judgements onto this extract. Returns how many hit."""
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
    parser.add_argument("--english", type=Path, action="append", required=True)
    parser.add_argument("--data-out", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--repo-out", type=Path, default=DEFAULT_REPO_OUT)
    parser.add_argument("--target", type=int, default=DEFAULT_TARGET)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--adjudicate",
        action="store_true",
        help="ask Claude to judge proposals (nothing is called without this flag)",
    )
    parser.add_argument(
        "--adjudicate-limit",
        type=int,
        default=None,
        help=(
            "cap how many eligible proposals are sent to the adjudicator, "
            "year-spread. Default: all eligible. 120 is enough for a 40-item "
            "target at the expected 25-40% yield."
        ),
    )
    parser.add_argument("--model", default=llm_adjudicator.DEFAULT_MODEL)
    args = parser.parse_args(argv)

    data_out = pd_alignment._assert_outside_repo(args.data_out)
    data_out.mkdir(parents=True, exist_ok=True)

    metadata, report = miskawayh.extract(args.arabic, args.english)
    print(
        f"parsed: {report.arabic_years} Arabic years, "
        f"{report.english_years} English years -> "
        f"{report.shared_years} shared, {len(report.used_years)} used, "
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
        "work_title": "Miskawayh, Tajarib al-Umam / Margoliouth & Amedroz",
        "subtitle": (
            f"{len(selected_records)} selected of {len(all_records)} proposals "
            f"· genre {metadata.book_subject} · author d. {metadata.author_died} AH"
        ),
        "work_id": miskawayh.WORK_ID,
        "english_source": miskawayh.ENGLISH_SOURCE,
        "rights": miskawayh.RIGHTS_STATUS,
        "stats": {
            "proposed": len(all_records),
            "years used": len(report.used_years),
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
        "slice": "miskawayh_eclipse",
        "work_id": miskawayh.WORK_ID,
        "translator": miskawayh.TRANSLATOR,
        "english_source": miskawayh.ENGLISH_SOURCE,
        "rights_status": miskawayh.RIGHTS_STATUS,
        "rights_evidence": miskawayh.RIGHTS_EVIDENCE,
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
