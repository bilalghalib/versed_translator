"""Tests for block segmentation (D2e).

RIGHTS NOTE: every Arabic string here is either ASCII placeholder text or a
short public-domain phrase already present elsewhere in this repo's smoke
fixtures. The one test that touches real benchmark text reads it from off-tree
data and skips when that data is absent -- no corpus text is committed here.

The load-bearing test is `test_segment_never_loses_text`: this module exists
to make omission observable, so a segmenter that silently dropped a clause
would defeat its own purpose in the quietest possible way.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from versed_translator.harness.blocks import (
    DEFAULT_MAX_BLOCK_WORDS,
    BlockIdError,
    block_id,
    block_stats,
    blockify,
    expected_block_counts,
    is_block_id,
    parse_block_id,
    reassemble,
    segment,
)
from versed_translator.harness.schema import make_row

# ---------------------------------------------------------------------------
# block ids
# ---------------------------------------------------------------------------


def test_block_id_is_zero_padded_and_round_trips():
    bid = block_id("lk_hadith:AbuDaud_ch12_h1960", 7)
    assert bid == "lk_hadith:AbuDaud_ch12_h1960#b0007"
    assert parse_block_id(bid) == ("lk_hadith:AbuDaud_ch12_h1960", 7)


def test_block_id_refuses_to_nest():
    with pytest.raises(BlockIdError):
        block_id("item#b0001", 2)


def test_parse_block_id_rejects_a_plain_item_id():
    assert is_block_id("lk_hadith:AbuDaud_ch12_h1960") is False
    with pytest.raises(BlockIdError):
        parse_block_id("lk_hadith:AbuDaud_ch12_h1960")


def test_block_ids_sort_in_source_order_as_strings():
    ids = [block_id("x", i) for i in range(1, 12)]
    assert sorted(ids) == ids  # zero padding is what makes this true


# ---------------------------------------------------------------------------
# segment(): the no-text-lost invariant
# ---------------------------------------------------------------------------

_SENTENCES = " ".join(f"word{i} word{i} word{i} sentence{i}." for i in range(40))


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "one",
        "one two three.",
        _SENTENCES,
        "a b c, d e f, g h i, j k l, m n o, p q r",
        "nopunctuationatall " * 200,
        "بسم الله الرحمن الرحيم. العلم في الصغر كالنقش في الحجر.",
    ],
)
@pytest.mark.parametrize("max_words", [1, 3, 10, DEFAULT_MAX_BLOCK_WORDS])
def test_segment_never_loses_text(text, max_words):
    blocks = segment(text, max_words=max_words)
    assert " ".join(blocks) == " ".join(text.split())


@pytest.mark.parametrize("max_words", [1, 3, 10, DEFAULT_MAX_BLOCK_WORDS])
def test_segment_respects_the_word_budget(max_words):
    for block in segment(_SENTENCES, max_words=max_words):
        assert len(block.split()) <= max_words


def test_segment_of_whitespace_is_empty():
    assert segment("   \n ") == []


def test_segment_is_deterministic():
    assert segment(_SENTENCES) == segment(_SENTENCES)


def test_segment_prefers_sentence_boundaries_over_packing():
    # Two short sentences fit in one block; the budget is what packs them.
    assert segment("one two. three four.", max_words=10) == ["one two. three four."]
    assert segment("one two. three four.", max_words=2) == ["one two.", "three four."]


def test_segment_splits_a_run_with_no_punctuation_at_all():
    blocks = segment(" ".join(f"w{i}" for i in range(25)), max_words=10)
    # Evened, not greedy: three near-equal blocks, not 10 + 10 + a 5-word tail.
    assert [len(b.split()) for b in blocks] == [9, 9, 7]


def test_segment_evens_out_rather_than_leaving_a_one_word_runt():
    blocks = segment(" ".join(f"w{i}" for i in range(61)), max_words=60)
    assert [len(b.split()) for b in blocks] == [31, 30]


def test_segment_never_evens_at_the_cost_of_an_extra_block():
    """Evening must not inflate the block count -- blocks are API calls.

    Three 30-word sentences plus a 10-word one fit in two 60-word blocks. A
    target derived from total/max_words alone is 50, which splits them into
    three: more calls, no benefit.
    """
    text = " ".join(
        [" ".join(["a"] * 29 + ["a."]), " ".join(["b"] * 29 + ["b."]), " ".join(["c"] * 9 + ["c."])]
    )
    assert [len(b.split()) for b in segment(text, max_words=60)] == [60, 10]


def test_segment_rejects_a_nonsense_budget():
    with pytest.raises(ValueError):
        segment("text", max_words=0)


# ---------------------------------------------------------------------------
# blockify / stats
# ---------------------------------------------------------------------------


def test_blockify_assigns_sequential_ids_and_parentage():
    items = [{"id": "A", "arabic": "one two. three four."}, {"id": "B", "arabic": "five six."}]
    blocks = blockify(items, max_words=2)
    assert [b["id"] for b in blocks] == ["A#b0001", "A#b0002", "B#b0001"]
    assert [b["parent_id"] for b in blocks] == ["A", "A", "B"]
    assert [b["block_index"] for b in blocks] == [1, 2, 1]
    assert {b["block_count"] for b in blocks if b["parent_id"] == "A"} == {2}


def test_blockify_output_is_a_valid_items_file_shape():
    blocks = blockify([{"id": "A", "arabic": "one two three."}])
    for block in blocks:
        assert set(block) >= {"id", "arabic"}
        assert block["arabic"].strip()


def test_blockify_drops_an_empty_item_rather_than_emitting_an_empty_block():
    blocks = blockify([{"id": "A", "arabic": "  "}, {"id": "B", "arabic": "text"}])
    assert [b["parent_id"] for b in blocks] == ["B"]


def test_block_stats_reports_shape_not_text():
    blocks = blockify([{"id": "A", "arabic": "one two. three four."}], max_words=2)
    stats = block_stats(blocks)
    assert stats["blocks"] == 2
    assert stats["items"] == 1
    assert stats["block_words_max"] == 2
    assert "one" not in json.dumps(stats)


# ---------------------------------------------------------------------------
# reassemble()
# ---------------------------------------------------------------------------


def _row(item_id, translation, error=None):
    return make_row(
        run_id="r", item_id=item_id, model="m", adapter="a",
        prompt_template_id="structured_blocks_v1", translation=translation, error=error,
    )


def test_reassemble_joins_blocks_in_index_order_not_row_order():
    rows = [_row("A#b0002", "second"), _row("A#b0001", "first")]
    translations, incomplete = reassemble(rows)
    assert translations == {"A": "first second"}
    assert incomplete == {}


def test_reassemble_refuses_to_hide_a_missing_block():
    rows = [_row("A#b0001", "first"), _row("A#b0002", None, error="id_missing_from_structured_response")]
    translations, incomplete = reassemble(rows)
    assert translations == {}
    assert incomplete == {"A": ["A#b0002"]}


def test_reassemble_treats_a_blank_translation_as_incomplete():
    rows = [_row("A#b0001", "first"), _row("A#b0002", "   ")]
    translations, incomplete = reassemble(rows)
    assert translations == {}
    assert incomplete["A"] == ["A#b0002"]


def test_reassemble_refuses_to_join_across_an_absent_block():
    """The row is not merely errored -- it is not in the file at all.

    Caught by index contiguity. Before this, `#b0001` + `#b0003` joined into a
    shortened translation reported clean, which is precisely the silent
    omission blocks exist to expose.
    """
    translations, incomplete = reassemble([_row("A#b0001", "first"), _row("A#b0003", "third")])
    assert translations == {}
    assert incomplete == {"A": ["A#b0002"]}


def test_reassemble_catches_a_block_lost_from_the_end():
    """Trailing loss leaves no gap, so only an external count can see it."""
    rows = [_row("A#b0001", "first"), _row("A#b0002", "second")]
    translations, incomplete = reassemble(rows, expected_counts={"A": 3})
    assert translations == {}
    assert incomplete == {"A": ["A#b0003"]}
    # ...and the same rows are clean when that really is all the blocks.
    assert reassemble(rows, expected_counts={"A": 2}) == ({"A": "first second"}, {})


def test_reassemble_reports_an_item_whose_blocks_are_all_missing():
    _t, incomplete = reassemble([], expected_counts={"A": 2})
    assert incomplete == {"A": ["A#b0001", "A#b0002"]}


def test_expected_block_counts_uses_the_declared_count():
    blocks = blockify([{"id": "A", "arabic": "one two. three four."}], max_words=2)
    assert expected_block_counts(blocks) == {"A": 2}
    # Falls back to counting rows when block_count is absent.
    stripped = [{k: v for k, v in b.items() if k != "block_count"} for b in blocks]
    assert expected_block_counts(stripped) == {"A": 2}


def test_reassemble_keeps_unaffected_items_whole():
    rows = [_row("A#b0001", "a"), _row("B#b0001", "b"), _row("B#b0002", None, error="boom")]
    translations, incomplete = reassemble(rows)
    assert translations == {"A": "a"}
    assert set(incomplete) == {"B"}


# ---------------------------------------------------------------------------
# Against the real benchmark slice (off-tree; skips without it)
# ---------------------------------------------------------------------------

_DATA = Path(os.environ.get("VERSED_DATA_ROOT", Path.home() / "versed-translator-data"))
_DEV = _DATA / "benchmark-data" / "v0.1-draft" / "dev_bakeoff.jsonl"


@pytest.mark.skipif(not _DEV.exists(), reason="off-tree benchmark data not present on this machine")
def test_segmentation_of_the_real_slice_is_stable():
    """Pin the block count on the frozen slice.

    Block ids are positional, so a change here silently re-keys every
    downstream artifact — run rows, QE pairs, the lot. This caught a real
    change once already: fixing the over-splitting bug moved the count from
    522 to 496 *after* a paid GPU run had been measured on the 522-block file.
    That is fine as long as it is noticed; the point of this test is that it
    cannot happen unnoticed.
    """
    items = [json.loads(line) for line in _DEV.read_text(encoding="utf-8").splitlines() if line.strip()]
    blocks = blockify(items)
    assert len(blocks) == 496
    assert min(len(b["arabic"].split()) for b in blocks) >= 9


@pytest.mark.skipif(not _DEV.exists(), reason="off-tree benchmark data not present on this machine")
def test_segmentation_of_the_real_slice_loses_nothing_and_fits_the_budget():
    items = [json.loads(line) for line in _DEV.read_text(encoding="utf-8").splitlines() if line.strip()]
    blocks = blockify(items)
    by_parent: dict[str, list[str]] = {}
    for block in blocks:
        assert len(block["arabic"].split()) <= DEFAULT_MAX_BLOCK_WORDS
        by_parent.setdefault(block["parent_id"], []).append(block["arabic"])
    for item in items:
        assert " ".join(by_parent[item["id"]]) == " ".join(item["arabic"].split())
