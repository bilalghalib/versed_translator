"""Run-row schema for C2 harness output (master-plan run schema, extended
with a few fields the roadmap's C2 checkpoint-1 bullet adds on top of the
master-plan JSON sketch: adapter, prompt_template_id [vs. bare
"prompt_template"], item_id, and a nullable error).

Every run emits one JSONL row per item under
``/Volumes/Nodes/versed-translator/runs/<run_id>/results.jsonl`` (never in
the repo -- see paths.py SCRATCH_DIR and the repo's rights-hygiene rule)
plus one ``run_meta.json`` describing the run as a whole. This module only
defines/validates the row shape; runner.py does the actual run execution
and I/O.
"""

from __future__ import annotations

ROW_FIELDS: tuple[str, ...] = (
    "run_id",
    "item_id",
    "model",
    "model_version",
    "adapter",
    "quantization",
    "prompt_template_id",
    "source_tokens",
    "output_tokens",
    "latency_s",
    "batch_size",
    "gpu",
    "cost_estimate",
    "translation",
    "error",
)

# Fields that must never be None on a successful (error is None) row.
_REQUIRED_ON_SUCCESS = (
    "run_id",
    "item_id",
    "model",
    "adapter",
    "prompt_template_id",
    "translation",
)


def make_row(**kwargs: object) -> dict:
    """Build a result-row dict, defaulting any omitted field to None.

    Raises ValueError on an unknown key (schema drift should fail loudly,
    same convention as benchmark/sources/schema.make_pair).
    """
    unknown = set(kwargs) - set(ROW_FIELDS)
    if unknown:
        raise ValueError(f"unknown run-row field(s): {sorted(unknown)}")
    return {field: kwargs.get(field) for field in ROW_FIELDS}


def validate_row(row: dict) -> list[str]:
    """Return a list of validation problems (empty list == valid row).

    Checked structurally, not against live data: exact key set, and (when
    error is None, i.e. the item is claimed successful) the required
    fields listed in _REQUIRED_ON_SUCCESS are non-None.
    """
    problems: list[str] = []
    keys = set(row.keys())
    missing = set(ROW_FIELDS) - keys
    extra = keys - set(ROW_FIELDS)
    if missing:
        problems.append(f"missing field(s): {sorted(missing)}")
    if extra:
        problems.append(f"unexpected field(s): {sorted(extra)}")
    if row.get("error") is None:
        for field in _REQUIRED_ON_SUCCESS:
            if field in row and row.get(field) in (None, ""):
                problems.append(f"required field '{field}' is empty on a non-error row")
    return problems
