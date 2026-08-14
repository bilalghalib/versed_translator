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


def test_render_markdown_states_the_score_scale_when_known():
    """A MetricX matrix and a COMETKiwi matrix look identical on paper. The
    scale note is the only thing stopping a reader comparing the two."""
    summary = dm.summarize([dm.ScoredPair("a", "i", "OMISSION", "major", 1.0, 0.5)])
    summary["qe_model"] = "google/metricx-24-hybrid-large-v2p6"
    summary["score_note"] = "NEGATED MetricX error score"
    md = dm.render_markdown(summary)
    assert "metricx-24-hybrid-large" in md
    assert "NEGATED" in md


# --------------------------------------------------------------------------
# MetricX polarity. MetricX emits an ERROR score (0-25, lower is better);
# `load_metricx` negates it so the higher-is-better contract holds. If that
# negation is ever dropped — or applied twice — every delta flips sign and the
# study reports a ~0% detection rate that looks like a real finding about the
# model rather than a bug in this file. These tests pin the sign.
# --------------------------------------------------------------------------


def _metricx_like_scorer():
    """Stub standing in for the raw model: returns MetricX-style ERROR scores,
    high for corrupted text. Wrapped exactly as `load_metricx` wraps the real
    model, so the negation under test is the real one in spirit."""

    def raw(sources, hyps):
        return [1.2 if h.startswith("clean") else 9.7 for h in hyps]

    def negated(sources, hyps):
        return [-v for v in raw(sources, hyps)]

    return raw, negated


def test_metricx_negation_makes_corrupted_deltas_positive():
    pairs = [
        ("a", "src-a", _inj(original="clean-a", corrupted="corrupt-a")),
        ("b", "src-b", _inj(original="clean-b", corrupted="corrupt-b")),
    ]
    _raw, negated = _metricx_like_scorer()

    scored = dm.score_pairs(pairs, negated)
    for s in scored:
        assert s.clean_score == pytest.approx(-1.2)
        assert s.corrupted_score == pytest.approx(-9.7)
        # The whole point: a worse corruption yields a POSITIVE delta.
        assert s.delta == pytest.approx(8.5)

    out = dm.summarize(scored, threshold=dm.DEFAULT_THRESHOLDS["metricx"])
    assert out["by_injector"][0]["detection_rate"] == 1.0


def test_unnegated_metricx_scores_would_invert_detection():
    """Guard on the guard: feeding raw MetricX error scores straight into
    score_pairs produces negative deltas and 0% detection. This is the exact
    failure `load_metricx`'s negation prevents, asserted so nobody 'fixes'
    the sign back."""
    pairs = [("a", "src-a", _inj(original="clean-a", corrupted="corrupt-a"))]
    raw, _negated = _metricx_like_scorer()

    scored = dm.score_pairs(pairs, raw)
    assert scored[0].delta == pytest.approx(-8.5)
    out = dm.summarize(scored, threshold=dm.DEFAULT_THRESHOLDS["metricx"])
    assert out["overall_detection_rate"] == 0.0


def test_metricx_threshold_default_is_scale_adjusted():
    """0.02 on COMETKiwi's [0,1] must not be reused on MetricX's [0,25]."""
    assert dm.DEFAULT_THRESHOLDS["cometkiwi"] == 0.02
    assert dm.DEFAULT_THRESHOLDS["metricx"] == 0.5
    # Same fraction of each model's score range.
    assert dm.DEFAULT_THRESHOLDS["metricx"] / 25.0 == pytest.approx(
        dm.DEFAULT_THRESHOLDS["cometkiwi"] / 1.0
    )


