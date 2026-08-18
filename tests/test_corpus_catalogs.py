"""Tests for HathiTrust / Wikisource / OTF catalog parsers and Rasaif bibliography."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from versed_translator.corpus import catalogs, join as join_mod, translations

REPO = Path(__file__).resolve().parents[1]
RASAIF_SEED = REPO / "corpus" / "rasaif_works_seed.json"
SEED = REPO / "corpus" / "pd_translations_seed.json"

WORKS = [
    {
        "uri": "0429IbnTahirBaghdadi.FarqBaynaFiraq",
        "author": "Baghdadi",
        "title": "Farq Bayna Firaq",
    },
    {
        "uri": "0204IbnKalbi.Asnam",
        "author": "Ibn Kalbi",
        "title": "Asnam",
    },
    {
        "uri": "0456IbnHazm.TawqHamama",
        "author": "Ibn Hazm",
        "title": "Tawq Hamama",
    },
    {
        "uri": "0428IbnSina.QanunFiTibb",
        "author": "Ibn Sina",
        "title": "Qanun Fi Tibb",
    },
    {
        "uri": "0681IbnKhallikan.WafayatAcyan",
        "author": "Ibn Khallikan",
        "title": "Wafayat Acyan",
    },
]


def test_seelye_schisms_and_idols_and_dove_aliases():
    schisms = join_mod.join_hit(
        {
            "title": "Moslem Schisms and Sects",
            "authors": "Seelye, Kate Chambers",
            "source_id": "1",
        },
        WORKS,
    )
    assert schisms is not None
    assert schisms["uri"] == "0429IbnTahirBaghdadi.FarqBaynaFiraq"
    assert schisms["join_reason"] == "alias"

    idols = join_mod.join_hit(
        {"title": "The Book of Idols", "authors": "Faris, Nabih Amin", "source_id": "2"},
        WORKS,
    )
    assert idols is not None
    assert idols["uri"] == "0204IbnKalbi.Asnam"

    dove = join_mod.join_hit(
        {"title": "The Ring of the Dove", "authors": "Arberry", "source_id": "3"},
        WORKS,
    )
    assert dove is not None
    assert dove["uri"] == "0456IbnHazm.TawqHamama"


def test_parse_hathi_pdus_english_keyword_and_skip_in_copyright():
    pd_line = (
        "mdp.123\tallow\tpdus\tbib1\t\tsrc\t\t\t\t\t\t"
        "Moslem Schisms and Sects, (al-Fark bain al-firak)\t"
        "New York, Columbia, 1920\t\t\t0\t1920\tnyu\teng\tBK\t\t\t\t\topen\t"
        "Baghdadi; Seelye, Kate Chambers\n"
    )
    ic_line = (
        "mdp.999\tdeny\tic\tbib2\t\tsrc\t\t\t\t\t\t"
        "The Muqaddimah\tPrinceton, 1958\t\t\t0\t1958\tnju\teng\tBK\t\t\t\t\tgoogle\t"
        "Ibn Khaldun; Rosenthal, Franz\n"
    )
    french_line = (
        "mdp.888\tallow\tpd\tbib3\t\tsrc\t\t\t\t\t\t"
        "Les mil et une nuits\tParis, 1899\t\t\t0\t1899\tfr\tfre\tBK\t\t\t\t\topen\t"
        "Galland\n"
    )
    pd_row = catalogs.parse_hathi_line(pd_line)
    ic_row = catalogs.parse_hathi_line(ic_line)
    fr_row = catalogs.parse_hathi_line(french_line)
    assert pd_row is not None
    assert catalogs.hathi_row_is_candidate(pd_row)
    assert ic_row is not None
    assert not catalogs.hathi_row_is_candidate(ic_row)
    assert fr_row is not None
    assert not catalogs.hathi_row_is_candidate(fr_row)
    hit = catalogs.hathi_row_to_hit(pd_row)
    assert hit["source_id"] == "mdp.123"
    assert hit["year"] == "1920"


def test_iter_hathi_hits_from_tiny_tsv(tmp_path):
    tsv = tmp_path / "hathi.tsv"
    tsv.write_text(
        "htid\taccess\trights\tht_bib_key\tdescription\tsource\tsource_bib_num\toclc_num\t"
        "isbn\tissn\tlccn\ttitle\timprint\trights_reason_code\trights_timestamp\t"
        "us_gov_doc_flag\trights_date_used\tpub_place\tlang\tbib_fmt\tcollection_code\t"
        "content_provider_code\tresponsible_entity_code\tdigitization_agent_code\t"
        "access_profile_code\tauthor\n"
        "mdp.123\tallow\tpdus\tbib1\t\tsrc\t\t\t\t\t\t"
        "The Canon of Medicine of Avicenna\tLondon, 1930\t\t\t0\t1930\tenu\teng\t"
        "BK\t\t\t\t\topen\tGruner, O. Cameron\n"
        "mdp.ic\tdeny\tic\tbib2\t\tsrc\t\t\t\t\t\t"
        "The Canon of Medicine\tNew York, 1999\t\t\t0\t1999\tnyu\teng\t"
        "BK\t\t\t\t\tgoogle\tSomeone Modern\n"
    )
    hits = list(catalogs.iter_hathi_hits(tsv))
    assert len(hits) == 1
    assert hits[0]["source_id"] == "mdp.123"


def test_harvest_hathi_joins_without_stamping_public(tmp_path):
    db = tmp_path / "inventory.sqlite"
    translations.ensure_schema(db)
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO works (uri, priority_rank, author, title, meta_found) VALUES (?,?,?,?,1)",
        ("0428IbnSina.QanunFiTibb", 1, "Ibn Sina", "Qanun Fi Tibb"),
    )
    conn.commit()
    conn.close()
    tsv = tmp_path / "hathi.tsv"
    tsv.write_text(
        "mdp.123\tallow\tpdus\tbib1\t\tsrc\t\t\t\t\t\t"
        "The Canon of Medicine of Avicenna\tLondon, 1930\t\t\t0\t1930\tenu\teng\t"
        "BK\t\t\t\t\topen\tGruner\n"
    )
    report = catalogs.harvest_hathi(db, tsv)
    assert report["joined"] == 1
    conn = sqlite3.connect(db)
    policy, visibility, source = conn.execute(
        "SELECT usage_policy, visibility, source FROM translations"
    ).fetchone()
    conn.close()
    assert source == "hathitrust"
    assert policy == "unknown"
    assert visibility == "private_eval"


def test_parse_wikisource_skips_portals_and_categories():
    payload = {
        "query": {
            "categorymembers": [
                {"pageid": 1, "ns": 100, "title": "Portal:Arabic literature"},
                {"pageid": 2, "ns": 14, "title": "Category:Wikisource translations of works in Arabic"},
                {"pageid": 3, "ns": 0, "title": "The Ring of the Dove"},
                {"pageid": 4, "ns": 0, "title": "The Canon of Medicine"},
            ]
        }
    }
    hits = catalogs.parse_wikisource_category(payload)
    assert [h["title"] for h in hits] == ["The Ring of the Dove", "The Canon of Medicine"]


def test_harvest_otf_uses_otf_source(tmp_path):
    db = tmp_path / "inventory.sqlite"
    translations.ensure_schema(db)
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO works (uri, priority_rank, author, title, meta_found) VALUES (?,?,?,?,1)",
        ("0681IbnKhallikan.WafayatAcyan", 1, "Ibn Khallikan", "Wafayat Acyan"),
    )
    conn.commit()
    conn.close()

    def opener(_url: str) -> dict:
        return {
            "items": [
                {
                    "identifier": "ibnkhallikansbi00slangoog",
                    "title": "Ibn Khallikan's Biographical Dictionary",
                    "creator": "Oriental Translation Fund",
                    "date": "1842",
                }
            ],
            "cursor": None,
        }

    report = catalogs.harvest_otf(db, opener=opener)
    assert report["joined"] == 1
    conn = sqlite3.connect(db)
    source, policy = conn.execute("SELECT source, usage_policy FROM translations").fetchone()
    conn.close()
    assert source == "otf"
    assert policy == "unknown"


def test_load_rasaif_biblio_is_not_public_and_not_coverage(tmp_path):
    db = tmp_path / "inventory.sqlite"
    translations.ensure_schema(db)
    n = translations.load_rasaif_biblio(db, seed_path=RASAIF_SEED)
    expected = len(json.loads(RASAIF_SEED.read_text())["entries"])
    assert n == expected
    conn = sqlite3.connect(db)
    rows = conn.execute(
        "SELECT usage_policy, visibility, alignment_status, rights_status FROM translations WHERE source='rasaif_biblio'"
    ).fetchall()
    conn.close()
    assert rows
    for policy, visibility, status, rights in rows:
        assert policy == "unknown"
        assert visibility == "none"
        assert status == "bibliography_only"
        assert rights == "BIBLIOGRAPHY_ONLY_NO_TEXT"
        assert policy != "redistribute_ok"
    stats = translations.translation_stats(db)
    assert stats["public_wuquf"] == 0
    assert stats["unique_openiti_works"] == 0


def test_latest_hathi_full_picks_newest_monthly():
    listing = [
        {
            "filename": "hathi_full_20260701.txt.gz",
            "full": True,
            "created": "2026-07-01 08:06:43 -0400",
            "url": "https://example/old",
        },
        {
            "filename": "hathi_full_20260801.txt.gz",
            "full": True,
            "created": "2026-08-01 08:37:44 -0400",
            "url": "https://example/new",
        },
        {
            "filename": "hathi_upd_20260816.txt.gz",
            "full": False,
            "created": "2026-08-16 04:35:57 -0400",
            "url": "https://example/upd",
        },
    ]
    latest = catalogs.latest_hathi_full(listing)
    assert latest["url"] == "https://example/new"
