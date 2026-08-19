"""Simulate cascade policies on a silver (or gold) long-format grade CSV.

Oracle policies assume we already know which outputs are publishable.
The implementable policy uses only deterministic checks + glossary retrieve.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from versed_translator.factory.glossary import load_glossary
from versed_translator.factory.router import (
    cascade_after_lite,
    check_output,
    pick_accepted,
    pick_auto,
    source_route,
)


def _ok(row: dict) -> bool:
    return (row.get("publishable") or "").strip().upper() == "Y"


def _prf(pred_fail: list[bool], gold_block: list[bool]) -> dict:
    tp = fp = fn = tn = 0
    for pred, gold in zip(pred_fail, gold_block):
        if pred and gold:
            tp += 1
        elif pred and not gold:
            fp += 1
        elif (not pred) and gold:
            fn += 1
        else:
            tn += 1
    n = tp + fp + fn + tn
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return {
        "n": n,
        "gold_blocking": tp + fn,
        "checker_flagged": tp + fp,
        "tp": tp,
        "fp": fp,
        "fn_escaped": fn,
        "tn": tn,
        "precision": round(prec, 3),
        "recall": round(rec, 3),
        "f1": round(f1, 3),
    }


def _rate(flags: list[bool]) -> dict:
    n = len(flags)
    ok = sum(1 for x in flags if x)
    return {
        "n_passages": n,
        "publishable": ok,
        "escaped_blockers": n - ok,
        "escaped_rate": round((n - ok) / n, 3) if n else 0.0,
    }


def simulate(rows: list[dict], glossary) -> dict:
    by_item: dict[str, dict[str, dict]] = defaultdict(dict)
    for row in rows:
        by_item[row["item_id"]][row["system_id"]] = row

    checker_pred: dict[str, list[bool]] = defaultdict(list)
    checker_gold: dict[str, list[bool]] = defaultdict(list)

    policies = {
        "all_flash": [],
        "all_lite": [],
        "oracle_lite_else_flash": [],
        "source_gate_only": [],
        "checker_auto_keep_both": [],
        "checker_escalate_overwrite": [],
    }
    n_escalate = 0
    n_source_flash = 0
    n_human = 0
    n_auto_flash_after_check = 0

    for systems in by_item.values():
        lite = systems.get("flash_lite") or {}
        flash = systems.get("flash") or {}
        lite_ok, flash_ok = _ok(lite), _ok(flash)
        hint = lite.get("register_hint") or flash.get("register_hint") or ""
        book = lite.get("source") or flash.get("source") or ""
        arabic = lite.get("arabic") or flash.get("arabic") or ""
        lite_en = lite.get("translation") or ""
        flash_en = flash.get("translation") or ""

        for sid, rec in systems.items():
            fails = check_output(
                rec.get("arabic") or arabic,
                rec.get("translation") or "",
                book=rec.get("source") or book,
                glossary=glossary,
            )
            checker_pred[sid].append(bool(fails))
            checker_gold[sid].append(not _ok(rec))

        src = source_route(hint)
        if src.primary == "flash":
            n_source_flash += 1
        decision = cascade_after_lite(
            arabic, lite_en, register_hint=hint, book=book, glossary=glossary
        )
        flash_fails = check_output(
            arabic, flash_en, book=book, glossary=glossary
        )
        if decision.escalate:
            n_escalate += 1

        auto_sys, queue = pick_auto(decision, flash_check_fails=flash_fails)
        if queue == "human":
            n_human += 1
        if auto_sys == "flash" and decision.escalate:
            n_auto_flash_after_check += 1

        auto_ok = flash_ok if auto_sys == "flash" else lite_ok
        # Human queue: treat as caught (not escaped) for the factory metric.
        shipped_if_human_catches = True if queue == "human" else auto_ok
        overwrite_ok = flash_ok if decision.escalate else lite_ok
        if src.primary == "flash":
            overwrite_ok = flash_ok

        oracle_sys = pick_accepted(decision, lite_ok=lite_ok, flash_ok=flash_ok)

        policies["all_flash"].append(flash_ok)
        policies["all_lite"].append(lite_ok)
        policies["oracle_lite_else_flash"].append(bool(lite_ok or flash_ok))
        policies["source_gate_only"].append(
            flash_ok if src.primary == "flash" else lite_ok
        )
        policies["checker_auto_keep_both"].append(shipped_if_human_catches)
        policies["checker_escalate_overwrite"].append(overwrite_ok)
        _ = oracle_sys

    lite_conf = _prf(checker_pred.get("flash_lite", []), checker_gold.get("flash_lite", []))
    flash_conf = _prf(checker_pred.get("flash", []), checker_gold.get("flash", []))
    all_pred, all_gold = [], []
    for sid, preds in checker_pred.items():
        all_pred.extend(preds)
        all_gold.extend(checker_gold[sid])

    n = len(policies["all_lite"])
    return {
        "label_quality": "silver_fable",
        "train_eligible": False,
        "n_passages": n,
        "n_escalate_checker": n_escalate,
        "n_source_gate_flash": n_source_flash,
        "n_human_queue": n_human,
        "n_auto_flash_after_lite_fail": n_auto_flash_after_check,
        "checker_vs_fable": {
            "flash_lite": lite_conf,
            "flash": flash_conf,
            "all_systems": _prf(all_pred, all_gold),
            "note": (
                "fn_escaped = checker clean and Fable N. That is the "
                "publication-risk the cascade would auto-ship. Precision "
                "is false escalations (extra Flash/human cost)."
            ),
        },
        "policies": {name: _rate(vals) for name, vals in policies.items()},
        "note": (
            "oracle_lite_else_flash assumes we already know which Lite rows "
            "are safe — not implementable. checker_auto_keep_both ships Lite "
            "when checks are clean; if Lite fails and Flash checks are clean, "
            "ships Flash; if both look dirty, queues a human and counts those "
            "as caught. checker_escalate_overwrite always replaces Lite with "
            "Flash on a check fail (unsafe: errors are non-nested). "
            "n_source_gate_flash counts verse/sajʿ/metalinguistic items."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--grades", type=Path, required=True)
    parser.add_argument("--glossary", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    with args.grades.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    glossary = load_glossary(args.glossary)
    report = simulate(rows, glossary)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