def test_metricx_default_threshold_would_miss_cometkiwi_sized_deltas():
    """A delta of 0.02 MetricX points is noise, not a detection — the point
    of not sharing one threshold across scales."""
    scored = [dm.ScoredPair("a", "i", "OMISSION", "major", -1.00, -1.02)]
    out = dm.summarize(scored, threshold=dm.DEFAULT_THRESHOLDS["metricx"])
    assert out["overall_detection_rate"] == 0.0
    out_wrong = dm.summarize(scored, threshold=dm.DEFAULT_THRESHOLDS["cometkiwi"])
    assert out_wrong["overall_detection_rate"] == 1.0


def test_metricx_qe_input_matches_upstream_format():
    """Verbatim from metricx24/predict.py. No `reference:` marker in QE mode."""
    assert (
        dm.metricx_qe_input("مرحبا", "Hello")
        == "source: مرحبا candidate: Hello"
    )
    assert "reference:" not in dm.metricx_qe_input("a", "b")


class _StubTokenizer:
    """Minimal stand-in: one id per character, plus an EOS id of 1."""

    EOS = 1
    PAD = 0

    def __call__(self, texts, max_length, truncation, padding):
        assert truncation is True and padding is False
        ids = [[ord(c) for c in t][: max_length - 1] + [self.EOS] for t in texts]
        return {"input_ids": ids, "attention_mask": [[1] * len(r) for r in ids]}

    def pad(self, batch, return_tensors=None):
        width = max(len(r) for r in batch["input_ids"])
        return {
            "input_ids": [r + [self.PAD] * (width - len(r)) for r in batch["input_ids"]],
            "attention_mask": [
                r + [0] * (width - len(r)) for r in batch["attention_mask"]
            ],
        }


def test_metricx_encode_strips_eos_before_padding():
    """The EOS must go, and padding must not be what gets chopped instead."""
    out, n_trunc = dm.metricx_encode(
        _StubTokenizer(), ["ab", "abcd"], max_input_length=64
    )
    # "ab" -> [97,98] (EOS dropped) then padded to width 4 with PAD=0.
    assert out["input_ids"] == [[97, 98, 0, 0], [97, 98, 99, 100]]
    assert out["attention_mask"] == [[1, 1, 0, 0], [1, 1, 1, 1]]
    assert all(_StubTokenizer.EOS not in row for row in out["input_ids"])
    # Padding is real padding, not a truncated tail: the short row keeps all
    # its content tokens.
    assert out["input_ids"][0][:2] == [97, 98]
    assert n_trunc == 0


def test_metricx_encode_respects_max_input_length():
    out, n_trunc = dm.metricx_encode(
        _StubTokenizer(), ["abcdefghij"], max_input_length=5
    )
    assert len(out["input_ids"][0]) == 4  # 5 minus the dropped EOS
    assert n_trunc == 1
    assert dm.METRICX_MAX_INPUT_LENGTH == 1536  # upstream's documented cap


def test_metricx_encode_reports_truncation():
    """Truncation eats the candidate, not the source — silence here would
    hide scores that are not really QE scores at all."""
    _out, n_trunc = dm.metricx_encode(
        _StubTokenizer(), ["ab", "abcdefghijklmnop"], max_input_length=6
    )
    assert n_trunc == 1  # only the long one


def test_scorer_without_truncation_counters_is_still_accepted():
    """The engine contract is one plain callable. `load_cometkiwi` returns a
    closure with no counters, and the study runner must not require them."""
    plain = lambda s, h: [1.0] * len(h)
    assert getattr(plain, "truncated", None) is None
    scored = dm.score_pairs([("a", "s", _inj())], plain)
    assert len(scored) == 1


def test_qe_model_ids_cover_every_default_threshold():
    """The CLI dispatches on these keys; a backend without a threshold (or
    vice versa) means a KeyError at run time, after model load."""
    assert set(dm.QE_MODEL_IDS) == set(dm.DEFAULT_THRESHOLDS)
    assert dm.QE_MODEL_IDS["metricx"] == dm.DEFAULT_METRICX_MODEL
    assert dm.QE_MODEL_IDS["cometkiwi"] == dm.DEFAULT_QE_MODEL
