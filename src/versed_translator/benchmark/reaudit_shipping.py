"""Blind second-model re-audit of shipping sets.

The first `aligned` verdict (claude-sonnet-5) selected the pair. This pass
uses a different model, does not see that verdict, and records its own.
Not a human audit. Not a random web translation prompt.

    uv run python -m versed_translator.benchmark.reaudit_shipping
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from versed_translator.benchmark.sources import llm_adjudicator

DEFAULT_MODEL = "claude-opus-5"
SOURCES = (
    Path.home() / "versed-translator-data" / "benchmark-alignment" / "miskawayh_eclipse",
    Path.home() / "versed-translator-data" / "benchmark-alignment" / "hariri_assemblies",
)
CONTEXT = (
    "Blind re-audit of a candidate already selected for a Classical Arabic "
    "to English benchmark. You are not shown any prior verdict. Judge whether "
    "this English span translates this Arabic span. Cite order: start, a "
    "middle probe, and the end. Abridgement or extra material on either side "
    "is partial, not aligned. Reply with the JSON object only — do not "
    "continue, quote, or complete the English."
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=llm_adjudicator.DEFAULT_MAX_TOKENS,
        help="thinking+text budget; raise on empty/end_turn or prose dumps",
    )
    parser.add_argument(
        "--retry-errors",
        action="store_true",
        help="re-call pairs whose cached verdict carries an error",
    )
    parser.add_argument(
        "--out-name",
        default="reaudit.jsonl",
        help="filename under each source directory",
    )
    args = parser.parse_args(argv)

    client = None
    for data_dir in SOURCES:
        rows = [
            json.loads(line)
            for line in (data_dir / "passages.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        cache_path = data_dir / "reaudit_verdicts.json"
        cache = (
            json.loads(cache_path.read_text(encoding="utf-8"))
            if cache_path.exists()
            else {}
        )
        out_path = data_dir / args.out_name
        print(f"{data_dir.name}: {len(rows)} shipping pairs", file=sys.stderr)
        results = []
        for index, row in enumerate(rows, 1):
            key = f"{args.model}:{row['id']}"
            cached = cache.get(key)
            if cached and not (args.retry_errors and cached.get("error")):
                verdict = llm_adjudicator.Verdict(**cached)
                fresh = False
            else:
                client = client or llm_adjudicator._get_client()
                verdict = llm_adjudicator.adjudicate(
                    row["arabic"],
                    row.get("english") or row.get("reference_english") or "",
                    model=args.model,
                    max_tokens=args.max_tokens,
                    client=client,
                    context=CONTEXT,
                )
                cache[key] = asdict(verdict)
                cache_path.write_text(
                    json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                fresh = True
            rec = {
                "id": row["id"],
                "source": row.get("source"),
                "band": row.get("band"),
                "first_verdict": (row.get("llm_verdict") or {}).get("verdict"),
                "reaudit_verdict": verdict.verdict or None,
                "reaudit_confidence": verdict.confidence,
                "reaudit_note": verdict.note,
                "reaudit_error": verdict.error,
                "reaudit_model": args.model,
            }
            results.append(rec)
            print(
                f"  [{index}/{len(rows)}] {row['id']}: "
                f"{verdict.verdict or verdict.error} "
                f"({'fresh' if fresh else 'cache'})",
                file=sys.stderr,
            )
        with out_path.open("w", encoding="utf-8") as handle:
            for rec in results:
                handle.write(json.dumps(rec, ensure_ascii=False) + "\n")
        counts: dict[str, int] = {}
        for rec in results:
            counts[rec["reaudit_verdict"] or rec["reaudit_error"] or "empty"] = (
                counts.get(rec["reaudit_verdict"] or rec["reaudit_error"] or "empty", 0)
                + 1
            )
        print(f"{data_dir.name} -> {out_path} {counts}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
