"""Tests for the read-only OpenITI reader, the transliteration anchors, and
the Hitti OCR cleaner.

Every fixture here is SYNTHETIC. The Arabic strings are invented placeholder
names (Zayd, 'Amr, Khalid -- the Arabic equivalent of Alice and Bob) written
in the mARkdown shape; no corpus text appears in this repo, per the standing
rights rule.
"""

from __future__ import annotations

from versed_translator.benchmark.sources import (
    baladhuri,
    hitti_ocr,
    openiti_markdown,
    translit,
)

# --------------------------------------------------------------------------
# openiti_markdown
# --------------------------------------------------------------------------

SAMPLE = """######OpenITI#


#META# 000.BookURI\t:: #9999.Placeholder.Sample
#META# 010.AuthorNAME\t:: MISTER PLACEHOLDER
#META# 011.AuthorDIED\t:: 123
#META# 019.AuthorDIED\t:: NODATA
#META# 020.BookTITLE\t:: SAMPLE BOOK
#META# 021.BookSUBJ\t:: SAMPLE SUBJECT
#META# 022.BookVOLS\t:: NODATA

#META#Header#End#

# PageV00P000
### | FIRST SECTION
# alpha one PageV01P001 two
~~three four
# beta ms012 five
### |PARATEXT|
# editorial note
### | SECOND SECTION
# gamma six %~% seven
"""


def test_meta_header_parsed_and_nulls_dropped():
    text = openiti_markdown.parse(SAMPLE, uri="9999Placeholder.Sample")
    assert text.author_name == "MISTER PLACEHOLDER"
    assert text.author_died == 123
    assert text.book_title == "SAMPLE BOOK"
    assert text.book_subject == "SAMPLE SUBJECT"
    assert text.book_uri == "#9999.Placeholder.Sample"
    # NODATA values must not survive as strings.
    assert "022.BookVOLS" not in text.meta
    assert "019.AuthorDIED" not in text.meta


def test_sections_paragraphs_and_marker_stripping():
    text = openiti_markdown.parse(SAMPLE)
    assert [s.title for s in text.sections] == ["FIRST SECTION", "", "SECOND SECTION"]
    assert text.sections[1].is_paratext is True

    first = text.sections[0]
    assert [p.text for p in first.paragraphs] == [
        "alpha one two three four",
        "beta five",
    ]
    # Page markers, milestones and hemistich separators are all gone.
    joined = " ".join(p.text for p in text.all_paragraphs)
    assert "PageV" not in joined
    assert "ms012" not in joined
    assert "%~%" not in joined
    assert text.sections[2].paragraphs[0].text == "gamma six seven"


def test_paragraph_word_count_and_section_totals():
    text = openiti_markdown.parse(SAMPLE)
    assert text.sections[0].paragraphs[0].word_count == 5
    assert text.sections[0].word_count == 7


def test_parse_survives_input_with_no_header():
    text = openiti_markdown.parse("### | ONLY SECTION\n# lone paragraph\n")
    assert text.meta == {}
    assert text.author_died is None
    assert text.sections[0].paragraphs[0].text == "lone paragraph"


def test_level_one_heading_continuations_are_not_silently_lost():
    text = openiti_markdown.parse(
        "### | CHAPTER\n# | opening words\n~~continued words\n# next paragraph\n"
    )
    assert [paragraph.text for paragraph in text.all_paragraphs] == [
        "opening words continued words",
        "next paragraph",
    ]


# --------------------------------------------------------------------------
# translit
# --------------------------------------------------------------------------


def test_arabic_and_latin_skeletons_agree_on_placeholder_names():
    # Invented placeholder names, not corpus text.
    for arabic, latin in [
        ("زيد", "Zaid"),
        ("خالد", "Khalid"),
        ("سليمان", "Sulaiman"),
        ("الحسين", "Husain"),
        ("هيثم", "Haitham"),
        ("محمد", "Muhammad"),
    ]:
        skeleton = translit.latin_skeleton(latin)
        assert skeleton, latin
        assert skeleton in translit.arabic_search_blob(arabic), (arabic, latin, skeleton)


