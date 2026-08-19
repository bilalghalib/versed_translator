"""Normalize r1a glossary candidates, audit sample, and same-book holdout ids."""

from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path

from versed_translator.benchmark.compare_page import SAMPLE_14
from versed_translator.benchmark.fable_export import load_jsonl
from versed_translator.factory.glossary import load_glossary, write_candidates_csv

DISAGREEMENT_ITEM = "baladhuri_hitti:s32-a000_001-e000_002"
MAJOR_FLAGS = (
    "ENTITY",
    "NUMBER",
    "ROLE",
    "TERM",
    "OMISSION",
    "ADDITION",
    "MISSING",
    "OK",
)
SYSTEMS = ("flash_lite", "flash", "tg27b", "qwen")


def _flag_set(row: dict) -> set[str]:
    raw = (row.get("blocking_flags") or "").replace(",", "|")
    return {p.strip() for p in raw.split("|") if p.strip()}


def select_audit_rows(rows: list[dict], n: int = 24) -> list[dict]:
    """Stratified 20–24 outputs: disagreement, Y and N, each flag, each system."""
    selected: list[dict] = []
    seen: set[str] = set()

    def take(row: dict) -> None:
        rid = row.get("row_id") or f"{row['item_id']}:{row['system_id']}"
        if rid not in seen:
            selected.append(row)
            seen.add(rid)

    for row in rows:
        if row["item_id"] == DISAGREEMENT_ITEM and row["system_id"] in {
            "flash_lite",
            "flash",
        }:
            take(row)

    for flag in MAJOR_FLAGS:
        for row in rows:
            if flag in _flag_set(row):
                take(row)
                break

    for sid in SYSTEMS:
        for want in ("Y", "N"):
            for row in rows:
                if (
                    row["system_id"] == sid
                    and (row.get("publishable") or "").strip().upper() == want
                ):
                    take(row)
                    break

    for row in rows:
        if len(selected) >= n:
            break
        take(row)
    return selected[:n]


def pick_holdout_ids(
    items: dict[str, dict],
    *,
    exclude: set[str],
    n_baladhuri: int = 16,
    n_khallikan: int = 8,
    seed: int = 20260816,
) -> list[str]:
    rng = random.Random(seed)
    by_source: dict[str, list[str]] = {
        "baladhuri_hitti": [],
        "ibn_khallikan_deslane": [],
    }
    for item_id, item in items.items():
        if item_id in exclude:
            continue
        src = item.get("source") or ""
        if src in by_source:
            by_source[src].append(item_id)
    chosen: list[str] = []
    for src, n in (
        ("baladhuri_hitti", n_baladhuri),
        ("ibn_khallikan_deslane", n_khallikan),
    ):
        pool = sorted(by_source[src])
        if len(pool) < n:
            raise ValueError(f"{src} has {len(pool)} unseen ids, need {n}")
        rng.shuffle(pool)
        chosen.extend(pool[:n])
    return chosen


def write_holdout_jsonl(
    path: Path, items: dict[str, dict], ids: list[str]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for item_id in ids:
            item = items[item_id]
            fh.write(
                json.dumps(
                    {
                        "id": item_id,
                        "source": item.get("source"),
                        "genre": item.get("genre"),
                        "band": item.get("band"),
                        "arabic": item.get("arabic"),
                        "rights_status": item.get("rights_status"),
                        "split": "glossary_holdout_unseen",
                        "note": "not in r1a or SAMPLE_14; 2x2 glossary experiment",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )


def write_audit_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    extra = [
        "human_publishable",
        "human_blocking_flags",
        "human_notes",
        "agree_with_fable",
    ]
    fieldnames = list(rows[0].keys()) + [
        c for c in extra if c not in rows[0]
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            out = dict(row)
            for col in extra:
                out.setdefault(col, "")
            writer.writerow(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mined-glossary", type=Path, required=True)
    parser.add_argument("--grades", type=Path, required=True)
    parser.add_argument("--eval-jsonl", type=Path, required=True)
    parser.add_argument("--r1a-ids", type=Path, required=True, help="manifest json")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)

    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)

    entries = load_glossary(args.mined_glossary)
    write_candidates_csv(out / "glossary_candidates.csv", entries)

    with args.grades.open(encoding="utf-8", newline="") as fh:
        grades = list(csv.DictReader(fh))
    write_audit_csv(out / "audit_r1a_24.csv", select_audit_rows(grades, 24))

    manifest = json.loads(args.r1a_ids.read_text(encoding="utf-8"))
    fable_ids = set(manifest["item_ids"])
    items = load_jsonl(args.eval_jsonl)
    holdout = pick_holdout_ids(
        items, exclude=fable_ids | set(SAMPLE_14)
    )
    write_holdout_jsonl(out / "glossary_holdout_24.jsonl", items, holdout)
    print(
        json.dumps(
            {
                "glossary_candidates": len(entries),
                "audit_rows": 24,
                "holdout_ids": holdout,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
