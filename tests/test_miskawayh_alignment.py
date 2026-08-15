"""Synthetic tests for the Miskawayh/Margoliouth driver and year parser.

Fixtures are invented Arabic tokens plus ASCII. No corpus text lives here.
"""

from __future__ import annotations

from versed_translator.benchmark import (
    alignment_review,
    miskawayh_alignment,
    pd_alignment,
)
from versed_translator.benchmark.sources import miskawayh


def _passage(
    year: int,
    words: int,
    start: int = 0,
    *,
    confidence: float = 0.7,
    flags: list[str] | None = None,
    verdict: dict | None = None,
    english_words: int | None = None,
) -> miskawayh.Passage:
    english_count = english_words if english_words is not None else int(words * 1.6)
    return miskawayh.Passage(
        ah_year=year,
        arabic_range=(start, start + 1),
        english_range=(start, start + 1),
        arabic=" ".join(["كلمة"] * words),
        english=" ".join(["word"] * english_count),
        arabic_word_count=words,
        english_word_count=english_count,
        arabic_pages=[year],
        year_complete=False,
        structural_confidence=0.6,
        confidence=confidence,
        flags=list(flags if flags is not None else ["llm_required"]),
        llm_verdict=verdict,
    )


class _FakeText:
    author_name = "PLACEHOLDER AUTHOR"
    author_died = 421
    book_subject = "التاريخ"


# --------------------------------------------------------------------------
# Year parser
# --------------------------------------------------------------------------


def test_parse_arabic_year_reads_spelled_out_hijri():
    assert miskawayh.parse_arabic_year("ودخلت سنة خمس وتسعين ومائتين") == 295


def test_parse_arabic_year_stops_at_the_first_non_numeral():
    assert miskawayh.parse_arabic_year("سنة خمس وثلاثين فيها كان ظهور السبائية") == 35


def test_parse_arabic_year_returns_none_without_سنة():
    assert miskawayh.parse_arabic_year("باب ذكر الوقائع") is None


# --------------------------------------------------------------------------
# Eligibility / selection
# --------------------------------------------------------------------------


def test_eligibility_rejects_out_of_band_ratio_and_hard_flags():
    assert miskawayh_alignment.eligible_for_adjudication(_passage(300, 150))
    assert not miskawayh_alignment.eligible_for_adjudication(
        _passage(300, 150, english_words=20)
    )
    assert not miskawayh_alignment.eligible_for_adjudication(_passage(300, 20))
    assert not miskawayh_alignment.eligible_for_adjudication(
        _passage(300, 150, flags=["llm_required", "page_markers_nonmonotone"])
    )


def test_select_requires_an_aligned_verdict():
    bare = _passage(300, 150)
    partial = _passage(301, 150, verdict={"verdict": "partial", "confidence": 0.9})
    aligned = _passage(302, 150, verdict={"verdict": "aligned", "confidence": 0.9})
    assert miskawayh_alignment.select([bare, partial], target=4) == []
    assert miskawayh_alignment.select([bare, partial, aligned], target=4) == [aligned]


def test_select_spreads_across_years_rather_than_draining_one():
    passages = []
    for year in (300, 301):
        for index in range(10):
            passages.append(
                _passage(
                    year,
                    150,
                    start=index,
                    verdict={"verdict": "aligned", "confidence": 0.9},
                )
            )
    chosen = miskawayh_alignment.select(passages, target=8, seed=7)
    assert {p.ah_year for p in chosen} == {300, 301}


def test_select_balances_the_two_target_bands():
    short = [
        _passage(300 + i, 150, verdict={"verdict": "aligned", "confidence": 0.9})
        for i in range(6)
    ]
    long = [
        _passage(320 + i, 300, verdict={"verdict": "aligned", "confidence": 0.9})
        for i in range(6)
    ]
    chosen = miskawayh_alignment.select(short + long, target=4, seed=1)
    bands = {p.arabic_word_count < 250 for p in chosen}
    assert bands == {True, False}
    assert len(chosen) == 4


def test_adjudication_pool_spreads_a_limit_across_years():
    passages = [
        _passage(year, 150, start=index)
        for year in range(300, 310)
        for index in range(8)
    ]
    pool = miskawayh_alignment.adjudication_pool(passages, limit=10, seed=3)
    assert len(pool) == 10
    assert len({p.ah_year for p in pool}) == 10


