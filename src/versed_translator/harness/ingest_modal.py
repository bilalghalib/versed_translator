"""Ingest a Modal ``run_batch`` raw output file into a harness run directory.

WHY THIS EXISTS: ``throughput/serve_translategemma.py::run_batch`` writes its
own compact raw format (one ``{id, english, output_tokens, latency_s}`` object
per item, plus a trailing ``{"_run_summary": {...}}`` line). The bakeoff
compares that against harness runs, which use ``schema.ROW_FIELDS`` rows plus a
``run_meta.json``. The first 27B leg was converted by an ad-hoc script that was
never committed, which made a step in the measurement path unreproducible. This
module is that conversion, in the package, with a CLI and a regression test.

DETERMINISM: the run_id is derived from the raw file's own ``_run_summary``
(started_at + model_key), not from wall-clock time at ingest, so re-ingesting
the same raw file always produces the same run_id and the same rows. This
deliberately differs from ``runner.new_run_id``, which mints a fresh uuid
suffix because it is naming a run it is about to execute.

FIELDS THAT CANNOT BE DERIVED FROM THE RAW FILE (emitted as None, never
back-filled):

* ``source_tokens`` -- run_batch tokenizes the prompt to enforce the context
  budget but does not record the count in its output.
* ``batch_size`` -- run_batch's ``chunk_size`` is a client-side chunking knob,
  not the engine's batch size; vLLM does continuous batching, so no single
  number describes the batch an item was served in. Neither value reaches the
  raw file.
* ``cost_estimate`` (per row) -- Modal bills container wall-clock for the whole
  batch. Only a run-level ``est_cost_usd`` exists; splitting it per item would
  be an invention, so it stays on run_meta as ``est_cost_usd_total`` and stays
  None per row.

FIELDS THAT COME FROM SERVING CONFIG, NOT THE RAW FILE: ``model``,
``quantization`` and ``gpu`` are constants of the serving path (mirrored below
from serve_translategemma.py) and default from ``model_key``.

``prompt_template_id``: ``run_batch`` does not record it, so for those files
it is a required argument the caller must state (it is not guessable, and
guessing it wrong is exactly how both TranslateGemma legs came to be
mislabelled). ``run_blocks`` *does* record it, taken from the same registry
lookup that built the prompt; when the summary carries it, it wins, and an
explicit ``--template`` that disagrees is an error rather than an override.
A caller's belief must never quietly overwrite the run's own record of what
it sent.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from versed_translator.harness.schema import make_row, validate_row
from versed_translator.harness.structured import id_error_counts
from versed_translator.paths import SCRATCH_DIR

#: Adapter name recorded on every row this module emits. There is no live
#: adapter module under ``harness/adapters/`` for it on purpose: this path
#: cannot be driven from ``runner.run`` (the GPU job is launched by
#: ``modal run``, out of band), so registering it in ADAPTERS would advertise
#: a capability the harness does not have.
ADAPTER_NAME = "modal_vllm"

# Mirrors serve_translategemma.MODEL_REPOS / GPU_KIND / dtype. Duplicated
# rather than imported because that module imports `modal` at module scope and
# is not part of the installed package; keep the two in sync.
MODEL_REPOS: dict[str, str] = {
    "27b": "google/translategemma-27b-it",
    "12b": "google/translategemma-12b-it",
}
SERVING_GPU = "H100"
SERVING_QUANTIZATION = "bfloat16"

SUMMARY_KEY = "_run_summary"

#: Summary keys `run_blocks` records that `build_run_meta` copies through.
#: The GPU job's own id counters are deliberately NOT here: ``id_error_counts``
#: re-derives them from the rows actually on disk, which is the stronger
#: source (it cannot disagree with the file it describes), and two keys of the
#: same name from two sources would silently shadow each other.
PASSTHROUGH_SUMMARY_KEYS: tuple[str, ...] = (
    "structured",
    "structured_probe_ok",
    "structured_chunk_size",
    "prompt_modes",
    "has_chat_template",
    "sampling",
    "chat_template_errors",
)


def resolve_template_id(summary: dict, requested: str | None) -> str:
    """The prompt_template_id to record: the run's own, if it has one.

    Raises RawIngestError when the caller states a template that contradicts
    the one the run recorded, and when neither exists.
    """
    recorded = summary.get("prompt_template_id")
    if recorded and requested and recorded != requested:
        raise RawIngestError(
            f"raw file records prompt_template_id={recorded!r} but --template "
            f"says {requested!r}. The run's own record wins; drop --template "
            "or fix the caller."
        )
    resolved = recorded or requested
    if not resolved:
        raise RawIngestError(
            "no prompt_template_id in the raw file's summary and none passed; "
            "it is not guessable -- state it with --template"
        )
    return resolved


class RawIngestError(ValueError):
    """The raw file is not a well-formed run_batch output."""


def read_raw(raw_path: str | Path) -> tuple[list[dict], dict]:
    """Split a run_batch raw file into (per-item rows, run summary).

    Raises RawIngestError if the trailing ``_run_summary`` line is missing --
    without it there is no started_at/wall/cost, and silently emitting a run
    with invented metadata is exactly the failure mode this module exists to
    prevent.
    """
    raw_rows: list[dict] = []
    summary: dict | None = None
    with open(raw_path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RawIngestError(f"{raw_path}:{lineno}: not JSON: {exc}") from exc
            if not isinstance(obj, dict):
                raise RawIngestError(f"{raw_path}:{lineno}: expected a JSON object")
            if SUMMARY_KEY in obj:
                if summary is not None:
                    raise RawIngestError(f"{raw_path}:{lineno}: more than one {SUMMARY_KEY} line")
                summary = obj[SUMMARY_KEY]
                continue
            raw_rows.append(obj)
    if summary is None:
        raise RawIngestError(
            f"{raw_path}: no trailing {SUMMARY_KEY!r} line -- the run either died "
            "before finishing or this is not a run_batch output file"
        )
    return raw_rows, summary


def model_slug(repo_id: str) -> str:
    """``google/translategemma-27b-it`` -> ``translategemma_27b``."""
    return repo_id.rsplit("/", 1)[-1].removesuffix("-it").replace("-", "_")


def derive_run_id(summary: dict) -> str:
    """Deterministic run_id: ``<started_at stamp>-modal-<model slug>``."""
    model_key = summary.get("model_key")
    if not model_key:
        raise RawIngestError(f"{SUMMARY_KEY} has no model_key")
    started_at = summary.get("started_at")
    if not started_at:
        raise RawIngestError(f"{SUMMARY_KEY} has no started_at")
    stamp = datetime.fromisoformat(started_at).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-modal-{model_slug(_repo_for(model_key))}"


def _repo_for(model_key: str) -> str:
    try:
        return MODEL_REPOS[model_key]
    except KeyError as exc:
        raise RawIngestError(
            f"unknown model_key {model_key!r}; known: {sorted(MODEL_REPOS)}"
        ) from exc


def build_rows(
    raw_rows: list[dict],
    summary: dict,
    *,
    run_id: str,
    prompt_template_id: str,
    model: str,
    model_version: str,
    gpu: str | None,
    quantization: str | None,
) -> list[dict]:
    """Convert raw run_batch rows to harness schema rows, preserving order."""
    rows: list[dict] = []
    for raw in raw_rows:
        english = raw.get("english")
        error = raw.get("error")
        if error is None and english is None:
            # run_batch guarantees english is None exactly when it set an
            # error; a row with neither means the file is malformed, and the
            # honest record of that is an error row, not a dropped item.
            error = "raw row has neither 'english' nor 'error'"
        row = make_row(
            run_id=run_id,
            item_id=raw.get("id"),
            model=model,
            model_version=model_version,
            adapter=ADAPTER_NAME,
            quantization=quantization,
            prompt_template_id=prompt_template_id,
            source_tokens=None,  # not recorded by run_batch; see module docstring
            output_tokens=raw.get("output_tokens"),
            latency_s=raw.get("latency_s"),
            batch_size=None,  # not recoverable; see module docstring
            gpu=gpu,
            cost_estimate=None,  # run-level only; see module docstring
            translation=english if english is not None else "",
            error=error,
        )
        problems = validate_row(row)
        # Same policy as runner.run: a bad item is data about that item, not a
        # reason to lose the run.
        if problems and not row["error"]:
            row["error"] = f"invalid result row: {problems}"
        rows.append(row)
    return rows


def build_run_meta(
    rows: list[dict],
    summary: dict,
    *,
    run_id: str,
    prompt_template_id: str,
    model: str,
    model_version: str,
    gpu: str | None,
    quantization: str | None,
) -> dict:
    """Build run_meta.json matching runner.run's shape, plus est_cost_usd_total."""
    meta = {
        "run_id": run_id,
        "adapter": ADAPTER_NAME,
        "model": model,
        "model_version": model_version,
        "prompt_template_id": prompt_template_id,
        "quantization": quantization,
        "gpu": gpu,
        "batch_size": None,
        "item_count": summary.get("n_items", len(rows)),
        "error_count": sum(1 for r in rows if r["error"]),
        # The run's own measured wall clock, not this ingest's. Using
        # time.monotonic() here (as runner.run does) would time the file copy.
        "wall_s": summary.get("total_wall_s"),
        "items_path": summary.get("input"),
        # runner.run stamps created_at when the run finishes writing; the
        # equivalent instant for a Modal run is when run_batch finished.
        "created_at": summary.get("finished_at"),
        "est_cost_usd_total": summary.get("est_cost_usd"),
    }
    meta.update(
        {key: summary[key] for key in PASSTHROUGH_SUMMARY_KEYS if key in summary}
    )
    meta.update(id_error_counts(rows))
    return meta


