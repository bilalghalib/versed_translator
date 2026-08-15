"""Synthetic tests for the Ibn Rushd / Jamil-ur-Rehman treatise aligner.

Fixtures are invented tokens plus ASCII. No corpus text lives here.
"""

from __future__ import annotations

from pathlib import Path

from versed_translator.benchmark import ibn_rushd_alignment, pd_alignment
from versed_translator.benchmark.sources import ibn_rushd, openiti_markdown


class _FakeText:
    author_name = "PLACEHOLDER AUTHOR"
    author_died = 595
    book_subject = "كتب متنوعة"


def _passage(
    treatise: str,
    words: int,
    start: int = 0,
    *,
    confidence: float = 0.7,
    verdict: dict | None = None,
    english_words: int | None = None,
) -> ibn_rushd.Passage:
    english_count = english_words if english_words is not None else int(words * 1.6)
    return ibn_rushd.Passage(
        treatise_id=treatise,
        arabic_title="t",
        english_title="A DECISIVE DISCOURSE",
        arabic_range=(start, start + 1),
        english_range=(start, start + 1),
        arabic=" ".join(["كلمة"] * words),
        english=" ".join(["word"] * english_count),
        arabic_word_count=words,
        english_word_count=english_count,
        treatise_complete=False,
        structural_confidence=0.6,
        confidence=confidence,
        llm_verdict=verdict,
    )


def test_gutenberg_body_drops_license_wrapper():
    text = (
        "The Project Gutenberg eBook of X\n\n"
        "*** START OF THE PROJECT GUTENBERG EBOOK X ***\n\n"
        "And after: Praise be to God for all His praiseworthy acts. BODY.\n\n"
        "*** END OF THE PROJECT GUTENBERG EBOOK X ***\n\n"
        "1.A. By reading or using any part of this Project Gutenberg\n"
    )
    body = ibn_rushd.gutenberg_body(text)
    assert "And after: Praise be to God" in body
    assert "1.A. By reading" not in body
    assert "The Project Gutenberg eBook of X" not in body


def test_parse_english_treatises_finds_three_and_strips_footnotes():
    text = (
        "*** START OF THE PROJECT GUTENBERG EBOOK X ***\n\n"
        "CONTENTS\n\n"
        "I. A Decisive Discourse\n\n"
        "I a. Appendix\n\n"
        "II. An Exposition\n\n"
        "A DECISIVE DISCOURSE ON THE DELINEATION\n"
        "OF THE RELATION BETWEEN RELIGION AND PHILOSOPHY.[1]\n\n"
        "And after: Praise be to God for all His praiseworthy acts. "
        "Fasl token one. Fasl token two.\n\n"
        "FOOTNOTES\n\n"
        "[Footnote 1: Quran ii, 1.]\n\n"
        "APPENDIX.\n\n"
        "ON THE PROBLEM OF ETERNAL KNOWLEDGE.\n\n"
        "May God perpetuate your honour and bless you. Damima token.\n\n"
        "FOOTNOTES\n\n"
        "[Footnote 24: Quran lxvi, 14.]\n\n"
        "II\n\n"
        "AN EXPOSITION OF THE METHODS OF ARGUMENTS CONCERNING THE BELIEFS OF "
        "THE FAITH.\n\n"
        "And after--Praise be to God, who sets apart anyone. Kashf token.\n\n"
        "FOOTNOTES\n\n"
        "[Footnote 25: Quran i, 1.]\n\n"
        "*** END OF THE PROJECT GUTENBERG EBOOK X ***\n"
    )
    parsed = ibn_rushd.parse_english_treatises(text)
    ids = [item.treatise_id for item in parsed]
    assert ids == ["fasl", "damima", "kashf"]
    fasl = parsed[0]
    damima = parsed[1]
    kashf = parsed[2]
    assert "Fasl token one" in fasl.text
    assert "[1]" not in fasl.text
    assert "FOOTNOTES" not in fasl.text
    assert "Quran" not in fasl.text
    assert fasl.text.startswith("And after: Praise be to God")
    assert damima.text.startswith("May God perpetuate your honour")
    assert "Damima token" in damima.text
    assert "Kashf token" in kashf.text
    assert "CONTENTS" not in fasl.text