def test_cached_verdicts_replay_and_are_skipped_by_a_second_pool():
    passage = _passage(300, 150)
    key = miskawayh_alignment._passage_key(passage, "m")
    cache = {
        key: {
            "verdict": "aligned",
            "confidence": 0.9,
            "note": "",
            "model": "m",
            "error": None,
        }
    }
    assert miskawayh_alignment.apply_cached_verdicts([passage], cache, "m") == 1
    assert passage.llm_verdict["verdict"] == "aligned"
    uncached = [p for p in [passage] if p.llm_verdict is None]
    assert miskawayh_alignment.adjudication_pool(uncached, limit=10, seed=1) == []


def test_select_is_deterministic_for_a_fixed_seed():
    passages = [
        _passage(
            300 + i,
            120 + i,
            verdict={"verdict": "aligned", "confidence": 0.9},
        )
        for i in range(20)
    ]
    first = [
        p.native_id for p in miskawayh_alignment.select(passages, target=8, seed=7)
    ]
    second = [
        p.native_id for p in miskawayh_alignment.select(passages, target=8, seed=7)
    ]
    assert first == second


# --------------------------------------------------------------------------
# Records / rights
# --------------------------------------------------------------------------


def test_manifest_records_carry_no_text_and_pass_the_guard():
    record = miskawayh_alignment.to_record(
        _passage(295, 150, verdict={"verdict": "aligned", "confidence": 0.9}),
        _FakeText(),
    )
    manifest = miskawayh_alignment.to_manifest_record(record)
    assert "arabic" not in manifest
    assert "english" not in manifest
    assert "reference_english" not in manifest
    assert manifest["sha256_arabic"] == record["sha256_arabic"]
    assert manifest["ah_year"] == 295
    assert manifest["rights_status"] == miskawayh.RIGHTS_STATUS
    pd_alignment._assert_textfree([manifest], "manifest")


def test_record_carries_provenance_and_the_year_anchor():
    record = miskawayh_alignment.to_record(_passage(295, 150), _FakeText())
    assert record["source"] == "miskawayh_eclipse"
    assert record["work_id"] == miskawayh.WORK_ID
    assert record["rights_status"] == miskawayh.RIGHTS_STATUS
    assert record["rights_evidence"]
    assert record["genre"] == "التاريخ"
    assert record["date_or_century"] == "421 AH"
    assert record["chapter_label"] == "AH 295"
    assert record["anchors_open"] == ["AH 295"]


# --------------------------------------------------------------------------
# Review pages
# --------------------------------------------------------------------------


def _review_record(rid: str, confidence: float, selected: bool = True) -> dict:
    return {
        "id": rid,
        "confidence": confidence,
        "method": "llm_proposed",
        "band": "100-250",
        "translator": "Margoliouth",
        "arabic": "كلمة كلمة",
        "english": "word word",
        "arabic_word_count": 2,
        "english_word_count": 2,
        "word_ratio": 1.0,
        "anchors_open": ["AH 295"],
        "anchors_close": ["AH 295"],
        "section_title": "",
        "chapter_label": "AH 295",
        "chapter_title": "",
        "arabic_range": [0, 1],
        "english_range": [0, 1],
        "flags": [],
        "headings_stripped": [],
        "llm_verdict": {"verdict": "aligned", "confidence": 0.9},
        "selected": selected,
    }


def test_shipping_page_sorts_highest_confidence_first_opposite_of_triage():
    records = [_review_record("high", 0.95), _review_record("low", 0.2)]
    summary = {"work_title": "T", "stats": {}}
    triage = alignment_review.render_page(records, summary)
    shipping = alignment_review.render_shipping_page(records, summary)
    assert triage.index('data-id="low"') < triage.index('data-id="high"')
    assert shipping.index('data-id="high"') < shipping.index('data-id="low"')


def test_shipping_page_says_it_is_the_selected_set_and_numbers_pairs():
    html = alignment_review.render_shipping_page(
        [_review_record("a", 0.9)], {"work_title": "T", "stats": {"selected": 1}}
    )
    assert "selected set, best first" in html
    assert "do not review from there" in html
    assert "1 / 1" in html
    assert "Margoliouth" in html