def test_doubled_letters_collapse_on_both_sides():
    # Arabic writes no shadda here; the transliteration doubles the letter.
    assert translit.latin_skeleton("Khattab") == translit.arabic_skeleton("خطاب")


def test_ta_marbuta_matches_both_h_and_t_spellings():
    blob = translit.arabic_search_blob("دومة")
    assert translit.latin_skeleton("Dumah") in blob
    assert translit.latin_skeleton("Dumat") in blob


def test_only_capitalised_tokens_count_as_names():
    names = translit.english_name_skeletons("supposed to have been Khalid the father")
    assert translit.latin_skeleton("Khalid") in names
    assert translit.latin_skeleton("supposed") not in names


def test_chain_particles_and_titles_are_not_evidence():
    names = translit.english_name_skeletons("ibn-al-Haitham from az-Zuhri the Prophet")
    assert set(names) == {translit.latin_skeleton("Haitham"), translit.latin_skeleton("Zuhri")}


def test_name_evidence_scores_and_reports_offset():
    evidence = translit.name_evidence("Khalid ibn-Zaid", "خالد بن زيد قال شيئا ما")
    assert evidence.score == 1.0
    assert evidence.missed == ()
    assert evidence.first_offset == 0
    evidence_late = translit.name_evidence(
        "Khalid", "زيد قال شيئا ما وما وما وما وما وما ثم خالد"
    )
    assert evidence_late.score == 1.0
    assert evidence_late.first_offset > 0


def test_short_skeletons_do_not_count_toward_mass():
    evidence = translit.name_evidence("Zaid", "زيد")
    assert evidence.matched  # it did match
    assert evidence.mass == 0  # but "zd" is too short to be evidence
    assert evidence.strong_matches == 0


# --------------------------------------------------------------------------
# hitti_ocr
# --------------------------------------------------------------------------


def test_dehyphenate_rejoins_words_but_keeps_chain_hyphens():
    assert hitti_ocr.dehyphenate("they ex-\npelled him") == "they expelled him"
    assert hitti_ocr.dehyphenate("Zaid ibn-al-\nKhalid") == "Zaid ibn-al-Khalid"
    # A particle followed by a lower-case fragment is a broken word, not a chain.
    assert hitti_ocr.dehyphenate("an at-\ntempt") == "an attempt"


def test_footnotes_running_heads_and_page_numbers_are_dropped():
    lines = [
        "Zaid ibn-Khalid from Amr : - The first report runs like this",
        "and continues onto a second line.",
        "",
        "1 Somebody, vol. iii, pp. 10-11.",
        "",
        "2 A short gloss.",
        "",
        "50",
        "",
        "",
        "SAMPLE RUNNING HEAD",
        "",
        "The second report begins here and is long enough to survive.",
    ]
    cleaned = " ".join(hitti_ocr.clean_body_lines(lines))
    assert "Somebody" not in cleaned
    assert "A short gloss" not in cleaned
    assert "SAMPLE RUNNING HEAD" not in cleaned
    assert "The first report" in cleaned
    assert "The second report" in cleaned


def test_running_head_survives_letter_spacing_in_the_scan():
    assert hitti_ocr._is_running_head("36 THE ORIGIXS OF THE ISLAMIC ST A TE")
    assert not hitti_ocr._is_running_head("The Prophet went to the city and stayed")


def test_margin_page_numbers_removed_only_as_a_long_increasing_run():
    lines = []
    for i in range(30):
        lines.append(f"body line number {i} ending in a margin mark {100 + i}")
    lines.append("he paid them 500")  # a real number, not part of the run
    out = hitti_ocr.mask_margin_page_numbers(lines)
    assert out[0].endswith("margin mark")
    assert out[29].endswith("margin mark")
    assert out[30] == "he paid them 500"


def test_margin_masking_is_a_no_op_without_a_long_run():
    lines = ["he paid them 500", "and later 12"]
    assert hitti_ocr.mask_margin_page_numbers(lines) == lines


