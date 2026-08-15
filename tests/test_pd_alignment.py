"""Tests for PD-alignment orchestration: rights guards, selection, the LLM
adjudicator's parsing, and the review page.

All fixtures are synthetic ASCII (plus a couple of invented Arabic tokens
where the code path requires Arabic script). No corpus text lives in this
repo. The rights-guard tests are the important ones: they are what stands
between a public repository and a committed corpus.
"""

from __future__ import annotations

import pytest

from versed_translator.benchmark import alignment_review, pd_alignment
from versed_translator.benchmark.sources import baladhuri, llm_adjudicator


def _passage(
    native_suffix: int,
    words: int,
    confidence: float,
    chapter: str = "PART I / CHAPTER I",
    flags: list[str] | None = None,
) -> baladhuri.Passage:
    return baladhuri.Passage(
        work_id="w",
        section_index=native_suffix,
        section_title="",
        chapter_label=chapter,
        chapter_title="Someplace",
        arabic=" ".join(["كلمة"] * words),
        english=" ".join(["word"] * int(words * 1.4)),
        arabic_word_count=words,
        english_word_count=int(words * 1.4),
        method="structural",
        confidence=confidence,
        structural_confidence=confidence,
        open_names=("abcd",),
        close_names=("efgh",),
        n_spans=1,
        arabic_range=(0, 1),
        english_range=(0, 1),
        flags=list(flags or []),
    )


# --------------------------------------------------------------------------
# Rights guards -- the reason this repo can stay public
# --------------------------------------------------------------------------


def test_writing_text_inside_the_repo_is_refused(tmp_path):
    inside = pd_alignment.REPO_ROOT / "benchmark" / "should-never-exist"
    with pytest.raises(SystemExit) as excinfo:
        pd_alignment._assert_outside_repo(inside)
    assert "refusing to write corpus text inside the repository" in str(excinfo.value)
    # A path outside the repo is returned resolved, not rejected.
    assert pd_alignment._assert_outside_repo(tmp_path) == tmp_path.resolve()


def test_arabic_script_in_a_repo_bound_record_is_refused():
    with pytest.raises(SystemExit) as excinfo:
        pd_alignment._assert_textfree([{"id": "x", "note": "كلمة"}], "manifest")
    assert "Arabic script" in str(excinfo.value)


def test_a_long_latin_run_in_a_repo_bound_record_is_refused():
    prose = (
        "The Prophet went out to the city and stayed there for many days on end indeed"
    )
    with pytest.raises(SystemExit) as excinfo:
        pd_alignment._assert_textfree([{"id": "x", "english": prose}], "manifest")
    assert "long Latin text run" in str(excinfo.value)


def test_manifest_records_carry_no_text_and_pass_their_own_guard():
    passage = _passage(0, 150, 0.85)
    record = pd_alignment.to_record(passage, _FakeText())
    manifest = pd_alignment.to_manifest_record(record)
    assert "arabic" not in manifest
    assert "english" not in manifest
    assert "reference_english" not in manifest
    assert manifest["sha256_arabic"] == record["sha256_arabic"]
    # And it survives the guard that runs before it is written.
    pd_alignment._assert_textfree([manifest], "manifest")


class _FakeText:
    author_name = "MISTER PLACEHOLDER"
    author_died = 123
    book_subject = "SAMPLE SUBJECT"


def test_record_carries_provenance_and_rights_from_birth():
    record = pd_alignment.to_record(_passage(0, 150, 0.85), _FakeText())
    for field in (
        "work_id",
        "translator",
        "english_source",
        "rights_status",
        "rights_evidence",
        "genre",
        "date_or_century",
        "method",
        "confidence",
        "structural_confidence",
    ):
        assert record[field], field
    assert record["genre"] == "SAMPLE SUBJECT"
    assert record["date_or_century"] == "123 AH"


# --------------------------------------------------------------------------
# Selection
# --------------------------------------------------------------------------


def test_select_rejects_low_confidence_and_hard_flagged_passages():
    passages = [
        _passage(0, 150, 0.9),
        _passage(1, 150, 0.3),
        _passage(2, 150, 0.9, flags=["apparatus_residue:2"]),
        _passage(3, 150, 0.9, flags=["arabic_side_not_arabic"]),
        # 20 words is outside both target bands.
        _passage(4, 20, 0.9),
    ]
    chosen = pd_alignment.select(passages, target=10)
    assert [p.section_index for p in chosen] == [0]


def test_select_keeps_ratio_flagged_passages_because_confidence_already_prices_them():
    passages = [_passage(0, 150, 0.7, flags=["word_ratio_out_of_band:2.40"])]
    assert len(pd_alignment.select(passages, target=10)) == 1


