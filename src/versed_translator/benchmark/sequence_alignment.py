"""Build LLM-gated sequence slices for Ockley's Hayy or Blunt's odes."""

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
from versed_translator.benchmark.sources import blunt_odes, llm_adjudicator, ockley_hayy
from versed_translator.benchmark.sources.schema import length_band, make_pair

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SEED = 20260814
TARGET_BANDS = ("100-250", "250-600")

WORKS = {
    "ockley_hayy": {
        "module": ockley_hayy,
        "slice": "ockley_hayy",
        "title": "Ibn Tufayl / Simon Ockley",
        "context": (
            "The Arabic is from Ibn Tufayl's Hayy ibn Yaqzan. The English is "
            "Simon Ockley's complete 1708 translation. Boundaries were proposed "
            "from the shared narrative order and must be judged for content."
        ),
    },
    "blunt_odes": {
        "module": blunt_odes,
        "slice": "blunt_odes",
        "title": "The Muallaqat / Blunt's Seven Golden Odes",
        "context": (
            "The Arabic is a consecutive run of original Muallaqat verses, with "
            "al-Zawzani's commentary excluded. The English is the corresponding "
            "run in Blunt's 1903 verse translation."
        ),
    },
}


def _eligible(passage: Any) -> bool:
    return (
        100 <= passage.arabic_word_count <= 600
        and 0.75 <= passage.word_ratio <= 3.2
        and not any(flag != "llm_required" for flag in passage.flags)
    )