def test_run_in_heading_split_is_conservative():
    body = " ".join(["word"] * 40)
    head, rest = hitti_ocr.split_run_in_heading(f"The capture of Someplace. Zaid said {body}")
    assert head == "The capture of Someplace."
    assert rest.startswith("Zaid said")

    # Too little body left to be sure -- leave it alone.
    assert hitti_ocr.split_run_in_heading("A short thing. And then nothing.") == (
        None,
        "A short thing. And then nothing.",
    )
    # An isnad is not a heading.
    text = f"Zaid ibn-Khalid from Amr. He said {body}"
    assert hitti_ocr.split_run_in_heading(text)[0] is None


def test_parse_chapters_uses_body_headings_not_the_contents_list():
    volume = (
        "CONTENTS\n\n"
        # The table of contents uses mixed case and the em-dash form; it must
        # not be mistaken for the body.
        "PART  I— ARABIA\nChapter  I\nSomeplace    15\n\n"
        "PART I\nARABIA\n\n"
        "CHAPTER I\nSomeplace\n\n"
        "Zaid ibn-Khalid from Amr : - a report long enough to be kept here.\n\n"
        "CHAPTER II\nOtherplace\n\n"
        "Khalid ibn-Zaid from Amr : - a second report, also long enough.\n"
    )
    chapters = hitti_ocr.parse_chapters(volume)
    assert [c.title for c in chapters] == ["Someplace", "Otherplace"]
    assert [c.chapter_roman for c in chapters] == ["I", "II"]
    assert chapters[0].part_roman == "I"
    assert chapters[0].paragraphs[0].isnad_head.startswith("Zaid ibn-Khalid from Amr")


# --------------------------------------------------------------------------
# baladhuri: cuts, spans, passages
# --------------------------------------------------------------------------


def _section(paragraph_texts: list[str]) -> openiti_markdown.Section:
    section = openiti_markdown.Section(index=0, title="SAMPLE", line_no=1, level=3)
    for index, text in enumerate(paragraph_texts):
        section.paragraphs.append(
            openiti_markdown.Paragraph(index=index, section_index=0, line_no=index, text=text)
        )
    return section


def _chapter(paragraph_texts: list[str]) -> hitti_ocr.EnglishChapter:
    chapter = hitti_ocr.EnglishChapter(
        part_roman="I", part_title="P", chapter_roman="I", title="SAMPLE", line_no=1
    )
    chapter.paragraphs = [
        hitti_ocr.EnglishParagraph(index=i, text=t) for i, t in enumerate(paragraph_texts)
    ]
    return chapter


FILLER_AR = " ".join(["كلمة"] * 60)
FILLER_EN = " ".join(["word"] * 90)


def test_find_cuts_matches_heads_and_stays_monotone():
    section = _section(
        [
            f"حدثنا سليمان بن خالد عن الحسين {FILLER_AR}",
            f"حدثنا هيثم بن محمد عن سليمان {FILLER_AR}",
        ]
    )
    chapter = _chapter(
        [
            f"Sulaiman ibn-Khalid from Husain : - {FILLER_EN}",
            f"Haitham ibn-Muhammad from Sulaiman : - {FILLER_EN}",
        ]
    )
    cuts = baladhuri.find_cuts(section, chapter)
    assert [(c.arabic_index, c.english_index) for c in cuts] == [(0, 0), (1, 1)]
    assert all(c.confidence > 0 for c in cuts)


def test_a_match_buried_mid_paragraph_is_not_a_cut():
    """The failure this whole design exists to prevent.

    The English paragraph corresponds to material deep inside the Arabic
    paragraph. Treating that as a cut would silently prepend the first half
    of the Arabic to a passage whose English does not contain it.
    """
    section = _section([f"حدثنا سليمان بن خالد {FILLER_AR} ثم حدثنا هيثم بن محمد {FILLER_AR}"])
    chapter = _chapter([f"Haitham ibn-Muhammad from Sulaiman : - {FILLER_EN}"])
    assert baladhuri.find_cuts(section, chapter) == []


def test_build_spans_leaves_the_tail_unbracketed():
    section = _section(["a", "b", "c"])
    chapter = _chapter(["A", "B", "C"])
    cuts = [
        baladhuri.Cut(0, 0, translit.NameEvidence(("abcd",), ())),
        baladhuri.Cut(1, 1, translit.NameEvidence(("efgh",), ())),
    ]
    spans = baladhuri.build_spans(section, chapter, cuts)
    assert (spans[0].arabic_start, spans[0].arabic_end) == (0, 1)
    assert spans[0].close_confidence > 0
    # The last span runs to the end of both sides and is NOT closed.
    assert (spans[1].arabic_start, spans[1].arabic_end) == (1, 3)
    assert spans[1].close_confidence == 0.0


