"""C1 checkpoint 2: deterministic stratified assembly of Versed Benchmark v0.1-DRAFT.

Builds two splits from the checkpoint-1 source loaders:

  - ``draft_test``  (target ~1,200 items): ATHAR's NATIVE test split
    (source_split == "test"; ATHAR train rows are never eligible) plus all
    of LK Hadith. hadith-json is excluded entirely -- its English side is
    INDEX_ONLY_NO_REDISTRIBUTION per corpus/rights_ledger.json and must
    never be shipped as benchmark data.
  - ``dev_bakeoff`` (target 150 items): same source pool, same
    stratification, disjoint from draft_test by id AND by sha256(arabic).

Stratification is over two axes:
  - length band: 30-80 / 100-250 / 250-600 Arabic words (schema.LENGTH_BANDS,
    minus the open-ended 600+ band, which this draft does not target).
  - attribution group: LK Hadith carries a real per-row work/collection
    field (work_id = Bukhari/Muslim/AbuDaud/IbnMaja/Nesai/Tirmizi) which is
    used as the attribution group. ATHAR's parquet files carry only
    ("arabic", "english") columns -- verified by inspecting both the train
    and test parquet schemas -- so ATHAR rows carry no work/author/genre
    metadata at all and are grouped under the single bucket
    ATHAR_UNKNOWN_ATTRIBUTION rather than invented.

Everything here is seeded and deterministic: for a fixed seed and fixed
corpus checkouts, re-running produces byte-identical manifest.json /
stats.md content (item ordering included).

Rights hygiene (repo is public): this module writes full item data
(including Arabic/English text) ONLY under /Volumes/Nodes/versed-translator
(benchmark-data/v0.1-draft/{draft_test,dev_bakeoff}.jsonl). The repo-tracked
outputs (benchmark/releases/v0.1-draft/manifest.json and stats.md) carry
only ids, hashes, counts, and rights_status -- never quoted text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from versed_translator.benchmark.sources import DEFAULT_CORPUS_DIRS, athar, lk_hadith
from versed_translator.benchmark.sources.schema import arabic_word_count, length_band
from versed_translator.paths import SCRATCH_DIR

DEFAULT_SEED = 20260812

# Only these three bands are targeted by v0.1-draft (see roadmap C1
# checkpoint 2). The open-ended 600+ band is out of scope for this draft.
TARGET_BANDS: tuple[str, ...] = ("30-80", "100-250", "250-600")

# Equal per-band targets are used *on purpose* rather than targets
# proportional to each band's availability: proportional targets would
# silently shrink a sparse band instead of surfacing it as a shortfall.
# Splitting 1200/150 evenly across 3 bands (400/50 each) and then letting
# _allocate_counts cap+report is what makes the expected 250-600 shortfall
# visible in stats.md instead of hidden.
DRAFT_TEST_TARGET = 1200
DEV_BAKEOFF_TARGET = 150
BAND_TARGET_DRAFT = {b: DRAFT_TEST_TARGET // len(TARGET_BANDS) for b in TARGET_BANDS}
BAND_TARGET_DEV = {b: DEV_BAKEOFF_TARGET // len(TARGET_BANDS) for b in TARGET_BANDS}

ATHAR_UNKNOWN_ATTRIBUTION = "ATHAR_UNKNOWN_ATTRIBUTION"


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _attribution_group(pair: dict) -> str:
    if pair["source"] == "athar":
        return ATHAR_UNKNOWN_ATTRIBUTION
    return pair["work_id"] or "UNKNOWN"


def load_candidate_pool(corpus_dirs: dict[str, Path] | None = None) -> list[dict]:
    """Load the eligible candidate pool: ATHAR native test split + all LK Hadith.

    ATHAR train rows and all of hadith-json are never eligible for
    inclusion in this pool (see module docstring). Returns pairs already
    restricted to TARGET_BANDS, deduplicated globally by sha256(arabic)
    (first occurrence wins, in a stable (source, source_native_id) sort
    order so dedup itself is deterministic).
    """
    dirs = corpus_dirs or DEFAULT_CORPUS_DIRS
    raw: list[dict] = []

    for pair in athar.iter_pairs(dirs["athar"]):
        if pair["source_split"] != "test":
            continue  # never touch ATHAR train rows
        raw.append(pair)

    raw.extend(lk_hadith.iter_pairs(dirs["lk_hadith"]))

    raw.sort(key=lambda p: (p["source"], str(p["source_native_id"])))

    seen_hashes: set[str] = set()
    pool: list[dict] = []
    for pair in raw:
        band = length_band(arabic_word_count(pair["arabic"]))
        if band not in TARGET_BANDS:
            continue
        h = sha256_hex(pair["arabic"])
        if h in seen_hashes:
            continue
        seen_hashes.add(h)
        enriched = dict(pair)
        enriched["_sha256"] = h
        enriched["_band"] = band
        enriched["_attribution"] = _attribution_group(pair)
        pool.append(enriched)
    return pool


def _allocate_counts(sizes: dict[str, int], target: int) -> dict[str, int]:
    """Capped-proportional allocation of `target` items across groups.

    Largest-remainder rounding, then any shortfall from small/exhausted
    groups is redistributed to groups with spare capacity. Deterministic:
    ties in the remainder ordering are broken by sorted group name.
    """
    keys = sorted(sizes)
    total_available = sum(sizes.values())
    target = max(0, min(target, total_available))
    counts = {k: 0 for k in keys}
    if target == 0 or not keys or total_available == 0:
        return counts

    raw = {k: sizes[k] * target / total_available for k in keys}
    counts = {k: min(sizes[k], int(raw[k])) for k in keys}
    remainder = target - sum(counts.values())

    order = sorted(keys, key=lambda k: (-(raw[k] - int(raw[k])), k))
    i = 0
    guard = 0
    max_guard = 10_000 * max(1, len(keys))
    while remainder > 0 and guard < max_guard:
        k = order[i % len(order)]
        if counts[k] < sizes[k]:
            counts[k] += 1
            remainder -= 1
        i += 1
        guard += 1
    return counts


def assemble(
    corpus_dirs: dict[str, Path] | None = None, seed: int = DEFAULT_SEED
) -> dict[str, Any]:
    """Run the full deterministic stratified assembly.

    Returns a dict with keys: "draft_test", "dev_bakeoff" (lists of full
    item dicts, each carrying the schema fields plus sha256, band, split),
    and "band_stats" (per-band target/actual/shortfall + per-group
    breakdown), for use by both the CLI writer and tests.
    """
    pool = load_candidate_pool(corpus_dirs)
    rng = random.Random(seed)

    by_band: dict[str, dict[str, list[dict]]] = {b: {} for b in TARGET_BANDS}
    for pair in pool:
        by_band[pair["_band"]].setdefault(pair["_attribution"], []).append(pair)

    # Deterministic per-group shuffle (order depends only on seed + the
    # stable sort already applied in load_candidate_pool).
    for band in TARGET_BANDS:
        for group, items in by_band[band].items():
            rng.shuffle(items)

    draft_items: list[dict] = []
    dev_items: list[dict] = []
    band_stats: dict[str, dict[str, Any]] = {}

    for band in TARGET_BANDS:
        group_sizes = {g: len(items) for g, items in by_band[band].items()}
        available = sum(group_sizes.values())
        want_draft = BAND_TARGET_DRAFT[band]
        want_dev = BAND_TARGET_DEV[band]
        want_total = want_draft + want_dev

        if available >= want_total:
            draft_target_band = want_draft
            dev_target_band = want_dev
        else:
            # Scale both targets down together, preserving the draft:dev
            # ratio, rather than starving one split to fully satisfy the
            # other.
            draft_target_band = round(available * want_draft / want_total) if want_total else 0
            dev_target_band = available - draft_target_band

        draft_counts = _allocate_counts(group_sizes, draft_target_band)
        remaining_sizes = {g: group_sizes[g] - draft_counts.get(g, 0) for g in group_sizes}
        dev_counts = _allocate_counts(remaining_sizes, dev_target_band)

        group_breakdown: dict[str, dict[str, int]] = {}
        for group in sorted(group_sizes):
            items = by_band[band][group]
            d_n = draft_counts.get(group, 0)
            v_n = dev_counts.get(group, 0)
            draft_slice = items[:d_n]
            dev_slice = items[d_n : d_n + v_n]
            for item in draft_slice:
                out = dict(item)
                out["split"] = "draft_test"
                draft_items.append(out)
            for item in dev_slice:
                out = dict(item)
                out["split"] = "dev_bakeoff"
                dev_items.append(out)
            group_breakdown[group] = {
                "available": group_sizes[group],
                "draft_test": d_n,
                "dev_bakeoff": v_n,
            }

        band_stats[band] = {
            "available": available,
            "target_draft_test": want_draft,
            "target_dev_bakeoff": want_dev,
            "actual_draft_test": sum(draft_counts.values()),
            "actual_dev_bakeoff": sum(dev_counts.values()),
            "shortfall_draft_test": want_draft - sum(draft_counts.values()),
            "shortfall_dev_bakeoff": want_dev - sum(dev_counts.values()),
            "by_attribution": group_breakdown,
        }

    # Final ordering deterministic and stable for output files.
    draft_items.sort(key=lambda p: (p["source"], str(p["source_native_id"])))
    dev_items.sort(key=lambda p: (p["source"], str(p["source_native_id"])))

    return {
        "draft_test": draft_items,
        "dev_bakeoff": dev_items,
        "band_stats": band_stats,
        "seed": seed,
    }


def item_id(pair: dict) -> str:
    return f"{pair['source']}:{pair['source_native_id']}"


def to_data_record(pair: dict) -> dict:
    """Full candidate record (with text) for the /Volumes jsonl outputs."""
    record = {
        "id": item_id(pair),
        "source": pair["source"],
        "source_native_id": pair["source_native_id"],
        "work_id": pair["work_id"],
        "author": pair["author"],
        "genre": pair["genre"],
        "date_or_century": pair["date_or_century"],
        "arabic": pair["arabic"],
        "reference_english": pair["reference_english"],
        "translator": pair["translator"],
        "english_source": pair["english_source"],
        "rights_status": pair["rights_status"],
        "source_split": pair["source_split"],
        "notes": pair["notes"],
        "sha256_arabic": pair["_sha256"],
        "band": pair["_band"],
        "attribution": pair["_attribution"],
        "split": pair["split"],
    }
    return record


def to_manifest_record(pair: dict) -> dict:
    """Text-free manifest record (repo-safe) for benchmark/releases/v0.1-draft/manifest.json."""
    return {
        "id": item_id(pair),
        "source": pair["source"],
        "source_native_id": pair["source_native_id"],
        "sha256_arabic": pair["_sha256"],
        "split": pair["split"],
        "band": pair["_band"],
        "attribution": pair["_attribution"],
        "rights_status": pair["rights_status"],
    }


def write_data_jsonl(items: Iterable[dict], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as f:
        for pair in items:
            f.write(json.dumps(to_data_record(pair), ensure_ascii=False))
            f.write("\n")
            n += 1
    return n


def build_manifest(result: dict) -> dict:
    all_items = result["draft_test"] + result["dev_bakeoff"]
    all_items_sorted = sorted(all_items, key=lambda p: (p["source"], str(p["source_native_id"])))
    return {
        "release": "v0.1-draft",
        "seed": result["seed"],
        "counts": {
            "draft_test": len(result["draft_test"]),
            "dev_bakeoff": len(result["dev_bakeoff"]),
            "total": len(all_items_sorted),
        },
        "items": [to_manifest_record(p) for p in all_items_sorted],
    }


def build_stats_md(result: dict) -> str:
    lines: list[str] = []
    lines.append("# Versed Benchmark v0.1-DRAFT -- assembly stats")
    lines.append("")
    lines.append(f"Seed: `{result['seed']}`")
    lines.append("")
    lines.append(
        f"- draft_test: **{len(result['draft_test'])}** items "
        f"(target ~{DRAFT_TEST_TARGET})"
    )
    lines.append(
        f"- dev_bakeoff: **{len(result['dev_bakeoff'])}** items (target {DEV_BAKEOFF_TARGET})"
    )
    lines.append("")
    lines.append(
        "Sources: ATHAR native **test** split only (train rows never eligible); "
        "all of LK Hadith. hadith-json excluded entirely "
        "(rights_status=INDEX_ONLY_NO_REDISTRIBUTION -- English side never ships)."
    )
    lines.append("")
    lines.append(
        "Attribution finding: ATHAR's parquet files carry only `(arabic, english)` "
        "columns -- no per-row work/author/genre metadata exists in the source data "
        "(verified against both train and test parquet schemas), so ATHAR rows are "
        f"grouped under `{ATHAR_UNKNOWN_ATTRIBUTION}`. LK Hadith carries a real "
        "per-row collection field (`work_id`: AbuDaud/Bukhari/IbnMaja/Muslim/Nesai/"
        "Tirmizi) which is used as the attribution axis for that source."
    )
    lines.append("")
    lines.append("## By length band")
    lines.append("")
    lines.append(
        "| band | available | target draft_test | actual draft_test | shortfall | "
        "target dev_bakeoff | actual dev_bakeoff | shortfall |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    for band in TARGET_BANDS:
        s = result["band_stats"][band]
        lines.append(
            f"| {band} | {s['available']} | {s['target_draft_test']} | "
            f"{s['actual_draft_test']} | {s['shortfall_draft_test']} | "
            f"{s['target_dev_bakeoff']} | {s['actual_dev_bakeoff']} | "
            f"{s['shortfall_dev_bakeoff']} |"
        )
    lines.append("")
    lines.append("## By length band x attribution group")
    lines.append("")
    lines.append("| band | attribution | available | draft_test | dev_bakeoff |")
    lines.append("|---|---|---|---|---|")
    for band in TARGET_BANDS:
        for group, g in sorted(result["band_stats"][band]["by_attribution"].items()):
            lines.append(
                f"| {band} | {group} | {g['available']} | {g['draft_test']} | "
                f"{g['dev_bakeoff']} |"
            )
    lines.append("")
    lines.append("## By source")
    lines.append("")
    source_counts: dict[str, dict[str, int]] = {}
    for split_name in ("draft_test", "dev_bakeoff"):
        for pair in result[split_name]:
            src = pair["source"]
            source_counts.setdefault(src, {"draft_test": 0, "dev_bakeoff": 0})
            source_counts[src][split_name] += 1
    lines.append("| source | draft_test | dev_bakeoff |")
    lines.append("|---|---|---|")
    for src in sorted(source_counts):
        c = source_counts[src]
        lines.append(f"| {src} | {c['draft_test']} | {c['dev_bakeoff']} |")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--repo-out",
        type=Path,
        default=Path(__file__).resolve().parents[3] / "benchmark" / "releases" / "v0.1-draft",
        help="repo-tracked output dir for manifest.json + stats.md (no text)",
    )
    parser.add_argument(
        "--data-out",
        type=Path,
        default=SCRATCH_DIR / "benchmark-data" / "v0.1-draft",
        help="off-repo output dir for draft_test.jsonl / dev_bakeoff.jsonl (has text)",
    )
    args = parser.parse_args(argv)

    result = assemble(seed=args.seed)

    args.data_out.mkdir(parents=True, exist_ok=True)
    n_draft = write_data_jsonl(result["draft_test"], args.data_out / "draft_test.jsonl")
    n_dev = write_data_jsonl(result["dev_bakeoff"], args.data_out / "dev_bakeoff.jsonl")

    args.repo_out.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(result)
    (args.repo_out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (args.repo_out / "stats.md").write_text(build_stats_md(result), encoding="utf-8")

    print(f"draft_test: {n_draft} items -> {args.data_out / 'draft_test.jsonl'}")
    print(f"dev_bakeoff: {n_dev} items -> {args.data_out / 'dev_bakeoff.jsonl'}")
    print(f"manifest + stats -> {args.repo_out}")


if __name__ == "__main__":
    main()
