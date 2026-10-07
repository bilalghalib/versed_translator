#!/usr/bin/env python3
"""
One-time helper for whale-lane routing:

1) Recheck the 23 `M2_REMAINDER_CANDIDATE` books on the Nautilus coordinator.
2) If a book has active leases, skip it (leave it untouched).
3) Otherwise, in a short transaction, flip only `status='pending'` rows
   for that book to `status='archived'` (non-claimable).
4) After commit, export the flipped rows (chunk_id/payload/hashes/etc)
   to Descent as compressed JSONL.

This script is intentionally narrow/surgical: it mutates Nautilus rows
only for the explicitly provided book list, and it never deletes rows or
attempts any Wayway import.
"""

from __future__ import annotations

import argparse
import base64
import csv
import datetime as dt
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterable


PREPARED_ROW_FIELDS = (
    "chunk_id",
    "batch_label",
    "book_relpath",
    "book_uri",
    "language",
    "block_sequence",
    "source_hash",
    "settings_hash",
    "job_payload_json",
    "status",
    "audio_sha256",
    "audio_size_bytes",
    "audio_format",
    "json_sha256",
    "completed_at",
    "audio_duration_ms",
    "updated_at",
)


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _b64_job_payload(value: Any) -> str:
    # Stored in sqlite as TEXT affinity but practically bytes (zlib payload).
    if value is None:
        raise ValueError("job_payload_json is None")
    if isinstance(value, (bytes, bytearray)):
        raw = bytes(value)
    elif isinstance(value, memoryview):
        raw = value.tobytes()
    else:
        # Best-effort: accept already base64-ish strings by encoding the bytes.
        raw = str(value).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def zstd_jsonl_writer(out_path: Path):
    """
    Returns a callable `write_line(str)` that streams through `zstd`.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    f = out_path.open("wb")
    proc = subprocess.Popen(
        ["zstd", "-q", "-T0", "-c"],
        stdin=subprocess.PIPE,
        stdout=f,
        stderr=subprocess.PIPE,
    )

    def write_line(line: str) -> None:
        assert proc.stdin is not None
        proc.stdin.write(line.encode("utf-8"))
        proc.stdin.write(b"\n")

    def close() -> None:
        assert proc.stdin is not None
        proc.stdin.close()
        code = proc.wait(timeout=300)
        f.close()
        if code != 0:
            err = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
            raise RuntimeError(f"zstd failed code={code}: {err[:300]}")

    return write_line, close


def read_book_uris(csv_path: Path) -> list[str]:
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    # `wayway_existing_whales.csv` created by this run includes book_uri column.
    if "book_uri" not in rows[0]:
        raise ValueError(f"Missing book_uri column in {csv_path}")
    return [r["book_uri"].strip() for r in rows if r.get("book_uri", "").strip()]


def query_one_int(con: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> int:
    return int(con.execute(sql, params).fetchone()[0])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--coordinator-db", required=True, help="absolute path to catalog-coordinator.sqlite3")
    ap.add_argument("--books-csv", required=True, help="CSV with a book_uri column (wayway_existing_whales.csv)")
    ap.add_argument("--out-dir", required=True, help="SSD destination root for exports")
    ap.add_argument("--receipt-jsonl", required=True, help="append-only receipt file")
    args = ap.parse_args()

    coordinator_db = Path(args.coordinator_db)
    books_csv = Path(args.books_csv)
    out_dir = Path(args.out_dir)
    receipt = Path(args.receipt_jsonl)

    if not coordinator_db.exists():
        raise SystemExit(f"coordinator db missing: {coordinator_db}")
    if not books_csv.exists():
        raise SystemExit(f"books csv missing: {books_csv}")

    book_uris = read_book_uris(books_csv)
    if len(book_uris) != 23:
        print(f"WARNING: expected 23 book_uris, got {len(book_uris)}", file=sys.stderr)

    now_epoch = time.time()
    print(f"Loaded {len(book_uris)} candidate books", flush=True)
    print(f"Active-lease cutoff now_epoch={now_epoch}", flush=True)

    con = sqlite3.connect(f"file:{coordinator_db}?mode=rw", uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=30000")
    con.execute("PRAGMA foreign_keys = ON")

    exported_total_jobs = 0
    exported_total_payload_bytes = 0
    delegated_total_books = 0
    skipped_active_lease = 0

    with receipt.open("a", encoding="utf-8") as recf:
        for idx, book_uri in enumerate(book_uris, 1):
            print(f"[{idx}/{len(book_uris)}] book_uri={book_uri}", flush=True)

            active_leased = query_one_int(
                con,
                """
                SELECT COUNT(*)
                FROM catalog_jobs
                WHERE book_uri=? AND status='leased' AND lease_expires_at>?
                """,
                (book_uri, now_epoch),
            )

            if active_leased > 0:
                skipped_active_lease += 1
                entry = {
                    "book_uri": book_uri,
                    "skipped": True,
                    "reason": "active_leases_present",
                    "active_leased_rows": active_leased,
                    "at": utc_now_iso(),
                }
                recf.write(json.dumps(entry) + "\n")
                print(f"  SKIP active leased rows={active_leased}", flush=True)
                continue

            # Short transaction: flip pending -> archived for this book.
            updated_at = utc_now_iso()
            with con:
                con.execute("BEGIN IMMEDIATE")
                cur = con.execute(
                    """
                    UPDATE catalog_jobs
                    SET status='archived',
                        lease_owner=NULL,
                        lease_token_hash=NULL,
                        lease_expires_at=NULL,
                        updated_at=?
                    WHERE book_uri=? AND status='pending'
                    """,
                    (updated_at, book_uri),
                )
                pending_to_archived = int(cur.rowcount)

            # Now export exactly what we just flipped:
            # (filter by updated_at so we never touch previously-archived rows)
            rows = con.execute(
                f"""
                SELECT {', '.join(PREPARED_ROW_FIELDS)}
                FROM catalog_jobs
                WHERE book_uri=? AND status='archived' AND updated_at=?
                """,
                (book_uri, updated_at),
            ).fetchall()

            if len(rows) != pending_to_archived:
                raise RuntimeError(
                    f"export count mismatch for {book_uri}: "
                    f"updated rows={pending_to_archived} exported rows={len(rows)}"
                )

            payload_bytes = int(
                con.execute(
                    """
                    SELECT COALESCE(SUM(LENGTH(job_payload_json)), 0)
                    FROM catalog_jobs
                    WHERE book_uri=? AND status='archived' AND updated_at=?
                    """,
                    (book_uri, updated_at),
                ).fetchone()[0]
            )

            export_subdir = out_dir / "existing-whales"
            out_path = export_subdir / f"{book_uri}.jsonl.zst"

            write_line, close = zstd_jsonl_writer(out_path)

            for r in rows:
                job_payload_b64 = _b64_job_payload(r["job_payload_json"])
                # Export rows as "pending" for Wayway ingest (workers claim pending).
                row_out = {
                    **{k: r[k] for k in PREPARED_ROW_FIELDS if k != "job_payload_json"},
                    "job_payload_json": job_payload_b64,
                    "status": "pending",
                }
                write_line(json.dumps(row_out, ensure_ascii=False))

            close()
            exported_total_jobs += len(rows)
            exported_total_payload_bytes += payload_bytes
            delegated_total_books += 1

            entry = {
                "book_uri": book_uri,
                "skipped": False,
                "source_transition": {"pending": pending_to_archived, "to": "archived"},
                "exported_rows": len(rows),
                "exported_payload_bytes": payload_bytes,
                "export_path": str(out_path),
                "updated_at": updated_at,
                "at": utc_now_iso(),
            }
            recf.write(json.dumps(entry) + "\n")
            print(f"  delegated rows={pending_to_archived} exported={len(rows)} bytes={payload_bytes/1e6:.1f}MB", flush=True)

    con.close()

    print("\n=== RECEIPT SUMMARY ===", flush=True)
    print(f"Delegated/exported books: {delegated_total_books}/{len(book_uris)}", flush=True)
    print(f"Skipped due to active leases: {skipped_active_lease}", flush=True)
    print(f"Total exported jobs: {exported_total_jobs:,}", flush=True)
    print(f"Total exported payload bytes: {exported_total_payload_bytes/1e9:.2f} GB", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

