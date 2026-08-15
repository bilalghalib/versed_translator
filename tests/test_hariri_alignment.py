"""Synthetic tests for the Hariri/Chenery–Steingass maqama aligner.

Fixtures are invented tokens plus ASCII. No corpus text lives here.
"""

from __future__ import annotations

from pathlib import Path

from versed_translator.benchmark import hariri_alignment, pd_alignment
from versed_translator.benchmark.sources import hariri, openiti_markdown


class _FakeText:
    author_name = "PLACEHOLDER AUTHOR"
    author_died = 516
    book_subject = "كتب الأدب"


def test_parse_english_ordinal_reads_hyphenated_names():
    assert hariri.parse_english_ordinal("THE FIRST ASSEMBLY, CALLED") == 1
    assert hariri.parse_english_ordinal("THE TWENTY-SEVENTH ASSEMBLY") == 27
    assert hariri.parse_english_ordinal("THE FIFTIETH ASSEMBLY, CALLED") == 50


def test_strip_running_heads_drops_page_headers_not_body():
    text = (
        "Al Harith related.\nFIRST ASSEMBLY. 109\nHe went on.\n"
        "12 SECOND ASSEMBLY.\nFIRST ASSEMBLY. din\nEnd."
    )
    stripped = hariri.strip_running_heads(text)
    assert "FIRST ASSEMBLY. 109" not in stripped
    assert "12 SECOND ASSEMBLY." not in stripped
    assert "FIRST ASSEMBLY. din" not in stripped
    assert "Al Harith related." in stripped
    assert "He went on." in stripped


def test_drop_english_argument_keeps_from_harith_narration():
    body = (
        ', CALLED "OF SANA."\n\n'
        "In this Assembly Al Harith arrives in the town.\n\n"
        "Al Harith, son of Hammam, related: When I mounted the hump.\n"
    )
    kept = hariri.drop_english_argument(body)
    assert kept.startswith("Al Harith, son of Hammam, related")
    assert "In this Assembly" not in kept
    assert "CALLED" not in kept


def test_drop_english_argument_falls_back_when_harith_formula_is_missing():
    body = (
        ", CALLED\n“OF TIFLIS.”\n\n"
        "In this Assembly Abu Zayd presents himself as a mendicant.\n\n"
        "I had covenanted with Allah since I was of the age of about a score.\n"
    )
    kept = hariri.drop_english_argument(body)
    assert kept.startswith("I had covenanted")
    assert "In this Assembly" not in kept


def test_parse_english_assemblies_keeps_fifty_unique_in_order():
    parts = [
        f"THE {ordinal} ASSEMBLY, CALLED OF X.\n\nBody {n}.\n"
        for n, ordinal in enumerate(hariri._ORDINALS, start=1)
    ]
    parsed = hariri.parse_english_assemblies("intro\n\n" + "".join(parts))
    assert [number for number, _heading, _body in parsed] == list(range(1, 51))
    assert "Body 1." in parsed[0][2]
    assert "Body 50." in parsed[-1][2]


