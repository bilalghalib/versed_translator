"""CLI for the C2 translation harness.

    # Segment an items file into ID-bearing blocks (the D2e production unit).
    python -m versed_translator.harness blocks --items <jsonl> --out <blocks.jsonl>

    # Translate. --template defaults to structured_blocks_v1 (D2e).
    python -m versed_translator.harness run --adapter anthropic --model claude-sonnet-5 \
        --items <blocks.jsonl> --out-dir /Volumes/Nodes/versed-translator/runs

    # Join block translations back into one translation per source item.
    python -m versed_translator.harness reassemble --run-dir <block run dir> \
        --items <original items jsonl>

    python -m versed_translator.harness score --run-dir /Volumes/Nodes/versed-translator/runs/<run_id>

    python -m versed_translator.harness ingest-modal --raw <results_raw.jsonl> \
        --template v1 --out-dir /Volumes/Nodes/versed-translator/runs
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from versed_translator.harness import blocks as blocks_mod
from versed_translator.harness import ingest_modal, runner, score
from versed_translator.harness.schema import make_row


def _cmd_run(args: argparse.Namespace) -> int:
    adapter_cfg: dict = {}
    if args.base_url:
        adapter_cfg["base_url"] = args.base_url
    if args.api_key:
        adapter_cfg["api_key"] = args.api_key

    run_meta = runner.run(
        adapter_name=args.adapter,
        model=args.model,
        template_id=args.template,
        items_path=args.items,
        out_dir=args.out_dir,
        batch_size=args.batch_size,
        gpu=args.gpu,
        quantization=args.quantization,
        model_version=args.model_version,
        use_exemplar=args.use_exemplar,
        **adapter_cfg,
    )
    print(json.dumps(run_meta, indent=2))
    return 0


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _cmd_blocks(args: argparse.Namespace) -> int:
    items = runner.load_items(args.items)
    rows = blocks_mod.blockify(items, max_words=args.max_words)
    out_path = Path(args.out).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)

    stats = blocks_mod.block_stats(rows)
    stats["source_items"] = len(items)
    stats["max_words"] = args.max_words
    stats["out"] = str(out_path)
    # A source item that produced no blocks (empty Arabic) would vanish here;
    # say so rather than letting the counts quietly disagree.
    stats["items_with_no_blocks"] = len(items) - stats.get("items", 0)
    print(json.dumps(stats, indent=2))
    return 0


def _cmd_reassemble(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).expanduser()
    rows = _read_jsonl(run_dir / "results.jsonl")
    meta = json.loads((run_dir / "run_meta.json").read_text(encoding="utf-8"))

    # Rows whose item_id is not a block id cannot be reassembled; they are
    # reported, never silently skipped.
    block_rows = [r for r in rows if blocks_mod.is_block_id(r["item_id"])]
    non_block = [r["item_id"] for r in rows if not blocks_mod.is_block_id(r["item_id"])]

    # How many blocks each item SHOULD have, from the block items file the run
    # was given. Without it, a block missing from the END of an item leaves no
    # gap in the index sequence and cannot be detected -- the item would
    # reassemble into a shortened translation marked clean.
    block_items_path = Path(args.block_items).expanduser() if args.block_items else Path(
        str(meta.get("items_path") or "")
    )
    expected_counts = None
    if block_items_path.exists():
        expected_counts = blocks_mod.expected_block_counts(_read_jsonl(block_items_path))
    else:
        print(
            f"WARNING: block items file not found ({block_items_path}); a block "
            "lost from the end of an item cannot be detected. Pass --block-items.",
            file=sys.stderr,
        )

    translations, incomplete = blocks_mod.reassemble(block_rows, expected_counts=expected_counts)

    out_dir = Path(args.out_dir).expanduser() if args.out_dir else run_dir.parent
    new_run_id = args.run_id or f"{run_dir.name}-reassembled"
    new_dir = out_dir / new_run_id
    new_dir.mkdir(parents=True, exist_ok=True)

    parent_ids = sorted(set(translations) | set(incomplete))
    out_rows = []
    for parent_id in parent_ids:
        bad = incomplete.get(parent_id)
        out_rows.append(
            make_row(
                run_id=new_run_id,
                item_id=parent_id,
                model=meta.get("model"),
                model_version=meta.get("model_version"),
                adapter=meta.get("adapter"),
                quantization=meta.get("quantization"),
                prompt_template_id=meta.get("prompt_template_id"),
                batch_size=meta.get("batch_size"),
                gpu=meta.get("gpu"),
                translation=translations.get(parent_id),
                # An item missing any block is an ERROR row, not a shorter
                # translation. Scoring a partial passage as if it were whole
                # is the precise failure structured blocks exist to prevent.
                error=(f"incomplete_blocks:{len(bad)}" if bad else None),
            )
        )
    with open(new_dir / "results.jsonl", "w", encoding="utf-8") as f:
        f.writelines(json.dumps(row, ensure_ascii=False) + "\n" for row in out_rows)

    # Counters measured over BLOCKS are moved under their own key rather than
    # left beside item-level counts they no longer describe: `id_expected: 522`
    # sitting next to `item_count: 139` invites reading one as the other.
    block_metrics = {
        k: meta.pop(k)
        for k in (
            "id_expected", "id_returned", "id_loss_count", "id_unexpected_count",
            "id_preservation_rate", "id_error_rows", "batch_failure_count",
            "id_missing_count", "id_duplicate_count", "structured_empty_count",
            "item_count", "row_count", "error_count",
        )
        if k in meta
    }
    new_meta = dict(meta)
    new_meta.update(
        {
            "run_id": new_run_id,
            "reassembled_from": meta.get("run_id"),
            "item_count": len(out_rows),
            "row_count": len(out_rows),
            "error_count": sum(1 for r in out_rows if r["error"]),
            "incomplete_item_count": len(incomplete),
            "incomplete_block_count": sum(len(v) for v in incomplete.values()),
            "non_block_row_count": len(non_block),
            "block_row_count": len(block_rows),
            "expected_counts_available": expected_counts is not None,
            "block_run_metrics": block_metrics,
        }
    )
    if args.items:
        new_meta["items_path"] = str(Path(args.items).expanduser())
    with open(new_dir / "run_meta.json", "w", encoding="utf-8") as f:
        json.dump(new_meta, f, indent=2)

    print(json.dumps({"run_dir": str(new_dir), "run_meta": new_meta}, indent=2))
    return 0


def _cmd_score(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir)
    results_path = run_dir / "results.jsonl"
    rows = [json.loads(line) for line in results_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    # Reference-based metrics (chrF) need the source items, which live outside
    # the run dir; run_meta.json records where. Without this the report shows
    # chrf: null and silently looks like "no references exist".
    source_texts: dict[str, str] = {}
    reference_texts: dict[str, str] = {}
    meta_path = run_dir / "run_meta.json"
    if meta_path.exists():
        items_path = Path(json.loads(meta_path.read_text(encoding="utf-8")).get("items_path", ""))
        if items_path.exists():
            for line in items_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                item = json.loads(line)
                if item.get("arabic"):
                    source_texts[item["id"]] = item["arabic"]
                if item.get("reference_english"):
                    reference_texts[item["id"]] = item["reference_english"]

    report = score.score_run(rows, source_texts=source_texts, reference_texts=reference_texts)
    report_path = run_dir / "score_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md_path = run_dir / "score_report.md"
    md_path.write_text(score.render_markdown(report, title=f"Run {run_dir.name}"), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


def _cmd_ingest_modal(args: argparse.Namespace) -> int:
    run_meta = ingest_modal.ingest(
        args.raw,
        prompt_template_id=args.template,
        out_dir=args.out_dir,
        run_id=args.run_id,
        model=args.model,
        model_version=args.model_version,
        gpu=args.gpu,
        quantization=args.quantization,
    )
    out: dict = {"run_meta": run_meta}
    if args.compare_to:
        out["reconstruction_diff"] = ingest_modal.compare_runs(run_meta["run_dir"], args.compare_to)
    print(json.dumps(out, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="versed-harness")
    sub = parser.add_subparsers(dest="command", required=True)

    blocks_p = sub.add_parser(
        "blocks",
        help="Segment an items file into ID-bearing blocks (the D2e translation unit).",
    )
    blocks_p.add_argument("--items", required=True, help="Path to a JSONL file of {id, arabic} items.")
    blocks_p.add_argument("--out", required=True, help="Where to write the block items JSONL.")
    blocks_p.add_argument(
        "--max-words", type=int, default=blocks_mod.DEFAULT_MAX_BLOCK_WORDS,
        help="Word budget per block (default sized to stay inside MetricX's 1536-token window).",
    )
    blocks_p.set_defaults(func=_cmd_blocks)

    run_p = sub.add_parser("run", help="Run the harness against a benchmark items file.")
    run_p.add_argument("--adapter", required=True, choices=["anthropic", "ollama", "openai_compat"])
    run_p.add_argument("--model", required=True)
    run_p.add_argument(
        "--template", dest="template", default=runner.DEFAULT_TEMPLATE_ID,
        help=f"Prompt template id (default: {runner.DEFAULT_TEMPLATE_ID}, the D2e production contract).",
    )
    run_p.add_argument("--items", required=True, help="Path to a JSONL file of {id, arabic} items.")
    run_p.add_argument("--out-dir", default=None)
    run_p.add_argument(
        "--batch-size", type=int, default=None,
        help=f"Items per structured call (default: {runner.DEFAULT_STRUCTURED_BATCH_SIZE} "
        "structured, 1 free-text).",
    )
    run_p.add_argument("--gpu", default=None)
    run_p.add_argument("--quantization", default=None)
    run_p.add_argument("--model-version", default=None)
    run_p.add_argument("--use-exemplar", action="store_true")
    run_p.add_argument("--base-url", default=None, help="Required for openai_compat; overrides ollama's default.")
    run_p.add_argument("--api-key", default=None, help="For openai_compat.")
    run_p.set_defaults(func=_cmd_run)

    re_p = sub.add_parser(
        "reassemble",
        help="Join a block-level run back into one translation per source item.",
    )
    re_p.add_argument("--run-dir", required=True, help="Block-level harness run dir.")
    re_p.add_argument("--out-dir", default=None, help="Defaults to the run dir's parent.")
    re_p.add_argument("--run-id", default=None, help="Name for the reassembled run dir.")
    re_p.add_argument(
        "--items", default=None,
        help="Original (pre-block) items JSONL; recorded as items_path so `score` "
        "can find the references for chrF.",
    )
    re_p.add_argument(
        "--block-items", default=None,
        help="Block items JSONL the run translated. Defaults to the run's own "
        "items_path. Supplies the expected block count per item, without which "
        "a block lost from the END of an item is undetectable.",
    )
    re_p.set_defaults(func=_cmd_reassemble)

    score_p = sub.add_parser("score", help="Score a finished run directory.")
    score_p.add_argument("--run-dir", required=True)
    score_p.set_defaults(func=_cmd_score)

    ing_p = sub.add_parser(
        "ingest-modal",
        help="Convert a Modal run_batch results_raw.jsonl into a harness run directory.",
    )
    ing_p.add_argument("--raw", required=True, help="Path to run_batch's results_raw.jsonl.")
    ing_p.add_argument(
        "--template",
        default=None,
        dest="template",
        help="prompt_template_id the Modal run actually used. Required for "
        "`run_batch` output, which does not record it (and it is not guessable). "
        "`run_blocks` records its own; passing a conflicting value there is an "
        "error, not an override.",
    )
    ing_p.add_argument("--out-dir", default=None)
    ing_p.add_argument("--run-id", default=None, help="Override the run_id derived from the raw file.")
    ing_p.add_argument("--model", default=None, help="Override the model derived from model_key.")
    ing_p.add_argument("--model-version", default=None, help="Defaults to the raw file's model_key.")
    ing_p.add_argument("--gpu", default=ingest_modal.SERVING_GPU)
    ing_p.add_argument("--quantization", default=ingest_modal.SERVING_QUANTIZATION)
    ing_p.add_argument(
        "--compare-to",
        default=None,
        help="Existing run dir to diff the reconstruction against (field-by-field).",
    )
    ing_p.set_defaults(func=_cmd_ingest_modal)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
