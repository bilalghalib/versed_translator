"""Map Ockley English onto Hayy edition.sqlite3 blocks.

The Arabic audio already lives on these block ids. English is a translation
row on the same ids — not a second book. Climate preface and the Yokdhan
story are locked apart before sentence DP runs inside each region.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from versed_translator.align.dp import align
from versed_translator.align.hayy import _YOKDHAN_STORY_EN
from versed_translator.align.sentences import split_arabic, split_paragraphs_english
from versed_translator.benchmark.sources import ockley_hayy
from versed_translator.paths import DATA_DIR

DEFAULT_ENGLISH = DATA_DIR / "pd-english" / "ockley_hayy_pg16831.txt"
DEFAULT_OUT = DATA_DIR / "benchmark-alignment" / "hayy_ockley" / "block_translations.jsonl"

_HEADING_WORDS = 4


@dataclass(frozen=True)
class Block:
    id: str
    sequence: int
    text: str
    text_hash: str
    block_type: str = "paragraph"


def is_heading(block: Block) -> bool:
    return len(block.text.split()) <= _HEADING_WORDS


def story_arabic_index(blocks: list[Block]) -> int:
    for index, block in enumerate(blocks):
        if "يقظان" in block.text:
            return index
    return 0


def story_english_index(sections: list[str]) -> int:
    for index, text in enumerate(sections):
        if _YOKDHAN_STORY_EN.search(text):
            return index
    return 0


def _assign_english(
    blocks: list[Block],
    english_sections: list[str],
) -> dict[str, list[str]]:
    texts: dict[str, list[str]] = {block.id: [] for block in blocks}
    if not blocks or not english_sections:
        return texts

    owners: list[str] = []
    arabic_sentences: list[str] = []
    for block in blocks:
        for sentence in split_arabic(block.text):
            arabic_sentences.append(sentence.text)
            owners.append(block.id)
    english_sentences = [
        sentence.text for sentence in split_paragraphs_english(english_sections)
    ]
    if not arabic_sentences or not english_sentences:
        return texts

    last_block = owners[0]
    for link in align(arabic_sentences, english_sentences):
        english_piece = english_sentences[link.english_start : link.english_end]
        if link.arabic_end > link.arabic_start:
            last_block = owners[link.arabic_end - 1]
        if not english_piece:
            continue
        joined = " ".join(english_piece)
        if link.operation == "0-1":
            texts[last_block].append(joined)
            continue
        block_ids: list[str] = []
        for index in range(link.arabic_start, link.arabic_end):
            block_id = owners[index]
            if block_id not in block_ids:
                block_ids.append(block_id)
        for block_id in block_ids:
            texts[block_id].append(joined)
        if block_ids:
            last_block = block_ids[-1]
    return texts


def to_import_rows(
    blocks: list[Block],
    english_sections: list[str],
) -> list[dict[str, str]]:
    """One JSONL object per Arabic block that received English text."""
    ar_lock = story_arabic_index(blocks)
    en_lock = story_english_index(english_sections)
    regions = (
        (
            [block for block in blocks[:ar_lock] if not is_heading(block)],
            english_sections[:en_lock],
        ),
        (
            [block for block in blocks[ar_lock:] if not is_heading(block)],
            english_sections[en_lock:],
        ),
    )
    assigned: dict[str, list[str]] = {block.id: [] for block in blocks}
    for region_blocks, region_english in regions:
        for block_id, pieces in _assign_english(region_blocks, region_english).items():
            assigned[block_id].extend(pieces)

    rows: list[dict[str, str]] = []
    for block in blocks:
        translated = " ".join(assigned[block.id]).strip()
        if not translated:
            continue
        rows.append(
            {
                "block_id": block.id,
                "source_hash": block.text_hash,
                "translated_text": translated,
            }
        )
    return rows


def load_blocks(sqlite_path: Path) -> list[Block]:
    connection = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT id, sequence, text, text_hash, block_type
            FROM blocks
            WHERE language='arabic' AND tts_skip=0
            ORDER BY sequence
            """
        ).fetchall()
    finally:
        connection.close()
    return [
        Block(
            id=str(row["id"]),
            sequence=int(row["sequence"]),
            text=str(row["text"] or ""),
            text_hash=str(row["text_hash"] or ""),
            block_type=str(row["block_type"] or "paragraph"),
        )
        for row in rows
        if str(row["text"] or "").strip()
    ]


def write_jsonl(rows: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", type=Path, required=True)
    parser.add_argument("--english", type=Path, default=DEFAULT_ENGLISH)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    blocks = load_blocks(args.sqlite)
    english = ockley_hayy.parse_english_sections(
        args.english.read_text(encoding="utf-8", errors="replace")
    )
    rows = to_import_rows(blocks, [section.text for section in english])
    write_jsonl(rows, args.out)
    print(
        json.dumps(
            {
                "out": str(args.out),
                "arabic_blocks": len(blocks),
                "imported_rows": len(rows),
                "english_sections": len(english),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
