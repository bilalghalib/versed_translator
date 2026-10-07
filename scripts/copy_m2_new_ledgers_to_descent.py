#!/usr/bin/env python3
"""
One-time ledger staging:

Copy only the 141 usable `edition.sqlite3` ledgers for the `M2_NEW` whale set
from Hikma into the Descent SSD in a layout compatible with the existing
`CatalogCoordinator` prepare path.

Manifest columns:
book_uri,source_path,destination_path,bytes,status,error
"""

from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def run(cmd: list[str]) -> None:
    subprocess.check_call(cmd)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--m2-new-books-csv",
        required=True,
        help="CSV with book_uri column (m2_new_whales.csv)",
    )
    ap.add_argument(
        "--ledgers-tsv",
        required=True,
        help="census ledgers.tsv with columns: ledger_bytes, book_uri, ledger_path ...",
    )
    ap.add_argument(
        "--dest-catalog-root",
        required=True,
        help="SSD root where we will create dest-books-root = <dest>/books",
    )
    ap.add_argument(
        "--manifest-out",
        required=True,
        help="CSV manifest path on the SSD",
    )
    ap.add_argument("--bwlimit", default="40M", help="rsync --bwlimit (e.g. 40M)")
    ap.add_argument(
        "--rsync-info",
        default="progress2",
        help="rsync info level; 'none' disables verbosity",
    )
    args = ap.parse_args()

    m2_new_csv = Path(args.m2_new_books_csv)
    ledgers_tsv = Path(args.ledgers_tsv)
    dest_catalog_root = Path(args.dest_catalog_root)
    manifest_out = Path(args.manifest_out)

    resume = manifest_out.exists() and manifest_out.stat().st_size > 0

    if not m2_new_csv.exists():
        raise SystemExit(f"missing m2-new csv: {m2_new_csv}")
    if not ledgers_tsv.exists():
        raise SystemExit(f"missing ledgers tsv: {ledgers_tsv}")

    m2_book_uris = []
    with m2_new_csv.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows or "book_uri" not in rows[0]:
        raise SystemExit("m2_new csv missing book_uri column")
    m2_book_uris = [r["book_uri"].strip() for r in rows if r.get("book_uri", "").strip()]

    ledgers: dict[str, tuple[str, int]] = {}
    with ledgers_tsv.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for r in reader:
            bu = (r.get("book_uri") or "").strip()
            if not bu:
                continue
            ledger_path = (r.get("ledger_path") or "").strip()
            ledger_bytes = int(r.get("ledger_bytes") or "0")
            if ledger_path and ledger_bytes > 0:
                ledgers[bu] = (ledger_path, ledger_bytes)

    dest_books_root = (dest_catalog_root / "books").resolve()
    dest_books_root.mkdir(parents=True, exist_ok=True)
    manifest_out.parent.mkdir(parents=True, exist_ok=True)

    copied = 0
    skipped = 0
    missing = 0
    errors = 0
    total_bytes = 0

    with manifest_out.open(
        "a" if resume else "w", encoding="utf-8", newline=""
    ) as f:
        w = csv.writer(f)
        if not resume:
            w.writerow(
                [
                    "book_uri",
                    "source_path",
                    "destination_path",
                    "bytes",
                    "status",
                    "error",
                ]
            )
            f.flush()
        for bu in m2_book_uris:
            src = None
            src_bytes = 0
            if bu in ledgers:
                src, src_bytes = ledgers[bu]
            if not src:
                missing += 1
                w.writerow([bu, "", "", 0, "missing_on_hikma", "no edition.sqlite3 ledger found in ledgers.tsv"])
                continue

            ledger_dir = Path(src).parent.name  # "<book_uri--hash>"
            dest = dest_books_root / ledger_dir / "edition.sqlite3"

            status = "copied"
            err = ""
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.exists() and dest.stat().st_size == src_bytes:
                    status = "already_present"
                    skipped += 1
                else:
                    # Conserve IO: low-ish bandwidth and resumable partials.
                    cmd = [
                        "rsync",
                        "-a",
                        "--partial",
                        "--inplace",
                        f"--bwlimit={args.bwlimit}",
                    ]
                    if args.rsync_info.lower() == "none":
                        cmd += ["--info=NONE"]
                    else:
                        cmd += [f"--info={args.rsync_info}"]
                    cmd += [src, str(dest)]
                    run(cmd)
                    if not dest.exists() or dest.stat().st_size != src_bytes:
                        raise RuntimeError(
                            f"size mismatch after rsync src_bytes={src_bytes} dest_bytes={dest.stat().st_size if dest.exists() else None}"
                        )
                    copied += 1
                total_bytes += src_bytes
            except Exception as e:  # noqa: BLE001
                errors += 1
                status = "error"
                err = str(e)[:300]
            w.writerow([bu, src, str(dest), src_bytes, status, err])
            f.flush()

    print("=== COPY SUMMARY ===", flush=True)
    print(f"m2_new books requested: {len(m2_book_uris)}", flush=True)
    print(f"copied: {copied} (already_present counted as skipped)", flush=True)
    print(f"already_present/skipped: {skipped}", flush=True)
    print(f"missing_on_hikma: {missing}", flush=True)
    print(f"errors: {errors}", flush=True)
    print(f"total bytes staged: {total_bytes/1e9:.2f} GB", flush=True)
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

