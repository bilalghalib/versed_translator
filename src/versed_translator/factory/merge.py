"""Verify a Fable sitting and merge round-1 graded CSVs."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from versed_translator.factory.glossary import GlossaryEntry
from versed_translator.factory.prepare import MAJOR_FLAGS
from versed_translator.factory.router import _empty_english

SOURCE_COLS = (
    "row_id",
    "batch_id",
    "item_id",
    "source",
    "genre",
    "band",
    "register_hint",
    "system_id",
    "system_label",
    "arabic",
    "translation",
    "error",
    "arabic_word_count",
    "translation_word_count",
    "length_ratio",
)

BLOCKING = (
    "ENTITY",
    "NUMBER",
    "ROLE",
    "TERM",
    "OMISSION",
    "ADDITION",
    "MISSING",
)

CONFIDENCE = {"high", "med", "low"}


def _load(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _write(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        raise ValueError(f"no rows to write: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _flag_set(raw: str) -> set[str]:
    text = (raw or "").replace(",", "|")
    return {p.strip() for p in text.split("|") if p.strip()}


def _source_value(row: dict, col: str) -> str:
    value = row.get(col) or ""
    if col == "translation" and _empty_english(value):
        return ""
    return value


def verify_graded(sent: list[dict], graded: list[dict]) -> dict:
    """Check 100-row sitting: source identity, Y/N ⇔ flags, filled grades."""
    problems: list[str] = []
    if len(graded) != len(sent):
        problems.append(f"row count graded={len(graded)} sent={len(sent)}")
    sent_by_id = {r["row_id"]: r for r in sent}
    graded_ids = [r.get("row_id") or "" for r in graded]
    if len(set(graded_ids)) != len(graded_ids):
        problems.append("duplicate row_id in graded")
    missing_ids = [rid for rid in sent_by_id if rid not in {r.get("row_id") for r in graded}]
    extra_ids = [rid for rid in graded_ids if rid not in sent_by_id]
    if missing_ids:
        problems.append(f"missing row_ids: {missing_ids[:5]}")
    if extra_ids:
        problems.append(f"extra row_ids: {extra_ids[:5]}")

    empty_outputs: list[str] = []
    yn = Counter()
    by_system = defaultdict(lambda: Counter())
    flag_on_n = Counter()
    confidence = Counter()
    n_source_mismatch = 0

    for row in graded:
        rid = row.get("row_id") or ""
        orig = sent_by_id.get(rid)
        if orig:
            for col in SOURCE_COLS:
                if _source_value(row, col) != _source_value(orig, col):
                    n_source_mismatch += 1
                    problems.append(f"{rid} source col {col} changed")
                    break
        pub = (row.get("publishable") or "").strip().upper()
        flags = _flag_set(row.get("blocking_flags") or "")
        blocking = flags & set(BLOCKING)
        conf = (row.get("confidence") or "").strip().lower()
        yn[pub] += 1
        by_system[row.get("system_id") or ""][pub] += 1
        confidence[conf] += 1
        if pub not in {"Y", "N"}:
            problems.append(f"{rid} publishable={pub!r}")
        if conf not in CONFIDENCE:
            problems.append(f"{rid} confidence={conf!r}")
        if pub == "Y" and blocking:
            problems.append(f"{rid} Y with blocking {sorted(blocking)}")
        if pub == "N" and not blocking:
            problems.append(f"{rid} N with no blocking flags ({sorted(flags)})")
        if pub == "Y" and flags - {"OK"}:
            extra = flags - {"OK"}
            if extra - set(MAJOR_FLAGS):
                # cosmetic-as-blocking mix is allowed only in cosmetic_flags
                problems.append(f"{rid} Y with non-OK blocking_flags {sorted(extra)}")
        if pub == "N":
            for flag in blocking:
                flag_on_n[flag] += 1
        if _empty_english(row.get("translation") or ""):
            empty_outputs.append(f"{rid}:{row.get('system_id')}:{row.get('item_id')}")
            if "MISSING" not in flags and pub != "N":
                problems.append(f"{rid} empty translation not flagged MISSING")

    return {
        "ok": not problems,
        "n_rows": len(graded),
        "n_source_mismatch": n_source_mismatch,
        "publishable": dict(yn),
        "by_system": {k: dict(v) for k, v in sorted(by_system.items())},
        "flags_on_n": dict(flag_on_n),
        "confidence": dict(confidence),
        "empty_outputs": empty_outputs,
        "problems": problems[:40],
        "n_problems": len(problems),
    }


def merge_rounds(*rounds: list[dict]) -> list[dict]:
    merged: list[dict] = []
    seen: set[str] = set()
    for rows in rounds:
        for row in rows:
            rid = row.get("row_id") or ""
            if rid in seen:
                raise ValueError(f"duplicate row_id across rounds: {rid}")
            seen.add(rid)
            merged.append(row)
    return merged


def harvest_term_candidates(
    rows: list[dict], *, source_label: str
) -> list[GlossaryEntry]:
    """TERM spans from a graded sitting → glossary candidates."""
    out: list[GlossaryEntry] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        flags = _flag_set(row.get("blocking_flags") or "")
        ar = (row.get("term_ar") or "").strip()
        should = (row.get("term_en_should") or "").strip()
        wrong = (row.get("term_en_wrong") or "").strip()
        if "TERM" not in flags or len(ar) < 2 or not should:
            continue
        book = (row.get("source") or "").strip()
        key = (ar, should, book)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            GlossaryEntry(
                arabic=ar,
                lemma="",
                en_should=should,
                en_wrong=wrong,
                kind="term",
                book=book,
                item_ids=row.get("item_id") or "",
                status="candidate",
                source_label=source_label,
                train_eligible="false",
            )
        )
    return out


def extend_glossary(
    existing: list[GlossaryEntry], extra: list[GlossaryEntry]
) -> tuple[list[GlossaryEntry], int]:
    seen = {(e.arabic, e.en_should, e.book) for e in existing}
    added = 0
    merged = list(existing)
    for entry in extra:
        key = (entry.arabic, entry.en_should, entry.book)
        if key in seen:
            continue
        seen.add(key)
        merged.append(entry)
        added += 1
    return merged, added


def round_headline(rows: list[dict]) -> dict:
    by_system: dict[str, Counter] = defaultdict(Counter)
    for row in rows:
        pub = (row.get("publishable") or "").strip().upper()
        by_system[row.get("system_id") or ""][pub] += 1
    return {
        sid: {"Y": counts["Y"], "N": counts["N"], "n": counts["Y"] + counts["N"]}
        for sid, counts in sorted(by_system.items())
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sent", type=Path, required=True)
    parser.add_argument("--graded", type=Path, required=True)
    parser.add_argument("--r1a", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)

    sent = _load(args.sent)
    graded = _load(args.graded)
    r1a = _load(args.r1a)
    check = verify_graded(sent, graded)
    if not check["ok"]:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(check, indent=2, ensure_ascii=False) + "\n")
        print(json.dumps(check, indent=2, ensure_ascii=False))
        return 1
    merged = merge_rounds(r1a, graded)
    _write(args.out, merged)
    report = {
        **check,
        "merged_rows": len(merged),
        "merged_item_ids": len({r["item_id"] for r in merged}),
        "r1b_headline": round_headline(graded),
        "r1_headline": round_headline(merged),
        "out": str(args.out),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
