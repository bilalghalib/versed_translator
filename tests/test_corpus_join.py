"""Tests for joining English catalog hits onto OpenITI works."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from versed_translator.corpus import join as join_mod
from versed_translator.corpus import translations

SEED = Path(__file__).resolve().parents[1] / "corpus" / "pd_translations_seed.json"

WORKS = [
    {
        "uri": "0581IbnTufayl.HayyIbnYaqzan",
        "author": "Ibn Tufayl",
        "title": "Hayy Ibn Yaqzan",
    },
    {
        "uri": "0001TufaylGhanawi.Diwan",
        "author": "Tufayl Ghanawi",
        "title": "Diwan",
    },
    {
        "uri": "0001Quran.Mushaf",
        "author": "Quran",
        "title": "al-Qurān",
    },
    {
        "uri": "0197IbnWahbQurashi.TafsirQuran",
        "author": "Ibn Wahb Qurashi",
        "title": "Tafsir Quran",
    },
    {
        "uri": "0516IbnCaliHariri.Maqamat",
        "author": "Ibn Cali Hariri",
        "title": "Maqamat",
    },
    {
        "uri": "0279Baladhuri.FutuhBuldan",
        "author": "Baladhuri",
        "title": "Futuh Buldan",
    },
    {
        "uri": "1300Anonymous.AlfLaylaWaLayla",
        "author": "Anonymous",
        "title": "Alf Layla Wa Layla",
    },
]


def test_hayy_joins_ibn_tufayl_not_the_other_tufayl():
    hit = {
        "title": "The History of Hayy Ibn Yaqzan",
        "authors": "Ockley, Simon",
        "source_id": "16831",
    }
    match = join_mod.join_hit(hit, WORKS)
    assert match is not None
    assert match["uri"] == "0581IbnTufayl.HayyIbnYaqzan"


def test_othello_does_not_join():
    hit = {"title": "Othello", "authors": "Shakespeare, William", "source_id": "1531"}
    assert join_mod.join_hit(hit, WORKS) is None


def test_othello_does_not_join_a_modern_arabic_shakespeare_study():
    works = WORKS + [
        {
            "uri": "1383CabbasMahmudCaqqad.Shakespeare",
            "author": "Abbas Mahmud Aqqad",
            "title": "Shakespeare",
        }
    ]
    hit = {"title": "Othello", "authors": "Shakespeare, William", "source_id": "1531"}
    assert join_mod.join_hit(hit, works) is None


def test_arabian_society_essays_do_not_join_nights():
    hit = {
        "title": "Arabian Society in the Middle Ages: Studies From The Thousand and One Nights",
        "authors": "Lane, Edward William",
        "source_id": "41110",
    }
    assert join_mod.join_hit(hit, WORKS) is None


def test_koran_joins_mushaf_not_a_tafsir():
    hit = {
        "title": "The Koran (Al-Qur'an)",
        "authors": "Palmer, E. H.",
        "source_id": "2800",
    }
    match = join_mod.join_hit(hit, WORKS)
    assert match is not None
    assert match["uri"] == "0001Quran.Mushaf"


def test_nights_volume_joins_alf_layla():
    hit = {
        "title": "The Book of the Thousand Nights and a Night — Volume 01 (of 10)",
        "authors": "Burton, Richard Francis, Sir",
        "source_id": "3435",
    }
    match = join_mod.join_hit(hit, WORKS)
    assert match is not None
    assert match["uri"] == "1300Anonymous.AlfLaylaWaLayla"


def test_hariri_assemblies_join():
    hit = {
        "title": "The Assemblies of Al-Hariri",
        "authors": "Chenery, Thomas",
        "source_id": "999",
    }
    match = join_mod.join_hit(hit, WORKS)
    assert match is not None
    assert match["uri"] == "0516IbnCaliHariri.Maqamat"


def test_hamadhani_mufaddaliyat_baydawi_join():
    works = WORKS + [
        {
            "uri": "0398BadicZamanHamadhani.Maqamat",
            "author": "Hamadhani",
            "title": "Maqamat",
        },
        {
            "uri": "0168MufaddalDabbi.Mufaddaliyyat",
            "author": "Mufaddal Dabbi",
            "title": "Mufaddaliyyat",
        },
        {
            "uri": "0685NasirDinBaydawi.AnwarTanzil",
            "author": "Baydawi",
            "title": "Anwar Tanzil",
        },
    ]
    ham = join_mod.join_hit(
        {
            "title": "The Maqamat of Badi al-Zaman al-Hamadhani",
            "authors": "Prendergast, W. J.",
            "source_id": "1",
        },
        works,
    )
    assert ham is not None
    assert ham["uri"] == "0398BadicZamanHamadhani.Maqamat"
    muf = join_mod.join_hit(
        {
            "title": "The Mufaddaliyat an anthology of ancient Arabian odes",
            "authors": "Lyall, Charles James",
            "source_id": "2",
        },
        works,
    )
    assert muf is not None
    assert muf["uri"] == "0168MufaddalDabbi.Mufaddaliyyat"
    bay = join_mod.join_hit(
        {
            "title": "Chrestomathia Baidawiana commentary of El-Baidawi on Sura III",
            "authors": "Margoliouth, D. S.",
            "source_id": "3",
        },
        works,
    )
    assert bay is not None
    assert bay["uri"] == "0685NasirDinBaydawi.AnwarTanzil"
    hariri = join_mod.join_hit(
        {
            "title": "The Assemblies of Al-Hariri",
            "authors": "Chenery, Thomas",
            "source_id": "4",
        },
        works,
    )
    assert hariri["uri"] == "0516IbnCaliHariri.Maqamat"


def test_munqidh_india_masudi_join():
    works = WORKS + [
        {"uri": "0505Ghazali.Munqidh", "author": "Ghazali", "title": "Munqidh"},
        {
            "uri": "0440AbuRayhanBiruni.TahqiqMaLilHind",
            "author": "Biruni",
            "title": "Tahqiq Ma Lil Hind",
        },
        {
            "uri": "0440AbuRayhanBiruni.AtharBaqiya",
            "author": "Biruni",
            "title": "Athar Baqiya",
        },
        {
            "uri": "0346Mascudi.MurujDhahab",
            "author": "Masudi",
            "title": "Muruj Dhahab",
        },
    ]
    conf = join_mod.join_hit(
        {
            "title": "The Confessions of Al Ghazzali",
            "authors": "Field, Claud",
            "source_id": "1",
        },
        works,
    )
    assert conf is not None
    assert conf["uri"] == "0505Ghazali.Munqidh"
    india = join_mod.join_hit(
        {
            "title": "Alberuni's India volume 1",
            "authors": "Sachau, Edward",
            "source_id": "2",
        },
        works,
    )
    assert india is not None
    assert india["uri"] == "0440AbuRayhanBiruni.TahqiqMaLilHind"
    biruni_india = join_mod.join_hit(
        {
            "title": "Biruni's India volume 1",
            "authors": "Sachau, Edward",
            "source_id": "2b",
        },
        works,
    )
    assert biruni_india is not None
    assert biruni_india["uri"] == "0440AbuRayhanBiruni.TahqiqMaLilHind"
    masudi = join_mod.join_hit(
        {
            "title": "Meadows of Gold and Mines of Gems",
            "authors": "Sprenger, Aloys",
            "source_id": "3",
        },
        works,
    )
    assert masudi is not None
    assert masudi["uri"] == "0346Mascudi.MurujDhahab"


def test_load_joined_hits_are_unknown_not_public(tmp_path):
    db = tmp_path / "inventory.sqlite"
    translations.ensure_schema(db)
    conn = sqlite3.connect(db)
    conn.executemany(
        "INSERT INTO works (uri, priority_rank, meta_found) VALUES (?, ?, 1)",
        [(w["uri"], i, ) for i, w in enumerate(WORKS, start=1)],
    )
    conn.execute(
        "UPDATE works SET author = ?, title = ? WHERE uri = ?",
        ("Ibn Tufayl", "Hayy Ibn Yaqzan", "0581IbnTufayl.HayyIbnYaqzan"),
    )
    conn.commit()
    conn.close()

    hits = [
        {
            "title": "The History of Hayy Ibn Yaqzan",
            "authors": "Ockley, Simon",
            "source_id": "16831",
            "subjects": "Philosophy -- Islamic",
            "language": "en",
        },
        {
            "title": "Othello",
            "authors": "Shakespeare, William",
            "source_id": "1531",
            "subjects": "Tragedies",
            "language": "en",
        },
    ]
    report = join_mod.load_catalog_hits(
        db,
        hits,
        works=WORKS,
        source="gutenberg",
        url_for=lambda h: f"https://www.gutenberg.org/ebooks/{h['source_id']}",
    )
    assert report["joined"] == 1
    assert report["unmatched"] == 1

    conn = sqlite3.connect(db)
    rows = conn.execute(
        "SELECT openiti_uri, usage_policy, visibility, source FROM translations WHERE source='gutenberg'"
    ).fetchall()
    conn.close()
    assert len(rows) == 1
    uri, policy, visibility, source = rows[0]
    assert uri == "0581IbnTufayl.HayyIbnYaqzan"
    assert policy == "unknown"
    assert visibility == "private_eval"
    assert source == "gutenberg"


def test_token_joins_are_quarantined(tmp_path):
    db = tmp_path / "inventory.sqlite"
    translations.ensure_schema(db)
    hits = [
        {
            "title": "Notes on Yaqzan",
            "authors": "Smith",
            "source_id": "1",
            "subjects": "",
            "language": "en",
        }
    ]
    join_mod.load_catalog_hits(
        db,
        hits,
        works=WORKS,
        source="gutenberg",
        url_for=lambda h: h["source_id"],
    )
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT usage_policy, visibility, confidence FROM translations WHERE source='gutenberg'"
    ).fetchone()
    conn.close()
    assert row is not None
    policy, visibility, confidence = row
    assert confidence == "tokens"
    assert policy == "quarantine"
    assert visibility == "none"


def test_mark_duplicates_of_pd_seed(tmp_path):
    db = tmp_path / "inventory.sqlite"
    translations.ensure_schema(db)
    translations.load_pd_seed(db, seed_path=SEED)
    conn = sqlite3.connect(db)
    translations._insert_translation(
        conn,
        translations._blank_row(
            openiti_uri="0279Baladhuri.FutuhBuldan",
            work_english_title="The origins of the Islamic state (IA scan)",
            source="archive_org",
            usage_policy="unknown",
            visibility="private_eval",
            rights_status="CATALOG_CANDIDATE_UNVERIFIED",
            confidence="alias",
        ),
    )
    conn.commit()
    conn.close()
    n = join_mod.mark_pd_seed_duplicates(db)
    assert n == 1
    conn = sqlite3.connect(db)
    status = conn.execute(
        "SELECT alignment_status FROM translations WHERE source='archive_org'"
    ).fetchone()[0]
    conn.close()
    assert status == "duplicate_pd_seed"


def test_suyuti_jarrett_and_biruni_aliases():
    works = WORKS + [
        {
            "uri": "0911Suyuti.TarikhKhulafa",
            "author": "Suyuti",
            "title": "Tarikh Khulafa",
        },
        {
            "uri": "0440AbuRayhanBiruni.AtharBaqiya",
            "author": "Biruni",
            "title": "Athar Baqiya",
        },
        {
            "uri": "0584IbnMunqidhShayzari.Ictibar",
            "author": "Usama",
            "title": "Ictibar",
        },
    ]
    caliphs = join_mod.join_hit(
        {"title": "History of the Caliphs", "authors": "Jarrett, H. S.", "source_id": "1"},
        works,
    )
    assert caliphs is not None
    assert caliphs["uri"] == "0911Suyuti.TarikhKhulafa"
    biruni = join_mod.join_hit(
        {
            "title": "The Chronology of Ancient Nations",
            "authors": "Sachau, C. Edward; al-Biruni",
            "source_id": "2",
        },
        works,
    )
    assert biruni is not None
    assert biruni["uri"] == "0440AbuRayhanBiruni.AtharBaqiya"
    usama = join_mod.join_hit(
        {
            "title": "An Arab-Syrian Gentleman and Warrior",
            "authors": "Hitti, Philip K.",
            "source_id": "3",
        },
        works,
    )
    assert usama is not None
    assert usama["uri"] == "0584IbnMunqidhShayzari.Ictibar"
    mishkat = join_mod.join_hit(
        {
            "title": "The Niche for Lights",
            "authors": "Gairdner, W. H. T.; al-Ghazali",
            "source_id": "4",
        },
        works
        + [
            {
                "uri": "0505Ghazali.MishkatAnwar",
                "author": "Ghazali",
                "title": "Mishkat Anwar",
            }
        ],
    )
    assert mishkat is not None
    assert mishkat["uri"] == "0505Ghazali.MishkatAnwar"
    year, status = join_mod.year_from_ia_metadata(
        {
            "metadata": {
                "year": "1916",
                "possible-copyright-status": "NOT_IN_COPYRIGHT",
            }
        }
    )
    assert year == "1916"
    assert status == "NOT_IN_COPYRIGHT"


def test_parse_archive_scrape_page():
    payload = {
        "items": [
            {
                "identifier": "originsofislamic01albauoft",
                "title": "The origins of the Islamic state",
                "creator": "Ahmad ibn Yahya al-Baladhuri",
                "date": "1916",
            }
        ],
        "count": 1,
        "cursor": None,
        "total": 1,
    }
    hits, cursor = join_mod.parse_archive_scrape(payload)
    assert cursor is None
    assert len(hits) == 1
    assert hits[0]["source_id"] == "originsofislamic01albauoft"
    assert "origins of the islamic state" in hits[0]["title"].lower()


def test_gayangos_joins_nafh_tib_not_lane_poole():
    works = WORKS + [
        {
            "uri": "1041Maqqari.NafhTib",
            "author": "Maqqari",
            "title": "Nafh Tib",
        }
    ]
    hit = join_mod.join_hit(
        {
            "title": "The History of the Mohammedan Dynasties in Spain",
            "authors": "Gayangos, Pascual de; al-Maqqari",
            "source_id": "spain-history-volume-1",
        },
        works,
    )
    assert hit is not None
    assert hit["uri"] == "1041Maqqari.NafhTib"
    lane = join_mod.join_hit(
        {
            "title": "The Mohammedan dynasties: chronological and genealogical tables",
            "authors": "Lane-Poole, Stanley",
            "source_id": "mohammedandynast00lane",
        },
        works,
    )
    assert lane is None


def test_renaudot_joins_sirafi_rihla():
    works = WORKS + [
        {
            "uri": "0330AbuZaydSirafi.Rihla",
            "author": "Abu Zayd al-Sirafi",
            "title": "Rihla",
        }
    ]
    hit = join_mod.join_hit(
        {
            "title": "Ancient Accounts of India and China by Two Mohammedan Travellers",
            "authors": "Renaudot, Eusebius",
            "source_id": "india.history.resource.71973",
        },
        works,
    )
    assert hit is not None
    assert hit["uri"] == "0330AbuZaydSirafi.Rihla"


def test_marvels_of_india_joins_buzurg():
    works = WORKS + [
        {
            "uri": "0350BuzurgIbnShahriyarRamhurmuzi.CajaibHind",
            "author": "Buzurg Ibn Shahriyar",
            "title": "Cajaib Hind",
        }
    ]
    hit = join_mod.join_hit(
        {
            "title": "The Book of the Marvels of India",
            "authors": "Quennell, Peter; Devic, L. Marcel",
            "source_id": "in.ernet.dli.2015.79621",
        },
        works,
    )
    assert hit is not None
    assert hit["uri"] == "0350BuzurgIbnShahriyarRamhurmuzi.CajaibHind"