def ingest(
    raw_path: str | Path,
    *,
    prompt_template_id: str | None = None,
    out_dir: str | Path | None = None,
    run_id: str | None = None,
    model: str | None = None,
    model_version: str | None = None,
    gpu: str | None = SERVING_GPU,
    quantization: str | None = SERVING_QUANTIZATION,
) -> dict:
    """Convert a run_batch raw file into a harness run dir. Returns run_meta."""
    raw_rows, summary = read_raw(raw_path)
    model_key = summary.get("model_key")
    resolved_model = model or _repo_for(model_key)
    resolved_version = model_version if model_version is not None else model_key
    resolved_run_id = run_id or derive_run_id(summary)
    resolved_template = resolve_template_id(summary, prompt_template_id)

    rows = build_rows(
        raw_rows,
        summary,
        run_id=resolved_run_id,
        prompt_template_id=resolved_template,
        model=resolved_model,
        model_version=resolved_version,
        gpu=gpu,
        quantization=quantization,
    )
    run_meta = build_run_meta(
        rows,
        summary,
        run_id=resolved_run_id,
        prompt_template_id=resolved_template,
        model=resolved_model,
        model_version=resolved_version,
        gpu=gpu,
        quantization=quantization,
    )

    out_root = Path(out_dir) if out_dir else SCRATCH_DIR / "runs"
    run_dir = out_root / resolved_run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    with open(run_dir / "results.jsonl", "w", encoding="utf-8") as f:
        f.writelines(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    with open(run_dir / "run_meta.json", "w", encoding="utf-8") as f:
        json.dump(run_meta, f, indent=2)

    run_meta = dict(run_meta)
    run_meta["run_dir"] = str(run_dir)
    return run_meta


# ---------------------------------------------------------------------------
# Reconstruction check: diff a freshly ingested run dir against a known-good
# one. Lives here (not in a throwaway script) so the validation that makes
# this tool trustworthy is itself reproducible.
# ---------------------------------------------------------------------------


def compare_runs(new_dir: str | Path, ref_dir: str | Path) -> dict:
    """Field-by-field diff of two run dirs.

    Returns ``{"row_count": {...}, "row_fields": {field: {...}},
    "meta_fields": {field: {...}}}``. A field entry records how many rows
    matched, how many differed, and up to three example differences -- never
    the translation text itself, so this is safe to print anywhere.
    """
    new_rows = _read_jsonl(Path(new_dir) / "results.jsonl")
    ref_rows = _read_jsonl(Path(ref_dir) / "results.jsonl")
    new_meta = json.loads((Path(new_dir) / "run_meta.json").read_text(encoding="utf-8"))
    ref_meta = json.loads((Path(ref_dir) / "run_meta.json").read_text(encoding="utf-8"))

    report: dict = {
        "row_count": {"new": len(new_rows), "ref": len(ref_rows), "match": len(new_rows) == len(ref_rows)},
        "row_fields": {},
        "meta_fields": {},
    }

    fields = sorted(set().union(*(set(r) for r in new_rows + ref_rows))) if (new_rows or ref_rows) else []
    for field in fields:
        differences = []
        for i, (a, b) in enumerate(zip(new_rows, ref_rows)):
            if a.get(field) != b.get(field):
                differences.append({"index": i, "new": _redact(field, a.get(field)), "ref": _redact(field, b.get(field))})
        report["row_fields"][field] = {
            "compared": min(len(new_rows), len(ref_rows)),
            "differing": len(differences),
            "examples": differences[:3],
        }

    for field in sorted(set(new_meta) | set(ref_meta)):
        if field == "run_dir":
            continue
        if new_meta.get(field) != ref_meta.get(field):
            report["meta_fields"][field] = {"new": new_meta.get(field), "ref": ref_meta.get(field)}
    return report


def _redact(field: str, value: object) -> object:
    """Never echo benchmark text into logs/reports; report a shape instead."""
    if field == "translation" and isinstance(value, str):
        return f"<str len={len(value)}>"
    return value


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
