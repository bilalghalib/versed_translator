"""Build the Ibn Rushd / Jamil-ur-Rehman treatise-anchored alignment slice.

`sources/ibn_rushd.py:extract()` pairs Fasl al-Maqal and the Damima by
treatise identity, then proposes interior cuts. Kashf is present only on
the English side and is left unpaired. Those cuts are not passages: a
treatise has no second structural bracket inside it, so every item is
adjudicated for content before it can be selected.

Run:

    uv run python -m versed_translator.benchmark.ibn_rushd_alignment \\
        --arabic  ~/versed-translator-data/openiti/0595IbnRushdHafid.FaslMaqal.txt \\
        --english ~/versed-translator-data/pd-english/pg65708_philosophy_theology_averroes.txt \\
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
from versed_translator.benchmark.sources import ibn_rushd, llm_adjudicator
from versed_translator.benchmark.sources.schema import length_band, make_pair

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA_DIR = (
    Path.home() / "versed-translator-data" / "benchmark-alignment" / "ibn_rushd_rehman"
)
DEFAULT_REPO_OUT = REPO_ROOT / "benchmark" / "alignment" / "ibn_rushd_rehman"
DEFAULT_SEED = 20260815
DEFAULT_TARGET = 40
DEFAULT_ADJUDICATE_LIMIT = 80
TARGET_BANDS = ("100-250", "250-600")
SELECT_MIN_CONFIDENCE = 0.6
RATIO_MIN = 0.75
RATIO_MAX = 3.2
ADJUDICATE_CONTEXT = (
    "The Arabic is from Ibn Rushd's Fasl al-Maqal and its Damima (appendix). "
    "The English is Mohammad Jamil-ur-Rehman's 1921 Philosophy and Theology "
    "of Averroes (Gutenberg 65708). Each treatise is a real bilateral unit, "
    "but cuts inside a treatise are proposals: the English book also contains "
    "Kashf, which this Arabic witness does not, and footnote markers may "
    "remain. Judge whether this English span translates this Arabic span."
)


def eligible_for_adjudication(passage: ibn_rushd.Passage) -> bool:
    return (
        length_band(passage.arabic_word_count) in TARGET_BANDS
        and RATIO_MIN <= passage.word_ratio <= RATIO_MAX
    )


def adjudication_pool(
    passages: list[ibn_rushd.Passage],
    limit: int | None,
    seed: int,
) -> list[ibn_rushd.Passage]:
    candidates = [p for p in passages if eligible_for_adjudication(p)]
    if limit is None or limit >= len(candidates):
        return candidates
    rng = random.Random(seed)
    by_treatise: dict[str, list[ibn_rushd.Passage]] = {}
    for passage in candidates:
        by_treatise.setdefault(passage.treatise_id, []).append(passage)
    for items in by_treatise.values():
        rng.shuffle(items)
        items.sort(key=lambda p: -p.structural_confidence)
    order = sorted(by_treatise)
    rng.shuffle(order)
    taken: list[ibn_rushd.Passage] = []
    cursor = 0
    while len(taken) < limit and any(by_treatise[n] for n in order):
        key = order[cursor % len(order)]
        if by_treatise[key]:
            taken.append(by_treatise[key].pop(0))
        cursor += 1
    return taken


def select(
    passages: list[ibn_rushd.Passage],
    target: int = DEFAULT_TARGET,
    seed: int = DEFAULT_SEED,
    min_confidence: float = SELECT_MIN_CONFIDENCE,
) -> list[ibn_rushd.Passage]:
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
    chosen: list[ibn_rushd.Passage] = []
    for band in TARGET_BANDS:
        pool = [p for p in eligible if length_band(p.arabic_word_count) == band]
        by_treatise: dict[str, list[ibn_rushd.Passage]] = {}
        for passage in pool:
            by_treatise.setdefault(passage.treatise_id, []).append(passage)
        for items in by_treatise.values():
            rng.shuffle(items)
            items.sort(key=lambda p: -p.confidence)
        order = sorted(by_treatise)
        rng.shuffle(order)
        taken: list[ibn_rushd.Passage] = []
        cursor = 0
        while len(taken) < per_band and any(by_treatise[n] for n in order):
            key = order[cursor % len(order)]
            if by_treatise[key]:
                taken.append(by_treatise[key].pop(0))
            cursor += 1
        chosen.extend(taken)
    return sorted(chosen, key=lambda p: (p.treatise_id, p.arabic_range[0]))


def to_record(passage: ibn_rushd.Passage, metadata: Any) -> dict:
    pair = make_pair(
        source="ibn_rushd_rehman",
        source_native_id=passage.native_id,
        work_id=ibn_rushd.WORK_ID,
        author=metadata.author_name,
        genre=metadata.book_subject,
        date_or_century=(
            f"{metadata.author_died} AH" if metadata.author_died else None
        ),
        arabic=passage.arabic,
        reference_english=passage.english,
        translator=ibn_rushd.TRANSLATOR,
        english_source=ibn_rushd.ENGLISH_SOURCE,
        rights_status=ibn_rushd.RIGHTS_STATUS,
        source_split=None,
        notes=None,
    )
    record = dict(pair)
    record.update(
        {
            "id": f"ibn_rushd_rehman:{passage.native_id}",
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
            "anchors_open": [f"treatise {passage.treatise_id}"],
            "anchors_close": [f"treatise {passage.treatise_id}"],
            "section_index": {"fasl": 1, "damima": 2}.get(passage.treatise_id, 0),
            "section_title": "",
            "chapter_label": f"treatise {passage.treatise_id}",
            "chapter_title": "",
            "arabic_range": list(passage.arabic_range),
            "english_range": list(passage.english_range),
            "headings_stripped": [],
            "flags": list(passage.flags),
            "rights_evidence": ibn_rushd.RIGHTS_EVIDENCE,
            "llm_verdict": passage.llm_verdict,
            "reference_fidelity": "pending_human_audit",
            "treatise_id": passage.treatise_id,
            "treatise_complete": passage.treatise_complete,
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
        "treatise_id": record["treatise_id"],
        "treatise_complete": record["treatise_complete"],
    }


def build_report(
    report: ibn_rushd.ExtractionReport,
    selected: list[dict],
    all_records: list[dict],
    seed: int,
) -> str:
    bands = Counter(record["band"] for record in selected)
    methods = Counter(record["method"] for record in selected)
    unpaired = ", ".join(report.unpaired_english) if report.unpaired_english else "none"
    return "\n".join(
        [
            "# PD alignment slice -- Ibn Rushd / Jamil-ur-Rehman",
            "",
            (
                "Treatise-anchored proposals from *Fasl al-Maqal* and the "
                "*Damima* against *The Philosophy and Theology of Averroes* "
                "(1921). Corpus text lives off-repo."
            ),
            "",
            f"- Arabic: OpenITI `{ibn_rushd.WORK_ID}` (PRIMARY_VERSION JK010686)",
            f"- English: {ibn_rushd.ENGLISH_SOURCE}",
            f"- Rights: `{ibn_rushd.RIGHTS_STATUS}` -- {ibn_rushd.RIGHTS_EVIDENCE}",
            f"- Selection seed: `{seed}`",
            "",
            "## Pipeline yield",
            "",
            "| stage | count |",
            "|---|---|",
            f"| Arabic treatises parsed | {report.arabic_treatises} |",
            f"| English treatises parsed | {report.english_treatises} |",
            f"| paired by treatise | {report.paired} |",
            f"| treatises used | {len(report.used)} |",
            f"| treatises rejected | {len(report.rejected)} |",
            f"| unpaired English treatises | {unpaired} |",
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
                "The treatise is a real bilateral anchor (Arabic Damima "
                "salutation; English APPENDIX / May God perpetuate). OpenITI "
                "FaslMaqal is Fasl plus Damima only. English Gutenberg 65708 "
                "also prints Kashf (An Exposition of the Methods of Argument); "
                "that treatise is unpaired and was not cut. Cuts *inside* a "
                "treatise are name-refined proportional proposals. Every "
                "selected item has an explicit `aligned` content verdict; "
                "`reference_fidelity` remains `pending_human_audit`."
            ),
            "",
            (
                "Review pages (corpus text, off-repo): "
                "`~/versed-translator-data/benchmark-alignment/ibn_rushd_rehman/"
                "review.html` (triage, worst first) and `review_shipping.html` "
                f"(selected only, best first). {len(all_records)} proposals "
                f"rendered; {len(selected)} selected."
            ),
            "",
            f"Rejected treatises: {len(report.rejected)} of {report.paired}.",
            "",
        ]
    )


def _apply_verdict(
    passage: ibn_rushd.Passage, verdict: llm_adjudicator.Verdict
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


def _passage_key(passage: ibn_rushd.Passage, model: str) -> str:
    return pd_alignment.sha256_hex(f"{model}\n{passage.arabic}\n{passage.english}")


def apply_cached_verdicts(
    passages: list[ibn_rushd.Passage],
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
    parser.add_argument(
        "--adjudicate-limit", type=int, default=DEFAULT_ADJUDICATE_LIMIT
    )
    parser.add_argument("--model", default=llm_adjudicator.DEFAULT_MODEL)
    args = parser.parse_args(argv)

    data_out = pd_alignment._assert_outside_repo(args.data_out)
    data_out.mkdir(parents=True, exist_ok=True)

    metadata, report = ibn_rushd.extract(args.arabic, args.english)
    print(
        f"parsed: {report.arabic_treatises} Arabic treatises, "
        f"{report.english_treatises} English treatises -> "
        f"{report.paired} paired, {len(report.used)} used, "
        f"{len(report.passages)} proposals; unpaired English: "
        f"{report.unpaired_english or []}",
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
        "work_title": "Ibn Rushd, Fasl al-Maqal / Jamil-ur-Rehman",
        "subtitle": (
            f"{len(selected_records)} selected of {len(all_records)} proposals "
            f"· genre {metadata.book_subject} · author d. {metadata.author_died} AH"
        ),
        "work_id": ibn_rushd.WORK_ID,
        "english_source": ibn_rushd.ENGLISH_SOURCE,
        "rights": ibn_rushd.RIGHTS_STATUS,
        "stats": {
            "proposed": len(all_records),
            "treatises used": len(report.used),
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
        "slice": "ibn_rushd_rehman",
        "work_id": ibn_rushd.WORK_ID,
        "translator": ibn_rushd.TRANSLATOR,
        "english_source": ibn_rushd.ENGLISH_SOURCE,
        "rights_status": ibn_rushd.RIGHTS_STATUS,
        "rights_evidence": ibn_rushd.RIGHTS_EVIDENCE,
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
            "by_treatise": dict(Counter(r["treatise_id"] for r in selected_records)),
            "unpaired_english": report.unpaired_english,
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
