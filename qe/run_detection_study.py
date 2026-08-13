#!/usr/bin/env python3
"""Run the C4 detection study: corrupt C2 translations, score with COMETKiwi.

Usage:
    uv run python qe/run_detection_study.py \
        --run-dir ~/versed-translator-data/runs/<run> \
        --items ~/versed-translator-data/benchmark-data/v0.1-draft/dev_bakeoff.jsonl \
        --out-dir ~/versed-translator-data/qe/<name> \
        [--limit 40]

Writes detection_matrix.{json,md} plus scored_pairs.jsonl (raw per-pair
deltas, so the threshold can be re-analysed without re-scoring).

Data stays outside the repo: source Arabic and translations are corpus text
under NC/eval-only terms, so only aggregate reports may ever be committed.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from versed_translator.qe import detection_matrix as dm  # noqa: E402


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True, help="harness run dir with results.jsonl")
    ap.add_argument("--items", required=True, help="benchmark items jsonl (source Arabic)")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--limit", type=int, default=None, help="cap distinct items (smoke runs)")
    ap.add_argument("--threshold", type=float, default=0.02)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    run_dir = Path(args.run_dir).expanduser()
    out_dir = Path(args.out_dir).expanduser()

    items = {r["id"]: r.get("arabic", "") for r in load_jsonl(Path(args.items).expanduser())}
    rows = load_jsonl(run_dir / "results.jsonl")
    translations = {
        r["item_id"]: r.get("translation") or ""
        for r in rows
        if not r.get("error") and (r.get("translation") or "").strip()
    }
    print(f"[study] {len(translations)} clean translations, {len(items)} source items")

    pairs = dm.build_pairs(items, translations, seed=args.seed, limit=args.limit)
    by_injector: dict[str, int] = {}
    for _i, _s, inj in pairs:
        by_injector[inj.injector] = by_injector.get(inj.injector, 0) + 1
    print(f"[study] {len(pairs)} corrupted pairs across {len(by_injector)} error types")
    for name, n in sorted(by_injector.items(), key=lambda kv: -kv[1]):
        print(f"          {name:28s} {n}")
    missing = sorted(set(dm.inject_all.__globals__["INJECTORS"]) - set(by_injector))
    if missing:
        # Not a failure: some corruptions need material this corpus slice
        # lacks (no Qur'anic citation, no paragraph breaks). Say so plainly
        # rather than letting the matrix imply those types were tested.
        print(f"[study] NOT EXERCISED on this slice ({len(missing)}): {', '.join(missing)}")

    print(f"[study] loading {dm.DEFAULT_QE_MODEL} (first run downloads ~2.3GB) ...")
    t0 = time.monotonic()
    scorer = dm.load_cometkiwi(batch_size=args.batch_size)
    print(f"[study] model ready in {time.monotonic() - t0:.1f}s; scoring {2 * len(pairs)} segments")

    t1 = time.monotonic()
    scored = dm.score_pairs(pairs, scorer)
    print(f"[study] scored in {time.monotonic() - t1:.1f}s")

    summary = dm.summarize(scored, threshold=args.threshold)
    summary["source_run"] = run_dir.name
    summary["qe_model"] = dm.DEFAULT_QE_MODEL
    summary["not_exercised"] = missing

    dm.write_reports(summary, out_dir, title=f"QE Detection Matrix — {run_dir.name}")
    dm.write_scored_pairs(scored, out_dir / "scored_pairs.jsonl")

    print(f"\n[study] overall detection rate: {summary['overall_detection_rate']}")
    print("[study] worst-detected error types:")
    for row in summary["by_injector"][:5]:
        print(f"          {row['injector']:28s} rate={row['detection_rate']:<8} "
              f"mean_delta={row['mean_delta']:<10} ({row['severity']})")
    print(f"\n[study] reports -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
