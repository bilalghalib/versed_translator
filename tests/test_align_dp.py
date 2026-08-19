"""Fixture tests for C7 v0: sentence split + monotone DP."""

from pathlib import Path

import pytest

from versed_translator.align.dp import align, buffer_hit, pair_score
from versed_translator.align.sentences import split_arabic, split_english


def test_english_keeps_abbreviations_together():
    sents = split_english("Dr. Jones went home. Then he slept.")
    assert [s.text for s in sents] == ["Dr. Jones went home.", "Then he slept."]


def test_arabic_splits_on_question_mark():
    sents = split_arabic("هل خرج؟ ثم عاد.")
    assert len(sents) == 2
    assert sents[0].text.endswith("؟")


def test_long_arabic_prose_gets_bounded_clause_spans():
    text = "، ".join(["هذه جملة عربية طويلة فيها عدد من الكلمات المفيدة"] * 12)
    sentences = split_arabic(text)
    assert len(sentences) > 1
    assert max(sentence.word_count for sentence in sentences) <= 55


def test_arabic_indic_numbers_match_western_numbers():
    assert pair_score("بلغ من العمر ٢١ سنة", "He reached age 21") > pair_score(
        "بلغ من العمر ٢١ سنة", "He reached age 40"
    )


def test_unreachable_move_set_fails_loudly():
    with pytest.raises(ValueError, match="cannot reach"):
        align(["أ", "ب"], ["a"], moves=((1, 1),))


def test_dp_prefers_one_to_one_when_names_match():
    arabic = ["قال حي بن يقظان هذا.", "ثم سار إلى الجزيرة."]
    english = ["Hayy ibn Yaqzan said this.", "Then he walked to the island."]
    links = align(arabic, english)
    assert [link.operation for link in links] == ["1-1", "1-1"]
    assert links[0].arabic_span == (0, 1)
    assert links[0].english_span == (0, 1)


def test_dp_allows_english_merge():
    arabic = ["خرج حي.", "وسار حتى بلغ البحر."]
    english = ["Hayy went out and walked until he reached the sea."]
    links = align(arabic, english)
    ops = [link.operation for link in links]
    assert "2-1" in ops or ops == ["1-1", "1-0"]
    # The translation of both Arabic sentences is inside the one English sentence.
    covered = {i for link in links for i in range(*link.english_span)}
    assert covered == {0}


def test_buffer_hit_treats_plus_minus_one_as_usable():
    links = align(
        ["قال حي بن يقظان هذا."],
        ["Hayy ibn Yaqzan said this."],
    )
    assert buffer_hit(0, links[0], window=1)
    assert not buffer_hit(4, links[0], window=1)


@pytest.mark.skipif(
    not Path.home().joinpath(
        "versed-translator-data/openiti/0581IbnTufayl.HayyIbnYaqzan.txt"
    ).is_file(),
    reason="Hayy corpus files are off-repo",
)
def test_hayy_book_emits_120_section_locks():
    from versed_translator.align.hayy import DEFAULT_ARABIC, DEFAULT_ENGLISH, align_book

    sections = align_book(DEFAULT_ARABIC, DEFAULT_ENGLISH)
    assert len(sections) == 120
    assert sections[0].printed_number == 1
    assert sections[-1].printed_number == 120
    assert all(section.links for section in sections)
