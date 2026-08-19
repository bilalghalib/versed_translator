"""Tests for the C6 translations table (works × English editions)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from versed_translator.corpus import inventory, translations

REPO = Path(__file__).resolve().parents[1]
SEED = REPO / "corpus" / "pd_translations_seed.json"
ATHAR_SEED = REPO / "corpus" / "athar_works_seed.json"


def _write_priority_list(tmp_path: Path, uris: list[str]) -> Path:
    p = tmp_path / "priority.txt"
    p.write_text("# header\n" + "\n".join(uris) + "\n")
    return p


def test_ensure_schema_creates_works_and_translations(tmp_path: Path) -> None:
    db = tmp_path / "inventory.sqlite"
    translations.ensure_schema(db)
    conn = sqlite3.connect(db)
    names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "works" in names
    assert "translations" in names
    assert "translation_files" in names


def test_load_pd_seed_inserts_one_row_per_entry(tmp_path: Path) -> None:
    db = tmp_path / "inventory.sqlite"
    translations.ensure_schema(db)
    n = translations.load_pd_seed(db, seed_path=SEED)
    expected = len(json.loads(SEED.read_text())["entries"])
    assert n == expected
    conn = sqlite3.connect(db)
    count = conn.execute("SELECT COUNT(*) FROM translations WHERE source='pd_seed'").fetchone()[0]
    conn.close()
    assert count == expected


def test_dropped_editions_are_not_redistribute_ok(tmp_path: Path) -> None:
    db = tmp_path / "inventory.sqlite"
    translations.ensure_schema(db)
    translations.load_pd_seed(db, seed_path=SEED)
    conn = sqlite3.connect(db)
    rows = conn.execute(
        """
        SELECT work_english_title, usage_policy, visibility
        FROM translations
        WHERE source='pd_seed'
          AND (
            work_english_title LIKE '%Mishkat-ul-Masabih%'
            OR work_english_title LIKE '%Life of Muhammad%'
            OR work_english_title LIKE '%Arabian Society%'
          )
        """
    ).fetchall()
    conn.close()
    assert rows, "expected dropped seed titles to be loaded so they stay documented"
    for _title, policy, visibility in rows:
        assert policy != "redistribute_ok"
        assert visibility != "public_wuquf"


def test_high_confidence_pd_seed_is_public(tmp_path: Path) -> None:
    db = tmp_path / "inventory.sqlite"
    translations.ensure_schema(db)
    translations.load_pd_seed(db, seed_path=SEED)
    conn = sqlite3.connect(db)
    row = conn.execute(
        """
        SELECT usage_policy, visibility, rights_status, openiti_uri
        FROM translations
        WHERE work_english_title LIKE '%Origins of the Islamic State%'
        """
    ).fetchone()
    conn.close()
    assert row is not None
    policy, visibility, rights, uri = row
    assert policy == "redistribute_ok"
    assert visibility == "public_wuquf"
    assert rights == "PD_US_PRE_1930_PUBLICATION"
    assert uri == "0279Baladhuri.FutuhBuldan"


def test_us_95_year_usama_1929_is_public(tmp_path: Path) -> None:
    db = tmp_path / "inventory.sqlite"
    translations.ensure_schema(db)
    translations.load_pd_seed(db, seed_path=SEED)
    conn = sqlite3.connect(db)
    row = conn.execute(
        """
        SELECT usage_policy, visibility, rights_status
        FROM translations
        WHERE source='pd_seed' AND work_english_title LIKE '%Arab-Syrian Gentleman%'
        """
    ).fetchone()
    conn.close()
    assert row is not None
    policy, visibility, rights = row
    assert policy == "redistribute_ok"
    assert visibility == "public_wuquf"
    assert rights == "PD_US_95_YEAR_TERM"


def test_gairdner_mishkat_1924_is_public(tmp_path: Path) -> None:
    db = tmp_path / "inventory.sqlite"
    translations.ensure_schema(db)
    translations.load_pd_seed(db, seed_path=SEED)
    conn = sqlite3.connect(db)
    row = conn.execute(
        """
        SELECT usage_policy, visibility, rights_status, openiti_uri
        FROM translations
        WHERE source='pd_seed' AND work_english_title = 'The Niche for Lights'
        """
    ).fetchone()
    conn.close()
    assert row is not None
    policy, visibility, rights, uri = row
    assert policy == "redistribute_ok"
    assert visibility == "public_wuquf"
    assert rights == "PD_US_PRE_1930_PUBLICATION"
    assert uri == "0505Ghazali.MishkatAnwar"


def test_nicholson_tarjuman_1911_is_public(tmp_path: Path) -> None:
    db = tmp_path / "inventory.sqlite"
    translations.ensure_schema(db)
    translations.load_pd_seed(db, seed_path=SEED)
    conn = sqlite3.connect(db)
    row = conn.execute(
        """
        SELECT usage_policy, visibility, rights_status, openiti_uri
        FROM translations
        WHERE source='pd_seed' AND work_english_title = 'The Tarjuman al-Ashwaq'
        """
    ).fetchone()
    conn.close()
    assert row is not None
    policy, visibility, rights, uri = row
    assert policy == "redistribute_ok"
    assert visibility == "public_wuquf"
    assert rights == "PD_US_PRE_1930_PUBLICATION"
    assert uri == "0638IbnCarabi.Diwan"


def test_sefi_khamriyya_1922_is_public(tmp_path: Path) -> None:
    db = tmp_path / "inventory.sqlite"
    translations.ensure_schema(db)
    translations.load_pd_seed(db, seed_path=SEED)
    conn = sqlite3.connect(db)
    row = conn.execute(
        """
        SELECT usage_policy, visibility, rights_status, openiti_uri
        FROM translations
        WHERE source='pd_seed' AND translator = 'A. Sefi'
        """
    ).fetchone()
    conn.close()
    assert row is not None
    policy, visibility, rights, uri = row
    assert policy == "redistribute_ok"
    assert visibility == "public_wuquf"
    assert rights == "PD_US_PRE_1930_PUBLICATION"
    assert uri == "0632SharafDinIbnFarid.Diwan"


def test_eclipse_vol6_continuation_is_not_miskawayh(tmp_path: Path) -> None:
    db = tmp_path / "inventory.sqlite"
    translations.ensure_schema(db)
    translations.load_pd_seed(db, seed_path=SEED)
    conn = sqlite3.connect(db)
    row = conn.execute(
        """
        SELECT usage_policy, visibility, rights_status, openiti_uri
        FROM translations
        WHERE source='pd_seed'
          AND work_english_title LIKE '%Continuation of the Experiences%'
        """
    ).fetchone()
    conn.close()
    assert row is not None
    policy, visibility, rights, uri = row
    assert policy == "redistribute_ok"
    assert visibility == "public_wuquf"
    assert rights == "PD_US_PRE_1930_PUBLICATION"
    assert uri in (None, "")


def test_gayangos_1840_is_public(tmp_path: Path) -> None:
    db = tmp_path / "inventory.sqlite"
    translations.ensure_schema(db)
    translations.load_pd_seed(db, seed_path=SEED)
    conn = sqlite3.connect(db)
    row = conn.execute(
        """
        SELECT usage_policy, visibility, rights_status, openiti_uri
        FROM translations
        WHERE source='pd_seed'
          AND work_english_title LIKE '%Mohammedan Dynasties in Spain%'
        """
    ).fetchone()
    conn.close()
    assert row is not None
    policy, visibility, rights, uri = row
    assert policy == "redistribute_ok"
    assert visibility == "public_wuquf"
    assert rights == "PD_US_PRE_1930_PUBLICATION"
    assert uri == "1041Maqqari.NafhTib"


def test_clouston_1881_is_public(tmp_path: Path) -> None:
    db = tmp_path / "inventory.sqlite"
    translations.ensure_schema(db)
    translations.load_pd_seed(db, seed_path=SEED)
    conn = sqlite3.connect(db)
    row = conn.execute(
        """
        SELECT usage_policy, visibility, rights_status
        FROM translations
        WHERE source='pd_seed' AND work_english_title LIKE '%Arabian Poetry for English Readers%'
        """
    ).fetchone()
    conn.close()
    assert row == ("redistribute_ok", "public_wuquf", "PD_US_PRE_1930_PUBLICATION")


def test_lyall_1930_reprint_is_public_95_year(tmp_path: Path) -> None:
    db = tmp_path / "inventory.sqlite"
    translations.ensure_schema(db)
    translations.load_pd_seed(db, seed_path=SEED)
    conn = sqlite3.connect(db)
    row = conn.execute(
        """
        SELECT usage_policy, visibility, rights_status
        FROM translations
        WHERE source='pd_seed' AND work_english_title LIKE '%Ancient Arabian Poetry%'
        """
    ).fetchone()
    conn.close()
    assert row is not None
    policy, visibility, rights = row
    assert policy == "redistribute_ok"
    assert visibility == "public_wuquf"
    assert rights == "PD_US_95_YEAR_TERM"


def test_pickthall_1930_is_public_95_year(tmp_path: Path) -> None:
    db = tmp_path / "inventory.sqlite"
    translations.ensure_schema(db)
    translations.load_pd_seed(db, seed_path=SEED)
    conn = sqlite3.connect(db)
    row = conn.execute(
        """
        SELECT usage_policy, visibility, rights_status
        FROM translations
        WHERE source='pd_seed' AND work_english_title LIKE '%Glorious Koran%'
        """
    ).fetchone()
    conn.close()
    assert row is not None
    policy, visibility, rights = row
    assert policy == "redistribute_ok"
    assert visibility == "public_wuquf"
    assert rights == "PD_US_95_YEAR_TERM"


def test_seelye_and_jarrett_are_public(tmp_path: Path) -> None:
    db = tmp_path / "inventory.sqlite"
    translations.ensure_schema(db)
    translations.load_pd_seed(db, seed_path=SEED)
    conn = sqlite3.connect(db)
    seelye = conn.execute(
        "SELECT visibility FROM translations WHERE work_english_title LIKE '%Moslem Schisms%'"
    ).fetchone()
    jarrett = conn.execute(
        "SELECT visibility FROM translations WHERE work_english_title LIKE '%History of the Caliphs%'"
    ).fetchone()
    conn.close()
    assert seelye[0] == "public_wuquf"
    assert jarrett[0] == "public_wuquf"


def test_ibn_rushd_jamil_1921_is_public(tmp_path: Path) -> None:
    db = tmp_path / "inventory.sqlite"
    translations.ensure_schema(db)
    translations.load_pd_seed(db, seed_path=SEED)
    conn = sqlite3.connect(db)
    row = conn.execute(
        """
        SELECT usage_policy, visibility, rights_status, openiti_uri
        FROM translations
        WHERE source='pd_seed' AND work_english_title LIKE '%Averroes%'
        """
    ).fetchone()
    conn.close()
    assert row is not None
    policy, visibility, rights, uri = row
    assert policy == "redistribute_ok"
    assert visibility == "public_wuquf"
    assert rights == "PD_US_PRE_1930_PUBLICATION"
    assert uri == "0595IbnRushdHafid.FaslMaqal"


def test_johnson_1893_stays_unverified_until_title_page(tmp_path: Path) -> None:
    db = tmp_path / "inventory.sqlite"
    translations.ensure_schema(db)
    translations.load_pd_seed(db, seed_path=SEED)
    conn = sqlite3.connect(db)
    row = conn.execute(
        """
        SELECT usage_policy, visibility, confidence
        FROM translations
        WHERE source='pd_seed' AND work_english_title LIKE '%Seven Poems Suspended%'
        """
    ).fetchone()
    conn.close()
    assert row is not None
    policy, visibility, confidence = row
    assert confidence == "medium"
    assert policy != "redistribute_ok"
    assert visibility != "public_wuquf"


def test_open_access_ithra_is_train_ok_not_public(tmp_path: Path) -> None:
    db = tmp_path / "inventory.sqlite"
    translations.ensure_schema(db)
    n = translations.load_open_access(db)
    expected = len(json.loads(translations.DEFAULT_OPEN_ACCESS_SEED.read_text())["entries"])
    assert n == expected
    conn = sqlite3.connect(db)
    rows = conn.execute(
        """
        SELECT source_id, usage_policy, visibility, rights_status, alignment_status
        FROM translations WHERE source='open_access'
        """
    ).fetchall()
    stats = translations.translation_stats(db)
    conn.close()
    by_id = {row[0]: row[1:] for row in rows}
    ithra = by_id["ithra_muallaqat_millennials_2020"]
    assert ithra[0] == "train_ok"
    assert ithra[1] == "private_train"
    assert ithra[2] == "OPEN_ACCESS_ALL_RIGHTS_RESERVED"
    assert ithra[3] == "bibliography_only"
    assert by_id["lal_english_series"][0] == "train_ok"
    assert by_id["arberry_seven_odes_1957"][0] == "train_ok"
    assert by_id["arberry_ring_of_the_dove"][0] == "train_ok"
    assert by_id["faris_book_of_idols_1952"][0] == "train_ok"
    assert by_id["ivry_kindi_metaphysics_1974"][0] == "train_ok"
    assert by_id["watt_ghazali_faith_practice_1953"][0] == "train_ok"
    assert by_id["watt_ghazali_faith_practice_1953"][1] == "private_train"
    assert by_id["karim_ihya_1993"][0] == "train_ok"
    assert by_id["karim_ihya_1993"][1] == "private_train"
    assert by_id["nahj_balagha_alislam"][0] == "train_ok"
    assert by_id["nahj_balagha_alislam"][1] == "private_train"
    assert by_id["sahifa_sajjadiyya_alislam"][0] == "train_ok"
    assert by_id["tabatabai_mizan_alislam"][0] == "train_ok"
    assert by_id["lantern_path_alislam"][0] == "train_ok"
    assert by_id["tuhaf_uqul_alislam"][0] == "train_ok"
    assert by_id["ghurar_hikam_alislam"][0] == "train_ok"
    assert by_id["uyun_akhbar_ridha_alislam"][0] == "train_ok"
    assert by_id["khisal_alislam"][0] == "train_ok"
    assert by_id["kamal_al_din_alislam"][0] == "train_ok"
    assert by_id["shiite_creed_alislam"][0] == "train_ok"
    assert by_id["mufid_amali_alislam"][0] == "train_ok"
    assert by_id["mufid_tashih_ictiqadat_alislam"][0] == "train_ok"
    assert by_id["tusi_ghayba_alislam"][0] == "train_ok"
    assert by_id["tusi_tenets_alislam"][0] == "train_ok"
    assert by_id["numani_ghayba_alislam"][0] == "train_ok"
    assert by_id["saduq_essence_shia_faith_alislam"][0] == "train_ok"
    assert by_id["tabarsi_mishkat_anwar_alislam"][0] == "train_ok"
    assert by_id["askari_tafsir_alislam"][0] == "train_ok"
    assert by_id["hilli_kashf_yaqin_alislam"][0] == "train_ok"
    assert by_id["ibn_tawus_lohoof_alislam"][0] == "train_ok"
    assert by_id["ibn_qulawayh_kamil_ziyarat_alislam"][0] == "train_ok"
    assert by_id["shahid_thani_musakkin_fuad_alislam"][0] == "train_ok"
    assert by_id["shahid_thani_kashf_reeba_alislam"][0] == "train_ok"
    assert by_id["tabarsi_ilam_wara_beacons_alislam"][0] == "train_ok"
    jones = by_id["qnl_jones_moallakat_1783"]
    assert jones[0] == "train_ok"
    assert jones[1] != "public_wuquf"
    assert stats["public_wuquf"] == 0
    assert stats["train_ok"] == expected


def test_open_access_all_rights_reserved_cannot_be_stamped_public() -> None:
    policy, visibility, rights = translations.classify_open_access_entry(
        {
            "reuse_class": "redistribute",
            "rights_status": "OPEN_ACCESS_ALL_RIGHTS_RESERVED",
            "confidence": "high",
        }
    )
    assert policy == "train_ok"
    assert visibility == "private_train"
    assert rights == "OPEN_ACCESS_ALL_RIGHTS_RESERVED"
    policy, visibility, _ = translations.classify_open_access_entry(
        {
            "reuse_class": "redistribute",
            "rights_status": "CC_BY",
            "confidence": "high",
        }
    )
    assert policy == "redistribute_ok"
    assert visibility == "public_wuquf"


def test_athar_works_are_eval_internal(tmp_path: Path) -> None:
    db = tmp_path / "inventory.sqlite"
    translations.ensure_schema(db)
    n = translations.load_athar_works(db, seed_path=ATHAR_SEED)
    assert n == 18
    conn = sqlite3.connect(db)
    policies = {
        row[0]
        for row in conn.execute("SELECT DISTINCT usage_policy FROM translations WHERE source='athar'")
    }
    vis = {
        row[0]
        for row in conn.execute("SELECT DISTINCT visibility FROM translations WHERE source='athar'")
    }
    conn.close()
    assert policies == {"eval_internal"}
    assert vis == {"private_eval"}


def test_rebuild_works_preserves_translations(tmp_path: Path) -> None:
    meta_dir = tmp_path / "meta"
    meta_dir.mkdir()
    (meta_dir / "0505Ghazali.Tahafut.json").write_text(
        '{"uri": "0505Ghazali.Tahafut", "title_en": "Tahafut", "author_en": "Ghazali"}'
    )
    db = tmp_path / "inventory.sqlite"
    translations.ensure_schema(db)
    translations.load_athar_works(db, seed_path=ATHAR_SEED)
    before = sqlite3.connect(db).execute("SELECT COUNT(*) FROM translations").fetchone()[0]

    inventory.build_inventory(
        priority_list_path=_write_priority_list(tmp_path, ["0505Ghazali.Tahafut"]),
        db_path=db,
        openiti_dir=tmp_path,
        limit=10,
    )
    conn = sqlite3.connect(db)
    after = conn.execute("SELECT COUNT(*) FROM translations").fetchone()[0]
    works = conn.execute("SELECT COUNT(*) FROM works").fetchone()[0]
    conn.close()
    assert after == before
    assert works == 1


def test_gutenberg_keyword_filter_on_tiny_csv(tmp_path: Path) -> None:
    csv_path = tmp_path / "pg_catalog.csv"
    csv_path.write_text(
        "Text#;Type;Issued;Title;Language;Authors;Subjects;LoCC;Bookshelves\n"
        "16831;Text;2005;The History of Hayy Ibn Yaqzan;en;Ockley, Simon;Philosophy -- Islamic;B;Philosophy\n"
        "11;Text;2008;Alice in Wonderland;en;Carroll, Lewis;Fantasy;PR;Children's Literature\n"
        "1;Text;1971;The Declaration of Independence;en;Jefferson, Thomas;United States -- History;E;American History\n"
    )
    hits = translations.gutenberg_keyword_hits(csv_path)
    titles = {row["title"] for row in hits}
    assert "The History of Hayy Ibn Yaqzan" in titles
    assert "Alice in Wonderland" not in titles


def test_queued_tanukhi_part2_1931_is_not_public(tmp_path: Path) -> None:
    db = tmp_path / "inventory.sqlite"
    translations.ensure_schema(db)
    translations.load_pd_seed(db, seed_path=SEED)
    conn = sqlite3.connect(db)
    row = conn.execute(
        """
        SELECT usage_policy, visibility, confidence, publication_year
        FROM translations
        WHERE source='pd_seed'
          AND work_english_title = 'The Table-Talk of a Mesopotamian Judge, Part 2'
        """
    ).fetchone()
    conn.close()
    assert row is not None
    policy, visibility, confidence, year = row
    assert policy != "redistribute_ok"
    assert visibility != "public_wuquf"
    assert confidence == "medium"
    assert year == "1931"


def test_tanukhi_part8_1929_clerk_renaudot_evetts_are_public(tmp_path: Path) -> None:
    db = tmp_path / "inventory.sqlite"
    translations.ensure_schema(db)
    translations.load_pd_seed(db, seed_path=SEED)
    conn = sqlite3.connect(db)
    titles = [
        "%Table-Talk of a Mesopotamian Judge, Part 8%",
        "%Ilam-en-Nas%",
        "%Ancient Accounts of India and China%",
        "%Churches and Monasteries of Egypt%",
        "%Apology of Al Kindy%",
        "%Algebra of Mohammed ben Musa%",
        "%Palestine under the Moslems%",
        "%Kitab-i-Yamini%",
        "%History of the Temple of Jerusalem%",
        "%Ottoman Conquest of Egypt%",
        "%First Steps in Muslim Jurisprudence%",
        "%Heterodoxies of the Shiites%",
        "%Lands of the Eastern Caliphate%",
        "%Baghdad during the Abbasid Caliphate%",
        "%Poems of 'Amr son of Qami'ah%",
        "%Patriarchs of the Coptic Church of Alexandria%",
        "%Marvels of India%",
        "%Al-Babu 'l-Hadi 'Ashar%",
    ]
    for like in titles:
        row = conn.execute(
            """
            SELECT work_english_title, usage_policy, visibility, rights_status
            FROM translations
            WHERE source='pd_seed' AND work_english_title LIKE ?
            """,
            (like,),
        ).fetchone()
        assert row is not None, like
        _title, policy, visibility, rights = row
        assert policy == "redistribute_ok", _title
        assert visibility == "public_wuquf"
        assert rights == "PD_US_PRE_1930_PUBLICATION"
    conn.close()


def test_van_dyck_and_rihani_are_public(tmp_path: Path) -> None:
    db = tmp_path / "inventory.sqlite"
    translations.ensure_schema(db)
    translations.load_pd_seed(db, seed_path=SEED)
    conn = sqlite3.connect(db)
    van = conn.execute(
        """
        SELECT usage_policy, visibility, rights_status, openiti_uri
        FROM translations
        WHERE source='pd_seed' AND work_english_title LIKE '%Compendium on the Soul%'
        """
    ).fetchone()
    rihani = conn.execute(
        """
        SELECT usage_policy, visibility, rights_status, openiti_uri
        FROM translations
        WHERE source='pd_seed' AND work_english_title LIKE '%Luzumiyat%'
        """
    ).fetchone()
    conn.close()
    assert van[:3] == ("redistribute_ok", "public_wuquf", "PD_US_PRE_1930_PUBLICATION")
    assert van[3] in (None, "")
    assert rihani[:3] == ("redistribute_ok", "public_wuquf", "PD_US_PRE_1930_PUBLICATION")
    assert rihani[3] in (None, "")


def test_login_walls_have_urls() -> None:
    payload = json.loads((REPO / "corpus" / "login_walls.json").read_text(encoding="utf-8"))
    walls = payload["walls"]
    assert walls
    ids: set[str] = set()
    allowed = {"blocked", "fetched", "partial"}
    for wall in walls:
        wid = wall["id"]
        assert wid not in ids, wid
        ids.add(wid)
        url = wall["url"]
        assert url.startswith("http"), wid
        assert wall["status"] in allowed, wid
        assert wall["bucket"] in {"train-english", "pd-english"}, wid
        for extra in wall.get("urls") or []:
            assert extra.startswith("http"), extra
    assert "lal_english_nyu_press" in ids
    assert "hathi_gruner_canon_1930" in ids
    assert "dodge_fihrist_1970" in ids
    assert "broadhurst_ibn_jubayr_1952" in ids
    assert "arberry_ring_of_the_dove" in ids
