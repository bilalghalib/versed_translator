"""Maqama profile discovers bodies but refuses count-only zips."""

from __future__ import annotations

from pathlib import Path

import pytest

from versed_translator.align.profiles import load_maqama_pair, load_plain_pair


def _arabic(units: list[tuple[str, str]]) -> str:
    body = ["######OpenITI#", "#META# 000.BookURI :: test.Maqamat", "#META#Header#End#"]
    for heading, text in units:
        body.extend((f"### | ( المقامة {heading} )", f"# {text}"))
    return "\n".join(body)


def _english(units: list[tuple[str, str, str]]) -> str:
    lines: list[str] = []
    for numeral, heading, text in units:
        lines.extend((f"{numeral}. THE MAQAMA OF {heading}", "", text, ""))
    return "\n".join(lines)


def test_maqama_profile_extracts_body_and_pairs_confirmed_sequence(tmp_path: Path):
    arabic = tmp_path / "ar.txt"
    english = tmp_path / "en.txt"
    arabic.write_text(
        _arabic(
            [
                ("البلخية", "قال الراوي كلاما عربيا."),
                ("البغداذية", "ثم ذهب إلى بغداد."),
                ("البصرية", "ثم وصل إلى البصرة."),
            ]
        ),
        encoding="utf-8",
    )
    english.write_text(
        _english(
            [
                ("I", "BALKH", "The narrator spoke in Balkh."),
                ("II", "BAGHDAD", "Then he went to Baghdad."),
                ("III", "BASRA", "Then he reached Basra."),
            ]
        ),
        encoding="utf-8",
    )
    ar_doc, en_doc, links, report = load_maqama_pair(arabic, english)
    assert len(links) == 3
    assert report["sequence_confirmed"] == 3
    assert en_doc.structures[1].paragraphs[0].text == "Then he went to Baghdad."
    assert ar_doc.work_id == en_doc.work_id == "test.Maqamat"


def test_maqama_profile_refuses_different_counts(tmp_path: Path):
    arabic = tmp_path / "ar.txt"
    english = tmp_path / "en.txt"
    arabic.write_text(
        _arabic(
            [
                ("البلخية", "نص."),
                ("البغداذية", "نص."),
                ("البصرية", "نص."),
            ]
        ),
        encoding="utf-8",
    )
    english.write_text(
        _english(
            [
                ("I", "BALKH", "Text."),
                ("II", "BAGHDAD", "Text."),
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="counts differ"):
        load_maqama_pair(arabic, english)


def test_plain_profile_preserves_openiti_sections_without_inventing_spine(
    tmp_path: Path,
):
    arabic = tmp_path / "book.txt"
    english = tmp_path / "translation.txt"
    arabic.write_text(
        """######OpenITI#
#META# 000.BookURI :: test.Book
#META#Header#End#
### | الباب الأول
# قال كلاما عربيا.
### | الباب الثاني
# ثم سار.""",
        encoding="utf-8",
    )
    english.write_text(
        "He spoke in Arabic.\n\nThen he walked.",
        encoding="utf-8",
    )
    ar_doc, en_doc, links, report = load_plain_pair(arabic, english)
    assert ar_doc.work_id == en_doc.work_id == "test.Book"
    assert [unit.heading for unit in ar_doc.structures] == [
        "الباب الأول",
        "الباب الثاني",
    ]
    assert len(en_doc.structures[0].paragraphs) == 2
    assert links[0].method == "whole_book_unanchored"
    assert "review_required" in links[0].flags
    assert report["bilateral_structural_anchors"] == 0
