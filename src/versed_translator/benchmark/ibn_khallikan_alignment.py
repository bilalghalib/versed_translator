"""Build the Ibn Khallikan/de Slane biography alignment slice.

Corpus-bearing JSONL and the review page are written outside the repository.
The repository receives only hashes, counts, confidence evidence, and a
text-free report.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from versed_translator.benchmark import alignment_review, pd_alignment
from versed_translator.benchmark.sources import ibn_khallikan, llm_adjudicator
from versed_translator.benchmark.sources.schema import length_band, make_pair

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA_DIR = (
    Path.home() / "versed-translator-data" / "benchmark-alignment" / "ibn_khallikan_deslane"
)
DEFAULT_REPO_OUT = REPO_ROOT / "benchmark" / "alignment" / "ibn_khallikan_deslane"
DEFAULT_SEED = 20260814
TARGET_BANDS = ("100-250", "250-600")


def select(
    passages: list[ibn_khallikan.Passage],
    target: int = 40,
    seed: int = DEFAULT_SEED,
) -> list[ibn_khallikan.Passage]:
    eligible = [
        passage
        for passage in passages
        if passage.confidence >= 0.8
        and not passage.flags
        and length_band(passage.arabic_word_count) in TARGET_BANDS
        and (
            not passage.llm_verdict
            or passage.llm_verdict.get("verdict") == "aligned"
        )
    ]
    rng = random.Random(seed)
    chosen: list[ibn_khallikan.Passage] = []
    per_band = max(1, target // len(TARGET_BANDS))
    for band in TARGET_BANDS:
        pool = [p for p in eligible if length_band(p.arabic_word_count) == band]
        rng.shuffle(pool)
        pool.sort(key=lambda p: (-p.confidence, p.entry_index))
        chosen.extend(pool[:per_band])
    return sorted(chosen, key=lambda p: p.entry_index)


def to_record(passage: ibn_khallikan.Passage, metadata) -> dict:
    pair = make_pair(
        source="ibn_khallikan_deslane",
        source_native_id=passage.native_id,
        work_id=ibn_khallikan.WORK_ID,
        author=metadata.author_name,
        genre=metadata.book_subject,
        date_or_century=(
            f"{metadata.author_died} AH" if metadata.author_died else None
        ),
        arabic=passage.arabic,
        reference_english=passage.english,
        translator=ibn_khallikan.TRANSLATOR,
        english_source=ibn_khallikan.ENGLISH_SOURCE,
        rights_status=ibn_khallikan.RIGHTS_STATUS,
        source_split=None,
        notes=None,
    )
    record = dict(pair)
    record.update(
        {
            "id": f"ibn_khallikan_deslane:{passage.native_id}",
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
            "anchors_open": list(passage.anchors_open),
            "anchors_close": [],
            "section_index": passage.entry_index,
            "section_title": "",
            "chapter_label": f"volume {passage.volume}",
            "chapter_title": "",
            "arabic_range": [passage.entry_index, passage.entry_index + 1],
            "english_range": [passage.entry_index, passage.entry_index + 1],
            "headings_stripped": [],
            "flags": list(passage.flags),
            "rights_evidence": ibn_khallikan.RIGHTS_EVIDENCE,
            "llm_verdict": passage.llm_verdict,
            "reference_fidelity": "pending_human_audit",
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
        "section_index": record["section_index"],
        "chapter_label": record["chapter_label"],
        "flags": record["flags"],
        "llm_verdict": verdict.get("verdict"),
        "llm_confidence": verdict.get("confidence"),
        "reference_fidelity": record["reference_fidelity"],
        "rights_status": record["rights_status"],
    }


def build_report(report: ibn_khallikan.ExtractionReport, selected: list[dict]) -> str:
    bands = Counter(record["band"] for record in selected)
    return "\n".join(
        [
            "# PD alignment slice -- Ibn Khallikan / de Slane",
            "",
            "Biography entries matched by bilateral printed headings. Corpus text lives off-repo.",
            "",
            f"- Arabic OpenITI biography entries: {report.arabic_entries}",
            f"- English heading candidates: {report.english_heading_candidates}",
            f"- structurally matched entries: {report.entries_matched}",
            f"- 100--600-word candidates assembled: {len(report.passages)}",
            f"- selected for review: {len(selected)}",
            f"- selected 100--250: {bands.get('100-250', 0)}",
            f"- selected 250--600: {bands.get('250-600', 0)}",
            "",
            "## Evidence and limits",
            "",
            "Each item is a complete Arabic biography and the English text between its matched "
            "romanised heading and the next matched heading. A match must preserve sequence and "
            "at least 75% of the usable name skeleton. Entries are never split internally because "
            "there is no second structural anchor inside a biography.",
            "",
            "Selection excludes entries with abnormal word ratios or Arabic leakage into the "
            "English column. `reference_fidelity` remains `pending_human_audit`; heading evidence "
            "establishes the entry boundary, not whether de Slane abridged material inside it.",
            "",
            "Review page (contains corpus text): "
            "`~/versed-translator-data/benchmark-alignment/ibn_khallikan_deslane/review.html`.",
            "",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arabic", type=Path, required=True)
    parser.add_argument("--english", type=Path, action="append", required=True)
    parser.add_argument("--data-out", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--repo-out", type=Path, default=DEFAULT_REPO_OUT)
    parser.add_argument("--target", type=int, default=40)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--adjudicate", action="store_true")
    parser.add_argument("--model", default=llm_adjudicator.DEFAULT_MODEL)
    args = parser.parse_args(argv)

    data_out = pd_alignment._assert_outside_repo(args.data_out)
    data_out.mkdir(parents=True, exist_ok=True)
    metadata, report = ibn_khallikan.extract(args.arabic, args.english)

    eligible = [p for p in report.passages if p.confidence >= 0.8 and not p.flags]
    cache_path = data_out / "llm_verdicts.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    if args.adjudicate:
        client = None
        for index, passage in enumerate(eligible, start=1):
            key = pd_alignment.sha256_hex(
                f"{args.model}\n{passage.arabic}\n{passage.english}"
            )
            if key in cache:
                verdict = llm_adjudicator.Verdict(**cache[key])
                origin = "cached"
            else:
                client = client or llm_adjudicator._get_client()
                verdict = llm_adjudicator.adjudicate(
                    passage.arabic,
                    passage.english,
                    model=args.model,
                    client=client,
                    context=(
                        "The Arabic is a complete biography from Ibn Khallikan's "
                        "Wafayat al-Ayan. The English is the text under the matched "
                        "romanised heading in de Slane's 1842-1871 translation."
                    ),
                )
                cache[key] = asdict(verdict)
                origin = "fresh"
            passage.llm_verdict = asdict(verdict)
            if verdict.ok:
                passage.confidence = llm_adjudicator.combined_confidence(
                    passage.structural_confidence, verdict
                )
            print(
                f"[{index}/{len(eligible)}] {passage.native_id}: "
                f"{verdict.verdict or verdict.error} ({origin})",
                file=sys.stderr,
            )
        cache_path.write_text(json.dumps(cache, indent=2, ensure_ascii=False))

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
        "work_title": "Ibn Khallikan / de Slane",
        "subtitle": f"{len(selected_records)} selected of {len(all_records)} assembled",
        "work_id": ibn_khallikan.WORK_ID,
        "english_source": ibn_khallikan.ENGLISH_SOURCE,
        "rights": ibn_khallikan.RIGHTS_STATUS,
        "stats": {
            "Arabic entries": report.arabic_entries,
            "headings matched": report.entries_matched,
            "assembled": len(all_records),
            "selected": len(selected_records),
        },
    }
    (data_out / "review.html").write_text(
        alignment_review.render_page(all_records, summary), encoding="utf-8"
    )

    repo_out = args.repo_out.expanduser().resolve()
    repo_out.mkdir(parents=True, exist_ok=True)
    manifest_items = [to_manifest_record(record) for record in selected_records]
    pd_alignment._assert_textfree(manifest_items, "manifest")
    manifest = {
        "slice": "ibn_khallikan_deslane",
        "work_id": ibn_khallikan.WORK_ID,
        "translator": ibn_khallikan.TRANSLATOR,
        "english_source": ibn_khallikan.ENGLISH_SOURCE,
        "rights_status": ibn_khallikan.RIGHTS_STATUS,
        "rights_evidence": ibn_khallikan.RIGHTS_EVIDENCE,
        "genre_openiti_021_booksubj": metadata.book_subject,
        "author_died_ah": metadata.author_died,
        "seed": args.seed,
        "counts": {
            "assembled": len(all_records),
            "selected": len(selected_records),
            "by_band": dict(Counter(r["band"] for r in selected_records)),
        },
        "items": manifest_items,
    }
    (repo_out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (repo_out / "report.md").write_text(
        build_report(report, selected_records), encoding="utf-8"
    )
    print(f"review page -> {data_out / 'review.html'}", file=sys.stderr)
    print(f"manifest + report -> {repo_out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
