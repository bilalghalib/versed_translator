"""Synthetic tests for the Ibn Khallikan/de Slane entry aligner."""

from pathlib import Path

from versed_translator.benchmark import ibn_khallikan_alignment
from versed_translator.benchmark.sources import ibn_khallikan


def test_arabic_biography_markers_become_complete_entries():
    text = """######OpenITI#
#META#Header#End#
### $BIO_MAN$ 1 - إبراهيم النخعي
# كلمة أولى
~~وكلمة ثانية PageV01P001
### $BIO_WOMAN$ 2 - فاطمة البصرية
# سيرة أخرى
"""

    entries = ibn_khallikan.parse_arabic_entries(text)

    assert [entry.number for entry in entries] == [1, 2]
    assert entries[0].title == "إبراهيم النخعي"
    assert entries[0].text == "كلمة أولى وكلمة ثانية"
    assert entries[1].kind == "BIO_WOMAN"


def test_heading_matching_ignores_running_headers_and_preserves_order():
    arabic = ibn_khallikan.parse_arabic_entries(
        """### $BIO_MAN$ 1 - إبراهيم النخعي
# متن
### $BIO_MAN$ 2 - أبو إسحاق المروزي
# متن
"""
    )
    english = """IBN KHALLIKAN'S

IBRAHIM AN-NAKHAI.

Body one.

BIOGRAPHICAL DICTIONARY. 3

ABU ISHAK AL-MARWAZI.

Body two.
"""

    matches = ibn_khallikan.match_entries(arabic, [(1, english)])

    assert [match.arabic_index for match in matches] == [0, 1]
    assert [match.heading.title for match in matches] == [
        "IBRAHIM AN-NAKHAI",
        "ABU ISHAK AL-MARWAZI",
    ]


def test_extract_keeps_only_whole_entries_in_the_target_word_range(tmp_path: Path):
    arabic_path = tmp_path / "work.txt"
    english_path = tmp_path / "volume.txt"
    arabic_path.write_text(
        """######OpenITI#
#META# 010.AuthorNAME :: مؤلف
#META# 011.AuthorDIED :: 123
#META# 021.BookSUBJ :: تراجم
#META#Header#End#
### $BIO_MAN$ 1 - إبراهيم النخعي
# """
        + " ".join(["كلمة"] * 120)
        + """
### $BIO_MAN$ 2 - أبو إسحاق المروزي
# """
        + " ".join(["قصير"] * 20),
        encoding="utf-8",
    )
    english_path.write_text(
        "IBRAHIM AN-NAKHAI.\n\n"
        + " ".join(["word"] * 150)
        + "\n\nABU ISHAK AL-MARWAZI.\n\nshort text",
        encoding="utf-8",
    )

    metadata, report = ibn_khallikan.extract(arabic_path, [english_path])

    assert metadata.author_died == 123
    assert len(report.matches) == 2
    assert [passage.entry_number for passage in report.passages] == [1]
    assert report.passages[0].arabic_word_count == 120
    assert report.passages[0].english_word_count == 150


def test_selection_rejects_ratio_flags_and_balances_bands():
    def passage(number: int, words: int, flags=None):
        return ibn_khallikan.Passage(
            entry_index=number,
            entry_number=number,
            volume=1,
            arabic=" ".join(["كلمة"] * words),
            english=" ".join(["word"] * words),
            arabic_word_count=words,
            english_word_count=words,
            confidence=0.9,
            structural_confidence=0.9,
            anchors_open=("name",),
            flags=list(flags or []),
        )

    passages = [passage(1, 150), passage(2, 300), passage(3, 150, ["bad"])]

    selected = ibn_khallikan_alignment.select(passages, target=4)

    assert [item.entry_number for item in selected] == [1, 2]