def test_assemble_passages_drops_unbracketed_and_undersized_spans():
    section = _section([FILLER_AR, FILLER_AR, FILLER_AR])
    chapter = _chapter([FILLER_EN, FILLER_EN, FILLER_EN])
    evidence = translit.NameEvidence(("abcdefghijkl",), ())
    cuts = [
        baladhuri.Cut(0, 0, evidence),
        baladhuri.Cut(2, 2, evidence),
    ]
    spans = baladhuri.build_spans(section, chapter, cuts)
    passages = baladhuri.assemble_passages(section, chapter, spans)
    assert len(passages) == 1
    passage = passages[0]
    assert passage.arabic_range == (0, 2)
    assert passage.english_range == (0, 2)
    assert passage.arabic_word_count == 120
    assert passage.method == "structural"
    assert passage.structural_confidence == passage.confidence


def test_word_ratio_outside_the_calibrated_band_is_flagged_and_discounted():
    section = _section([FILLER_AR, FILLER_AR, FILLER_AR])
    # Far too much English for the Arabic.
    long_en = " ".join(["word"] * 400)
    chapter = _chapter([long_en, long_en, long_en])
    evidence = translit.NameEvidence(("abcdefghijkl",), ())
    cuts = [baladhuri.Cut(0, 0, evidence), baladhuri.Cut(2, 2, evidence)]
    spans = baladhuri.build_spans(section, chapter, cuts)
    passages = baladhuri.assemble_passages(section, chapter, spans)
    assert passages
    assert any(f.startswith("word_ratio_out_of_band") for f in passages[0].flags)
    assert passages[0].confidence < min(spans[0].open_confidence, spans[0].close_confidence)


def test_apparatus_residue_is_flagged_not_silently_kept():
    passage = baladhuri.Passage(
        work_id="w",
        section_index=0,
        section_title="",
        chapter_label="",
        chapter_title="",
        arabic="كلمة كلمة",
        english="The report ran on Somebody, vol. iii, pp. 10-11. and then continued.",
        arabic_word_count=2,
        english_word_count=11,
        method="structural",
        confidence=1.0,
        open_names=(),
        close_names=(),
        n_spans=1,
        arabic_range=(0, 1),
        english_range=(0, 1),
    )
    baladhuri._flag_quality_issues([passage])
    assert any(f.startswith("apparatus_residue") for f in passage.flags)


def test_wrong_script_columns_are_flagged():
    passage = baladhuri.Passage(
        work_id="w",
        section_index=0,
        section_title="",
        chapter_label="",
        chapter_title="",
        arabic="this is not arabic at all",
        english="كلمة كلمة كلمة",
        arabic_word_count=6,
        english_word_count=3,
        method="structural",
        confidence=1.0,
        open_names=(),
        close_names=(),
        n_spans=1,
        arabic_range=(0, 1),
        english_range=(0, 1),
    )
    baladhuri._flag_quality_issues([passage])
    assert "arabic_side_not_arabic" in passage.flags
    assert "english_side_not_latin" in passage.flags
    assert "arabic_chars_in_english_side" in passage.flags


def test_monotone_chain_prefers_the_higher_scoring_consistent_set():
    # (0,0)+(1,1) scores 20; taking the stray (0,5) instead scores 11 and
    # would block (1,1), so it must be left out.
    chain = baladhuri._monotone_chain([(0, 0, 10.0), (1, 1, 10.0), (0, 5, 1.0)])
    assert [(a, b) for a, b, _ in chain] == [(0, 0), (1, 1)]


def test_monotone_chain_is_non_decreasing_in_both_coordinates():
    chain = baladhuri._monotone_chain([(0, 5, 1.0), (1, 0, 1.0), (2, 6, 1.0), (3, 7, 1.0)])
    arabic = [a for a, _b, _s in chain]
    english = [b for _a, b, _s in chain]
    assert arabic == sorted(arabic)
    assert english == sorted(english)
