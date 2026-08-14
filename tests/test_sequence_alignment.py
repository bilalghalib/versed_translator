"""Tests for length proposals used by the Ockley and Blunt slices."""

from versed_translator.benchmark import sequence_alignment
from versed_translator.benchmark.sources import blunt_odes, monotone_length, ockley_hayy


def test_monotone_partition_uses_every_fragment_once_in_order():
    ranges = monotone_length.partition(
        [10, 20, 10],
        [4, 6, 5, 5, 10, 10, 3, 7],
        min_fragments=1,
        max_fragments=4,
    )

    assert ranges[0][0] == 0
    assert ranges[-1][1] == 8
    assert all(left[1] == right[0] for left, right in zip(ranges, ranges[1:]))


def test_ockley_parser_stops_before_gutenberg_notes():
    text = """§ 1. First narrative section.
§ 2. Second narrative section.
§ 120. Last narrative section.

_FINIS_.

§ 1. A note that is not narrative.
"""

    sections = ockley_hayy.parse_english_sections(text)

    assert [section.printed_number for section in sections] == [1, 2, 120]
    assert sections[-1].text == "Last narrative section."


def test_sequence_selection_requires_an_aligned_verdict():
    passage = blunt_odes.Passage(
        poem_key="test",
        poem_name="Test",
        verse_range=(0, 10),
        arabic=" ".join(["كلمة"] * 150),
        english=" ".join(["word"] * 220),
        arabic_word_count=150,
        english_word_count=220,
    )
    assert sequence_alignment.select([passage], target=2, seed=1) == []

    passage.llm_verdict = {"verdict": "partial", "confidence": 0.9}
    assert sequence_alignment.select([passage], target=2, seed=1) == []

    passage.llm_verdict = {"verdict": "aligned", "confidence": 0.9}
    assert sequence_alignment.select([passage], target=2, seed=1) == [passage]
