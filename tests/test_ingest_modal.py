"""Regression tests pinning the Modal run_batch -> harness-schema conversion.

RIGHTS NOTE: every fixture row here is synthesized (ASCII placeholder text,
fake item ids). No Arabic or English benchmark text is committed to this repo
-- see the repo's rights-hygiene rule. The one test that touches the real 27B
reconstruction reads it from off-tree data and skips when that data is absent.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from versed_translator.harness import ingest_modal
from versed_translator.harness.ingest_modal import (
    ADAPTER_NAME,
    RawIngestError,
    compare_runs,
    derive_run_id,
    ingest,
    model_slug,
    read_raw,
)
from versed_translator.harness.schema import ROW_FIELDS, validate_row

# --- synthetic fixture: same shape as a real run_batch results_raw.jsonl ----

FIXTURE_ROWS = [
    {"id": "fixture:item_001", "english": "The first placeholder sentence.", "output_tokens": 7, "latency_s": 0.5904},
    {"id": "fixture:item_002", "english": "The second placeholder sentence.", "output_tokens": 12, "latency_s": 1.2},
    {"id": "fixture:item_003", "english": None, "error": "ValueError: empty or non-string 'arabic' field"},
]

FIXTURE_SUMMARY = {
    "input": "/off/tree/benchmark-data/fixture_items.jsonl",
    "output": "/off/tree/runs/fixture/results_raw.jsonl",
    "model_key": "27b",
    "started_at": "2026-08-13T23:32:52.942659+00:00",
    "finished_at": "2026-08-13T23:37:01.976323+00:00",
    "n_items": 3,
    "n_ok": 2,
    "n_err": 1,
    "total_wall_s": 249.03,
    "est_cost_usd": 0.2732,
    "price_constant_needs_verification": 3.95,
}


def _write_raw(tmp_path: Path, rows=FIXTURE_ROWS, summary=FIXTURE_SUMMARY) -> Path:
    path = tmp_path / "results_raw.jsonl"
    lines = [json.dumps(r) for r in rows]
    if summary is not None:
        lines.append(json.dumps({"_run_summary": summary}))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# read_raw / derivation
# ---------------------------------------------------------------------------


def test_read_raw_splits_rows_from_summary(tmp_path):
    rows, summary = read_raw(_write_raw(tmp_path))
    assert len(rows) == 3
    assert summary["model_key"] == "27b"


def test_read_raw_rejects_file_without_summary(tmp_path):
    with pytest.raises(RawIngestError, match="_run_summary"):
        read_raw(_write_raw(tmp_path, summary=None))


def test_read_raw_rejects_duplicate_summary(tmp_path):
    path = tmp_path / "dup.jsonl"
    line = json.dumps({"_run_summary": FIXTURE_SUMMARY})
    path.write_text(line + "\n" + line + "\n", encoding="utf-8")
    with pytest.raises(RawIngestError, match="more than one"):
        read_raw(path)


def test_model_slug_strips_it_suffix():
    assert model_slug("google/translategemma-27b-it") == "translategemma_27b"
    assert model_slug("google/translategemma-12b-it") == "translategemma_12b"


def test_derive_run_id_is_deterministic_and_matches_the_27b_leg():
    # This exact string is the run_id of the already-published 27B leg; the
    # derivation must keep reproducing it.
    assert derive_run_id(FIXTURE_SUMMARY) == "20260813T233252Z-modal-translategemma_27b"
    assert derive_run_id(FIXTURE_SUMMARY) == derive_run_id(dict(FIXTURE_SUMMARY))


def test_derive_run_id_rejects_unknown_model_key():
    with pytest.raises(RawIngestError, match="unknown model_key"):
        derive_run_id({**FIXTURE_SUMMARY, "model_key": "70b"})


# ---------------------------------------------------------------------------
# ingest(): full row + run_meta shape
# ---------------------------------------------------------------------------


def test_ingest_writes_schema_rows_and_run_meta(tmp_path):
    raw = _write_raw(tmp_path)
    meta = ingest(raw, prompt_template_id="v1", out_dir=tmp_path / "runs")
    run_dir = Path(meta["run_dir"])

    rows = [json.loads(line) for line in (run_dir / "results.jsonl").read_text().splitlines()]
    assert len(rows) == 3
    for row in rows:
        assert set(row) == set(ROW_FIELDS)
        assert row["run_id"] == "20260813T233252Z-modal-translategemma_27b"
        assert row["adapter"] == ADAPTER_NAME
        assert row["model"] == "google/translategemma-27b-it"
        assert row["model_version"] == "27b"
        assert row["quantization"] == "bfloat16"
        assert row["gpu"] == "H100"
        assert row["prompt_template_id"] == "v1"
        # Documented as not derivable from a run_batch raw file.
        assert row["source_tokens"] is None
        assert row["batch_size"] is None
        assert row["cost_estimate"] is None

    ok = rows[0]
    assert ok["item_id"] == "fixture:item_001"
    assert ok["translation"] == "The first placeholder sentence."
    assert ok["latency_s"] == 0.5904
    assert ok["output_tokens"] == 7  # present in the raw file, so it is carried through
    assert ok["error"] is None
    assert validate_row(ok) == []

    on_disk_meta = json.loads((run_dir / "run_meta.json").read_text())
    assert on_disk_meta == {
        "run_id": "20260813T233252Z-modal-translategemma_27b",
        "adapter": "modal_vllm",
        "model": "google/translategemma-27b-it",
        "model_version": "27b",
        "prompt_template_id": "v1",
        "quantization": "bfloat16",
        "gpu": "H100",
        "batch_size": None,
        "item_count": 3,
        "error_count": 1,
        "wall_s": 249.03,
        "items_path": "/off/tree/benchmark-data/fixture_items.jsonl",
        "created_at": "2026-08-13T23:37:01.976323+00:00",
        "est_cost_usd_total": 0.2732,
        # ID accounting is stamped on every ingested run, structured or not:
        # a run with nothing to report says 0, it does not stay silent.
        "id_missing_count": 0,
        "id_unexpected_count": 0,
        "id_duplicate_count": 0,
        "structured_empty_count": 0,
    }


def test_ingest_preserves_per_item_errors(tmp_path):
    meta = ingest(_write_raw(tmp_path), prompt_template_id="v1", out_dir=tmp_path / "runs")
    rows = [json.loads(line) for line in (Path(meta["run_dir"]) / "results.jsonl").read_text().splitlines()]
    err = rows[2]
    assert err["item_id"] == "fixture:item_003"
    assert err["error"].startswith("ValueError:")
    assert err["translation"] == ""
    assert err["output_tokens"] is None


def test_ingest_flags_rows_with_neither_translation_nor_error(tmp_path):
    raw = _write_raw(tmp_path, rows=[{"id": "fixture:item_bad"}])
    meta = ingest(raw, prompt_template_id="v1", out_dir=tmp_path / "runs")
    rows = [json.loads(line) for line in (Path(meta["run_dir"]) / "results.jsonl").read_text().splitlines()]
    assert "neither" in rows[0]["error"]


def test_ingest_is_idempotent(tmp_path):
    raw = _write_raw(tmp_path)
    first = ingest(raw, prompt_template_id="v1", out_dir=tmp_path / "runs")
    body = (Path(first["run_dir"]) / "results.jsonl").read_text()
    second = ingest(raw, prompt_template_id="v1", out_dir=tmp_path / "runs")
    assert second["run_dir"] == first["run_dir"]
    assert (Path(second["run_dir"]) / "results.jsonl").read_text() == body


def test_ingest_12b_key_resolves_the_12b_repo(tmp_path):
    raw = _write_raw(tmp_path, summary={**FIXTURE_SUMMARY, "model_key": "12b"})
    meta = ingest(raw, prompt_template_id="v1", out_dir=tmp_path / "runs")
    assert meta["run_id"] == "20260813T233252Z-modal-translategemma_12b"
    assert meta["model"] == "google/translategemma-12b-it"
    assert meta["model_version"] == "12b"


# ---------------------------------------------------------------------------
# compare_runs()
# ---------------------------------------------------------------------------


def test_compare_runs_reports_clean_and_dirty_fields(tmp_path):
    raw = _write_raw(tmp_path)
    a = Path(ingest(raw, prompt_template_id="v1", out_dir=tmp_path / "a")["run_dir"])
    b = Path(ingest(raw, prompt_template_id="v1", out_dir=tmp_path / "b")["run_dir"])
    assert compare_runs(a, b)["row_fields"]["translation"]["differing"] == 0
    assert compare_runs(a, b)["meta_fields"] == {}

    # Perturb one row field and one meta field in b.
    rows = [json.loads(line) for line in (b / "results.jsonl").read_text().splitlines()]
    rows[0]["output_tokens"] = None
    rows[0]["translation"] = "different placeholder text"
    (b / "results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    meta = json.loads((b / "run_meta.json").read_text())
    meta["wall_s"] = 1.0
    (b / "run_meta.json").write_text(json.dumps(meta))

    report = compare_runs(a, b)
    assert report["row_fields"]["output_tokens"]["differing"] == 1
    assert report["meta_fields"]["wall_s"] == {"new": 249.03, "ref": 1.0}
    # Benchmark text must never be echoed into a diff report.
    example = report["row_fields"]["translation"]["examples"][0]
    assert example["new"].startswith("<str len=")
    assert example["ref"].startswith("<str len=")


# ---------------------------------------------------------------------------
# Live reconstruction of the published 27B leg (off-tree data; skips without it)
# ---------------------------------------------------------------------------

_DATA = Path(os.environ.get("VERSED_DATA_ROOT", Path.home() / "versed-translator-data"))
_REAL_RAW = _DATA / "runs" / "tg27b-modal-dev139" / "results_raw.jsonl"
_REAL_REF = _DATA / "runs" / "20260813T233252Z-modal-translategemma_27b"


@pytest.mark.skipif(
    not (_REAL_RAW.exists() and (_REAL_REF / "results.jsonl").exists()),
    reason="off-tree 27B bakeoff data not present on this machine",
)
def test_reconstructs_the_published_27b_leg(tmp_path):
    """Every field of the published 27B leg must be re-derivable from its raw file.

    The expected differences are additive only: output_tokens (present in the
    raw file, dropped by the lost ad-hoc conversion script) and the ID-loss
    counters added with the structured-block contract. The reconstruction is a
    strict superset of the known-good output -- nothing is fabricated and
    nothing that was there before is lost.
    """
    meta = ingest(_REAL_RAW, prompt_template_id="v1", out_dir=tmp_path / "runs")
    report = compare_runs(meta["run_dir"], _REAL_REF)

    assert report["row_count"] == {"new": 139, "ref": 139, "match": True}
    # No field the published leg recorded may change value; only new fields
    # (whose reference side is absent) are allowed.
    changed = {f: d for f, d in report["meta_fields"].items() if d["ref"] is not None}
    assert changed == {}, "run_meta.json must reconstruct every published field exactly"
    assert set(report["meta_fields"]) == {
        "id_missing_count", "id_unexpected_count", "id_duplicate_count", "structured_empty_count",
    }

    dirty = {f: d["differing"] for f, d in report["row_fields"].items() if d["differing"]}
    assert dirty == {"output_tokens": 139}, f"unexpected reconstruction drift: {dirty}"

    rows = [json.loads(line) for line in (Path(meta["run_dir"]) / "results.jsonl").read_text().splitlines()]
    assert all(r["output_tokens"] is not None for r in rows)
    assert ingest_modal.compare_runs(meta["run_dir"], meta["run_dir"])["meta_fields"] == {}