def _arabic_fixture(tmp_path: Path, *, with_damima: bool = True) -> Path:
    words = " ".join(["كلمة"] * 40)
    lines = [
        "######OpenITI#",
        "#META# 010.AuthorNAME :: ابن رشد",
        "#META# 011.AuthorDIED :: 595",
        "#META# 021.BookSUBJ :: كتب متنوعة",
        "#META#Header#End#",
        "# بسم الله الرحمن الرحيم",
        "# وصلى الله على محمد",
        "# المنطق",
        f"# أما بعد حمد الله : {words}",
        f"# {words}",
        "# هل أوجب الشرع الفلسفة",
        f"# {words}",
        f"# {words}",
    ]
    if with_damima:
        lines.extend(
            [
                "# المسألة التي ذكرها الشيخ أبو الوليد",
                "# في فضل المقال رضي الله عنه",
                f"# أدام الله عزتكم، وأبقى بركتكم. {words}",
                f"# {words}",
            ]
        )
    path = tmp_path / "work.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_arabic_treatises_splits_fasl_from_damima_and_drops_headings(tmp_path: Path):
    text = openiti_markdown.read(_arabic_fixture(tmp_path))
    treatises = ibn_rushd.arabic_treatises(text)
    ids = [item.treatise_id for item in treatises]
    assert ids == ["fasl", "damima"]
    fasl, damima = treatises
    assert all("المنطق" not in para for para in fasl.paragraphs)
    assert all("بسم الله" not in para for para in fasl.paragraphs)
    assert damima.paragraphs[0].startswith("أدام الله عزتكم")
    assert "المسألة التي ذكرها" not in " ".join(damima.paragraphs)
    assert all(len(para.split()) > 8 for para in fasl.paragraphs)


def test_arabic_treatises_fasl_only_when_damima_is_absent(tmp_path: Path):
    text = openiti_markdown.read(_arabic_fixture(tmp_path, with_damima=False))
    treatises = ibn_rushd.arabic_treatises(text)
    assert [item.treatise_id for item in treatises] == ["fasl"]


def test_eligibility_rejects_out_of_band_and_ratio():
    assert ibn_rushd_alignment.eligible_for_adjudication(_passage("fasl", 150))
    assert not ibn_rushd_alignment.eligible_for_adjudication(
        _passage("fasl", 150, english_words=20)
    )
    assert not ibn_rushd_alignment.eligible_for_adjudication(_passage("fasl", 20))


def test_select_requires_an_aligned_verdict():
    bare = _passage("fasl", 150)
    partial = _passage("damima", 150, verdict={"verdict": "partial", "confidence": 0.9})
    aligned = _passage("fasl", 150, verdict={"verdict": "aligned", "confidence": 0.9})
    assert ibn_rushd_alignment.select([bare, partial], target=4) == []
    assert ibn_rushd_alignment.select([bare, partial, aligned], target=4) == [aligned]


def test_select_spreads_across_treatises():
    passages = [
        _passage(
            treatise,
            150,
            start=index,
            verdict={"verdict": "aligned", "confidence": 0.9},
        )
        for treatise in ("fasl", "damima")
        for index in range(8)
    ]
    chosen = ibn_rushd_alignment.select(passages, target=8, seed=7)
    assert {p.treatise_id for p in chosen} == {"fasl", "damima"}


def test_select_balances_the_two_target_bands():
    short = [
        _passage(
            "fasl", 150, start=n, verdict={"verdict": "aligned", "confidence": 0.9}
        )
        for n in range(1, 7)
    ]
    long = [
        _passage(
            "damima", 300, start=n, verdict={"verdict": "aligned", "confidence": 0.9}
        )
        for n in range(10, 16)
    ]
    chosen = ibn_rushd_alignment.select(short + long, target=4, seed=1)
    bands = {p.arabic_word_count < 250 for p in chosen}
    assert bands == {True, False}
    assert len(chosen) == 4


def test_adjudication_pool_spreads_a_limit_across_treatises():
    passages = [
        _passage(treatise, 150, start=index)
        for treatise in ("fasl", "damima")
        for index in range(8)
    ]
    pool = ibn_rushd_alignment.adjudication_pool(passages, limit=6, seed=3)
    assert len(pool) == 6
    assert {p.treatise_id for p in pool} == {"fasl", "damima"}


def test_cached_verdicts_replay_and_are_skipped_by_a_second_pool():
    passage = _passage("fasl", 150)
    key = ibn_rushd_alignment._passage_key(passage, "m")
    cache = {
        key: {
            "verdict": "aligned",
            "confidence": 0.9,
            "note": "",
            "model": "m",
            "error": None,
        }
    }
    assert ibn_rushd_alignment.apply_cached_verdicts([passage], cache, "m") == 1
    assert passage.llm_verdict["verdict"] == "aligned"
    uncached = [p for p in [passage] if p.llm_verdict is None]
    assert ibn_rushd_alignment.adjudication_pool(uncached, limit=10, seed=1) == []


