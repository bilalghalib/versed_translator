"""Detection-matrix mechanics, verified without loading a 2GB QE model.

The one bug that would silently invalidate the whole C4 study is a
clean/corrupted misalignment: if score i doesn't belong to pair i, every
delta is noise and the matrix looks like "QE detects nothing" (or worse,
plausibly-but-wrongly like it detects everything). These tests pin the
pairing with a stub scorer whose outputs are fully predictable.
"""

from __future__ import annotations

import pytest

from versed_translator.qe import detection_matrix as dm
from versed_translator.qe.injectors import Injection


def _inj(name="delete_negation", original="He did not pray.", corrupted="He did pray."):
    return Injection(name, "NEGATION", "critical", original, corrupted, "test")


def test_score_pairs_keeps_clean_and_corrupted_aligned():
    pairs = [
        ("a", "src-a", _inj(original="clean-a", corrupted="corrupt-a")),
        ("b", "src-b", _inj(original="clean-b", corrupted="corrupt-b")),
    ]

    # Stub scores each hypothesis by a marker so misalignment is detectable.
    def scorer(sources, hyps):
        return [1.0 if h.startswith("clean") else 0.5 for h in hyps]

    scored = dm.score_pairs(pairs, scorer)
    assert len(scored) == 2
    for s in scored:
        assert s.clean_score == 1.0
        assert s.corrupted_score == 0.5
        assert s.delta == pytest.approx(0.5)


def test_score_pairs_sends_source_twice_per_pair():
    """Both sides must be scored against the same source segment, or the
    delta is confounded by passage difficulty rather than by the error."""
    pairs = [("a", "SRC", _inj())]
    seen: dict[str, list[str]] = {}

    def scorer(sources, hyps):
        seen["sources"] = list(sources)
        seen["hyps"] = list(hyps)
        return [1.0, 0.4]

    dm.score_pairs(pairs, scorer)
    assert seen["sources"] == ["SRC", "SRC"]
    assert seen["hyps"] == ["He did not pray.", "He did pray."]


def test_score_pairs_rejects_wrong_score_count():
    """A scorer returning the wrong number of scores must fail loudly, not
    silently mispair clean and corrupted sides."""
    pairs = [("a", "src", _inj())]
    with pytest.raises(ValueError, match="misaligned"):
        dm.score_pairs(pairs, lambda s, h: [1.0])


def test_score_pairs_empty_input():
    assert dm.score_pairs([], lambda s, h: []) == []


def test_summarize_computes_detection_rate():
    scored = [
        dm.ScoredPair("a", "delete_negation", "NEGATION", "critical", 1.0, 0.5),   # delta .5
        dm.ScoredPair("b", "delete_negation", "NEGATION", "critical", 1.0, 0.99),  # delta .01
    ]
    out = dm.summarize(scored, threshold=0.02)
    row = out["by_injector"][0]
    assert row["n"] == 2
    assert row["detection_rate"] == 0.5  # only the 0.5 delta clears 0.02
    assert row["max_delta"] == pytest.approx(0.5)


def test_summarize_sorts_blind_spots_first():
    scored = [
        dm.ScoredPair("a", "good_detector", "OMISSION", "critical", 1.0, 0.2),
        dm.ScoredPair("b", "blind_spot", "REGISTER", "major", 1.0, 1.0),
    ]
    out = dm.summarize(scored, threshold=0.02)
    assert out["by_injector"][0]["injector"] == "blind_spot"


def test_summarize_handles_negative_delta():
    """A QE system can score a corruption *higher* than the clean text.
    That's a real (and alarming) result, not an error to swallow."""
    scored = [dm.ScoredPair("a", "x", "OMISSION", "major", 0.5, 0.9)]
    out = dm.summarize(scored, threshold=0.02)
    assert out["by_injector"][0]["mean_delta"] < 0
    assert out["by_injector"][0]["detection_rate"] == 0.0


def test_build_pairs_skips_items_without_translation():
    items = {"a": "arabic-a", "b": "arabic-b"}
    translations = {"a": "He did not pray. He left."}
    pairs = dm.build_pairs(items, translations)
    assert all(p[0] == "a" for p in pairs)
    assert pairs, "expected at least one applicable injection"


def test_build_pairs_is_deterministic():
    items = {"a": "arabic"}
    translations = {"a": 'He did not pray 2 rak\'ahs in 622 AH (2:255). He left.'}
    first = dm.build_pairs(items, translations, seed=3)
    second = dm.build_pairs(items, translations, seed=3)
    assert [(i, inj.injector, inj.corrupted) for i, _s, inj in first] == \
           [(i, inj.injector, inj.corrupted) for i, _s, inj in second]


def test_render_markdown_includes_every_row():
    scored = [
        dm.ScoredPair("a", "inj_one", "OMISSION", "critical", 1.0, 0.5),
        dm.ScoredPair("b", "inj_two", "NUMBER", "major", 1.0, 1.0),
    ]
    md = dm.render_markdown(dm.summarize(scored))
    assert "inj_one" in md and "inj_two" in md
    assert "delta" in md.lower()
