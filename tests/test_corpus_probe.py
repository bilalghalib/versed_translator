"""Offline tests for the sequential IA probe. No live HTTP."""

from __future__ import annotations

import json
from pathlib import Path

from versed_translator.corpus import probe


def test_skip_nights_and_quran_and_persian():
    assert probe.skip_reason("The Book of the Thousand Nights and One Night") == "skip_title:nights"
    assert probe.skip_reason("The Koran translated from the Arabic") == "skip_title:koran"
    assert probe.skip_reason("Customs and Manners of the Women of Persia") == "skip_title:women of persia"
    assert probe.skip_reason("Ibn Khallikan's Biographical Dictionary") == "skip_title:khallikan"
    assert probe.skip_reason("Kalila and Dimna, translated from the Arabic") is None
    assert probe.skip_reason(
        "The churches and monasteries of Egypt and some neighbouring countries"
    ) is None


def test_classify_fetch_pd_year_and_skip_restricted_reprint():
    have: set[str] = set()
    keep = probe.classify_item(
        title="History of the Mohammedan Dynasties in Spain, translated from the Arabic",
        source_id="spain-history-volume-1",
        year="1840",
        restricted=None,
        djvu_name="x_djvu.txt",
        djvu_size=2_000_000,
        have=have,
    )
    assert keep["decision"] == "fetch"
    have.add("spain-history-volume-1")
    again = probe.classify_item(
        title="History of the Mohammedan Dynasties in Spain, translated from the Arabic",
        source_id="spain-history-volume-1",
        year="1840",
        restricted=None,
        djvu_name="x_djvu.txt",
        djvu_size=2_000_000,
        have=have,
    )
    assert again["decision"] == "have"
    wall = probe.classify_item(
        title="A treatise on the Canon of medicine",
        source_id="treatiseoncanono0000avic",
        year="1970",
        restricted="true",
        djvu_name="x_djvu.txt",
        djvu_size=3_000_000,
        have=set(),
    )
    assert wall["decision"] == "skip"
    assert wall["reason"] == "access_restricted"
    late = probe.classify_item(
        title="Revival of Religious Learnings translated from the Arabic",
        source_id="karim",
        year="1993",
        restricted=None,
        djvu_name="x_djvu.txt",
        djvu_size=15_000_000,
        have=set(),
    )
    assert late["decision"] == "train_or_skip"


def test_probe_identifier_uses_injected_metadata():
    payload = {
        "metadata": {
            "title": "Continuation of the Experiences, translated from the original Arabic",
            "year": "1921",
            "possible-copyright-status": "NOT_IN_COPYRIGHT",
        },
        "files": [{"name": "eclipseofabbasid06ameduoft_djvu.txt", "size": "1087078"}],
    }

    def opener(url: str) -> dict:
        assert "eclipseofabbasid06ameduoft" in url
        return payload

    row = probe.probe_identifier(
        "eclipseofabbasid06ameduoft",
        have=set(),
        opener=opener,
    )
    assert row["decision"] == "fetch"
    assert row["djvu"] == "eclipseofabbasid06ameduoft_djvu.txt"


def test_run_probe_dry_writes_cache(tmp_path: Path):
    out = tmp_path / "probe_hits.json"
    scrape = {
        "response": {
            "docs": [
                {
                    "identifier": "kalilaanddimnao00almgoog",
                    "title": "Kalila and Dimna translated from the Arabic",
                    "year": "1819",
                }
            ]
        }
    }
    meta = {
        "metadata": {
            "title": "Kalila and Dimna translated from the Arabic",
            "year": "1819",
        },
        "files": [{"name": "kalila_djvu.txt", "size": "500000"}],
    }

    def scrape_opener(_url: str) -> dict:
        return scrape

    def meta_opener(url: str) -> dict:
        if "metadata" in url:
            return meta
        return scrape

    report = probe.run_probe(
        dest=out,
        db_path=tmp_path / "missing.sqlite",
        fetch=False,
        limit=5,
        opener=meta_opener,
        scrape_opener=scrape_opener,
    )
    assert out.exists()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["summary"]["probed"] >= 1
    assert report["summary"]["probed"] >= 1


def test_already_have_ids_includes_not_fetched(tmp_path: Path) -> None:
    pd_map = tmp_path / "pd.json"
    train_map = tmp_path / "train.json"
    pd_map.write_text(
        json.dumps(
            {
                "files": [{"id": "on_disk", "source_id": "have-id"}],
                "not_fetched": [
                    {
                        "id": "queued",
                        "source_id": "TheTable-talkOfAMesopotamianJudgePart2",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    train_map.write_text(json.dumps({"files": [], "not_fetched": []}), encoding="utf-8")
    have = probe.already_have_ids(pd_map, train_map)
    assert "have-id" in have
    assert "TheTable-talkOfAMesopotamianJudgePart2" in have
    assert "queued" in have
