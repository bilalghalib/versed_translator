"""C6 checkpoint 1 — works inventory.

Builds `corpus/inventory.sqlite`: one row per work drawn from versed's
curated-first OpenITI rollout priority list, enriched from OpenITI
per-work metadata (`meta/<uri>.json`) and the provenance resolver
(`versed_translator.corpus.resolver`).

Usage:
    python -m versed_translator.corpus.inventory --build --limit 250
    python -m versed_translator.corpus.inventory --stats
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sqlite3
import time
from collections import Counter
from pathlib import Path
from typing import Any

from versed_translator.corpus import resolver
from versed_translator.paths import OPENITI_DIR

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH = REPO_ROOT / "corpus" / "inventory.sqlite"
DEFAULT_STATS_PATH = REPO_ROOT / "corpus" / "inventory_stats.md"

# versed's curated-first OpenITI rollout priority list. Lives in the sibling
# `versed-app` repo (not this one); override via VERSED_PRIORITY_LIST if
# your checkout is elsewhere.
DEFAULT_PRIORITY_LIST = Path(
    "/Users/bilalghalib/Projects/scripts/versed/versed-app/config/"
    "openiti-rollout-priority/all_openiti_v1.uris.txt"
)

RESOLVER_COVERAGE_SAMPLE = 200  # C6 target: resolver coverage measured on top-200
DEFAULT_BUILD_LIMIT = 250  # C6 deliverable: populate metadata for >=250 top-priority works

RIGHTS_UNKNOWN = "UNKNOWN"


def load_priority_uris(path: Path) -> list[str]:
    """Return catalog URIs from the priority list, in curated-first order.

    Blank lines and '#'-comment lines (including the header block) are
    skipped. Order in the file *is* priority_rank (1-indexed).
    """
    uris: list[str] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            uris.append(line)
    return uris


def load_meta(uri: str, openiti_dir: Path) -> dict[str, Any] | None:
    meta_path = openiti_dir / "meta" / f"{uri}.json"
    try:
        with meta_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None


def _pick(meta: dict[str, Any] | None, *keys: str) -> str | None:
    if not meta:
        return None
    for key in keys:
        value = meta.get(key)
        if value:
            return value
    return None


def build_work_row(uri: str, priority_rank: int, openiti_dir: Path) -> dict[str, Any]:
    meta = load_meta(uri, openiti_dir)
    meta_found = meta is not None
    resolved = resolver.resolve(uri, meta=meta)

    genre = None
    if meta and meta.get("tags"):
        genre = ";".join(meta["tags"])

    return {
        "uri": uri,
        "priority_rank": priority_rank,
        "author": _pick(meta, "author_en", "author_ar", "author"),
        "title": _pick(meta, "title_en", "title_ar", "title"),
        "author_death_ah": resolved["author_death_ah"],
        "genre": genre,
        "source_lib_claim": resolved["source_lib_claim"],
        "source_evidence": json.dumps(resolved["evidence"]),
        "meta_found": meta_found,
        "arabic_rights": RIGHTS_UNKNOWN,
        "english_rights": RIGHTS_UNKNOWN,
        "commercial_status": RIGHTS_UNKNOWN,
    }


SCHEMA = """
CREATE TABLE IF NOT EXISTS works (
    uri TEXT PRIMARY KEY,
    priority_rank INTEGER NOT NULL,
    author TEXT,
    title TEXT,
    author_death_ah INTEGER,
    genre TEXT,
    source_lib_claim TEXT,
    source_evidence TEXT,
    meta_found INTEGER NOT NULL,
    arabic_rights TEXT NOT NULL DEFAULT 'UNKNOWN',
    english_rights TEXT NOT NULL DEFAULT 'UNKNOWN',
    commercial_status TEXT NOT NULL DEFAULT 'UNKNOWN'
);
"""


def build_inventory(
    priority_list_path: Path = DEFAULT_PRIORITY_LIST,
    db_path: Path = DEFAULT_DB_PATH,
    openiti_dir: Path = OPENITI_DIR,
    limit: int = DEFAULT_BUILD_LIMIT,
) -> dict[str, Any]:
    """Build (or rebuild) the inventory DB for the top `limit` priority URIs.

    Returns a small run report: rows ingested, meta hit-rate, elapsed time.
    """
    all_uris = load_priority_uris(priority_list_path)
    target_uris = all_uris[:limit]

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DROP TABLE IF EXISTS works")
        conn.execute(SCHEMA)

        start = time.monotonic()
        meta_hits = 0
        rows = []
        for rank, uri in enumerate(target_uris, start=1):
            row = build_work_row(uri, rank, openiti_dir)
            if row["meta_found"]:
                meta_hits += 1
            rows.append(row)
        elapsed = time.monotonic() - start

        conn.executemany(
            """
            INSERT INTO works (
                uri, priority_rank, author, title, author_death_ah, genre,
                source_lib_claim, source_evidence, meta_found,
                arabic_rights, english_rights, commercial_status
            ) VALUES (
                :uri, :priority_rank, :author, :title, :author_death_ah, :genre,
                :source_lib_claim, :source_evidence, :meta_found,
                :arabic_rights, :english_rights, :commercial_status
            )
            """,
            rows,
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "total_priority_uris": len(all_uris),
        "works_ingested": len(target_uris),
        "meta_hits": meta_hits,
        "meta_hit_rate": meta_hits / len(target_uris) if target_uris else 0.0,
        "elapsed_seconds": elapsed,
    }


def compute_resolver_coverage(
    db_path: Path = DEFAULT_DB_PATH, sample_size: int = RESOLVER_COVERAGE_SAMPLE
) -> dict[str, Any]:
    """Resolver coverage on the top-`sample_size` priority URIs already in the DB."""
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            "SELECT source_lib_claim FROM works WHERE priority_rank <= ? ORDER BY priority_rank",
            (sample_size,),
        )
        claims = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()

    n = len(claims)
    resolved = sum(1 for c in claims if c)
    return {
        "sample_size": n,
        "resolved": resolved,
        "coverage": resolved / n if n else 0.0,
    }


def compute_source_lib_distribution(db_path: Path = DEFAULT_DB_PATH) -> Counter:
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute("SELECT source_lib_claim FROM works")
        claims = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()
    return Counter(claims)


def gather_stats(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    conn = sqlite3.connect(db_path)
    try:
        total = conn.execute("SELECT COUNT(*) FROM works").fetchone()[0]
        meta_hits = conn.execute("SELECT COUNT(*) FROM works WHERE meta_found = 1").fetchone()[0]
    finally:
        conn.close()

    coverage = compute_resolver_coverage(db_path)
    distribution = compute_source_lib_distribution(db_path)

    return {
        "works_ingested": total,
        "meta_hits": meta_hits,
        "meta_hit_rate": meta_hits / total if total else 0.0,
        "resolver_coverage_top200": coverage,
        "source_lib_distribution": distribution,
    }


def format_stats_report(stats: dict[str, Any], generated_on: str) -> str:
    lines = [
        "# Corpus inventory stats (C6 checkpoints 1-2)",
        "",
        f"Generated on: {generated_on}",
        "",
        f"- Works ingested: {stats['works_ingested']}",
        (
            f"- Metadata hit-rate: {stats['meta_hits']}/{stats['works_ingested']} "
            f"({stats['meta_hit_rate']:.1%})"
        ),
        (
            f"- Resolver coverage (top-{stats['resolver_coverage_top200']['sample_size']}): "
            f"{stats['resolver_coverage_top200']['resolved']}/"
            f"{stats['resolver_coverage_top200']['sample_size']} "
            f"({stats['resolver_coverage_top200']['coverage']:.1%})"
        ),
        "",
        "## Source-library distribution (source_lib_claim, all ingested works)",
        "",
        "| source_lib_claim | count |",
        "|---|---|",
    ]
    for source, count in stats["source_lib_distribution"].most_common():
        label = source if source else "(unresolved)"
        lines.append(f"| {label} | {count} |")
    lines.append("")
    return "\n".join(lines)


def print_stats(stats: dict[str, Any]) -> None:
    print(f"works ingested: {stats['works_ingested']}")
    print(
        f"meta hit-rate: {stats['meta_hits']}/{stats['works_ingested']} "
        f"({stats['meta_hit_rate']:.1%})"
    )
    cov = stats["resolver_coverage_top200"]
    print(f"resolver coverage (top-{cov['sample_size']}): {cov['resolved']}/{cov['sample_size']} ({cov['coverage']:.1%})")
    print("source-library distribution:")
    for source, count in stats["source_lib_distribution"].most_common():
        print(f"  {source or '(unresolved)'}: {count}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="versed_translator.corpus.inventory")
    parser.add_argument(
        "--build", action="store_true", help="(Re)build the inventory DB from the priority list."
    )
    parser.add_argument("--stats", action="store_true", help="Print stats for the current DB.")
    parser.add_argument("--limit", type=int, default=DEFAULT_BUILD_LIMIT)
    parser.add_argument("--priority-list", type=Path, default=DEFAULT_PRIORITY_LIST)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--stats-path", type=Path, default=DEFAULT_STATS_PATH)
    parser.add_argument(
        "--today",
        type=str,
        default=_dt.datetime.now(tz=_dt.timezone.utc).date().isoformat(),
        help="Generated-on date stamped into inventory_stats.md (default: today).",
    )
    args = parser.parse_args(argv)

    if not args.build and not args.stats:
        args.build = True
        args.stats = True

    if args.build:
        report = build_inventory(
            priority_list_path=args.priority_list, db_path=args.db_path, limit=args.limit
        )
        print(
            f"built inventory: {report['works_ingested']} works "
            f"({report['meta_hits']} meta hits, "
            f"{report['meta_hit_rate']:.1%} hit-rate) "
            f"in {report['elapsed_seconds']:.1f}s"
        )

    if args.stats:
        stats = gather_stats(args.db_path)
        print_stats(stats)
        report_text = format_stats_report(stats, args.today)
        args.stats_path.parent.mkdir(parents=True, exist_ok=True)
        args.stats_path.write_text(report_text, encoding="utf-8")
        print(f"wrote {args.stats_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