def test_manifest_records_carry_no_text_and_pass_the_guard():
    record = ibn_rushd_alignment.to_record(
        _passage("fasl", 150, verdict={"verdict": "aligned", "confidence": 0.9}),
        _FakeText(),
    )
    manifest = ibn_rushd_alignment.to_manifest_record(record)
    assert "arabic" not in manifest
    assert "english" not in manifest
    assert "reference_english" not in manifest
    assert manifest["treatise_id"] == "fasl"
    assert manifest["rights_status"] == ibn_rushd.RIGHTS_STATUS
    assert "A DECISIVE DISCOURSE" not in str(manifest)
    pd_alignment._assert_textfree([manifest], "manifest")


def test_record_carries_provenance_and_the_treatise_anchor():
    record = ibn_rushd_alignment.to_record(_passage("fasl", 150), _FakeText())
    assert record["source"] == "ibn_rushd_rehman"
    assert record["work_id"] == ibn_rushd.WORK_ID
    assert record["rights_status"] == ibn_rushd.RIGHTS_STATUS
    assert record["rights_evidence"]
    assert record["genre"] == "كتب متنوعة"
    assert record["date_or_century"] == "595 AH"
    assert record["chapter_label"] == "treatise fasl"
    assert record["anchors_open"] == ["treatise fasl"]


def test_report_body_has_no_arabic_script():
    report = ibn_rushd.ExtractionReport(
        arabic_treatises=2,
        english_treatises=3,
        paired=2,
        used=["fasl", "damima"],
        rejected=[],
        unpaired_english=["kashf"],
        passages=[],
    )
    text = ibn_rushd_alignment.build_report(report, [], [], seed=1)
    assert not pd_alignment._ARABIC_RE.search(text)
    assert "kashf" in text
    assert "Fasl al-Maqal" in text


def test_extract_pairs_shared_treatises_and_leaves_kashf_unpaired(tmp_path: Path):
    arabic_words = " ".join(["كلمة"] * 80)
    arabic = tmp_path / "ar.txt"
    arabic.write_text(
        "\n".join(
            [
                "######OpenITI#",
                "#META# 010.AuthorNAME :: ابن رشد",
                "#META# 011.AuthorDIED :: 595",
                "#META# 021.BookSUBJ :: كتب متنوعة",
                "#META#Header#End#",
                "# بسم الله الرحمن الرحيم",
                f"# أما بعد حمد الله : {arabic_words}",
                f"# {arabic_words}",
                f"# أدام الله عزتكم، وأبقى بركتكم. {arabic_words}",
                f"# {arabic_words}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    english = tmp_path / "en.txt"
    english.write_text(
        "*** START OF THE PROJECT GUTENBERG EBOOK X ***\n\n"
        "A DECISIVE DISCOURSE ON THE DELINEATION\n\n"
        "And after: Praise be to God for all His praiseworthy acts. "
        + ("Fasl body token. " * 90)
        + "\n\nMore of the first. " * 40
        + "\n\nFOOTNOTES\n\n[Footnote 1: skip.]\n\n"
        + "APPENDIX.\n\n"
        + "May God perpetuate your honour and bless you. "
        + ("Damima body token. " * 90)
        + "\n\nMore of the appendix. " * 40
        + "\n\nII\n\n"
        + "AN EXPOSITION OF THE METHODS OF ARGUMENTS CONCERNING THE BELIEFS.\n\n"
        + "And after--Praise be to God, who sets apart anyone. "
        + ("Kashf body token. " * 90)
        + "\n\n*** END OF THE PROJECT GUTENBERG EBOOK X ***\n",
        encoding="utf-8",
    )
    metadata, report = ibn_rushd.extract(arabic, english, min_words=50)
    assert metadata.author_died == 595
    assert report.arabic_treatises == 2
    assert report.english_treatises == 3
    assert report.paired == 2
    assert report.used
    assert report.unpaired_english == ["kashf"]
    assert report.passages
    assert all(p.treatise_id in {"fasl", "damima"} for p in report.passages)
    assert all("llm_required" in p.flags for p in report.passages)
    assert all("Kashf body token" not in p.english for p in report.passages)
    assert all("FOOTNOTES" not in p.english for p in report.passages)
    assert any(p.treatise_id == "fasl" for p in report.passages)
    assert any(p.treatise_id == "damima" for p in report.passages)
