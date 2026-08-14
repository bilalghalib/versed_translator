"""Run orchestration: load items, call an adapter, write results.jsonl +
run_meta.json under /Volumes/Nodes/versed-translator/runs/<run_id>/.

DEFAULT PATH (D2e, 2026-08-14): ``structured_blocks_v1``. Translation is a
batched JSON-in/JSON-out call over ``{id, arabic}`` blocks whose ids must come
back unchanged. Free-text ``v1`` is still available via ``--template v1``, but
it is no longer the default, because on that path a dropped clause is
undetectable from (source, output) alone -- measured, not assumed: COMETKiwi
catches partial clause removal 22.9% of the time with a *negative* mean delta,
MetricX 33.3%.

ID LOSS IS A RUN-LEVEL METRIC, NOT A SHRUG. Every id sent must come back.
This module reconciles the ids it sent against the ids the adapter returned
and writes an error row for every discrepancy, then stamps the counts into
``run_meta.json`` (``id_loss_count`` and friends). Nothing is dropped
silently, in either direction: an id the model invented is reported too.

BATCH FAILURES DEGRADE, THEY DO NOT RAISE. A malformed response, a parse
error, or an unexpected exception inside one chunk produces one error row per
item *in that chunk* and the run continues. Completed chunks are already on
disk. (A bug once lost all 139 buffered results of a finished run because one
invalid row raised out of the writer; that must not be re-learnable.)

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
from versed_translator.harness.adapters.base import AdapterError
from versed_translator.harness.prompts import get_template, load_exemplar
from versed_translator.harness.schema import make_row, validate_row
from versed_translator.harness.structured import (
    ERR_ID_MISSING,
    ERR_ID_UNEXPECTED,
    ID_CONTRACT_ERRORS,
    batch_error_results,
    id_error_counts,
)
from versed_translator.paths import SCRATCH_DIR

#: The production contract (D2e). Overridable per run, but this is what a
#: caller that does not think about it gets.
DEFAULT_TEMPLATE_ID = "structured_blocks_v1"

#: Blocks per structured call when the caller does not say. Small on purpose:
#: the batch is the blast radius of a malformed response, and a batch that
#: overruns the model's output budget fails as a whole. 8 blocks of <=60 words
#: is ~1k output tokens, comfortably inside every adapter's default cap.
DEFAULT_STRUCTURED_BATCH_SIZE = 8


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


def _chunks(items: list[dict], size: int) -> list[list[dict]]:
    size = max(1, size)
    return [items[i : i + size] for i in range(0, len(items), size)]


def reconcile_ids(items: list[dict], results: list) -> tuple[list, dict]:
    """Force the returned results to account for exactly the ids that were sent.

    Returns ``(results, report)``. Any id that was sent but is absent from
    `results` gains an ``id_missing_from_structured_response`` error row; any
    id in `results` that was never sent is kept but marked
    ``id_unexpected_in_structured_response`` if the adapter did not already
    say so. Order follows the sent items, with unsent ids appended.

    ``id_loss_count`` counts sent ids the model did not honestly return --
    absent from the response *or* returned with an id-contract error by the
    adapter. Counting only physically-absent ids would read 0 on exactly the
    runs the adapters already diagnosed, which is the wrong direction for a
    safety metric to be wrong in.

    This duplicates a check the adapters already do for the structured path.
    That is deliberate: it is the run's own guarantee that every sent id is
    accounted for, independent of which adapter ran.
    """
    sent = [item["id"] for item in items]
    sent_set = set(sent)
    by_id: dict[str, list] = {}
    for result in results:
        by_id.setdefault(result.item_id, []).append(result)

    ordered: list = []
    lost: set[str] = set()
    for item_id in sent:
        got = by_id.pop(item_id, None)
        if not got:
            lost.add(item_id)
            ordered.extend(batch_error_results([item_id], ERR_ID_MISSING))
            continue
        if all(r.error in ID_CONTRACT_ERRORS for r in got):
            lost.add(item_id)
        ordered.extend(got)

    unexpected: list[str] = []
    for item_id, extras in by_id.items():
        unexpected.append(item_id)
        for extra in extras:
            if not extra.error:
                extra.error = ERR_ID_UNEXPECTED
                extra.translation = None
            ordered.append(extra)

    report = {
        "id_expected": len(sent_set),
        "id_returned": len({r.item_id for r in results}),
        "id_loss_count": len(lost),
        "id_unexpected_count": len(unexpected),
        "id_preservation_rate": (
            (len(sent_set) - len(lost)) / len(sent_set) if sent_set else None
        ),
    }
    return ordered, report


def run(
    *,
    adapter_name: str,
    model: str,
    template_id: str = DEFAULT_TEMPLATE_ID,
    items_path: str | Path,
    out_dir: str | Path | None = None,
    batch_size: int | None = None,
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

    if batch_size is None:
        batch_size = DEFAULT_STRUCTURED_BATCH_SIZE if template.structured else 1

    run_id = new_run_id(adapter_name, model)
    run_dir = out_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Free-text templates are handed the whole list in one call (the adapters
    # loop internally and already trap per-item failures); structured
    # templates are chunked, because there the batch really is one API call.
    chunk_size = batch_size if template.structured else max(len(items), 1)

    started = time.monotonic()
    results: list = []
    batch_failures = 0
    for chunk in _chunks(items, chunk_size):
        try:
            results.extend(
                adapter.translate_batch(chunk, template, model=model, exemplar=exemplar, **adapter_cfg)
            )
        except AdapterError:
            # Configuration failures (missing key, missing base_url) block the
            # whole run, not one batch. Fail loudly rather than writing N
            # identical error rows that look like a model problem.
            raise
        except Exception as exc:  # noqa: BLE001 -- one bad batch must not discard finished work
            batch_failures += 1
            results.extend(
                batch_error_results([i["id"] for i in chunk], f"batch_failed: {type(exc).__name__}: {exc}")
            )
    wall_s = time.monotonic() - started

    results, id_report = reconcile_ids(items, results)

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
                cost_estimate=result.cost_estimate,
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
        "structured": template.structured,
        "quantization": quantization,
        "gpu": gpu,
        "batch_size": batch_size,
        "item_count": len(items),
        "row_count": len(rows),
        "error_count": sum(1 for r in rows if r["error"]),
        "batch_failure_count": batch_failures,
        "wall_s": wall_s,
        "items_path": str(items_path),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    run_meta.update(id_report)
    # Row-level tally kept under its own key so it cannot collide with (or be
    # mistaken for) the reconciliation counts above.
    run_meta["id_error_rows"] = id_error_counts(rows)
    with open(run_dir / "run_meta.json", "w", encoding="utf-8") as f:
        json.dump(run_meta, f, indent=2)

    return run_meta
