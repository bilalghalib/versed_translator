#!/usr/bin/env python3
"""Run the C4 detection study: corrupt C2 translations, score with a QE model.

Usage:
    uv run python qe/run_detection_study.py \
        --run-dir ~/versed-translator-data/runs/<run> \
        --items ~/versed-translator-data/benchmark-data/v0.1-draft/dev_bakeoff.jsonl \
        --out-dir ~/versed-translator-data/qe/<name> \
        [--qe-model cometkiwi|metricx] [--limit 40]

Writes detection_matrix.{json,md} plus scored_pairs.jsonl (raw per-pair
deltas, so the threshold can be re-analysed without re-scoring).

Two backends, and their numbers are NOT interchangeable. COMETKiwi scores on
[0, 1]; MetricX is negated into [-25, 0] so higher-is-better holds for both,
but a delta of 0.5 means very different things on the two scales. The default
`--threshold` therefore follows `--qe-model` (see
`detection_matrix.DEFAULT_THRESHOLDS`); pass `--threshold` only if you mean to
override that, and never reuse one model's number for the other.

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

from versed_translator.qe import detection_matrix as dm


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True, help="harness run dir with results.jsonl")
    ap.add_argument("--items", required=True, help="benchmark items jsonl (source Arabic)")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--limit", type=int, default=None, help="cap distinct items (smoke runs)")
    ap.add_argument(
        "--qe-model",
        choices=sorted(dm.QE_MODEL_IDS),
        default="cometkiwi",
        help="which reference-free QE backend to score with",
    )
    ap.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="delta counted as 'detected'; defaults per --qe-model "
        f"({dm.DEFAULT_THRESHOLDS})",
    )
    ap.add_argument(
        "--metricx-model",
        default=dm.DEFAULT_METRICX_MODEL,
        help="HF id or local path (a local path avoids the HF symlink cache, "
        "which SMB volumes reject)",
    )
    ap.add_argument(
        "--metricx-tokenizer",
        default=dm.DEFAULT_METRICX_TOKENIZER,
        help="mT5 tokenizer matching the MetricX size; HF id or local path",
    )
    ap.add_argument(
        "--device",
        default=None,
        help="metricx only: torch device (e.g. cpu, mps, cuda). Default picks "
        "cuda if present, else cpu — MPS stays opt-in because its numerics on "
        "mT5 have not been validated here",
    )
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    run_dir = Path(args.run_dir).expanduser()
    out_dir = Path(args.out_dir).expanduser()
    threshold = (
        args.threshold
        if args.threshold is not None
        else dm.DEFAULT_THRESHOLDS[args.qe_model]
    )

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

    if args.qe_model == "metricx":
        model_id = args.metricx_model
        print(f"[study] loading MetricX {model_id} (first run downloads ~4.9GB) ...")
        t0 = time.monotonic()
        scorer = dm.load_metricx(
            model_name=model_id,
            tokenizer_name=args.metricx_tokenizer,
            batch_size=args.batch_size,
            device=args.device,
            progress_every=64,
        )
        # Reported scores are NEGATED MetricX error scores (higher = better).
        # Stamped into the summary so nobody reading the JSON later mistakes
        # the sign for a bug and "fixes" it.
        score_note = (
            "MetricX-24 error score on [0,25] (lower=better), NEGATED to "
            "[-25,0] so higher=better like COMETKiwi. Deltas are in MetricX "
            "points; do not compare to COMETKiwi deltas."
        )
    else:
        model_id = dm.DEFAULT_QE_MODEL
        print(f"[study] loading {model_id} (first run downloads ~2.3GB) ...")
        t0 = time.monotonic()
        scorer = dm.load_cometkiwi(batch_size=args.batch_size)
        score_note = "COMETKiwi score on [0,1], higher=better."
    print(f"[study] model ready in {time.monotonic() - t0:.1f}s; scoring {2 * len(pairs)} segments")

    t1 = time.monotonic()
    scored = dm.score_pairs(pairs, scorer)
    elapsed = time.monotonic() - t1
    print(f"[study] scored in {elapsed:.1f}s ({elapsed / max(2 * len(pairs), 1):.2f}s/segment)")

    # Plausibility guard. A model that fails to load its head, or a batching
    # bug, can still return the right *number* of scores — all identical.
    # A clean exit code and a full row count are compatible with total
    # failure, so say so loudly rather than writing a confident 0% matrix.
    all_scores = [s.clean_score for s in scored] + [s.corrupted_score for s in scored]
    distinct = len({round(v, 6) for v in all_scores})
    print(
        f"[study] score range [{min(all_scores):.4f}, {max(all_scores):.4f}], "
        f"{distinct} distinct values over {len(all_scores)} segments"
    )
    if distinct <= 2:
        print("[study] WARNING: scores are near-constant — this is a bug, not a finding.")

    summary = dm.summarize(scored, threshold=threshold)
    summary["source_run"] = run_dir.name
    summary["qe_backend"] = args.qe_model
    summary["qe_model"] = model_id
    summary["score_note"] = score_note
    summary["score_min"] = round(min(all_scores), 5)
    summary["score_max"] = round(max(all_scores), 5)
    summary["distinct_scores"] = distinct
    summary["scoring_seconds"] = round(elapsed, 1)
    summary["not_exercised"] = missing
    n_trunc = getattr(scorer, "truncated", None)
    if n_trunc is not None:
        n_seen = getattr(scorer, "scored", 0) or 1
        summary["truncated_inputs"] = n_trunc
        summary["truncated_fraction"] = round(n_trunc / n_seen, 4)
        if n_trunc:
            # Length-increasing injectors get truncated more often than their
            # clean counterparts, which pulls their deltas toward (or below)
            # zero. Any row read from this matrix has to be read against this
            # number.
            print(
                f"[study] CAVEAT: {n_trunc}/{n_seen} inputs truncated at the "
                "model's token cap; deltas for length-increasing injectors "
                "(duplicate_sentence, hallucinate_prose) are biased low."
            )

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