def _arabic_fixture(tmp_path: Path) -> Path:
    words = " ".join(["كلمة"] * 40)
    path = tmp_path / "work.txt"
    path.write_text(
        "\n".join(
            [
                "######OpenITI#",
                "#META# 010.AuthorNAME :: الحريري",
                "#META# 011.AuthorDIED :: 516",
                "#META# 021.BookSUBJ :: كتب الأدب",
                "#META#Header#End#",
                "# | بسم الله الرحمن الرحيم",
                f"# {words}",
                f"# المقامة الصنعانية حدث الحارث بن همام قال : {words}",
                "# | المقامة الثانية الحلوانية",
                f"# حكى الحارث بن همام قال : {words}",
                "# | المقامة التاسعة والأربعون الساسانية",
                f"# حكى الحارث بن همام قال : {words}",
                f"# المقامة الخمسون البصرية $ حكى الحارث بن همام قال : {words}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def test_arabic_maqamat_recovers_first_and_fiftieth(tmp_path: Path):
    text = openiti_markdown.read(_arabic_fixture(tmp_path))
    maqamat = hariri.arabic_maqamat(text)
    numbers = [number for number, _title, _paras in maqamat]
    assert numbers[0] == 1
    assert numbers[-1] == 50
    assert "صنعان" in maqamat[0][1]
    assert maqamat[0][2][0].startswith("المقامة")
    assert any("خمسون" in para for para in maqamat[-1][2])
    assert numbers == [1, 2, 49, 50]


def test_arabic_maqamat_does_not_duplicate_the_last_section(tmp_path: Path):
    text = openiti_markdown.read(_arabic_fixture(tmp_path))
    maqamat = hariri.arabic_maqamat(text)
    titles = [title for _n, title, _paras in maqamat]
    assert titles.count(text.sections[-1].title) == 1


def _passage(
    number: int,
    words: int,
    start: int = 0,
    *,
    confidence: float = 0.7,
    verdict: dict | None = None,
    english_words: int | None = None,
) -> hariri.Passage:
    english_count = english_words if english_words is not None else int(words * 1.6)
    return hariri.Passage(
        maqama_number=number,
        arabic_title="t",
        english_title="THE FIRST ASSEMBLY",
        arabic_range=(start, start + 1),
        english_range=(start, start + 1),
        arabic=" ".join(["كلمة"] * words),
        english=" ".join(["word"] * english_count),
        arabic_word_count=words,
        english_word_count=english_count,
        maqama_complete=False,
        structural_confidence=0.6,
        confidence=confidence,
        llm_verdict=verdict,
    )


def test_eligibility_rejects_out_of_band_and_ratio():
    assert hariri_alignment.eligible_for_adjudication(_passage(1, 150))
    assert not hariri_alignment.eligible_for_adjudication(
        _passage(1, 150, english_words=20)
    )
    assert not hariri_alignment.eligible_for_adjudication(_passage(1, 20))


def test_select_requires_an_aligned_verdict():
    bare = _passage(1, 150)
    partial = _passage(2, 150, verdict={"verdict": "partial", "confidence": 0.9})
    aligned = _passage(3, 150, verdict={"verdict": "aligned", "confidence": 0.9})
    assert hariri_alignment.select([bare, partial], target=4) == []
    assert hariri_alignment.select([bare, partial, aligned], target=4) == [aligned]


def test_select_spreads_across_maqamat():
    passages = [
        _passage(
            number, 150, start=index, verdict={"verdict": "aligned", "confidence": 0.9}
        )
        for number in (1, 2)
        for index in range(8)
    ]
    chosen = hariri_alignment.select(passages, target=8, seed=7)
    assert {p.maqama_number for p in chosen} == {1, 2}


def test_select_balances_the_two_target_bands():
    short = [
        _passage(n, 150, verdict={"verdict": "aligned", "confidence": 0.9})
        for n in range(1, 7)
    ]
    long = [
        _passage(n, 300, verdict={"verdict": "aligned", "confidence": 0.9})
        for n in range(10, 16)
    ]
    chosen = hariri_alignment.select(short + long, target=4, seed=1)
    bands = {p.arabic_word_count < 250 for p in chosen}
    assert bands == {True, False}
    assert len(chosen) == 4


def test_adjudication_pool_spreads_a_limit_across_maqamat():
    passages = [
        _passage(number, 150, start=index)
        for number in range(1, 11)
        for index in range(8)
    ]
    pool = hariri_alignment.adjudication_pool(passages, limit=10, seed=3)
    assert len(pool) == 10
    assert len({p.maqama_number for p in pool}) == 10


def test_cached_verdicts_replay_and_are_skipped_by_a_second_pool():
    passage = _passage(1, 150)
    key = hariri_alignment._passage_key(passage, "m")
    cache = {
        key: {
            "verdict": "aligned",
            "confidence": 0.9,
            "note": "",
            "model": "m",
            "error": None,
        }
    }
    assert hariri_alignment.apply_cached_verdicts([passage], cache, "m") == 1
    assert passage.llm_verdict["verdict"] == "aligned"
    uncached = [p for p in [passage] if p.llm_verdict is None]
    assert hariri_alignment.adjudication_pool(uncached, limit=10, seed=1) == []


def test_manifest_records_carry_no_text_and_pass_the_guard():
    record = hariri_alignment.to_record(
        _passage(1, 150, verdict={"verdict": "aligned", "confidence": 0.9}),
        _FakeText(),
    )
    manifest = hariri_alignment.to_manifest_record(record)
    assert "arabic" not in manifest
    assert "english" not in manifest
    assert "reference_english" not in manifest
    assert manifest["maqama_number"] == 1
    assert manifest["rights_status"] == hariri.RIGHTS_STATUS
    assert "THE FIRST ASSEMBLY" not in str(manifest)
    pd_alignment._assert_textfree([manifest], "manifest")


def test_record_carries_provenance_and_the_maqama_anchor():
    record = hariri_alignment.to_record(_passage(1, 150), _FakeText())
    assert record["source"] == "hariri_assemblies"
    assert record["work_id"] == hariri.WORK_ID
    assert record["rights_status"] == hariri.RIGHTS_STATUS
    assert record["rights_evidence"]
    assert record["genre"] == "كتب الأدب"
    assert record["date_or_century"] == "516 AH"
    assert record["chapter_label"] == "maqama 1"
    assert record["anchors_open"] == ["maqama 1"]


def test_extract_pairs_by_sequence_and_cuts_inside(tmp_path: Path):
    arabic_words = " ".join(["كلمة"] * 80)
    arabic = tmp_path / "ar.txt"
    arabic.write_text(
        "\n".join(
            [
                "######OpenITI#",
                "#META# 010.AuthorNAME :: الحريري",
                "#META# 011.AuthorDIED :: 516",
                "#META# 021.BookSUBJ :: كتب الأدب",
                "#META#Header#End#",
                "# | بسم الله الرحمن الرحيم",
                f"# {' '.join(['مقدمة'] * 20)}",
                f"# المقامة الصنعانية حدث الحارث بن همام قال : {arabic_words}",
                f"# {arabic_words}",
                "# | المقامة الثانية الحلوانية",
                f"# حكى الحارث بن همام قال : {arabic_words}",
                f"# {arabic_words}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    english = tmp_path / "en.txt"
    english.write_text(
        "THE FIRST ASSEMBLY, CALLED OF X.\n\n"
        "In this Assembly Al Harith arrives in the town.\n\n"
        + ("Al Harith, son of Hammam, related: When I mounted. " * 90)
        + "\n\nMore of the first. " * 40
        + "\n\nTHE SECOND ASSEMBLY, CALLED OF Y.\n\n"
        "In this Assembly the author displays subtlety.\n\n"
        + ("Al Harith, son of Hammam, related: Ever since. " * 90)
        + "\n\nMore of the second. " * 40,
        encoding="utf-8",
    )
    metadata, report = hariri.extract(arabic, english, min_words=50)
    assert metadata.author_died == 516
    assert report.arabic_maqamat == 2
    assert report.english_maqamat == 2
    assert report.paired == 2
    assert report.used
    assert report.passages
    assert all(p.maqama_number in {1, 2} for p in report.passages)
    assert all("llm_required" in p.flags for p in report.passages)
    assert all("In this Assembly" not in p.english for p in report.passages)
