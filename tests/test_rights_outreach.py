"""Tests for the rights-holder outreach tracker."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from versed_translator.corpus import outreach

REPO = Path(__file__).resolve().parents[1]
SEED = REPO / "corpus" / "rights_outreach.json"


def test_outreach_seed_validates():
    payload = outreach.load_payload(SEED)
    assert payload["hosts"]
    keys = [row["id"] for row in payload["hosts"]]
    assert "ghazali.org" in keys
    assert "traditionalhikma.com" in keys
    assert "sacred-texts.com" in keys
    assert "al-islam.org" in keys
    seen = set()
    for entry in payload["entries"]:
        outreach.validate_entry(entry)
        assert entry["edition_key"] not in seen
        seen.add(entry["edition_key"])
    assert "lal_english_series" in seen
    assert "hourani_fasl_maqal" in seen
    assert "davis_iqtisad_2005" in seen
    assert "mccall_book_of_knowledge_1940" in seen
    assert "shammas_maarij_1958" in seen
    assert "karim_ihya_1993" in seen
    assert "nahj_balagha_alislam" in seen
    assert "sahifa_sajjadiyya_alislam" in seen
    assert "tabatabai_mizan_alislam" in seen
    assert "lantern_path_alislam" in seen
    assert "tuhaf_uqul_alislam" in seen
    assert "ghurar_hikam_alislam" in seen
    assert "uyun_akhbar_ridha_alislam" in seen
    assert "khisal_alislam" in seen
    assert "kamal_al_din_alislam" in seen
    assert "shiite_creed_alislam" in seen
    assert "mufid_amali_alislam" in seen
    assert "mufid_tashih_ictiqadat_alislam" in seen
    assert "tusi_ghayba_alislam" in seen
    assert "tusi_tenets_alislam" in seen
    assert "numani_ghayba_alislam" in seen
    assert "saduq_essence_shia_faith_alislam" in seen
    assert "tabarsi_mishkat_anwar_alislam" in seen
    assert "askari_tafsir_alislam" in seen
    assert "hilli_kashf_yaqin_alislam" in seen
    assert "ibn_tawus_lohoof_alislam" in seen
    assert "ibn_qulawayh_kamil_ziyarat_alislam" in seen
    assert "shahid_thani_musakkin_fuad_alislam" in seen
    assert "shahid_thani_kashf_reeba_alislam" in seen
    assert "tabarsi_ilam_wara_beacons_alislam" in seen
    farid = next(e for e in payload["entries"] if e["edition_key"] == "ibn_farid_khamriyya_th")
    assert farid["status"] == "n_a_already_pd"
    assert farid["translator"] == "A. Sefi"


def test_load_outreach_and_csv(tmp_path: Path):
    db = tmp_path / "inventory.sqlite"
    n = outreach.load_outreach(db, seed_path=SEED)
    expected = len(json.loads(SEED.read_text())["entries"])
    assert n == expected
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT status, priority, followup_count FROM rights_outreach WHERE edition_key='lal_english_series'"
    ).fetchone()
    conn.close()
    assert row == ("not_started", "high", 0)
    csv_path = outreach.write_csv(tmp_path / "out.csv", seed_path=SEED)
    text = csv_path.read_text(encoding="utf-8")
    header = text.splitlines()[0]
    for col in ("status", "next_followup_date", "followup_count", "ask_who"):
        assert col in header
    assert "Gibb Memorial Trust" in text


def test_granted_without_license_fails():
    with pytest.raises(ValueError, match="grant_license"):
        outreach.validate_entry(
            {
                "edition_key": "x",
                "priority": "high",
                "status": "granted_cc_by",
            }
        )
