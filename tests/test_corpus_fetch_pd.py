"""Tests for off-repo PD English fetches. No live HTTP."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from versed_translator.corpus import fetch_pd, translations

REPO = Path(__file__).resolve().parents[1]
MAP = REPO / "corpus" / "pd_english_files.json"
SEED = REPO / "corpus" / "pd_translations_seed.json"

BURTON_PG_IDS = {str(n) for n in range(3435, 3445)}


def test_file_map_has_seelye_tanukhi_payne_not_burton():
    files = fetch_pd.load_file_map(MAP)
    ids = {row["id"] for row in files}
    assert "seelye_1920_part1" in ids
    assert "margoliouth_nishwar_1922" in ids
    assert "payne_nights_v1" in ids
    assert "payne_nights_v7" in ids
    pg_ids = {row["source_id"] for row in files if row["kind"] == "gutenberg"}
    assert pg_ids.isdisjoint(BURTON_PG_IDS)
    assert "8655" in pg_ids
    assert "5245" in pg_ids
    assert "73140" in pg_ids
    assert "33109" in pg_ids
    assert "58186" in pg_ids
    assert "50457" in pg_ids
    assert "13086" not in pg_ids
    assert "34572" not in pg_ids
    assert "7440" in pg_ids
    assert "58977" in pg_ids
    assert "16955" not in pg_ids
    assert "2800" not in pg_ids
    assert "sale_quran_1734" in ids
    assert "sprenger_masudi_1841" in ids
    assert "field_ghazali_munqidh_1909" in ids
    assert "sachau_biruni_india_v1" in ids
    assert "margoliouth_maarri_letters_1898" in ids
    assert "pickthall_quran_1930" in ids
    assert "payne_tales_from_arabic_5245" in ids
    assert "nawab_ali_ghazali_ihya_1921" in ids
    assert "wortabet_arabian_wisdom_1916" in ids
    assert "gairdner_mishkat_1924" in ids
    assert "nicholson_tarjuman_1911" in ids
    assert "sefi_ibn_farid_khamriyya_1922" in ids
    assert "clouston_arabian_poetry_1881" in ids
    assert "eclipse_vol6" in ids
    assert "gayangos_vol1" in ids
    assert "gayangos_vol2" in ids
    assert "margoliouth_nishwar_part8" in ids
    assert "clerk_ilam_ennas_1873" in ids
    assert "renaudot_india_china_1733" in ids
    assert "evetts_churches_egypt_1895" in ids
    assert "muir_kindy_apology_1882" in ids
    assert "rosen_khwarizmi_algebra_1831" in ids
    assert "lestrange_palestine_1890" in ids
    assert "reynolds_yamini_1858" in ids
    assert "reynolds_temple_jerusalem_1836" in ids
    assert "salmon_ibn_iyas_1921" in ids
    assert "russell_qayrawani_1906" in ids
    assert "friedlaender_ibn_hazm_1909" in ids
    assert "lestrange_eastern_caliphate_1905" in ids
    assert "lestrange_baghdad_1900" in ids
    assert "lyall_amr_qamiah_1919" in ids
    assert "evetts_patriarchs_i_ii" in ids
    assert "evetts_patriarchs_iii_iv" in ids
    assert "quennell_marvels_india_1928" in ids
    assert "miller_bab_hadi_ashar_1928" in ids
    assert "lyall_abid_amir_1913" not in ids
    assert "margoliouth_nishwar_part2" not in ids
    for row in files:
        blob = json.dumps(row).lower()
        assert "mardrus" not in blob or row["id"].startswith("payne")
        assert "halkin" not in row.get("source_id", "")


def test_remote_url_ia_and_gutenberg():
    assert fetch_pd.remote_url(
        {
            "kind": "ia_djvu",
            "source_id": "moslemschismssec01alba",
            "remote_name": "moslemschismssec01alba_djvu.txt",
        }
    ) == "https://archive.org/download/moslemschismssec01alba/moslemschismssec01alba_djvu.txt"
    assert (
        fetch_pd.remote_url({"kind": "gutenberg", "source_id": "8655"})
        == "https://www.gutenberg.org/cache/epub/8655/pg8655.txt"
    )
    encoded = fetch_pd.remote_url(
        {
            "kind": "ia_djvu",
            "source_id": "item",
            "remote_name": "The Mu’allaqāt _djvu.txt",
        }
    )
    assert " " not in encoded.split("/")[-1]
    assert "%20" in encoded


def test_ia_download_500_falls_back_to_storage_node(tmp_path: Path):
    import io
    import urllib.error

    dest = tmp_path / "train"
    entry = {
        "id": "johnson_train",
        "kind": "ia_djvu",
        "source_id": "alsabalmuallaqat00johnrich",
        "remote_name": "alsabalmuallaqat00johnrich_djvu.txt",
        "local_name": "johnson.txt",
        "needles": ["johnson", "1893"],
        "reject": [],
    }

    def opener(url: str) -> bytes:
        if "/download/" in url or "/cors/" in url:
            raise urllib.error.HTTPError(
                url, 500, "Internal Server Error", hdrs=None, fp=io.BytesIO()
            )
        if "/metadata/" in url:
            return json.dumps(
                {"d1": "ia.example.test", "dir": "/4/items/alsabalmuallaqat00johnrich"}
            ).encode()
        if "ia.example.test" in url:
            return b"CAPT F.E. JOHNSON 1893 seven poems suspended\n"
        raise AssertionError(url)

    result = fetch_pd.fetch_one(entry, dest, opener=opener)
    assert result["status"] == "fetched"
    assert "ia.example.test" in result["url"]
    assert (dest / "johnson.txt").read_text().startswith("CAPT")


def test_ia_download_500_falls_back_to_cors(tmp_path: Path):
    import io
    import urllib.error

    dest = tmp_path / "pd"
    entry = {
        "id": "lyall_mufaddaliyat_1918",
        "kind": "ia_djvu",
        "source_id": "mufaddaliyatanth00mufauoft",
        "remote_name": "mufaddaliyatanth00mufauoft_djvu.txt",
        "local_name": "lyall.txt",
        "needles": ["mufaddaliyat", "lyall", "1918"],
        "reject": [],
    }

    def opener(url: str) -> bytes:
        if "/download/" in url:
            raise urllib.error.HTTPError(
                url, 500, "Internal Server Error", hdrs=None, fp=io.BytesIO()
            )
        if "/cors/" in url:
            return b"THE MUFADDALIYAT CHARLES JAMES LYALL 1918 translation and notes\n"
        raise AssertionError(url)

    result = fetch_pd.fetch_one(entry, dest, opener=opener)
    assert result["status"] == "fetched"
    assert "/cors/" in result["url"]
    assert "MUFADDALIYAT" in (dest / "lyall.txt").read_text()


def test_title_page_accepts_needles_and_rejects_burton_formula():
    entry = {
        "id": "payne_nights_v1",
        "needles": ["john payne", "one night"],
        "reject": ["plain and literal translation"],
    }
    fetch_pd.check_title_page(
        "The Book of the Thousand Nights and One Night\nTranslator: John Payne\n",
        entry,
    )
    with pytest.raises(fetch_pd.TitlePageError, match="reject"):
        fetch_pd.check_title_page(
            "A Plain and Literal Translation of the Arabian Nights Entertainments",
            entry,
        )
    with pytest.raises(fetch_pd.TitlePageError, match="missing"):
        fetch_pd.check_title_page("unrelated scan", entry)
    fetch_pd.check_title_page(
        "THOUSAND  NIGHTS  AND  ONE  NIGHT\nJOHN  PAYNE\n",
        entry,
    )


def test_fetch_all_skips_existing_and_writes_new(tmp_path: Path):
    dest = tmp_path / "pd-english"
    dest.mkdir()
    (dest / "already.txt").write_text(
        "Moslem Schisms and Sects Columbia 1920 Seelye Part I\n",
        encoding="utf-8",
    )
    map_path = tmp_path / "map.json"
    map_path.write_text(
        json.dumps(
            {
                "files": [
                    {
                        "id": "seelye_1920_part1",
                        "kind": "ia_djvu",
                        "source_id": "moslemschismssec01alba",
                        "remote_name": "moslemschismssec01alba_djvu.txt",
                        "local_name": "already.txt",
                        "needles": ["schisms", "1920", "seelye"],
                        "reject": ["halkin"],
                    },
                    {
                        "id": "payne_nights_v1",
                        "kind": "gutenberg",
                        "source_id": "8655",
                        "local_name": "payne_nights_pg8655.txt",
                        "needles": ["john payne", "one night"],
                        "reject": ["mardrus"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    def opener(url: str) -> bytes:
        assert "8655" in url
        return b"The Thousand Nights and One Night by John Payne\n"

    report = fetch_pd.fetch_all(dest, map_path=map_path, opener=opener)
    assert report["skipped"] == 1
    assert report["fetched"] == 1
    assert report["errors"] == []
    written = dest / "payne_nights_pg8655.txt"
    assert written.exists()
    assert "John Payne" in written.read_text(encoding="utf-8")
    manifest = json.loads(Path(report["manifest"]).read_text(encoding="utf-8"))
    statuses = {row["id"]: row["status"] for row in manifest["files"]}
    assert statuses["seelye_1920_part1"] == "skipped"
    assert statuses["payne_nights_v1"] == "fetched"


def test_fetch_one_does_not_keep_rejected_bytes(tmp_path: Path):
    entry = {
        "id": "not_payne",
        "kind": "gutenberg",
        "source_id": "3435",
        "local_name": "burton.txt",
        "needles": ["one night"],
        "reject": ["plain and literal translation"],
    }

    def opener(_url: str) -> bytes:
        return b"A Plain and Literal Translation of the Arabian Nights Entertainments"

    with pytest.raises(fetch_pd.TitlePageError):
        fetch_pd.fetch_one(entry, tmp_path, opener=opener)
    assert not (tmp_path / "burton.txt").exists()
    assert not (tmp_path / "burton.txt.part").exists()


def test_gayangos_needles_accept_otf_and_reject_johnson_reprint():
    vol2 = {
        "id": "gayangos_vol2",
        "needles": ["gayangos", "mohammedan", "vol. ii."],
        "reject": ["johnson reprint", "1964"],
    }
    fetch_pd.check_title_page(
        "PASCUAL DE GAYANGOS\nMOHAMMEDAN DYNASTIES IN SPAIN\nVOL. II.\nM.DCCC.XLIII.",
        vol2,
    )
    with pytest.raises(fetch_pd.TitlePageError):
        fetch_pd.check_title_page(
            "PASCUAL DE GAYANGOS\nMOHAMMEDAN DYNASTIES IN SPAIN\nVOL. II.\n"
            "JOHNSON REPRINT CORPORATION 1964",
            vol2,
        )
    vol1 = {
        "id": "gayangos_vol1",
        "needles": ["gayangos", "mohammedan", "vol. i."],
        "reject": ["johnson reprint", "1964"],
    }
    fetch_pd.check_title_page(
        "PASCUAL DE GAYANGOS\nMOHAMMEDAN DYNASTIES IN SPAIN\nVOL. I.\nM.DCCC.XL.",
        vol1,
    )
    with pytest.raises(fetch_pd.TitlePageError):
        fetch_pd.check_title_page(
            "PASCUAL DE GAYANGOS\nMOHAMMEDAN DYNASTIES IN SPAIN\nVOL. II.\nM.DCCC.XLIII.",
            vol1,
        )


def test_record_pd_files_links_without_changing_rights(tmp_path: Path):
    db = tmp_path / "inventory.sqlite"
    translations.ensure_schema(db)
    translations.load_pd_seed(db, seed_path=SEED)
    dest = tmp_path / "pd-english"
    dest.mkdir()
    (dest / "kalila.txt").write_text(
        "Kalila and Dimna translated by Wyndham Knatchbull 1819\n",
        encoding="utf-8",
    )
    (dest / "payne1.txt").write_text(
        "The Thousand Nights and One Night by John Payne volume I\n",
        encoding="utf-8",
    )
    map_path = tmp_path / "map.json"
    map_path.write_text(
        json.dumps(
            {
                "files": [
                    {
                        "id": "knatchbull_kalila_1819",
                        "openiti_uri": "0139IbnMuqaffac.KalilaWaDimna",
                        "match_title": "Kalila and Dimna, or The Fables of Bidpai",
                        "kind": "ia_djvu",
                        "source_id": "kalilaanddimnao00almgoog",
                        "local_name": "kalila.txt",
                        "needles": ["knatchbull", "kalila"],
                        "reject": ["keith-falconer"],
                    },
                    {
                        "id": "payne_nights_v1",
                        "openiti_uri": "1300Anonymous.AlfLaylaWaLayla",
                        "match_title": "Thousand Nights and One Night (Payne)",
                        "kind": "gutenberg",
                        "source_id": "8655",
                        "local_name": "payne1.txt",
                        "needles": ["john payne", "one night"],
                        "reject": ["mardrus"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    before = {
        row[0]: (row[1], row[2])
        for row in sqlite3.connect(db).execute(
            "SELECT id, usage_policy, visibility FROM translations WHERE source='pd_seed'"
        )
    }
    report = fetch_pd.record_pd_files(db, dest, map_path=map_path)
    assert report["recorded"] == 2
    assert report["missing"] == 0
    assert report["unmatched"] == 0
    conn = sqlite3.connect(db)
    after = {
        row[0]: (row[1], row[2])
        for row in conn.execute(
            "SELECT id, usage_policy, visibility FROM translations WHERE source='pd_seed'"
        )
    }
    assert after == before
    _kalila_tid, kalila_title = conn.execute(
        """
        SELECT t.id, t.work_english_title
        FROM translation_files f
        JOIN translations t ON t.id = f.translation_id
        WHERE f.edition_key = 'knatchbull_kalila_1819'
        """
    ).fetchone()
    assert "Keith-Falconer" not in kalila_title
    assert "Bidpai" in kalila_title
    payne_count = conn.execute(
        """
        SELECT COUNT(DISTINCT translation_id) FROM translation_files
        WHERE edition_key LIKE 'payne%'
        """
    ).fetchone()[0]
    conn.close()
    assert payne_count == 1
    stats = translations.translation_stats(db)
    assert stats["files_on_disk"] == 2
    assert stats["public_with_files"] >= 2


def test_record_files_does_not_wipe_other_buckets(tmp_path: Path):
    db = tmp_path / "inventory.sqlite"
    translations.ensure_schema(db)
    translations.load_pd_seed(db, seed_path=SEED)
    dest = tmp_path / "pd-english"
    dest.mkdir()
    (dest / "kalila.txt").write_text(
        "Kalila and Dimna translated by Wyndham Knatchbull 1819\n",
        encoding="utf-8",
    )
    pd_map = tmp_path / "pd.json"
    pd_map.write_text(
        json.dumps(
            {
                "files": [
                    {
                        "id": "knatchbull_kalila_1819",
                        "openiti_uri": "0139IbnMuqaffac.KalilaWaDimna",
                        "match_title": "Kalila and Dimna, or The Fables of Bidpai",
                        "kind": "ia_djvu",
                        "source_id": "kalilaanddimnao00almgoog",
                        "local_name": "kalila.txt",
                        "needles": ["knatchbull", "kalila"],
                        "reject": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    fetch_pd.record_pd_files(db, dest, map_path=pd_map)
    train_dest = tmp_path / "train-english"
    train_dest.mkdir()
    (train_dest / "ithra.pdf").write_bytes(
        b"%PDF-1.4\n1 0 obj\n<< /Title (Muallaqat) >>\nendobj\n"
    )
    translations.load_open_access(db)
    train_map = tmp_path / "train.json"
    train_map.write_text(
        json.dumps(
            {
                "files": [
                    {
                        "id": "ithra_muallaqat_millennials_2020",
                        "source": "open_access",
                        "kind": "http",
                        "url": "https://example.test/ithra.pdf",
                        "local_name": "ithra.pdf",
                        "needles": ["endobj"],
                        "reject": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    fetch_pd.record_train_files(db, train_dest, map_path=train_map)
    conn = sqlite3.connect(db)
    keys = {
        row[0]
        for row in conn.execute("SELECT edition_key FROM translation_files")
    }
    conn.close()
    assert keys == {"knatchbull_kalila_1819", "ithra_muallaqat_millennials_2020"}


def test_train_map_is_train_only_and_skips_scribd():
    payload = json.loads((REPO / "corpus" / "train_english_files.json").read_text())
    ids = {row["id"] for row in payload["files"]}
    by_id = {row["id"]: row for row in payload["files"]}
    assert "ithra_muallaqat_millennials_2020" in ids
    assert "qnl_jones_moallakat_1783" in ids
    assert "johnson_seven_poems_ams_1973_train" in ids
    assert "arberry_seven_odes_1957" in ids
    assert "ivry_kindi_metaphysics_1974" in ids
    assert "genequand_ibn_rushd_metaphysics_lam" in ids
    assert "watt_ghazali_faith_practice_1953" in ids
    assert "hourani_fasl_maqal" in ids
    assert "van_den_bergh_tahafut_tahafut" in ids
    assert "mahdi_farabi_plato_aristotle" in ids
    assert "abul_quasem_bidayat_hidaya" in ids
    assert "davis_iqtisad_2005" in ids
    assert "mccall_book_of_knowledge_1940" in ids
    assert "calverley_worship_1992" in ids
    assert "rosenthal_muqaddimah_hikma" in ids
    assert "shammas_maarij_1958" in ids
    assert "masumi_razi_akhlaq_1978" in ids
    assert "karim_ihya_1993_v1" in ids
    assert "karim_ihya_1993_v4" in ids
    assert by_id["karim_ihya_1993_v2"]["lookup_id"] == "karim_ihya_1993"
    assert "nahj_balagha_alislam_sermons" in ids
    assert "nahj_balagha_alislam_letters" in ids
    assert by_id["nahj_balagha_alislam_letters"]["lookup_id"] == "nahj_balagha_alislam"
    assert "sahifa_sajjadiyya_alislam" in ids
    assert "tabatabai_mizan_vol1_alislam" in ids
    assert "tabatabai_mizan_vol6_alislam" in ids
    assert by_id["tabatabai_mizan_vol2_alislam"]["lookup_id"] == "tabatabai_mizan_alislam"
    assert "lantern_path_alislam" in ids
    assert "tuhaf_uqul_alislam" in ids
    assert "ghurar_hikam_alislam" in ids
    assert "uyun_akhbar_ridha_vol1_alislam" in ids
    assert "khisal_alislam" in ids
    assert "kamal_al_din_vol1_alislam" in ids
    assert "shiite_creed_alislam" in ids
    assert "mufid_amali_alislam" in ids
    assert "mufid_tashih_ictiqadat_alislam" in ids
    assert "tusi_ghayba_alislam" in ids
    assert "tusi_tenets_alislam" in ids
    assert "numani_ghayba_alislam" in ids
    assert "saduq_essence_shia_faith_alislam" in ids
    assert "tabarsi_mishkat_anwar_alislam" in ids
    assert "askari_tafsir_alislam" in ids
    assert "hilli_kashf_yaqin_alislam" in ids
    assert "ibn_tawus_lohoof_alislam" in ids
    assert "ibn_qulawayh_kamil_ziyarat_alislam" in ids
    assert "shahid_thani_musakkin_fuad_alislam" in ids
    assert "shahid_thani_kashf_reeba_alislam" in ids
    assert "tabarsi_ilam_wara_beacons_alislam" in ids
    assert by_id["uyun_akhbar_ridha_vol2_alislam"]["lookup_id"] == "uyun_akhbar_ridha_alislam"
    assert by_id["kamal_al_din_vol2_alislam"]["lookup_id"] == "kamal_al_din_alislam"
    assert "arberry_ring_of_the_dove" in ids
    assert by_id["arberry_ring_of_the_dove"]["kind"] == "http"
    assert by_id["arberry_seven_odes_1957"]["kind"] == "http"
    assert by_id["watt_ghazali_faith_practice_1953"]["kind"] == "http"
    file_urls = " ".join(str(row.get("url") or "") for row in payload["files"]).lower()
    assert "scribd.com" not in file_urls
    assert "libgen" not in file_urls
    assert by_id["lal_english_series"]["kind"] == "local"
    assert by_id["faris_book_of_idols_1952"]["kind"] == "local"
    assert by_id["arberry_seven_odes_1957_ocr"]["lookup_id"] == "arberry_seven_odes_1957"
    for row in payload["files"]:
        assert "pd-english" not in row.get("local_name", "")


def test_local_drop_missing_is_not_an_error(tmp_path: Path):
    dest = tmp_path / "train"
    result = fetch_pd.fetch_one(
        {
            "id": "lal_english_series",
            "kind": "local",
            "local_name": "lal_english_drop.pdf",
            "needles": ["library of arabic literature"],
        },
        dest,
    )
    assert result["status"] == "missing"
    assert not (dest / "lal_english_drop.pdf").exists()


def test_lookup_id_maps_ocr_sidecar_to_open_access(tmp_path: Path):
    db = tmp_path / "inventory.sqlite"
    translations.ensure_schema(db)
    translations.load_open_access(db)
    dest = tmp_path / "train"
    dest.mkdir()
    (dest / "arberry_ocr.txt").write_text(
        "The Seven Odes translated by A. J. Arberry 1957\n",
        encoding="utf-8",
    )
    map_path = tmp_path / "train.json"
    map_path.write_text(
        json.dumps(
            {
                "files": [
                    {
                        "id": "arberry_seven_odes_1957_ocr",
                        "lookup_id": "arberry_seven_odes_1957",
                        "source": "open_access",
                        "local_name": "arberry_ocr.txt",
                        "kind": "local",
                        "needles": ["arberry", "seven odes"],
                        "reject": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    recorded = fetch_pd.record_train_files(db, dest, map_path=map_path)
    assert recorded["recorded"] == 1
    assert recorded["unmatched"] == 0
    conn = sqlite3.connect(db)
    row = conn.execute(
        """
        SELECT t.source_id, f.edition_key
        FROM translation_files f
        JOIN translations t ON t.id = f.translation_id
        WHERE f.edition_key = 'arberry_seven_odes_1957_ocr'
        """
    ).fetchone()
    conn.close()
    assert row == ("arberry_seven_odes_1957", "arberry_seven_odes_1957_ocr")


def test_http_remote_url_and_pdf_title_check():
    assert (
        fetch_pd.remote_url(
            {"kind": "http", "url": "https://example.test/book.pdf"}
        )
        == "https://example.test/book.pdf"
    )
    fetch_pd.check_title_page(
        fetch_pd._title_text(
            b"%PDF-1.4\nendobj\n",
            {"id": "ithra", "local_name": "x.pdf"},
        ),
        {"id": "ithra", "needles": ["endobj"], "reject": []},
    )
    fetch_pd._title_text(
        b"\n\n%PDF-1.4\n",
        {"id": "alislam", "local_name": "x.pdf"},
    )
    with pytest.raises(fetch_pd.TitlePageError, match="not a PDF"):
        fetch_pd._title_text(b"<html>nope</html>", {"id": "ithra", "local_name": "x.pdf"})


def test_file_map_skips_lee_and_burton():
    payload = json.loads(MAP.read_text(encoding="utf-8"))
    ids = {row["id"] for row in payload["files"]}
    assert "lee_battuta_1829" in ids
    assert "lyall_poetry_1930_reprint" in ids
    assert "jamil_ibn_rushd_1921" in ids
    assert "prendergast_hamadhani_1915" in ids
    assert "lyall_mufaddaliyat_1918" in ids
    assert "margoliouth_baydawi_1894" in ids
    assert "rodwell_quran_1861" in ids
    assert "hamilton_antar_1819" in ids
    assert all("3435" not in json.dumps(row) for row in payload["files"])


def test_file_map_keeps_1931_tanukhi_part2_in_train_not_pd():
    pd = json.loads(MAP.read_text(encoding="utf-8"))
    queued = {row["id"] for row in pd.get("not_fetched") or []}
    assert "margoliouth_nishwar_part2" not in queued
    assert "margoliouth_nishwar_part8" not in queued
    train = json.loads((REPO / "corpus" / "train_english_files.json").read_text(encoding="utf-8"))
    train_ids = {row["id"] for row in train["files"]}
    assert "margoliouth_nishwar_part2" in train_ids
    assert "margoliouth_nishwar_part8" not in train_ids


def test_lookup_pd_seed_keeps_tanukhi_parts_distinct(tmp_path: Path) -> None:
    db = tmp_path / "inventory.sqlite"
    translations.ensure_schema(db)
    translations.load_pd_seed(db, seed_path=SEED)
    conn = sqlite3.connect(db)
    first = fetch_pd.lookup_pd_seed_id(
        conn,
        {
            "openiti_uri": "0384MuhassinTanukhi.NishwarMuhadara",
            "match_title": "Table-Talk of a Mesopotamian Judge",
        },
    )
    part2 = fetch_pd.lookup_pd_seed_id(
        conn,
        {
            "openiti_uri": "0384MuhassinTanukhi.NishwarMuhadara",
            "match_title": "Table-Talk of a Mesopotamian Judge, Part 2",
        },
    )
    titles = {
        tid: conn.execute(
            "SELECT work_english_title FROM translations WHERE id=?", (tid,)
        ).fetchone()[0]
        for tid in (first, part2)
    }
    conn.close()
    assert first != part2
    assert "Part 2" not in titles[first]
    assert titles[part2].endswith("Part 2")
