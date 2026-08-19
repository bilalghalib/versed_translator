"""C6 checkpoint 1 — works inventory.

Builds `corpus/inventory.sqlite`: one row per work drawn from versed's
curated-first OpenITI rollout priority list, enriched from OpenITI
per-work metadata (`meta/<uri>.json`) and the provenance resolver
(`versed_translator.corpus.resolver`).

Usage:
    python -m versed_translator.corpus.inventory --build --limit 250
    python -m versed_translator.corpus.inventory --stats
    python -m versed_translator.corpus.inventory --fetch-pd-english
    python -m versed_translator.corpus.inventory --fetch-train-english
    python -m versed_translator.corpus.inventory --record-pd-files --stats
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

    Rebuilds `works` only. The `translations` table is created if missing and
    left intact — English editions must survive an Arabic-side refresh.

    Returns a small run report: rows ingested, meta hit-rate, elapsed time.
    """
    from versed_translator.corpus import translations as translations_mod

    all_uris = load_priority_uris(priority_list_path)
    target_uris = all_uris if limit <= 0 else all_uris[:limit]

    translations_mod.ensure_schema(db_path)
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

    report: dict[str, Any] = {
        "works_ingested": total,
        "meta_hits": meta_hits,
        "meta_hit_rate": meta_hits / total if total else 0.0,
        "resolver_coverage_top200": coverage,
        "source_lib_distribution": distribution,
    }
    try:
        from versed_translator.corpus import translations as translations_mod

        report["translations"] = translations_mod.translation_stats(db_path)
    except sqlite3.OperationalError:
        pass
    return report


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
    if stats.get("translations"):
        t = stats["translations"]
        lines.extend(
            [
                "## Translations (English editions)",
                "",
                f"- Rows: {t['translations']}",
                f"- Public (wuquf-eligible): {t['public_wuquf']}",
                f"- Train-only (online, not dataset-publish): {t.get('train_ok', 0)}",
                f"- Joined to an OpenITI URI: {t.get('joined_to_openiti', t['translations'])}",
                f"- Distinct OpenITI works with an English row (excl. quarantine): {t.get('unique_openiti_works', '?')}",
                f"- Alias candidates still unverified: {t.get('alias_candidates', '?')}",
                f"- Catalog dupes of PD seed: {t.get('duplicate_pd_seed', '?')}",
                (f"- Local English files recorded: {t.get('files_on_disk', '?')} "
                f"({t.get('files_title_ok', '?')} title-page ok)"),
                (f"- Public editions with a local file: {t.get('public_with_files', '?')}/"
                f"{t.get('public_wuquf', '?')}"),
                f"- By policy: {t['by_policy']}",
                f"- By source: {t['by_source']}",
                "",
            ]
        )
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
    if stats.get("translations"):
        t = stats["translations"]
        print(
            f"translations: {t['translations']} "
            f"({t['public_wuquf']} public_wuquf, {t.get('train_ok', 0)} train_ok)"
        )
        if "unique_openiti_works" in t:
            print(
                f"  joined to OpenITI: {t['joined_to_openiti']} rows / "
                f"{t['unique_openiti_works']} distinct works (excl. quarantine)"
            )
        if t.get("alias_candidates") is not None:
            print(f"  alias candidates: {t['alias_candidates']}")
        if t.get("duplicate_pd_seed") is not None:
            print(f"  duplicate of pd_seed: {t['duplicate_pd_seed']}")
        if t.get("files_on_disk") is not None:
            print(
                f"  local files: {t['files_on_disk']} "
                f"({t.get('files_title_ok', 0)} title-page ok); "
                f"public with file: {t.get('public_with_files', 0)}/"
                f"{t.get('public_wuquf', 0)}"
            )
        print(f"  by policy: {t['by_policy']}")
        print(f"  by source: {t['by_source']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="versed_translator.corpus.inventory")
    parser.add_argument(
        "--build", action="store_true", help="(Re)build the inventory DB from the priority list."
    )
    parser.add_argument("--stats", action="store_true", help="Print stats for the current DB.")
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_BUILD_LIMIT,
        help="Top-N priority URIs (default 250). 0 means the whole list.",
    )
    parser.add_argument(
        "--all",
        dest="limit",
        action="store_const",
        const=0,
        help="Ingest every URI in the priority list (same as --limit 0).",
    )
    parser.add_argument(
        "--load-translations",
        action="store_true",
        help="Load pd_seed + ATHAR + rasaif biblio + open-access catalog into translations.",
    )
    parser.add_argument(
        "--join-gutenberg",
        nargs="?",
        const=True,
        default=False,
        help="Join Gutenberg keyword hits onto OpenITI works (unverified candidates).",
    )
    parser.add_argument(
        "--harvest-ia",
        action="store_true",
        help="Scrape archive.org (OTF/RAS/known translators) and join onto OpenITI works.",
    )
    parser.add_argument(
        "--harvest-ia-more",
        action="store_true",
        help="Append extra IA queries without wiping existing archive.org rows.",
    )
    parser.add_argument(
        "--review-queue",
        action="store_true",
        help="Write alias candidates that still need a title-page read.",
    )
    parser.add_argument(
        "--quarantine-tokens",
        action="store_true",
        help="Mark token-join rows as quarantine (do not count as coverage).",
    )
    parser.add_argument(
        "--mark-duplicates",
        action="store_true",
        help="Flag Gutenberg/IA rows that share a URI with the PD seed.",
    )
    parser.add_argument(
        "--enrich-ia",
        action="store_true",
        help="Fetch archive.org metadata (year / possible-copyright-status) for alias rows.",
    )
    parser.add_argument(
        "--load-rasaif-biblio",
        action="store_true",
        help="Load Al-Ghamdi Rasaif work list as bibliography only (no English text).",
    )
    parser.add_argument(
        "--load-open-access",
        action="store_true",
        help="Load modern free-to-read editions (train_ok unless PD/CC-BY).",
    )
    parser.add_argument(
        "--harvest-wikisource",
        action="store_true",
        help="Join English Wikisource 'Works originally in Arabic' onto OpenITI works.",
    )
    parser.add_argument(
        "--harvest-otf",
        action="store_true",
        help="Scrape Oriental Translation Fund items on archive.org and join them.",
    )
    parser.add_argument(
        "--harvest-hathi",
        nargs="?",
        const=True,
        default=False,
        help="Join a local Hathifile (.txt or .txt.gz). Does not download.",
    )
    parser.add_argument(
        "--download-hathi",
        action="store_true",
        help="Download the latest monthly Hathifile (~1.2GB gzipped) into corpus/cache/hathi/.",
    )
    parser.add_argument(
        "--fetch-pd-english",
        action="store_true",
        help="Download public pd_seed English texts off-repo. Does not stamp rights.",
    )
    parser.add_argument(
        "--record-pd-files",
        action="store_true",
        help="Record off-repo PD English filenames into translation_files. Does not stamp rights.",
    )
    parser.add_argument(
        "--pd-english-dir",
        type=Path,
        default=None,
        help="Destination for --fetch-pd-english (default: ~/versed-translator-data/pd-english).",
    )
    parser.add_argument(
        "--fetch-train-english",
        action="store_true",
        help="Download train-only English (Ithra etc.) off-repo. Does not stamp redistribute_ok.",
    )
    parser.add_argument(
        "--record-train-files",
        action="store_true",
        help="Record train-english filenames into translation_files without wiping pd-english rows.",
    )
    parser.add_argument(
        "--load-outreach",
        action="store_true",
        help="Load corpus/rights_outreach.json (ask/follow-up tracker). Does not stamp translations.",
    )
    parser.add_argument(
        "--outreach-csv",
        nargs="?",
        const=True,
        default=False,
        help="Write the outreach tracker to CSV (default: corpus/rights_outreach.csv).",
    )
    parser.add_argument(
        "--probe-ia",
        action="store_true",
        help="Scrape Archive.org for unfetched PD English and write corpus/cache/probe_hits.json.",
    )
    parser.add_argument(
        "--probe-fetch",
        action="store_true",
        help="With --probe-ia, download fetch-classified djvu.txt into pd-english.",
    )
    parser.add_argument(
        "--probe-limit",
        type=int,
        default=80,
        help="Max IA items to metadata-probe (default 80).",
    )
    parser.add_argument(
        "--train-english-dir",
        type=Path,
        default=None,
        help="Destination for --fetch-train-english (default: ~/versed-translator-data/train-english).",
    )
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

    if (
        not args.build
        and not args.stats
        and not args.load_translations
        and not args.join_gutenberg
        and not args.harvest_ia
        and not args.harvest_ia_more
        and not args.review_queue
        and not args.quarantine_tokens
        and not args.mark_duplicates
        and not args.enrich_ia
        and not args.load_rasaif_biblio
        and not args.load_open_access
        and not args.harvest_wikisource
        and not args.harvest_otf
        and not args.harvest_hathi
        and not args.download_hathi
        and not args.fetch_pd_english
        and not args.record_pd_files
        and not args.fetch_train_english
        and not args.record_train_files
        and not args.load_outreach
        and not args.outreach_csv
        and not args.probe_ia
    ):
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

    if args.load_translations:
        from versed_translator.corpus import translations as translations_mod

        translations_mod.ensure_schema(args.db_path)
        n_pd = translations_mod.load_pd_seed(args.db_path)
        n_athar = translations_mod.load_athar_works(args.db_path)
        n_rasaif = translations_mod.load_rasaif_biblio(args.db_path)
        n_oa = translations_mod.load_open_access(args.db_path)
        from versed_translator.corpus import outreach as outreach_mod

        outreach_mod.ensure_schema(args.db_path)
        n_out = outreach_mod.load_outreach(args.db_path)
        print(
            f"loaded translations: {n_pd} pd_seed, {n_athar} athar, "
            f"{n_rasaif} rasaif_biblio, {n_oa} open_access, {n_out} outreach"
        )

    if args.join_gutenberg:
        from versed_translator.corpus import join as join_mod
        from versed_translator.corpus import translations as translations_mod

        csv_path = (
            Path(args.join_gutenberg)
            if args.join_gutenberg is not True
            else REPO_ROOT / "corpus" / "cache" / "gutenberg" / "pg_catalog.csv"
        )
        hits = translations_mod.gutenberg_keyword_hits(csv_path)
        report = join_mod.load_catalog_hits(
            args.db_path,
            hits,
            source="gutenberg",
            url_for=lambda h: f"https://www.gutenberg.org/ebooks/{h['source_id']}",
        )
        print(
            f"joined gutenberg: {report['joined']} / {report['hits']} "
            f"({report['unmatched']} unmatched)"
        )

    if args.harvest_ia:
        from versed_translator.corpus import join as join_mod

        report = join_mod.harvest_archive_org(args.db_path)
        print(
            f"joined archive.org: {report['joined']} / {report['hits']} "
            f"({report['unmatched']} unmatched)"
        )

    if args.harvest_ia_more:
        from versed_translator.corpus import join as join_mod

        report = join_mod.harvest_archive_org(
            args.db_path,
            queries=join_mod.EXTRA_ARCHIVE_QUERIES,
            replace_source=False,
        )
        print(
            f"appended archive.org: inserted {report.get('inserted', report['joined'])} / "
            f"{report['hits']} ({report['unmatched']} unmatched, "
            f"{report.get('skipped_existing', 0)} already present)"
        )

    if args.load_rasaif_biblio:
        from versed_translator.corpus import translations as translations_mod

        n = translations_mod.load_rasaif_biblio(args.db_path)
        print(f"loaded rasaif bibliography: {n}")

    if args.load_open_access:
        from versed_translator.corpus import translations as translations_mod

        n = translations_mod.load_open_access(args.db_path)
        print(f"loaded open-access catalog: {n}")

    if args.harvest_wikisource:
        from versed_translator.corpus import catalogs

        report = catalogs.harvest_wikisource(args.db_path)
        print(
            f"joined wikisource: {report['joined']} / {report['hits']} "
            f"({report['unmatched']} unmatched)"
        )

    if args.harvest_otf:
        from versed_translator.corpus import catalogs

        report = catalogs.harvest_otf(args.db_path, replace_source=False)
        print(
            f"joined otf: inserted {report.get('inserted', report['joined'])} / "
            f"{report['hits']} ({report['unmatched']} unmatched, "
            f"{report.get('skipped_existing', 0)} already present)"
        )

    if args.download_hathi:
        from versed_translator.corpus import catalogs

        dest = catalogs.DEFAULT_HATHI_DIR / "hathi_full.txt.gz"
        path = catalogs.download_hathi_full(dest)
        print(f"downloaded hathifile: {path} ({path.stat().st_size} bytes)")

    if args.fetch_pd_english:
        from versed_translator.corpus import fetch_pd

        dest = args.pd_english_dir or fetch_pd.DEFAULT_DEST
        report = fetch_pd.fetch_all(dest)
        print(
            f"pd english: fetched {report['fetched']}, "
            f"skipped {report['skipped']}, "
            f"errors {len(report['errors'])} → {report['manifest']}"
        )
        for err in report["errors"]:
            print(f"  error: {err}")
        args.record_pd_files = True
        if report["errors"]:
            fetch_failed = True
        else:
            fetch_failed = False
    else:
        fetch_failed = False

    if args.fetch_train_english:
        from versed_translator.corpus import fetch_pd

        dest = args.train_english_dir or fetch_pd.DEFAULT_TRAIN_DEST
        report = fetch_pd.fetch_all(dest, map_path=fetch_pd.DEFAULT_TRAIN_MAP)
        print(
            f"train english: fetched {report['fetched']}, "
            f"skipped {report['skipped']}, "
            f"errors {len(report['errors'])} → {report['manifest']}"
        )
        for err in report["errors"]:
            print(f"  error: {err}")
        args.record_train_files = True
        if report["errors"]:
            fetch_failed = True

    if args.record_pd_files:
        from versed_translator.corpus import fetch_pd

        dest = args.pd_english_dir or fetch_pd.DEFAULT_DEST
        recorded = fetch_pd.record_pd_files(args.db_path, dest)
        print(
            f"recorded pd files: {recorded['recorded']} "
            f"(missing {recorded['missing']}, unmatched {recorded['unmatched']})"
        )

    if args.record_train_files:
        from versed_translator.corpus import fetch_pd

        dest = args.train_english_dir or fetch_pd.DEFAULT_TRAIN_DEST
        recorded = fetch_pd.record_train_files(args.db_path, dest)
        print(
            f"recorded train files: {recorded['recorded']} "
            f"(missing {recorded['missing']}, unmatched {recorded['unmatched']})"
        )

    if args.harvest_hathi:
        from versed_translator.corpus import catalogs

        if args.harvest_hathi is True:
            cached = catalogs.DEFAULT_HATHI_DIR / "hathi_full.txt.gz"
            if not cached.exists():
                print(
                    "no local Hathifile; download first with "
                    "--download-hathi (~1.2GB gzipped)"
                )
                return 2
            tsv_path = cached
        else:
            tsv_path = Path(args.harvest_hathi)
        report = catalogs.harvest_hathi(args.db_path, tsv_path)
        print(
            f"joined hathitrust: {report['joined']} / {report['hits']} "
            f"({report['unmatched']} unmatched)"
        )

    if args.quarantine_tokens:
        from versed_translator.corpus import join as join_mod

        n = join_mod.quarantine_token_joins(args.db_path)
        print(f"quarantined token joins: {n}")

    if args.mark_duplicates:
        from versed_translator.corpus import join as join_mod

        n = join_mod.mark_pd_seed_duplicates(args.db_path)
        print(f"marked pd-seed duplicates: {n}")

    if args.enrich_ia:
        from versed_translator.corpus import join as join_mod

        n = join_mod.enrich_archive_metadata(args.db_path)
        print(f"enriched archive.org alias rows: {n}")

    if args.review_queue:
        from versed_translator.corpus import join as join_mod

        out = REPO_ROOT / "corpus" / "cache" / "review_queue.json"
        report = join_mod.write_review_queue(args.db_path, out)
        print(f"review queue: {report['editions']} editions across {report['works']} works → {out}")

    if args.load_outreach and not args.load_translations:
        from versed_translator.corpus import outreach as outreach_mod

        n = outreach_mod.load_outreach(args.db_path)
        print(f"loaded outreach: {n}")

    if args.outreach_csv:
        from versed_translator.corpus import outreach as outreach_mod

        dest = (
            Path(args.outreach_csv)
            if args.outreach_csv is not True
            else outreach_mod.DEFAULT_CSV
        )
        path = outreach_mod.write_csv(dest)
        print(f"wrote outreach csv: {path}")

    if args.probe_ia:
        from versed_translator.corpus import probe as probe_mod

        dest = args.pd_english_dir
        report = probe_mod.run_probe(
            fetch=bool(args.probe_fetch),
            pd_dir=dest,
            limit=args.probe_limit,
        )
        summary = report["summary"]
        print(
            "probe ia: "
            f"probed {summary['probed']}, fetch {summary['fetch']}, "
            f"skip {summary['skip']}, have {summary['have']}, "
            f"review {summary['review']}, after-1930 {summary['train_or_skip']}, "
            f"errors {summary['error']}"
        )
        if args.probe_fetch:
            print(f"probe fetch ok: {summary['fetched_ok']}")
        print(f"wrote {report['path']}")

    if args.stats:
        stats = gather_stats(args.db_path)
        print_stats(stats)
        report_text = format_stats_report(stats, args.today)
        args.stats_path.parent.mkdir(parents=True, exist_ok=True)
        args.stats_path.write_text(report_text, encoding="utf-8")
        print(f"wrote {args.stats_path}")

    return 1 if fetch_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
