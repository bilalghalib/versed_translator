"""CLI for the C2 translation harness.

    python -m versed_translator.harness run --adapter anthropic --model claude-sonnet-5 \
        --template v1 --items <jsonl path> --out-dir /Volumes/Nodes/versed-translator/runs

    python -m versed_translator.harness score --run-dir /Volumes/Nodes/versed-translator/runs/<run_id>

    python -m versed_translator.harness ingest-modal --raw <results_raw.jsonl> \
        --template v1 --out-dir /Volumes/Nodes/versed-translator/runs
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from versed_translator.harness import ingest_modal, runner, score


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

    run_p = sub.add_parser("run", help="Run the harness against a benchmark items file.")
    run_p.add_argument("--adapter", required=True, choices=["anthropic", "ollama", "openai_compat"])
    run_p.add_argument("--model", required=True)
    run_p.add_argument("--template", required=True, dest="template")
    run_p.add_argument("--items", required=True, help="Path to a JSONL file of {id, arabic} items.")
    run_p.add_argument("--out-dir", default=None)
    run_p.add_argument("--batch-size", type=int, default=1)
    run_p.add_argument("--gpu", default=None)
    run_p.add_argument("--quantization", default=None)
    run_p.add_argument("--model-version", default=None)
    run_p.add_argument("--use-exemplar", action="store_true")
    run_p.add_argument("--base-url", default=None, help="Required for openai_compat; overrides ollama's default.")
    run_p.add_argument("--api-key", default=None, help="For openai_compat.")
    run_p.set_defaults(func=_cmd_run)

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
        required=True,
        dest="template",
        help="prompt_template_id the Modal run actually used. Not recorded in the "
        "raw file and not guessable, so you must state it.",
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
