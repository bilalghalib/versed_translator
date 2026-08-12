"""Schema-shape + real-count-floor tests for the C1-checkpoint-1 source loaders.

These tests read the actual downloaded corpora (no mocks, no fixtures
standing in for real data), per the repo's frozen-benchmark hygiene rule
that verification must use real data with real measured counts. If a
corpus checkout is not present at its configured location (e.g. the
/Volumes/Nodes scratch disk is not mounted on this machine), the
corresponding tests are skipped rather than faked -- a skip is an honest
signal that verification did not happen here, not a pass.

Count floors below were set from measurements taken 2026-08-12 (see
corpus/rights_ledger.json for the full discrepancy writeup):
  - ATHAR: 66,043 pairs measured (matches its own README exactly) -> floor 60,000.
  - LK Hadith: 33,845 pairs measured. The corpus's own README claims 39,038
    hadiths; the task brief's suggested floor was >35,000. Neither holds:
    raw CSV rows across all six collections total only 34,088, of which
    33,845 have both Arabic and English populated. Floor set to 30,000
    (below measured reality) rather than papering over the shortfall by
    inflating the floor toward the README's unverified number.
  - hadith-json: 47,317 pairs measured (of 50,884 raw hadith objects,
    which does match the README exactly; 3,567 are dropped here for a
    missing arabic or english.text field) -> floor 45,000, as suggested.
"""

from __future__ import annotations

import pytest

from versed_translator.benchmark.sources import DEFAULT_CORPUS_DIRS, SOURCE_MODULES
from versed_translator.benchmark.sources.schema import (
    PAIR_FIELDS,
    arabic_word_count,
    length_band,
)

COUNT_FLOORS = {
    "athar": 60_000,
    "lk_hadith": 30_000,
    "hadith_json": 45_000,
}

REQUIRED_RIGHTS_STATUS = {
    "athar": "CC_BY_NC_4.0_LICENSE_CONFLICT_SEE_LEDGER",
    "lk_hadith": "RIGHTS_UNVERIFIED_NO_LICENSE_FILE",
    "hadith_json": "INDEX_ONLY_NO_REDISTRIBUTION",
}


def _corpus_dir_or_skip(source_name: str):
    corpus_dir = DEFAULT_CORPUS_DIRS[source_name]
    if not corpus_dir.exists():
        pytest.skip(f"{source_name} corpus not present at {corpus_dir}")
    return corpus_dir


@pytest.fixture(scope="module")
def pairs_by_source():
    """Materialize each source's pairs once per test session (real data, real I/O)."""
    cache: dict[str, list[dict]] = {}

    def _get(source_name: str) -> list[dict]:
        if source_name not in cache:
            corpus_dir = _corpus_dir_or_skip(source_name)
            module = SOURCE_MODULES[source_name]
            cache[source_name] = list(module.iter_pairs(corpus_dir))
        return cache[source_name]

    return _get


@pytest.mark.parametrize("source_name", list(SOURCE_MODULES))
def test_schema_shape(pairs_by_source, source_name):
    pairs = pairs_by_source(source_name)
    assert pairs, f"{source_name} produced zero pairs"
    sample = pairs[: min(500, len(pairs))]
    for pair in sample:
        assert set(pair.keys()) == set(PAIR_FIELDS)
        assert isinstance(pair["arabic"], str) and pair["arabic"]
        assert isinstance(pair["reference_english"], str) and pair["reference_english"]
        assert pair["source"] == source_name
        assert pair["rights_status"] == REQUIRED_RIGHTS_STATUS[source_name]


@pytest.mark.parametrize("source_name", list(SOURCE_MODULES))
def test_count_floor(pairs_by_source, source_name):
    pairs = pairs_by_source(source_name)
    floor = COUNT_FLOORS[source_name]
    assert len(pairs) >= floor, (
        f"{source_name}: measured {len(pairs)} pairs, below floor {floor} "
        "(see corpus/rights_ledger.json and this file's module docstring "
        "for the measured-vs-claimed discrepancy writeup)"
    )


def test_athar_preserves_native_split(pairs_by_source):
    pairs = pairs_by_source("athar")
    splits = {p["source_split"] for p in pairs}
    assert splits == {"train", "test"}
    train_count = sum(1 for p in pairs if p["source_split"] == "train")
    test_count = sum(1 for p in pairs if p["source_split"] == "test")
    # Matches the ATHAR dataset card's stated split sizes exactly.
    assert train_count == 65_043
    assert test_count == 1_000


def test_lk_hadith_genre_is_hadith(pairs_by_source):
    pairs = pairs_by_source("lk_hadith")
    assert {p["genre"] for p in pairs} == {"hadith"}
    work_ids = {p["work_id"] for p in pairs}
    assert work_ids == {"AbuDaud", "Bukhari", "IbnMaja", "Muslim", "Nesai", "Tirmizi"}


def test_hadith_json_index_only_and_genre(pairs_by_source):
    pairs = pairs_by_source("hadith_json")
    assert {p["genre"] for p in pairs} == {"hadith"}
    assert {p["rights_status"] for p in pairs} == {"INDEX_ONLY_NO_REDISTRIBUTION"}
    # README lists 17 canonical books, but Sunan al-Darimi (book 9 of
    # the_9_books) has zero English translations in this checkout -- every
    # one of its 3,406 hadith objects has Arabic text but an empty
    # english.text field, so it contributes zero valid pairs and vanishes
    # from work_id here. Measured, not a loader bug: verified by reading
    # db/by_book/the_9_books/darimi.json directly.
    assert len({p["work_id"] for p in pairs}) == 16


@pytest.mark.parametrize("source_name", list(SOURCE_MODULES))
def test_length_band_coverage_nonzero(pairs_by_source, source_name):
    """At least one of the master-plan length bands is populated per source."""
    pairs = pairs_by_source(source_name)
    bands_hit = {length_band(arabic_word_count(p["arabic"])) for p in pairs}
    bands_hit.discard(None)
    assert bands_hit, f"{source_name}: no pair fell into any of the master-plan length bands"


def test_make_pair_rejects_unknown_field():
    from versed_translator.benchmark.sources.schema import make_pair

    with pytest.raises(ValueError):
        make_pair(not_a_real_field="x")