def select(passages: list[Any], target: int, seed: int) -> list[Any]:
    pool = [
        passage
        for passage in passages
        if _eligible(passage)
        and passage.llm_verdict
        and passage.llm_verdict.get("verdict") == "aligned"
    ]
    rng = random.Random(seed)
    chosen: list[Any] = []
    per_band = max(1, target // len(TARGET_BANDS))
    for band in TARGET_BANDS:
        band_pool = [p for p in pool if length_band(p.arabic_word_count) == band]
        rng.shuffle(band_pool)
        chosen.extend(band_pool[:per_band])
    return sorted(chosen, key=lambda passage: passage.native_id)


def _record_fields(work: str, passage: Any) -> dict:
    if work == "ockley_hayy":
        return {
            "section_index": passage.section_range[0],
            "section_title": "",
            "chapter_label": (
                f"English sections {passage.section_range[0] + 1}-{passage.section_range[1]}"
            ),
            "chapter_title": "",
            "arabic_range": list(passage.arabic_range),
            "english_range": list(passage.section_range),
        }
    return {
        "section_index": passage.verse_range[0],
        "section_title": "",
        "chapter_label": passage.poem_key,
        "chapter_title": passage.poem_name,
        "arabic_range": list(passage.verse_range),
        "english_range": list(passage.verse_range),
    }


def to_record(work: str, passage: Any, metadata: Any, module: Any) -> dict:
    pair = make_pair(
        source=work,
        source_native_id=passage.native_id,
        work_id=module.WORK_ID,
        author=metadata.author_name,
        genre=metadata.book_subject,
        date_or_century=(
            f"{metadata.author_died} AH" if metadata.author_died else None
        ),
        arabic=passage.arabic,
        reference_english=passage.english,
        translator=module.TRANSLATOR,
        english_source=module.ENGLISH_SOURCE,
        rights_status=module.RIGHTS_STATUS,
        source_split=None,
        notes=None,
    )
    record = dict(pair)
    record.update(
        {
            "id": f"{work}:{passage.native_id}",
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
            "anchors_open": [],
            "anchors_close": [],
            "headings_stripped": [],
            "flags": list(passage.flags),
            "rights_evidence": module.RIGHTS_EVIDENCE,
            "llm_verdict": passage.llm_verdict,
            "reference_fidelity": "pending_human_audit",
            **_record_fields(work, passage),
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
        "section_index": record["section_index"],
        "chapter_label": record["chapter_label"],
        "arabic_range": record["arabic_range"],
        "english_range": record["english_range"],
        "flags": record["flags"],
        "llm_verdict": verdict.get("verdict"),
        "llm_confidence": verdict.get("confidence"),
        "reference_fidelity": record["reference_fidelity"],
        "rights_status": record["rights_status"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", choices=sorted(WORKS), required=True)
    parser.add_argument("--arabic", type=Path, required=True)
    parser.add_argument("--english", type=Path, required=True)
    parser.add_argument("--data-out", type=Path)
    parser.add_argument("--repo-out", type=Path)
    parser.add_argument("--target", type=int, default=30)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--adjudicate", action="store_true")
    parser.add_argument("--model", default=llm_adjudicator.DEFAULT_MODEL)
    args = parser.parse_args(argv)

    config = WORKS[args.work]
    module = config["module"]
    data_out = args.data_out or (
        Path.home() / "versed-translator-data" / "benchmark-alignment" / config["slice"]
    )
    repo_out = args.repo_out or (
        REPO_ROOT / "benchmark" / "alignment" / config["slice"]
    )
    data_out = pd_alignment._assert_outside_repo(data_out)
    data_out.mkdir(parents=True, exist_ok=True)

    metadata, report = module.extract(args.arabic, args.english)
    candidates = [passage for passage in report.passages if _eligible(passage)]
    cache_path = data_out / "llm_verdicts.json"
    cache = (
        json.loads(cache_path.read_text(encoding="utf-8"))
        if cache_path.exists()
        else {}
    )
    if args.adjudicate:
        client = None
        for index, passage in enumerate(candidates, start=1):
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
                    context=config["context"],
                )
                cache[key] = asdict(verdict)
                origin = "fresh"
            passage.llm_verdict = asdict(verdict)
            if verdict.ok:
                passage.confidence = llm_adjudicator.combined_confidence(
                    passage.structural_confidence, verdict
                )
                if verdict.verdict == "aligned":
                    passage.flags = [
                        flag for flag in passage.flags if flag != "llm_required"
                    ]
            print(
                f"[{index}/{len(candidates)}] {passage.native_id}: "
                f"{verdict.verdict or verdict.error} ({origin})",
                file=sys.stderr,
            )
        cache_path.write_text(
            json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    selected = select(report.passages, target=args.target, seed=args.seed)
    selected_ids = {passage.native_id for passage in selected}
    all_records = [
        to_record(args.work, passage, metadata, module) for passage in report.passages
    ]
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
        "work_title": config["title"],
        "subtitle": f"{len(selected_records)} selected of {len(all_records)} proposals",
        "work_id": module.WORK_ID,
        "english_source": module.ENGLISH_SOURCE,
        "rights": module.RIGHTS_STATUS,
        "stats": {
            "proposed": len(all_records),
            "adjudicated": sum(bool(r.get("llm_verdict")) for r in all_records),
            "selected": len(selected_records),
        },
    }
    (data_out / "review.html").write_text(
        alignment_review.render_page(all_records, summary), encoding="utf-8"
    )

    repo_out = repo_out.expanduser().resolve()
    repo_out.mkdir(parents=True, exist_ok=True)
    items = [to_manifest_record(record) for record in selected_records]
    pd_alignment._assert_textfree(items, "manifest")
    manifest = {
        "slice": config["slice"],
        "work_id": module.WORK_ID,
        "translator": module.TRANSLATOR,
        "english_source": module.ENGLISH_SOURCE,
        "rights_status": module.RIGHTS_STATUS,
        "rights_evidence": module.RIGHTS_EVIDENCE,
        "genre_openiti_021_booksubj": metadata.book_subject,
        "author_died_ah": metadata.author_died,
        "seed": args.seed,
        "counts": {
            "proposed": len(all_records),
            "eligible_for_adjudication": len(candidates),
            "selected": len(selected_records),
            "by_band": dict(Counter(r["band"] for r in selected_records)),
        },
        "items": items,
    }
    (repo_out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    report_lines = [
        f"# PD alignment slice -- {config['title']}",
        "",
        f"- proposals: {len(all_records)}",
        f"- eligible for content adjudication: {len(candidates)}",
        f"- selected after aligned verdict: {len(selected_records)}",
        f"- selected 100--250: {manifest['counts']['by_band'].get('100-250', 0)}",
        f"- selected 250--600: {manifest['counts']['by_band'].get('250-600', 0)}",
        "",
        "## Evidence and limits",
        "",
        (
            "The sequence/length partition is a proposal, not a structural anchor. Every selected "
            "item has an explicit `aligned` content verdict, and all remain pending human review. "
            "No model is allowed to propose or rewrite a boundary."
        ),
        "",
        f"Review page: `~/versed-translator-data/benchmark-alignment/{config['slice']}/review.html`.",
        "",
    ]
    (repo_out / "report.md").write_text("\n".join(report_lines), encoding="utf-8")
    print(f"review page -> {data_out / 'review.html'}", file=sys.stderr)
    print(f"manifest + report -> {repo_out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