def test_select_spreads_across_chapters_rather_than_draining_the_biggest():
    passages = [_passage(i, 150, 0.9, chapter="PART I / CHAPTER I") for i in range(10)]
    passages += [
        _passage(100 + i, 150, 0.9, chapter="PART I / CHAPTER II") for i in range(10)
    ]
    chosen = pd_alignment.select(passages, target=8)
    chapters = {p.chapter_label for p in chosen}
    assert chapters == {"PART I / CHAPTER I", "PART I / CHAPTER II"}


def test_select_is_deterministic_for_a_fixed_seed():
    passages = [_passage(i, 120 + i, 0.9, chapter=f"CH{i % 4}") for i in range(30)]
    first = [p.native_id for p in pd_alignment.select(passages, target=10, seed=7)]
    second = [p.native_id for p in pd_alignment.select(passages, target=10, seed=7)]
    assert first == second


# --------------------------------------------------------------------------
# LLM adjudicator (no network)
# --------------------------------------------------------------------------


def test_parse_verdict_reads_a_well_formed_reply():
    verdict = llm_adjudicator.parse_verdict(
        'Sure: {"verdict": "partial", "confidence": 0.8, "note": "one side has more"}',
        "m",
    )
    assert verdict.ok
    assert verdict.verdict == "partial"
    assert verdict.confidence == 0.8


def test_parse_verdict_never_defaults_to_aligned():
    for reply in ("no json here", '{"verdict": "maybe"}', '{"verdict": "aligned", '):
        verdict = llm_adjudicator.parse_verdict(reply, "m")
        assert not verdict.ok
        assert verdict.verdict != "aligned"
        assert verdict.error


def test_confidence_is_clamped_to_the_unit_interval():
    verdict = llm_adjudicator.parse_verdict('{"verdict":"aligned","confidence":9}', "m")
    assert verdict.confidence == 1.0


def test_a_misaligned_verdict_pulls_a_strongly_anchored_passage_down():
    verdict = llm_adjudicator.Verdict("misaligned", 0.9, "", "m")
    assert llm_adjudicator.combined_confidence(1.0, verdict) <= 0.15


def test_an_aligned_verdict_is_capped_below_a_pure_anchor_match():
    verdict = llm_adjudicator.Verdict("aligned", 1.0, "", "m")
    assert llm_adjudicator.combined_confidence(1.0, verdict) == 0.85


def test_an_unparseable_verdict_leaves_the_structural_confidence_alone():
    verdict = llm_adjudicator.parse_verdict("garbage", "m")
    assert llm_adjudicator.combined_confidence(0.72, verdict) == 0.72


# --------------------------------------------------------------------------
# Review page
# --------------------------------------------------------------------------


def _review_record(rid: str, confidence: float, method: str = "structural") -> dict:
    return {
        "id": rid,
        "confidence": confidence,
        "method": method,
        "band": "100-250",
        "arabic": "كلمة كلمة",
        "english": "word word",
        "arabic_word_count": 2,
        "english_word_count": 2,
        "word_ratio": 1.0,
        "anchors_open": ["abcd"],
        "anchors_close": ["efgh"],
        "section_title": "sec",
        "chapter_label": "PART I / CHAPTER I",
        "chapter_title": "Someplace",
        "arabic_range": [0, 1],
        "english_range": [0, 1],
        "flags": [],
        "headings_stripped": [],
        "llm_verdict": None,
    }


def test_review_page_sorts_lowest_confidence_first():
    html = alignment_review.render_page(
        [_review_record("high", 0.95), _review_record("low", 0.2)],
        {"work_title": "T", "stats": {}},
    )
    assert html.index('data-id="low"') < html.index('data-id="high"')


def test_review_page_is_rtl_theme_aware_and_warns_about_corpus_text():
    html = alignment_review.render_page(
        [_review_record("a", 0.9)], {"work_title": "T", "stats": {}}
    )
    assert 'class="col ar"' in html
    assert "direction: rtl" in html
    assert "prefers-color-scheme" in html
    assert "#3d5a80" in html
    assert "Contains corpus text" in html


def test_review_page_escapes_markup_in_the_text():
    record = _review_record("a", 0.9)
    record["english"] = "<script>alert(1)</script>"
    html = alignment_review.render_page([record], {"work_title": "T", "stats": {}})
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_review_page_shows_method_and_confidence_on_every_pair():
    html = alignment_review.render_page(
        [_review_record("a", 0.42, method="llm_proposed")],
        {"work_title": "T", "stats": {}},
    )
    assert "confidence 0.42" in html
    assert "llm_proposed" in html


def test_review_page_uses_the_translator_not_a_hardcoded_hitti_label():
    record = _review_record("a", 0.9)
    record["translator"] = "Simon Ockley"
    html = alignment_review.render_page([record], {"work_title": "T", "stats": {}})
    assert "Simon Ockley" in html
    assert "Hitti 1916" not in html
