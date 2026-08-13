"""Run orchestration: load items, call an adapter, write results.jsonl +
run_meta.json under /Volumes/Nodes/versed-translator/runs/<run_id>/.

Per repo rights-hygiene rules, no per-run output ever lands in the repo
tree -- everything this module writes goes to paths.SCRATCH_DIR (see
paths.py; overridable via VERSED_SCRATCH for tests).
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from versed_translator.harness.adapters import get_adapter
from versed_translator.harness.prompts import get_template, load_exemplar
from versed_translator.harness.schema import make_row, validate_row
from versed_translator.paths import SCRATCH_DIR


def new_run_id(adapter: str, model: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    short = uuid.uuid4().hex[:8]
    safe_model = model.replace("/", "_").replace(":", "_")
    return f"{stamp}-{adapter}-{safe_model}-{short}"


def load_items(items_path: str | Path) -> list[dict]:
    """Load a JSONL file of {"id": ..., "arabic": ...} items.

    Deliberately dumb: no normalization, no corpus-loader logic. Callers
    are responsible for pointing this at rights-appropriate data (never a
    path inside the repo tree).
    """
    items = []
    with open(items_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if "id" not in obj or "arabic" not in obj:
                raise ValueError(f"item missing 'id' or 'arabic': {obj!r}")
            items.append({"id": obj["id"], "arabic": obj["arabic"]})
    return items


def run(
    *,
    adapter_name: str,
    model: str,
    template_id: str,
    items_path: str | Path,
    out_dir: str | Path | None = None,
    batch_size: int = 1,
    gpu: str | None = None,
    quantization: str | None = None,
    model_version: str | None = None,
    use_exemplar: bool = False,
    **adapter_cfg,
) -> dict:
    """Execute a full harness run and write its outputs. Returns run_meta dict."""
    out_root = Path(out_dir) if out_dir else SCRATCH_DIR / "runs"
    out_root.mkdir(parents=True, exist_ok=True)

    adapter = get_adapter(adapter_name)
    template = get_template(template_id)
    items = load_items(items_path)
    exemplar = load_exemplar() if use_exemplar else None

    run_id = new_run_id(adapter_name, model)
    run_dir = out_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    results = adapter.translate_batch(items, template, model=model, exemplar=exemplar, **adapter_cfg)
    wall_s = time.monotonic() - started

    rows = []
    results_path = run_dir / "results.jsonl"
    with open(results_path, "w", encoding="utf-8") as f:
        for result in results:
            row = make_row(
                run_id=run_id,
                item_id=result.item_id,
                model=model,
                model_version=model_version,
                adapter=adapter_name,
                quantization=quantization,
                prompt_template_id=template_id,
                source_tokens=result.source_tokens,
                output_tokens=result.output_tokens,
                latency_s=result.latency_s,
                batch_size=batch_size,
                gpu=gpu,
                cost_estimate=None,
                translation=result.translation,
                error=result.error,
            )
            problems = validate_row(row)
            if problems:
                # A model returning an empty/invalid payload for one item is
                # data about that item, not a reason to lose the whole run:
                # demote to an error row and keep going.
                if not row.get("error"):
                    row["error"] = f"invalid result row: {problems}"
                if validate_row(row):
                    row["translation"] = ""
                    row["error"] = f"unvalidatable result row: {problems}"
            rows.append(row)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()

    run_meta = {
        "run_id": run_id,
        "adapter": adapter_name,
        "model": model,
        "model_version": model_version,
        "prompt_template_id": template_id,
        "quantization": quantization,
        "gpu": gpu,
        "batch_size": batch_size,
        "item_count": len(items),
        "error_count": sum(1 for r in rows if r["error"]),
        "wall_s": wall_s,
        "items_path": str(items_path),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(run_dir / "run_meta.json", "w", encoding="utf-8") as f:
        json.dump(run_meta, f, indent=2)

    return run_meta
