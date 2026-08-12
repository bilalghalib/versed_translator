"""Loader for AhmedBaset/hadith-json.

Source: a git checkout of a JSON hadith database (17 books) whose Arabic
text is transcribed hadith text but whose English translations were
scraped from Sunnah.com (per this repo's README and task brief). The
repo's own package.json declares an ISC license, but that covers the
*scraper code*, not the underlying hadith text or the scraped English
translations -- no LICENSE file governing the data itself exists in the
checkout, and Sunnah.com's translations are all-rights-reserved.

Note also: Sunan al-Darimi (one of the 17 listed books) has Arabic text
but an empty english.text field on every single one of its 3,406 hadith
objects in this checkout -- it contributes zero pairs here, so only 16 of
the 17 books actually appear in the loader's output.

Consequently every pair yielded here carries
rights_status="INDEX_ONLY_NO_REDISTRIBUTION": the English side may be used
internally for matching/indexing/alignment-quality comparison (per roadmap
C6 standing constraint D6c) but must never be redistributed, published, or
used to train a model that could reproduce Sunnah.com's copyrighted
English text. The Arabic side (transcribed classical hadith text) is not
itself Sunnah.com's copyrighted expression, but this loader keeps the
whole pair under the conservative INDEX_ONLY status since the two sides
are only useful here as an aligned unit.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from versed_translator.benchmark.sources.schema import make_pair

RIGHTS_STATUS = "INDEX_ONLY_NO_REDISTRIBUTION"


def _iter_book_file(path: Path) -> Iterator[dict]:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)

    metadata = data.get("metadata") or {}
    english_meta = metadata.get("english") or {}
    arabic_meta = metadata.get("arabic") or {}
    book_id = metadata.get("id")
    work_id = english_meta.get("title") or arabic_meta.get("title") or path.stem
    author = english_meta.get("author") or arabic_meta.get("author")

    for hadith in data.get("hadiths", []):
        arabic = hadith.get("arabic")
        english = hadith.get("english") or {}
        narrator = english.get("narrator")
        text = english.get("text")
        if not arabic or not text:
            continue
        reference_english = f"{narrator} {text}".strip() if narrator else text
        native_id = f"book{book_id}_h{hadith.get('id')}_inbook{hadith.get('idInBook')}"
        notes = f"narrator: {narrator}" if narrator else None
        yield make_pair(
            source="hadith_json",
            source_native_id=native_id,
            work_id=work_id,
            author=author,
            genre="hadith",
            date_or_century=None,
            arabic=arabic,
            reference_english=reference_english,
            translator=None,
            english_source="Sunnah.com (scraped, via hadith-json)",
            rights_status=RIGHTS_STATUS,
            source_split=None,
            notes=notes,
        )


def iter_pairs(corpus_dir: Path) -> Iterator[dict]:
    """Yield candidate pairs from every by_book JSON file.

    corpus_dir is the hadith-json checkout root, e.g.
    .../corpus-cache/hadith-json. Uses db/by_book/**/*.json (one file per
    book) rather than by_chapter, to avoid double-counting hadiths.
    """
    by_book = Path(corpus_dir) / "db" / "by_book"
    for book_path in sorted(by_book.glob("*/*.json")):
        yield from _iter_book_file(book_path)
