"""Tests for C1 checkpoint 2: benchmark.assemble (v0.1-DRAFT stratified assembly).

Runs against the real downloaded corpora (repo hygiene rule: verify with
real data), skipping if the checkout isn't present at DEFAULT_CORPUS_DIRS
(e.g. /Volumes/Nodes not mounted on this machine) rather than faking a
pass. Covers: determinism, draft_test/dev_bakeoff disjointness (by id and
by arabic sha256), no-ATHAR-train leakage, and a repo-hygiene guard that
the jsonl data files never land inside the repo tree.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from versed_translator.benchmark import assemble
from versed_translator.benchmark.sources import DEFAULT_CORPUS_DIRS

REPO_ROOT = Path(__file__).resolve().parents[1]


def _corpora_present() -> bool:
    return DEFAULT_CORPUS_DIRS["athar"].exists() and DEFAULT_CORPUS_DIRS["lk_hadith"].exists()


pytestmark = pytest.mark.skipif(
    not _corpora_present(),
    reason="ATHAR / LK Hadith corpus checkouts not present at DEFAULT_CORPUS_DIRS",
)


@pytest.fixture(scope="module")
def result():
    return assemble.assemble(seed=assemble.DEFAULT_SEED)


def test_determinism_same_seed_same_manifest():
    r1 = assemble.assemble(seed=42)
    r2 = assemble.assemble(seed=42)
    m1 = assemble.build_manifest(r1)
    m2 = assemble.build_manifest(r2)
    assert m1 == m2


def test_different_seed_can_change_selection():
    r1 = assemble.assemble(seed=1)
    r2 = assemble.assemble(seed=2)
    ids1 = {assemble.item_id(p) for p in r1["draft_test"]}
    ids2 = {assemble.item_id(p) for p in r2["draft_test"]}
    # Not a strict requirement that they differ (a degenerate pool could
    # make selection forced), but for this real corpus pool the two seeds
    # must not coincidentally pick the identical set.
    assert ids1 != ids2


def test_disjoint_by_id(result):
    draft_ids = {assemble.item_id(p) for p in result["draft_test"]}
    dev_ids = {assemble.item_id(p) for p in result["dev_bakeoff"]}
    assert draft_ids.isdisjoint(dev_ids)


def test_disjoint_by_arabic_hash(result):
    draft_hashes = {p["_sha256"] for p in result["draft_test"]}
    dev_hashes = {p["_sha256"] for p in result["dev_bakeoff"]}
    assert draft_hashes.isdisjoint(dev_hashes)


def test_no_athar_train_leakage(result):
    for split_name in ("draft_test", "dev_bakeoff"):
        for pair in result[split_name]:
            if pair["source"] == "athar":
                assert pair["source_split"] == "test", (
                    f"ATHAR train row leaked into {split_name}: {pair['source_native_id']}"
                )


def test_no_hadith_json_items(result):
    for split_name in ("draft_test", "dev_bakeoff"):
        for pair in result[split_name]:
            assert pair["source"] != "hadith_json"


def test_items_restricted_to_target_bands(result):
    for split_name in ("draft_test", "dev_bakeoff"):
        for pair in result[split_name]:
            assert pair["_band"] in assemble.TARGET_BANDS


def test_draft_test_target_roughly_met(result):
    # Target ~1200; allow shortfall only where the sparse 250-600 band
    # legitimately runs out of candidates (recorded in band_stats).
    assert len(result["draft_test"]) > 0
    total_shortfall = sum(
        s["shortfall_draft_test"] for s in result["band_stats"].values()
    )
    assert len(result["draft_test"]) + total_shortfall == assemble.DRAFT_TEST_TARGET


def test_dev_bakeoff_target_roughly_met(result):
    total_shortfall = sum(s["shortfall_dev_bakeoff"] for s in result["band_stats"].values())
    assert len(result["dev_bakeoff"]) + total_shortfall == assemble.DEV_BAKEOFF_TARGET


def test_manifest_has_no_text_fields():
    r = assemble.assemble(seed=7)
    manifest = assemble.build_manifest(r)
    manifest_str = repr(manifest)
    for pair in r["draft_test"][:5] + r["dev_bakeoff"][:5]:
        assert pair["arabic"] not in manifest_str
        if pair["reference_english"]:
            assert pair["reference_english"] not in manifest_str
    for item in manifest["items"]:
        assert set(item) == {
            "id",
            "source",
            "source_native_id",
            "sha256_arabic",
            "split",
            "band",
            "attribution",
            "rights_status",
        }


# --- repo hygiene: jsonl data files must never exist inside the repo tree ---


def test_repo_hygiene_no_jsonl_data_in_repo_tree():
    hits = subprocess.run(
        ["find", str(REPO_ROOT), "-name", "*.jsonl"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    offenders = [h for h in hits if "benchmark-data" in h or "v0.1-draft" in h]
    assert offenders == [], f"benchmark data jsonl found inside repo tree: {offenders}"


def test_repo_out_dir_has_no_arabic_text_files(tmp_path):
    # Guard the actual release dir this task owns: manifest.json/stats.md
    # only, no .jsonl, ever.
    release_dir = REPO_ROOT / "benchmark" / "releases" / "v0.1-draft"
    if not release_dir.exists():
        pytest.skip("v0.1-draft release dir not yet written")
    names = {p.name for p in release_dir.iterdir()}
    assert names <= {"manifest.json", "stats.md"}
