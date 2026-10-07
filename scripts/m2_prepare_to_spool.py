#!/usr/bin/env python3
"""
One-time M2 prepare lane:

For each book in m2_new_whales.csv whose ledger is present under
`catalog-root/books/`, call CatalogCoordinator.index_book(ingest=False) and
write compressed JSONL spool files for later Wayway ingest.

Output layout (under --spool-dir):
  prepared/<book_uri>.jsonl.zst
  manifests/m2_prepare_progress.csv

Rows are base64 job_payload_json, status pending, matching the existing-whale
export format and the ingest endpoint wire format.
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

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

SETTINGS = {
    "language": "ar",
    "voice_id": "1c3294e9c96b47dc8621dc8b2283bc97",
    "model_id": "s2.1-pro-free",
    "latency": "normal",
    "max_chars": 700,
    "text_projection": "diacritized",
    "batch_label": "cat_next_ar_v1",
    "include_quran_tts": False,
}


def _b64_job_payload(value: Any) -> str:
    if isinstance(value, (bytes, bytearray)):
        raw = bytes(value)
    elif isinstance(value, memoryview):
        raw = value.tobytes()
    else:
        raw = str(value).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def zstd_jsonl_writer(out_path: Path) -> tuple[Callable[[str], None], Callable[[], None]]:
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
        code = proc.wait(timeout=3600)
        f.close()
        if code != 0:
            err = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
            raise RuntimeError(f"zstd failed code={code}: {err[:300]}")

    return write_line, close


def read_progress(path: Path) -> dict[str, str]:
    done: dict[str, str] = {}
    if not path.exists():
        return done
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            bu = (row.get("book_uri") or "").strip()
            st = (row.get("status") or "").strip()
            if bu and st == "done":
                done[bu] = row.get("export_path") or ""
    return done


def append_progress(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists()
    with path.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "book_uri",
                "status",
                "rows",
                "payload_bytes",
                "wall_s",
                "export_path",
                "error",
                "at",
            ],
        )
        if new_file:
            w.writeheader()
        w.writerow(row)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--m2-new-books-csv", required=True)
    ap.add_argument(
        "--catalog-root",
        required=True,
        help="OpenITI catalog root containing books/<dir>/edition.sqlite3",
    )
    ap.add_argument(
        "--spool-dir",
        required=True,
        help="SSD root; writes prepared/ and manifests/ beneath it",
    )
    ap.add_argument(
        "--versed-app-root",
        default=os.environ.get("VERSED_APP_ROOT", ""),
        help="path to versed-app for versed_core imports",
    )
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument(
        "--force",
        action="store_true",
        help="re-prepare even if prepared/<book_uri>.jsonl.zst exists",
    )
    args = ap.parse_args()

    app_root = Path(args.versed_app_root) if args.versed_app_root else None
    if not app_root or not app_root.is_dir():
        raise SystemExit(
            "Set --versed-app-root or VERSED_APP_ROOT to a checkout with versed_core"
        )
    sys.path.insert(0, str(app_root))

    from versed_core.audio.openiti_catalog_sync import (  # noqa: E402
        CatalogCoordinator,
        safe_book_dir,
    )

    m2_csv = Path(args.m2_new_books_csv)
    catalog_root = Path(args.catalog_root)
    spool_dir = Path(args.spool_dir)
    prepared_dir = spool_dir / "prepared"
    progress_csv = spool_dir / "manifests" / "m2_prepare_progress.csv"

    with m2_csv.open("r", encoding="utf-8", newline="") as f:
        book_uris = [
            r["book_uri"].strip()
            for r in csv.DictReader(f)
            if r.get("book_uri", "").strip()
        ]

    done = read_progress(progress_csv)
    coordinator = CatalogCoordinator(catalog_root, min_free_bytes=0)

    prepared_count = skipped = missing = failed = 0
    total_rows = 0

    for idx, book_uri in enumerate(book_uris, 1):
        if args.limit and prepared_count >= args.limit:
            break

        out_path = prepared_dir / f"{book_uri}.jsonl.zst"
        if not args.force and (book_uri in done or out_path.is_file()):
            skipped += 1
            print(f"[{idx}/{len(book_uris)}] {book_uri}: skip (already prepared)", flush=True)
            continue

        book_dir = (
            coordinator.books_root
            / safe_book_dir(catalog_root / ".catalog-selection", book_uri).name
        )
        if not (book_dir / "edition.sqlite3").is_file():
            missing += 1
            append_progress(
                progress_csv,
                {
                    "book_uri": book_uri,
                    "status": "missing_ledger",
                    "rows": 0,
                    "payload_bytes": 0,
                    "wall_s": 0,
                    "export_path": "",
                    "error": str(book_dir),
                    "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                },
            )
            print(f"[{idx}/{len(book_uris)}] {book_uri}: missing ledger", flush=True)
            continue

        print(f"[{idx}/{len(book_uris)}] {book_uri}: preparing...", flush=True)
        t0 = time.monotonic()
        try:
            prepared = coordinator.index_book(
                book_dir,
                ingest=False,
                **SETTINGS,
            )
        except Exception as exc:  # noqa: BLE001
            failed += 1
            append_progress(
                progress_csv,
                {
                    "book_uri": book_uri,
                    "status": "error",
                    "rows": 0,
                    "payload_bytes": 0,
                    "wall_s": round(time.monotonic() - t0, 1),
                    "export_path": "",
                    "error": str(exc)[:300],
                    "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                },
            )
            print(f"  ERROR: {exc}", flush=True)
            continue

        rows = prepared.get("rows") or []
        if not rows:
            append_progress(
                progress_csv,
                {
                    "book_uri": book_uri,
                    "status": "empty",
                    "rows": 0,
                    "payload_bytes": 0,
                    "wall_s": round(time.monotonic() - t0, 1),
                    "export_path": "",
                    "error": prepared.get("reason", "no rows"),
                    "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                },
            )
            print(f"  empty ({prepared.get('reason', 'no rows')})", flush=True)
            continue

        payload_bytes = 0
        write_line, close = zstd_jsonl_writer(out_path)
        for row in rows:
            raw = row["job_payload_json"]
            if isinstance(raw, (bytes, bytearray, memoryview)):
                payload_bytes += len(raw)
            job_payload_b64 = _b64_job_payload(raw)
            row_out = {
                **{k: row[k] for k in PREPARED_ROW_FIELDS if k != "job_payload_json"},
                "job_payload_json": job_payload_b64,
                "status": "pending",
            }
            write_line(json.dumps(row_out, ensure_ascii=False, default=str))
        close()

        wall_s = round(time.monotonic() - t0, 1)
        prepared_count += 1
        total_rows += len(rows)
        append_progress(
            progress_csv,
            {
                "book_uri": book_uri,
                "status": "done",
                "rows": len(rows),
                "payload_bytes": payload_bytes,
                "wall_s": wall_s,
                "export_path": str(out_path),
                "error": "",
                "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
        )
        print(
            f"  done rows={len(rows):,} payload={payload_bytes/1e6:.1f}MB wall_s={wall_s}",
            flush=True,
        )

    print("\n=== M2 PREPARE SUMMARY ===", flush=True)
    print(f"books requested: {len(book_uris)}", flush=True)
    print(f"prepared: {prepared_count}", flush=True)
    print(f"skipped/already: {skipped}", flush=True)
    print(f"missing ledger: {missing}", flush=True)
    print(f"errors: {failed}", flush=True)
    print(f"total rows: {total_rows:,}", flush=True)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
