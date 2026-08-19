"""Compare Hayy special-case locks to the book-agnostic zipper.

Same Arabic paragraphs, same Ockley sections. Gold is the selected
Hayy passages (paragraph/section ranges). Does not write the edition ledger.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from versed_translator.align.hayy import (
    DEFAULT_ARABIC,
    DEFAULT_ENGLISH,
    _arabic_paragraphs,
    align_book,
)
from versed_translator.align.standard import anchors, section_hit, zip_units
from versed_translator.benchmark.sources import ockley_hayy
from versed_translator.paths import DATA_DIR

GOLD = DATA_DIR / "benchmark-alignment" / "ockley_hayy" / "passages.jsonl"


def _invert_special(sections, n_arabic: int) -> list[tuple[int, int]]:
    mapping = [(0, 0) for _ in range(n_arabic)]
    for section in sections:
        start, end = section.arabic_paragraph_range
        for index in range(start, min(end, n_arabic)):
            prev_start, prev_end = mapping[index]
            new_start, new_end = section.section_index, section.section_index + 1
            if prev_start == prev_end == 0:
                mapping[index] = (new_start, new_end)
            else:
                mapping[index] = (min(prev_start, new_start), max(prev_end, new_end))
    return mapping


def _union_en(mapping: list[tuple[int, int]], ar_start: int, ar_end: int) -> tuple[int, int] | None:
    spans = [
        mapping[index]
        for index in range(ar_start, min(ar_end, len(mapping)))
        if mapping[index] != (0, 0)
    ]
    if not spans:
        return None
    return (min(start for start, _ in spans), max(end for _, end in spans))


def _score(mapping: list[tuple[int, int]], gold_rows: list[dict]) -> dict:
    exact = buffer_1 = buffer_2 = paragraph = catastrophic = 0
    misses: list[dict] = []
    for row in gold_rows:
        gold_en = tuple(row["english_range"])
        gold_ar = tuple(row["arabic_range"])
        predicted = _union_en(mapping, gold_ar[0], gold_ar[1])
        if predicted is None:
            catastrophic += 1
            misses.append({"id": row["id"], "gold_en": gold_en, "predicted": None})
            continue
        if section_hit(gold_en, predicted, window=0):
            exact += 1
            buffer_1 += 1
            buffer_2 += 1
            paragraph += 1
        elif section_hit(gold_en, predicted, window=1):
            buffer_1 += 1
            buffer_2 += 1
            paragraph += 1
        elif section_hit(gold_en, predicted, window=2):
            buffer_2 += 1
            paragraph += 1
        elif section_hit(gold_en, predicted, window=4):
            paragraph += 1
            misses.append(
                {
                    "id": row["id"],
                    "gold_en": gold_en,
                    "predicted": predicted,
                    "kind": "wide",
                }
            )
        else:
            catastrophic += 1
            misses.append(
                {
                    "id": row["id"],
                    "gold_en": gold_en,
                    "predicted": predicted,
                    "kind": "catastrophic",
                }
            )
    n = max(len(gold_rows), 1)
    return {
        "n": len(gold_rows),
        "exact": round(exact / n, 3),
        "buffer_1": round(buffer_1 / n, 3),
        "buffer_2": round(buffer_2 / n, 3),
        "paragraph": round(paragraph / n, 3),
        "catastrophic": round(catastrophic / n, 3),
        "misses": misses[:8],
    }


def climate_story_cut(
    mapping: list[tuple[int, int]],
    arabic: list[str],
) -> dict:
    story = next(
        (
            index
            for index, text in enumerate(arabic)
            if "يقظان" in text and len(text.split()) > 4
        ),
        None,
    )
    predicted = mapping[story] if story is not None else (0, 0)
    return {
        "story_arabic_index": story,
        "predicted_english": predicted,
        "crossed_into_preface": bool(predicted[1] <= 2 and predicted != (0, 0)),
    }


def run_bakeoff(arabic_path: Path, english_path: Path, gold_path: Path) -> dict:
    paragraphs = [p.text for p in _arabic_paragraphs(arabic_path)]
    english = [
        section.text
        for section in ockley_hayy.parse_english_sections(
            english_path.read_text(encoding="utf-8", errors="replace")
        )
    ]
    gold_rows = [
        json.loads(line)
        for line in gold_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    special = align_book(arabic_path, english_path)
    special_map = _invert_special(special, len(paragraphs))
    standard_map = zip_units(paragraphs, english)
    return {
        "arabic_paragraphs": len(paragraphs),
        "english_sections": len(english),
        "gold_passages": len(gold_rows),
        "standard_anchors": len(anchors(paragraphs, english)),
        "special": {
            **_score(special_map, gold_rows),
            "climate": climate_story_cut(special_map, paragraphs),
        },
        "standard": {
            **_score(standard_map, gold_rows),
            "climate": climate_story_cut(standard_map, paragraphs),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arabic", type=Path, default=DEFAULT_ARABIC)
    parser.add_argument("--english", type=Path, default=DEFAULT_ENGLISH)
    parser.add_argument("--gold", type=Path, default=GOLD)
    args = parser.parse_args(argv)
    result = run_bakeoff(args.arabic, args.english, args.gold)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
