
from versed_translator.factory.merge import (
    harvest_term_candidates,
    merge_rounds,
    verify_graded,
)


def _row(**kwargs) -> dict:
    base = {
        "row_id": "r1",
        "batch_id": "fable_r1",
        "item_id": "item-a",
        "source": "ockley_hayy",
        "genre": "philosophy",
        "band": "100-250",
        "register_hint": "philosophy",
        "system_id": "flash",
        "system_label": "Gemini Flash",
        "arabic": "كتاب",
        "translation": "a book",
        "error": "",
        "arabic_word_count": "1",
        "translation_word_count": "2",
        "length_ratio": "2",
        "publishable": "Y",
        "blocking_flags": "OK",
        "confidence": "high",
        "term_ar": "",
        "term_en_should": "",
        "term_en_wrong": "",
    }
    base.update(kwargs)
    return base


def test_verify_accepts_clean_sitting():
    sent = [_row()]
    graded = [_row()]
    report = verify_graded(sent, graded)
    assert report["ok"] is True
    assert report["n_source_mismatch"] == 0


def test_verify_nan_translation_matches_empty_sent():
    sent = [_row(translation="", system_id="flash")]
    graded = [_row(translation="nan", system_id="flash", publishable="N", blocking_flags="MISSING")]
    report = verify_graded(sent, graded)
    assert report["ok"] is True
    assert report["empty_outputs"]


def test_verify_rejects_source_edit_and_yn_mismatch():
    sent = [_row(arabic="كتاب")]
    graded = [_row(arabic="كتب", publishable="Y", blocking_flags="TERM")]
    report = verify_graded(sent, graded)
    assert report["ok"] is False
    assert report["n_source_mismatch"] == 1


def test_merge_concatenates_and_rejects_duplicate_ids():
    a = [_row(row_id="a")]
    b = [_row(row_id="b", item_id="item-b")]
    merged = merge_rounds(a, b)
    assert [r["row_id"] for r in merged] == ["a", "b"]


def test_harvest_term_candidates_skips_incomplete():
    rows = [
        _row(
            publishable="N",
            blocking_flags="TERM",
            term_ar="خلافة",
            term_en_should="deputyship",
            term_en_wrong="caliphate",
        ),
        _row(row_id="r2", publishable="N", blocking_flags="TERM", term_ar="", term_en_should="x"),
    ]
    entries = harvest_term_candidates(rows, source_label="fable_r1b")
    assert len(entries) == 1
    assert entries[0].arabic == "خلافة"
    assert entries[0].train_eligible == "false"
    assert entries[0].source_label == "fable_r1b"
