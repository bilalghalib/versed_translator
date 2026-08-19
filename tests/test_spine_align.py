"""Fixture tests for bilateral spine pairing. No corpus text."""

from versed_translator.benchmark import spine_align
from versed_translator.benchmark.sources.openiti_markdown import (
    OpenITIText,
    Paragraph,
    Section,
)


def _section(index: int, title: str, words: str, *, level: int = 3) -> Section:
    paragraph = Paragraph(index=index, section_index=index, line_no=index, text=words)
    section = Section(index=index, title=title, line_no=index, level=level)
    if words:
        section.paragraphs.append(paragraph)
    return section


def test_arabic_folds_empty_heading_into_next_body():
    doc = OpenITIText(
        uri="x",
        meta={},
        preamble=[],
        sections=[
            _section(0, "( المقامة البلخية )", "كلام عربي طويل هنا"),
            _section(1, "( المقامة البغداذية )", ""),
            _section(
                2,
                "حدثنا عيسى بن هشام قال : | اشتهيت الأزاذ",
                "بقية المقامة",
                level=1,
            ),
            _section(3, "( المقامة البصرية )", "نص البصرة"),
        ],
    )
    units = spine_align.arabic_maqama_units(doc)
    assert [unit.title for unit in units] == [
        "( المقامة البلخية )",
        "( المقامة البغداذية )",
        "( المقامة البصرية )",
    ]
    baghdad = units[1]
    assert baghdad.word_count > 0
    assert baghdad.paragraph_count == 1


def test_english_skips_notes_running_headers_and_ocr_wreckage():
    text = "scene of the maqama of Madirah is laid in Basra while the con-\n2 THE MAQAMAT OF BADI 1\nI. THE MAQAMA OF BALKH\nnote on the maqama of the Yellow Text p, 230.\nTHE MAQAMA OF THE ASYLUM...\nXXVIII. THE MAQAMA OP ‘IRAQ 9\nXXXIX. THE MAQARIA OF NISIIArUE\n• XX. THE MAQAMA OF THE APE\nXXXHX. THE MAQAMA OF HULWAN\nXUV. THE MAQAMA OF POETRY\nXII. THE MAQAMA OF BAGHDAD\nXLVIII. MAQAMA OF TAMIN\nIV. ORIGIN AND CHARACTER OF THE MAQAMAT"
    units = spine_align.english_maqama_units(text)
    assert [unit.title for unit in units] == [
        "BALKH",
        "‘IRAQ",
        "NISIIArUE",
        "THE APE",
        "HULWAN",
        "POETRY",
        "BAGHDAD",
        "TAMIN",
    ]
    assert units[1].printed_label == "XXVIII"


def test_monotone_match_skips_a_gap_index_pairing_would_shift():
    arabic = [
        spine_align.ArabicUnit(1, "المقامة البلخية", 10, 1),
        spine_align.ArabicUnit(2, "المقامة العراقية", 10, 1),
        spine_align.ArabicUnit(3, "المقامة البصرية", 10, 1),
    ]
    english = [
        spine_align.EnglishUnit(1, "BALKH", "I", 1),
        spine_align.EnglishUnit(2, "BASRA", "II", 2),
    ]
    indexed = spine_align.pair_by_index(arabic, english)
    assert indexed[1].arabic.title == "المقامة العراقية"
    assert indexed[1].english.title == "BASRA"
    assert indexed[1].evidence_mass == 0
    monotone = spine_align.pair_monotone(arabic, english)
    assert [(p.arabic.index, p.english.title) for p in monotone] == [
        (1, "BALKH"),
        (3, "BASRA"),
    ]
    assert all(pair.evidence_mass >= 3 for pair in monotone)


def test_sequence_zip_is_confirmed_by_epithet_and_qaf():
    arabic = [
        spine_align.ArabicUnit(1, "المقامة القريضية", 10, 1),
        spine_align.ArabicUnit(2, "المقامة القزوينية", 10, 1),
        spine_align.ArabicUnit(3, "المقامة الكوفية", 10, 1),
    ]
    english = [
        spine_align.EnglishUnit(1, "FOESIE", "I", 1),
        spine_align.EnglishUnit(2, "QAZWIN", "II", 2),
        spine_align.EnglishUnit(3, "KUFA", "III", 3),
    ]
    sequence = spine_align.pair_by_sequence(arabic, english)
    assert [p.confirmation for p in sequence] == [
        "epithet",
        "short_or_qaf",
        "short_or_qaf",
    ]


def test_ocr_nishapur_and_short_tamin_confirm():
    assert spine_align.confirm_pair("المقامة النيسابورية", "NISIIArUE") == "epithet"
    assert spine_align.confirm_pair("المقامة التميمية", "TAMIN") == "epithet"
