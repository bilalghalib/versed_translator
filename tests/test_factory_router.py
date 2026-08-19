from pathlib import Path

from versed_translator.factory.glossary import (
    GlossaryEntry,
    glossary_contradictions,
    normalize_mined_rows,
    retrieve_for_passage,
    write_candidates_csv,
)
from versed_translator.factory.prepare import DISAGREEMENT_ITEM, select_audit_rows
from versed_translator.factory.router import (
    RouteDecision,
    cascade_after_lite,
    check_output,
    pick_accepted,
    pick_auto,
    source_route,
)
from versed_translator.factory.simulate import simulate


def _entry(**kwargs) -> GlossaryEntry:
    defaults = {
        "arabic": "الحلقة",
        "lemma": "",
        "en_should": "mail-armor",
        "en_wrong": "the ring",
        "kind": "term",
        "book": "baladhuri_hitti",
        "item_ids": "",
        "status": "candidate",
        "source_label": "t",
    }
    defaults.update(kwargs)
    return GlossaryEntry(**defaults)


def test_source_route_verse_goes_to_flash():
    assert source_route("verse").primary == "flash"
    assert source_route("history").primary == "flash_lite"
    assert source_route("saj_maqama").primary == "flash"


def test_nan_english_is_missing():
    assert "MISSING" in check_output("كتاب", "nan")
    assert "MISSING" in check_output("كتاب", "")


def test_pick_accepted_does_not_overwrite_good_lite():
    decision = RouteDecision(
        primary="flash_lite",
        reason="lite_check_fail_keep_both",
        escalate=True,
        keep_alternate=True,
        check_fails=["LENGTH"],
    )
    assert pick_accepted(decision, lite_ok=True, flash_ok=False) == "flash_lite"
    assert pick_accepted(decision, lite_ok=False, flash_ok=True) == "flash"


def test_pick_auto_keeps_lite_when_both_checks_fail():
    decision = RouteDecision(
        primary="flash_lite",
        reason="lite_check_fail_keep_both",
        escalate=True,
        keep_alternate=True,
        check_fails=["LENGTH"],
    )
    system, queue = pick_auto(decision, flash_check_fails=["LENGTH"])
    assert system == "flash_lite"
    assert queue == "human"


def test_pick_auto_ships_flash_only_when_flash_checks_clean():
    decision = RouteDecision(
        primary="flash_lite",
        reason="lite_check_fail_keep_both",
        escalate=True,
        keep_alternate=True,
        check_fails=["GLOSSARY_WRONG"],
    )
    system, queue = pick_auto(decision, flash_check_fails=[])
    assert system == "flash"
    assert queue == "auto"


def test_normalize_splits_pipes():
    entries = normalize_mined_rows(
        [
            {
                "kind": "entity",
                "arabic": "الكتيبة|سلالم",
                "en_should": "al-Katiba|Salalim",
                "en_wrong_examples": "battalion|ladders",
                "sources": "baladhuri_hitti",
                "item_ids": "x",
            }
        ]
    )
    assert {e.arabic for e in entries} == {"الكتيبة", "سلالم"}
    assert all(e.status == "candidate" for e in entries)
    assert all(e.train_eligible == "false" for e in entries)


def test_retrieve_only_terms_in_passage():
    entries = [
        _entry(),
        _entry(
            arabic="نجوم",
            en_should="installments",
            en_wrong="stars",
            book="miskawayh_eclipse",
        ),
    ]
    hits = retrieve_for_passage(entries, "وأخذ الحلقة والسلاح", book="baladhuri_hitti")
    assert [h.arabic for h in hits] == ["الحلقة"]
    bad = glossary_contradictions("he kept the ring and the weapon", hits)
    assert len(bad) == 1


def test_glossary_contradiction_ignores_leading_gloss_paren():
    hits = [
        _entry(
            arabic="المصرين",
            en_should="the two garrison cities (Kufa and Basra)",
            en_wrong="(gloss) Egypt and Syria | Egyptians",
        )
    ]
    assert glossary_contradictions(
        "he went between Egypt and Syria", hits
    )
    assert not glossary_contradictions(
        "he went between the two garrison cities", hits
    )


def test_cascade_glossary_fail_escalates_and_keeps_lite():
    glossary = [_entry()]
    decision = cascade_after_lite(
        "وأخذ الحلقة",
        "he took the ring",
        register_hint="history",
        book="baladhuri_hitti",
        glossary=glossary,
    )
    assert decision.escalate is True
    assert "GLOSSARY_WRONG" in decision.check_fails
    assert decision.keep_alternate is True


def test_write_candidates_roundtrip(tmp_path: Path):
    path = tmp_path / "g.csv"
    entries = normalize_mined_rows(
        [{"kind": "term", "arabic": "حلقة", "en_should": "mail", "sources": "b"}]
    )
    write_candidates_csv(path, entries)
    text = path.read_text(encoding="utf-8")
    assert "status" in text
    assert "candidate" in text


def test_audit_includes_disagreement():
    rows = [
        {
            "row_id": "a",
            "item_id": DISAGREEMENT_ITEM,
            "system_id": "flash_lite",
            "publishable": "Y",
            "blocking_flags": "OK",
        },
        {
            "row_id": "b",
            "item_id": DISAGREEMENT_ITEM,
            "system_id": "flash",
            "publishable": "N",
            "blocking_flags": "TERM",
        },
        {
            "row_id": "c",
            "item_id": "other",
            "system_id": "tg27b",
            "publishable": "N",
            "blocking_flags": "NUMBER",
        },
        {
            "row_id": "d",
            "item_id": "other",
            "system_id": "qwen",
            "publishable": "N",
            "blocking_flags": "ENTITY",
        },
    ]
    picked = select_audit_rows(rows, n=4)
    ids = {r["row_id"] for r in picked}
    assert "a" in ids and "b" in ids


def test_simulate_marks_oracle_and_does_not_train():
    rows = [
        {
            "item_id": "p1",
            "system_id": "flash_lite",
            "publishable": "Y",
            "register_hint": "history",
            "source": "baladhuri_hitti",
            "arabic": "كتاب",
            "translation": "a book",
        },
        {
            "item_id": "p1",
            "system_id": "flash",
            "publishable": "N",
            "register_hint": "history",
            "source": "baladhuri_hitti",
            "arabic": "كتاب",
            "translation": "a book",
        },
    ]
    report = simulate(rows, [])
    assert report["train_eligible"] is False
    assert report["label_quality"] == "silver_fable"
    assert report["policies"]["oracle_lite_else_flash"]["publishable"] == 1
    assert report["policies"]["all_lite"]["publishable"] == 1
    assert report["policies"]["all_flash"]["publishable"] == 0
