"""D1e option (d): extract aligned benchmark passages from a PD translation pair.

First vertical slice: al-Baladhuri, *Futuh al-Buldan* (OpenITI
``0279Baladhuri.FutuhBuldan``) against Hitti's 1916 *The Origins of the
Islamic State*, vol. 1. One work, end to end, rather than a framework for
eight.

Run:

    uv run python -m versed_translator.benchmark.pd_alignment \\
        --arabic  ~/versed-translator-data/openiti/0279Baladhuri.FutuhBuldan.txt \\
        --english ~/versed-translator-data/pd-english/originsofislamic01albauoft_djvu.txt

Outputs, split strictly by whether they contain corpus text:

  OFF-REPO (default under ~/versed-translator-data/benchmark-alignment/):
    passages.jsonl   full items, Arabic + English text, per the item schema
    review.html      the [HUMAN] side-by-side review gate (C1 checkpoint 3)

  REPO-TRACKED (benchmark/alignment/baladhuri_hitti/):
    manifest.json    ids, sha256s, counts, confidences, rights -- NO text
    report.md        stats and honest caveats -- NO text

The split is enforced, not merely intended: `_assert_outside_repo` refuses to
write a text-bearing file anywhere under the repository root, and
`_assert_textfree` scans every repo-bound record for Arabic script or long
Latin runs before it is written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

from versed_translator.benchmark import alignment_review
from versed_translator.benchmark.sources import baladhuri, llm_adjudicator
from versed_translator.benchmark.sources.schema import length_band, make_pair

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA_DIR = Path.home() / "versed-translator-data" / "benchmark-alignment" / "baladhuri_hitti"
DEFAULT_REPO_OUT = REPO_ROOT / "benchmark" / "alignment" / "baladhuri_hitti"

DEFAULT_SEED = 20260814
DEFAULT_TARGET = 60
# The two bands v0.1-draft is thin on (its 250-600 band came out short and
# its 100-250 band is 99.6% hadith). Equal targets, so a shortfall in either
# shows up as a shortfall rather than being quietly absorbed by the other.
TARGET_BANDS = ("100-250", "250-600")

# Below this, a passage is shown for review but not proposed for the
# benchmark. It is never dropped from the review page -- that is where a
# human is supposed to see what the aligner was unsure about.
SELECT_MIN_CONFIDENCE = 0.6
# At or below this, the LLM adjudicator is asked for a second opinion.
ADJUDICATE_BELOW = 0.8

# Flags that disqualify a passage outright, as opposed to merely discounting
# its confidence. A surviving footnote or a wrong-script column is a defect
# in the TEXT and no confidence number can make the item usable; an
# out-of-band word ratio is only evidence about the alignment, and it is
# already priced into `confidence`, so it is not repeated here as a veto.
HARD_FLAG_PREFIXES = (
    "arabic_side",
    "english_side",
    "arabic_chars",
    "apparatus_residue",
)

_ARABIC_RE = re.compile(r"[؀-ۿ]")
_LONG_LATIN_RE = re.compile(r"[A-Za-z][A-Za-z ,.;:'\"-]{80,}")


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _assert_outside_repo(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(REPO_ROOT)
    except ValueError:
        return resolved
    raise SystemExit(
        f"refusing to write corpus text inside the repository: {resolved}\n"
        "This repo is public. Text-bearing outputs belong under "
        "~/versed-translator-data/ (see the module docstring)."
    )


def _assert_textfree(records: list[dict], where: str) -> None:
    """Fail loudly if a repo-bound record carries corpus text."""
    for record in records:
        blob = json.dumps(record, ensure_ascii=False)
        if _ARABIC_RE.search(blob):
            raise SystemExit(f"{where}: Arabic script in a repo-tracked record: {record.get('id')}")
        if _LONG_LATIN_RE.search(blob):
            raise SystemExit(
                f"{where}: a long Latin text run in a repo-tracked record: {record.get('id')}"
            )


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def select(
    passages: list[baladhuri.Passage],
    target: int = DEFAULT_TARGET,
    seed: int = DEFAULT_SEED,
    min_confidence: float = SELECT_MIN_CONFIDENCE,
) -> list[baladhuri.Passage]:
    """Pick a band-balanced, chapter-spread subset, deterministically.

    Spreading across chapters matters as much as the band balance: 87 raw
    passages concentrated in the four longest chapters would give a
    "history" genre slice that is really four episodes of one narrative.
    Selection therefore round-robins over chapters within each band, taking
    the highest-confidence unused passage from each in turn.
    """
    eligible = [
        p
        for p in passages
        if p.confidence >= min_confidence
        and not any(f.startswith(HARD_FLAG_PREFIXES) for f in p.flags)
        and length_band(p.arabic_word_count) in TARGET_BANDS
    ]
    rng = random.Random(seed)
    per_band = max(1, target // len(TARGET_BANDS))
    chosen: list[baladhuri.Passage] = []

    for band in TARGET_BANDS:
        pool = [p for p in eligible if length_band(p.arabic_word_count) == band]
        by_chapter: dict[str, list[baladhuri.Passage]] = {}
        for passage in pool:
            by_chapter.setdefault(passage.chapter_label, []).append(passage)
        for items in by_chapter.values():
            rng.shuffle(items)
            items.sort(key=lambda p: -p.confidence)
        order = sorted(by_chapter)
        rng.shuffle(order)
        taken: list[baladhuri.Passage] = []
        cursor = 0
        while len(taken) < per_band and any(by_chapter[c] for c in order):
            chapter = order[cursor % len(order)]
            if by_chapter[chapter]:
                taken.append(by_chapter[chapter].pop(0))
            cursor += 1
        chosen.extend(taken)

    chosen.sort(key=lambda p: (p.section_index, p.arabic_range[0]))
    return chosen


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


def to_record(passage: baladhuri.Passage, text: Any) -> dict:
    """Full item record, with text. Off-repo only."""
    pair = make_pair(
        source="baladhuri_hitti",
        source_native_id=passage.native_id,
        work_id=baladhuri.WORK_ID,
        author=text.author_name,
        genre=text.book_subject,
        date_or_century=f"{text.author_died} AH" if text.author_died else None,
        arabic=passage.arabic,
        reference_english=passage.english,
        translator=baladhuri.TRANSLATOR,
        english_source=baladhuri.ENGLISH_SOURCE,
        rights_status=baladhuri.RIGHTS_STATUS,
        source_split=None,
        notes=None,
    )
    record = dict(pair)
    record.update(
        {
            "id": f"baladhuri_hitti:{passage.native_id}",
            "english": passage.english,
            "sha256_arabic": sha256_hex(passage.arabic),
            "sha256_english": sha256_hex(passage.english),
            "band": length_band(passage.arabic_word_count),
            "arabic_word_count": passage.arabic_word_count,
            "english_word_count": passage.english_word_count,
            "word_ratio": round(passage.word_ratio, 3),
            "method": passage.method,
            "confidence": passage.confidence,
            "structural_confidence": passage.structural_confidence,
            "anchors_open": list(passage.open_names),
            "anchors_close": list(passage.close_names),
            "section_index": passage.section_index,
            "section_title": passage.section_title,
            "chapter_label": passage.chapter_label,
            "chapter_title": passage.chapter_title,
            "arabic_range": list(passage.arabic_range),
            "english_range": list(passage.english_range),
            "headings_stripped": list(passage.headings_stripped),
            "flags": list(passage.flags),
            "rights_evidence": baladhuri.RIGHTS_EVIDENCE,
            "llm_verdict": passage.llm_verdict,
        }
    )
    return record


def to_manifest_record(record: dict) -> dict:
    """Text-free record for the repo-tracked manifest."""
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
        "rights_status": record["rights_status"],
    }


def build_report_md(
    report: baladhuri.ExtractionReport,
    selected: list[dict],
    all_records: list[dict],
    genre: str | None,
    century: str | None,
    seed: int,
) -> str:
    band_counts = Counter(r["band"] for r in selected)
    method_counts = Counter(r["method"] for r in selected)
    conf = sorted(r["confidence"] for r in selected)
    median = conf[len(conf) // 2] if conf else 0.0
    lines: list[str] = []
    add = lines.append
    add("# PD alignment slice -- al-Baladhuri / Hitti")
    add("")
    add(
        "First vertical slice of **D1e option (d)**: aligned benchmark passages "
        "extracted from a public-domain translation pair. ONE work, end to end."
    )
    add("")
    add(f"- Arabic: OpenITI `{baladhuri.WORK_ID}`")
    add(f"- English: {baladhuri.ENGLISH_SOURCE}")
    add(
        f"- Genre (`021.BookSUBJ`, read from the OpenITI header, not inferred): "
        f"**{genre}** (*al-tarikh*, history) -- a genre v0.1-draft does not contain at all"
    )
    add(f"- Author death year (`011.AuthorDIED`): **{century}**")
    add(f"- Rights: `{baladhuri.RIGHTS_STATUS}` -- {baladhuri.RIGHTS_EVIDENCE}")
    add(f"- Selection seed: `{seed}`")
    add("")
    add("## Pipeline yield")
    add("")
    add("| stage | count |")
    add("|---|---|")
    add(f"| Arabic `### \\|` sections in the OpenITI text | {report.arabic_sections} |")
    add(f"| English Part/Chapter units parsed from the scan | {report.english_chapters} |")
    add(f"| section <-> chapter pairs confirmed | {report.chapters_matched} |")
    add(f"| khabar-level cuts (matched transmitter names) | {report.cuts_found} |")
    add(f"| passages assembled between cuts | {len(report.passages)} |")
    add(f"| passages selected for the benchmark | {len(selected)} |")
    add("")
    add("## Selected passages")
    add("")
    add("| band | count |")
    add("|---|---|")
    for band, count in sorted(band_counts.items()):
        add(f"| {band} | {count} |")
    add("")
    add("| method | count |")
    add("|---|---|")
    for method, count in sorted(method_counts.items()):
        add(f"| {method} | {count} |")
    add("")
    add(f"Median confidence: **{median:.2f}**.")
    add("")
    add("## What the confidence means")
    add("")
    add(
        "Every passage begins and ends at a *cut*: a point where an English "
        "paragraph's abridged isnad matches the head of an Arabic paragraph by "
        "transliterated transmitter name. A passage is therefore bracketed at "
        "both ends by independent name evidence, which is what makes the "
        "classic failure -- a systematic one-report shift that looks plausible "
        "row by row -- structurally hard rather than merely unlikely. "
        "`confidence` is the weaker of its two brackets, discounted when the "
        "English/Arabic word ratio falls outside Hitti's normal 0.85-2.30."
    )
    add("")
    add(
        "`method=structural` means the brackets alone carried it. "
        "`method=llm_proposed` means the structural confidence was below "
        f"{ADJUDICATE_BELOW} and Claude was asked whether the English "
        "translates the Arabic; the verdict and the model's own confidence are "
        "recorded per item, and the structural confidence is preserved "
        "alongside it. No LLM judgement is ever written as if it were an "
        "anchor match."
    )
    add("")
    add("## Known limits")
    add("")
    add(
        "- **Volume 1 only.** Hitti's vol. 1 covers roughly the first 70 of the "
        "90 Arabic sections. Murgotten's vol. 2 is a separate scan and has not "
        "been validated here."
    )
    add(
        "- **Chapter coverage is partial by design.** Sections whose chapter "
        "could not be confirmed by both title evidence and khabar-level cuts "
        "are dropped, never assigned to the nearest chapter."
    )
    add(
        "- **OCR damage persists inside passages.** The 1916 scan mangles "
        "proper names ('Busy a' for 'Busra'); footnote and running-head "
        "stripping is rule-based and is not perfect. The review page exists to "
        "surface what survived."
    )
    add(
        "- **Hitti abridges.** He states in his own footnote that isnads are "
        "cut to first and last authority, and he omits the occasional report. "
        "Passages where that happens show up as a low word ratio and are "
        "flagged, but a short omission inside a long passage will not be."
    )
    add("")
    add(f"Unconfirmed Arabic sections: {len(report.unmatched_sections)} of {report.arabic_sections}.")
    add("")
    add("## Per-chapter detail")
    add("")
    add(
        "Arabic section titles are deliberately omitted from this table: it is "
        "repo-tracked, and the standing rule keeps corpus text out of the repo "
        "even when it is only a heading. The English chapter titles below are "
        "bibliographic metadata from a 1916 public-domain table of contents."
    )
    add("")
    add("| Arabic section # | English chapter | Ar paras | En paras | cuts | passages |")
    add("|---|---|---|---|---|---|")
    for row in report.per_chapter:
        add(
            f"| {row['section_index']} | {row['chapter']} -- {row['chapter_title']} | "
            f"{row['arabic_paragraphs']} | {row['english_paragraphs']} | "
            f"{row['cuts']} | {row['passages']} |"
        )
    add("")
    add(
        f"Review page (contains corpus text, lives outside the repo): "
        f"`~/versed-translator-data/benchmark-alignment/baladhuri_hitti/review.html`. "
        f"{len(all_records)} passages are rendered there, including the "
        f"{len(all_records) - len(selected)} not selected."
    )
    add("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arabic", type=Path, required=True, help="OpenITI mARkdown .txt")
    parser.add_argument("--english", type=Path, required=True, help="archive.org djvu.txt")
    parser.add_argument("--data-out", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--repo-out", type=Path, default=DEFAULT_REPO_OUT)
    parser.add_argument("--target", type=int, default=DEFAULT_TARGET)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--adjudicate",
        action="store_true",
        help=(
            "ask Claude to judge passages below the structural confidence "
            "threshold (costs API calls; nothing is called without this flag)"
        ),
    )
    parser.add_argument(
        "--adjudicate-all",
        action="store_true",
        help=(
            "adjudicate every assembled passage, not just the uncertain ones. "
            "Used to MEASURE alignment quality across the whole set; passages "
            "the anchors already settled keep method=structural."
        ),
    )
    parser.add_argument("--model", default=llm_adjudicator.DEFAULT_MODEL)
    args = parser.parse_args(argv)

    data_out = _assert_outside_repo(args.data_out)
    data_out.mkdir(parents=True, exist_ok=True)

    text, _chapters, report = baladhuri.extract(args.arabic, args.english)
    print(
        f"parsed: {report.arabic_sections} Arabic sections, "
        f"{report.english_chapters} English chapters -> "
        f"{report.chapters_matched} confirmed, {report.cuts_found} cuts, "
        f"{len(report.passages)} passages",
        file=sys.stderr,
    )

    # Verdicts are cached by content hash, not by id: change how a passage is
    # cut and it is re-judged, leave it alone and the API is not called again.
    cache_path = data_out / "llm_verdicts.json"
    cache: dict[str, dict] = {}
    if cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))

    verdicts: dict[str, llm_adjudicator.Verdict] = {}
    if args.adjudicate or args.adjudicate_all:
        pending = (
            list(report.passages)
            if args.adjudicate_all
            else [p for p in report.passages if p.confidence < ADJUDICATE_BELOW or p.flags]
        )
        print(f"adjudicating {len(pending)} passages with {args.model}...", file=sys.stderr)
        client = None
        for index, passage in enumerate(pending, 1):
            key = sha256_hex(f"{args.model}\n{passage.arabic}\n{passage.english}")
            if key in cache:
                verdict = llm_adjudicator.Verdict(**cache[key])
                origin = "cached"
            else:
                client = client or llm_adjudicator._get_client()
                verdict = llm_adjudicator.adjudicate(
                    passage.arabic, passage.english, model=args.model, client=client
                )
                cache[key] = asdict(verdict)
                origin = "fresh"
            verdicts[passage.native_id] = verdict
            print(
                f"  [{index}/{len(pending)}] {passage.native_id}: "
                f"{verdict.verdict or verdict.error} ({origin})",
                file=sys.stderr,
            )
        cache_path.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")

    # Apply verdicts BEFORE selecting. Selecting first and judging afterwards
    # would put passages in the benchmark that the adjudicator had already
    # said were only partially parallel.
    for passage in report.passages:
        verdict = verdicts.get(passage.native_id)
        if verdict is None or not verdict.ok:
            continue
        passage.llm_verdict = asdict(verdict)
        passage.confidence = llm_adjudicator.combined_confidence(
            passage.structural_confidence, verdict
        )
        # Method records what actually carried the passage. Anchors strong
        # enough on their own stay `structural` even when a verdict was
        # recorded for measurement; only a passage the anchors could not
        # settle is credited to the model.
        if passage.structural_confidence < ADJUDICATE_BELOW or passage.flags:
            passage.method = "llm_proposed"

    selected = select(report.passages, target=args.target, seed=args.seed)
    selected_ids = {p.native_id for p in selected}

    all_records = [to_record(p, text) for p in report.passages]
    for record in all_records:
        record["selected"] = record["source_native_id"] in selected_ids
    selected_records = [r for r in all_records if r["selected"]]

    passages_path = data_out / "passages.jsonl"
    with passages_path.open("w", encoding="utf-8") as handle:
        for record in selected_records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    all_path = data_out / "passages_all.jsonl"
    with all_path.open("w", encoding="utf-8") as handle:
        for record in all_records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    summary = {
        "work_title": "al-Baladhuri, Futuh al-Buldan / Hitti, The Origins of the Islamic State",
        # Plain text, not entities: the renderer HTML-escapes this field.
        "subtitle": (
            f"{len(selected_records)} selected of {len(all_records)} assembled "
            f"· genre {text.book_subject} · author d. {text.author_died} AH"
        ),
        "work_id": baladhuri.WORK_ID,
        "english_source": baladhuri.ENGLISH_SOURCE,
        "rights": baladhuri.RIGHTS_STATUS,
        "stats": {
            "assembled": len(all_records),
            "selected": len(selected_records),
            "chapters confirmed": report.chapters_matched,
            "cuts": report.cuts_found,
            "llm adjudicated": len(verdicts),
        },
    }
    review_path = data_out / "review.html"
    review_path.write_text(alignment_review.render_page(all_records, summary), encoding="utf-8")

    repo_out = args.repo_out.expanduser().resolve()
    repo_out.mkdir(parents=True, exist_ok=True)
    manifest_items = [to_manifest_record(r) for r in selected_records]
    _assert_textfree(manifest_items, "manifest")
    manifest = {
        "slice": "baladhuri_hitti",
        "work_id": baladhuri.WORK_ID,
        "translator": baladhuri.TRANSLATOR,
        "english_source": baladhuri.ENGLISH_SOURCE,
        "rights_status": baladhuri.RIGHTS_STATUS,
        "rights_evidence": baladhuri.RIGHTS_EVIDENCE,
        "genre_openiti_021_booksubj": text.book_subject,
        "author_died_ah": text.author_died,
        "seed": args.seed,
        "counts": {
            "assembled": len(all_records),
            "selected": len(selected_records),
            "by_band": dict(Counter(r["band"] for r in selected_records)),
            "by_method": dict(Counter(r["method"] for r in selected_records)),
        },
        "items": manifest_items,
    }
    (repo_out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (repo_out / "report.md").write_text(
        build_report_md(
            report,
            selected_records,
            all_records,
            text.book_subject,
            f"{text.author_died} AH" if text.author_died else None,
            args.seed,
        ),
        encoding="utf-8",
    )

    print(f"passages (with text) -> {passages_path}", file=sys.stderr)
    print(f"all passages         -> {all_path}", file=sys.stderr)
    print(f"review page          -> {review_path}", file=sys.stderr)
    print(f"manifest + report    -> {repo_out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
