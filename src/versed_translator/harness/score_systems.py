"""Score reassembled API-bakeoff runs against the frozen 120 and official TG.

Writes counts only (no source/translation text) to stdout JSON.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from versed_translator.harness.score import chrf_score, has_untranslated_arabic


def _rows(path: Path) -> dict[str, dict]:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        out[row["item_id"]] = row
    return out


def _items(path: Path) -> dict[str, dict]:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        out[row["id"]] = row
    return out


def score_systems(items_path: Path, systems: dict[str, Path]) -> dict:
    items = _items(items_path)
    loaded = {name: _rows(path) for name, path in systems.items()}
    all_ok: dict[str, set[str]] = {}
    for name, rows in loaded.items():
        all_ok[name] = {
            i for i, r in rows.items()
            if not r.get("error") and (r.get("translation") or "").strip()
        }
    overlap = set.intersection(*all_ok.values()) if all_ok else set()
    report: dict = {
        "n_items": len(items),
        "per_system": {},
        "overlap_n": len(overlap),
    }
    for name, rows in loaded.items():
        ok = all_ok[name]
        hyps, refs = [], []
        leftover = 0
        for iid in sorted(ok):
            hyp = rows[iid].get("translation") or ""
            ref = items.get(iid, {}).get("reference_english") or ""
            if hyp and ref:
                hyps.append(hyp)
                refs.append(ref)
            if has_untranslated_arabic(hyp):
                leftover += 1
        report["per_system"][name] = {
            "ok": len(ok),
            "errors": len(rows) - len(ok),
            "chrf_ok": chrf_score(hyps, refs),
            "leftover_arabic_ok": leftover,
            "n_scored": len(hyps),
        }
    if overlap:
        for name, rows in loaded.items():
            hyps = [rows[i]["translation"] for i in sorted(overlap)]
            refs = [items[i]["reference_english"] for i in sorted(overlap)]
            leftover = sum(1 for i in overlap if has_untranslated_arabic(rows[i].get("translation")))
            report["per_system"][name]["chrf_overlap"] = chrf_score(hyps, refs)
            report["per_system"][name]["leftover_arabic_overlap"] = leftover
        by_source: dict[str, dict] = {}
        for iid in overlap:
            src = items[iid].get("source") or iid.split(":")[0]
            by_source.setdefault(src, []).append(iid)
        report["overlap_by_source"] = {}
        for src, ids in sorted(by_source.items()):
            report["overlap_by_source"][src] = {"n": len(ids)}
            for name, rows in loaded.items():
                hyps = [rows[i]["translation"] for i in ids]
                refs = [items[i]["reference_english"] for i in ids]
                report["overlap_by_source"][src][name] = chrf_score(hyps, refs)
    return report


def main(argv: list[str] | None = None) -> int:
    # argv: items.jsonl name=path name=path ...
    args = list(sys.argv[1:] if argv is None else argv)
    items_path = Path(args[0])
    systems = {}
    for spec in args[1:]:
        name, _, path = spec.partition("=")
        systems[name] = Path(path)
    print(json.dumps(score_systems(items_path, systems), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
