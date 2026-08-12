"""Loader for the LK (Leeds/King Saud University) Hadith Corpus.

Source: ShathaTm/LK-Hadith-Corpus (git checkout), one CSV per chapter under
per-collection directories (Bukhari, Muslim, AbuDaud, IbnMaja, Nesai,
Tirmizi). Each row is one hadith with chapter/section titles in both
languages, the full hadith text, and an isnad/matn split done by an
automatic segmentation tool (README: "92% accuracy") for every collection
except Bukhari, which the corpus README says was "manually checked and is
considered the gold standard."

No LICENSE file exists in the checkout (verified: only README.md and
starter.py present at repo root). The README asks for citation but states
no redistribution/reuse terms, so rights_status is left explicitly
unverified here rather than assumed permissive -- see
corpus/rights_ledger.json.

arabic/reference_english are the full Arabic_Hadith / English_Hadith
fields (isnad+matn combined, matching how the corpus itself pairs them);
the isnad/matn split and grading are carried in notes for provenance, not
computed into new fields.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from pathlib import Path

import pandas as pd

from versed_translator.benchmark.sources.schema import make_pair

RIGHTS_STATUS = "RIGHTS_UNVERIFIED_NO_LICENSE_FILE"

COLLECTIONS: tuple[str, ...] = ("AbuDaud", "Bukhari", "IbnMaja", "Muslim", "Nesai", "Tirmizi")


def _clean(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    return text


def _iter_chapter_file(path: Path, collection: str) -> Iterator[dict]:
    df = pd.read_csv(path)
    for row in df.itertuples(index=False):
        arabic = _clean(getattr(row, "Arabic_Hadith", None))
        english = _clean(getattr(row, "English_Hadith", None))
        if arabic is None or english is None:
            continue
        chapter_num = _clean(getattr(row, "Chapter_Number", None))
        hadith_num = _clean(getattr(row, "Hadith_number", None))
        native_id = f"{collection}_ch{chapter_num}_h{hadith_num}"
        notes_parts = []
        isnad = _clean(getattr(row, "Arabic_Isnad", None))
        matn = _clean(getattr(row, "Arabic_Matn", None))
        grade_en = _clean(getattr(row, "English_Grade", None))
        grade_ar = _clean(getattr(row, "Arabic_Grade", None))
        if isnad or matn:
            notes_parts.append("isnad/matn split available in source CSV")
        if grade_en or grade_ar:
            notes_parts.append(f"grade: {grade_en or grade_ar}")
        if collection != "Bukhari":
            notes_parts.append(
                "automatic isnad/matn segmentation (~92% accuracy per corpus README); "
                "Bukhari is the only manually-checked collection"
            )
        yield make_pair(
            source="lk_hadith",
            source_native_id=native_id,
            work_id=collection,
            author=None,
            genre="hadith",
            date_or_century=None,
            arabic=arabic,
            reference_english=english,
            translator=None,
            english_source="LK Hadith Corpus (Leeds/King Saud University)",
            rights_status=RIGHTS_STATUS,
            source_split=None,
            notes="; ".join(notes_parts) if notes_parts else None,
        )


def iter_pairs(corpus_dir: Path) -> Iterator[dict]:
    """Yield candidate pairs from every chapter CSV in every collection dir.

    corpus_dir is the LK-Hadith-Corpus checkout root, e.g.
    .../corpus-cache/lk-hadith.
    """
    root = Path(corpus_dir)
    for collection in COLLECTIONS:
        coll_dir = root / collection
        if not coll_dir.is_dir():
            continue
        for csv_path in sorted(coll_dir.glob("Chapter*.csv")):
            yield from _iter_chapter_file(csv_path, collection)
