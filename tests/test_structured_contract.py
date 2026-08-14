"""Tests for the structured-block ID contract (D2e).

ID preservation is the entire point of the structured template, so these pin
the behaviours that make ID loss *visible*: every sent id comes back as some
row, every named failure mode has its own name, an invented id is reported
rather than discarded, and a malformed response degrades a batch instead of
raising and discarding finished work.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from versed_translator.harness import runner
from versed_translator.harness.adapters.base import AdapterError, TranslationResult
from versed_translator.harness.structured import (
    ERR_EMPTY,
    ERR_ID_DUPLICATE,
    ERR_ID_MISSING,
    ERR_ID_UNEXPECTED,
    ERR_PARSE_PREFIX,
    ID_CONTRACT_ERRORS,
    batch_error_results,
    id_error_counts,
    split_structured_results,
)

# ---------------------------------------------------------------------------
# import hygiene
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "module",
    [
        "versed_translator.harness.structured",
        "versed_translator.harness.runner",
        "versed_translator.harness.score",
        "versed_translator.harness.modal_batch",
        "versed_translator.harness.__main__",
    ],
)
def test_module_imports_first_in_a_fresh_interpreter(module):
    """Each harness module must import standalone, in its own process.

    A circular import between harness.structured and the adapters package
    passed the whole test suite while breaking the CLI, because pytest
    happened to import the modules in a luckier order than `python -m` did.
    Importing one module per interpreter is what actually catches that.
    """
    proc = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr


# ---------------------------------------------------------------------------
# split_structured_results
# ---------------------------------------------------------------------------


def test_split_returns_one_result_per_sent_id_in_order():
    parsed = [{"id": "b", "english": "B"}, {"id": "a", "english": "A"}]
    results = split_structured_results(parsed, ["a", "b"])
    assert [r.item_id for r in results] == ["a", "b"]
    assert [r.translation for r in results] == ["A", "B"]


def test_split_names_a_missing_id():
    results = split_structured_results([{"id": "a", "english": "A"}], ["a", "b"])
    assert results[1].error == ERR_ID_MISSING
    assert results[1].translation is None


def test_split_names_an_invented_id_instead_of_dropping_it():
    parsed = [{"id": "a", "english": "A"}, {"id": "ZZZ", "english": "junk"}]
    results = split_structured_results(parsed, ["a"])
    assert [r.item_id for r in results] == ["a", "ZZZ"]
    assert results[1].error == ERR_ID_UNEXPECTED


def test_split_names_a_duplicated_id():
    parsed = [{"id": "a", "english": "A"}, {"id": "a", "english": "A again"}]
    results = split_structured_results(parsed, ["a"])
    assert results[0].error == ERR_ID_DUPLICATE
    assert results[0].translation is None


def test_split_names_an_empty_translation():
    for english in ("", "   ", None, 7):
        results = split_structured_results([{"id": "a", "english": english}], ["a"])
        assert results[0].error == ERR_EMPTY, english


def test_split_attributes_batch_usage_to_every_item():
    results = split_structured_results(
        [{"id": "a", "english": "A"}, {"id": "b", "english": "B"}],
        ["a", "b"],
        source_tokens=100, output_tokens=50, latency_s=1.5, cost_estimate=0.01,
    )
    assert [r.source_tokens for r in results] == [100, 100]
    assert [r.cost_estimate for r in results] == [0.01, 0.01]


def test_split_withholds_cost_from_error_rows():
    results = split_structured_results([], ["a"], cost_estimate=0.01)
    assert results[0].cost_estimate is None


def test_batch_error_results_covers_every_id():
    results = batch_error_results(["a", "b", "c"], "boom")
    assert [r.item_id for r in results] == ["a", "b", "c"]
    assert all(r.error == "boom" and r.translation is None for r in results)


def test_id_error_counts_tallies_each_named_failure():
    rows = [
        {"error": ERR_ID_MISSING},
        {"error": ERR_ID_MISSING},
        {"error": ERR_ID_UNEXPECTED},
        {"error": ERR_ID_DUPLICATE},
        {"error": ERR_EMPTY},
        {"error": None},
        {"error": "something else"},
    ]
    assert id_error_counts(rows) == {
        "id_missing_count": 2,
        "id_unexpected_count": 1,
        "id_duplicate_count": 1,
        "structured_empty_count": 1,
    }


def test_id_contract_errors_is_the_set_the_metrics_use():
    assert ID_CONTRACT_ERRORS == {ERR_ID_MISSING, ERR_ID_UNEXPECTED, ERR_ID_DUPLICATE}


# ---------------------------------------------------------------------------
# adapters, structured path (network mocked)
# ---------------------------------------------------------------------------


def test_ollama_structured_parse_error_degrades_the_batch(monkeypatch):
    from versed_translator.harness.adapters import ollama_adapter
    from versed_translator.harness.prompts import get_template

    monkeypatch.setattr(
        ollama_adapter, "_post",
        lambda base_url, path, payload, timeout: {"response": "not json at all"},
    )
    results = ollama_adapter.translate_batch(
        [{"id": "a", "arabic": "x"}, {"id": "b", "arabic": "y"}],
        get_template("structured_blocks_v1"),
        model="m",
    )
    assert [r.item_id for r in results] == ["a", "b"]
    assert all(r.error.startswith(ERR_PARSE_PREFIX) for r in results)


def test_openai_compat_structured_reports_invented_ids(monkeypatch):
    from versed_translator.harness.adapters import openai_compat_adapter
    from versed_translator.harness.prompts import get_template

    payload = json.dumps([{"id": "a", "english": "A"}, {"id": "nope", "english": "N"}])
    monkeypatch.setattr(
        openai_compat_adapter, "_post",
        lambda *a, **k: {"choices": [{"message": {"content": payload}}], "usage": {}},
    )
    results = openai_compat_adapter.translate_batch(
        [{"id": "a", "arabic": "x"}],
        get_template("structured_blocks_v1"),
        model="m", base_url="https://example.com/v1",
    )
    by_id = {r.item_id: r for r in results}
    assert by_id["a"].error is None
    assert by_id["nope"].error == ERR_ID_UNEXPECTED


# ---------------------------------------------------------------------------
# runner: default template, chunking, reconciliation, degradation
# ---------------------------------------------------------------------------


def _items_file(tmp_path, n=5):
    path = tmp_path / "items.jsonl"
    path.write_text(
        "\n".join(json.dumps({"id": f"AR_{i:03d}", "arabic": f"text {i}"}) for i in range(n)),
        encoding="utf-8",
    )
    return path


def test_structured_blocks_is_the_default_template():
    assert runner.DEFAULT_TEMPLATE_ID == "structured_blocks_v1"


def test_runner_defaults_to_structured_and_chunks_by_batch_size(tmp_path, monkeypatch):
    from versed_translator.harness.adapters import ollama_adapter

    seen_chunks = []

    def fake(items, template, **cfg):
        assert template.structured is True
        seen_chunks.append([i["id"] for i in items])
        return [
            TranslationResult(item_id=i["id"], translation=f"EN:{i['id']}",
                              source_tokens=1, output_tokens=1, latency_s=0.1)
            for i in items
        ]

    monkeypatch.setattr(ollama_adapter, "translate_batch", fake)
    meta = runner.run(
        adapter_name="ollama", model="m", items_path=_items_file(tmp_path, 5),
        out_dir=tmp_path / "runs", batch_size=2,
    )
    assert meta["prompt_template_id"] == "structured_blocks_v1"
    assert meta["structured"] is True
    assert [len(c) for c in seen_chunks] == [2, 2, 1]
    assert meta["id_loss_count"] == 0
    assert meta["id_preservation_rate"] == 1.0


def test_runner_default_batch_size_follows_the_template(tmp_path, monkeypatch):
    from versed_translator.harness.adapters import ollama_adapter

    monkeypatch.setattr(
        ollama_adapter, "translate_batch",
        lambda items, template, **cfg: [
            TranslationResult(item_id=i["id"], translation="EN", source_tokens=1,
                              output_tokens=1, latency_s=0.1)
            for i in items
        ],
    )
    structured = runner.run(adapter_name="ollama", model="m",
                            items_path=_items_file(tmp_path), out_dir=tmp_path / "s")
    assert structured["batch_size"] == runner.DEFAULT_STRUCTURED_BATCH_SIZE
    free = runner.run(adapter_name="ollama", model="m", template_id="v1",
                      items_path=_items_file(tmp_path), out_dir=tmp_path / "f")
    assert free["batch_size"] == 1


def test_runner_counts_id_loss_and_writes_an_error_row(tmp_path, monkeypatch):
    from versed_translator.harness.adapters import ollama_adapter

    def fake(items, template, **cfg):
        # Adapter silently returns nothing for the last item of each chunk.
        return [
            TranslationResult(item_id=i["id"], translation="EN", source_tokens=1,
                              output_tokens=1, latency_s=0.1)
            for i in items[:-1]
        ]

    monkeypatch.setattr(ollama_adapter, "translate_batch", fake)
    meta = runner.run(adapter_name="ollama", model="m", items_path=_items_file(tmp_path, 4),
                      out_dir=tmp_path / "runs", batch_size=2)
    rows = [json.loads(line) for line in (tmp_path / "runs" / meta["run_id"] / "results.jsonl").read_text().splitlines()]
    assert len(rows) == 4, "every sent id must have a row"
    assert meta["id_loss_count"] == 2
    assert meta["id_preservation_rate"] == 0.5
    assert meta["id_error_rows"]["id_missing_count"] == 2
    assert sum(1 for r in rows if r["error"] == ERR_ID_MISSING) == 2


def test_runner_counts_adapter_reported_id_loss_not_just_absent_rows(tmp_path, monkeypatch):
    """An adapter that already diagnosed the loss must still move the metric."""
    from versed_translator.harness.adapters import ollama_adapter

    monkeypatch.setattr(
        ollama_adapter, "translate_batch",
        lambda items, template, **cfg: batch_error_results([i["id"] for i in items], ERR_ID_MISSING),
    )
    meta = runner.run(adapter_name="ollama", model="m", items_path=_items_file(tmp_path, 3),
                      out_dir=tmp_path / "runs")
    assert meta["id_loss_count"] == 3
    assert meta["id_preservation_rate"] == 0.0


def test_split_rejects_a_non_string_id_as_a_parse_error(tmp_path, monkeypatch):
    """An unhashable id used to escape every guard as a TypeError.

    Every consumer keys a dict by the id, so `{"id": ["a"]}` raised
    `unhashable type: 'list'` out of the splitting loop, past the ValueError
    handlers, and took the whole run with it.
    """
    from versed_translator.harness.prompts import parse_structured_response

    for bad in ([{"id": ["a"], "english": "x"}], [{"id": 7, "english": "x"}]):
        with pytest.raises(ValueError, match="non-string 'id'"):
            parse_structured_response(json.dumps(bad))


def test_ollama_structured_survives_a_non_string_id(monkeypatch):
    from versed_translator.harness.adapters import ollama_adapter
    from versed_translator.harness.prompts import get_template

    payload = json.dumps([{"id": ["a"], "english": "x"}])
    monkeypatch.setattr(
        ollama_adapter, "_post", lambda *a, **k: {"response": payload}
    )
    results = ollama_adapter.translate_batch(
        [{"id": "a", "arabic": "x"}], get_template("structured_blocks_v1"), model="m"
    )
    assert results[0].error.startswith(ERR_PARSE_PREFIX)


def test_runner_emits_exactly_one_row_per_sent_id_on_a_cross_chunk_collision(tmp_path, monkeypatch):
    """A model inventing an id that a LATER chunk legitimately owns.

    Both results carry the same item_id; emitting both would duplicate a row
    in results.jsonl and desynchronise row_count from item_count.
    """
    from versed_translator.harness.adapters import ollama_adapter

    calls = {"n": 0}

    def fake(items, template, **cfg):
        calls["n"] += 1
        out = [
            TranslationResult(item_id=i["id"], translation="EN", source_tokens=1,
                              output_tokens=1, latency_s=0.1)
            for i in items
        ]
        if calls["n"] == 1:
            # Invents an id that chunk 2 will legitimately return.
            out += batch_error_results(["AR_003"], ERR_ID_UNEXPECTED)
        return out

    monkeypatch.setattr(ollama_adapter, "translate_batch", fake)
    meta = runner.run(adapter_name="ollama", model="m", items_path=_items_file(tmp_path, 4),
                      out_dir=tmp_path / "runs", batch_size=2)
    rows = [json.loads(line) for line in (tmp_path / "runs" / meta["run_id"] / "results.jsonl").read_text().splitlines()]
    ids = [r["item_id"] for r in rows]
    assert len(ids) == len(set(ids)) == 4
    assert meta["row_count"] == meta["item_count"] == 4
    collided = next(r for r in rows if r["item_id"] == "AR_003")
    assert collided["error"] == ERR_ID_DUPLICATE
    assert meta["id_loss_count"] == 1


def test_runner_keeps_an_invented_id_as_an_error_row(tmp_path, monkeypatch):
    from versed_translator.harness.adapters import ollama_adapter

    def fake(items, template, **cfg):
        out = [
            TranslationResult(item_id=i["id"], translation="EN", source_tokens=1,
                              output_tokens=1, latency_s=0.1)
            for i in items
        ]
        out.append(TranslationResult(item_id="GHOST", translation="who?", source_tokens=1,
                                     output_tokens=1, latency_s=0.1))
        return out

    monkeypatch.setattr(ollama_adapter, "translate_batch", fake)
    meta = runner.run(adapter_name="ollama", model="m", items_path=_items_file(tmp_path, 2),
                      out_dir=tmp_path / "runs")
    rows = [json.loads(line) for line in (tmp_path / "runs" / meta["run_id"] / "results.jsonl").read_text().splitlines()]
    ghost = [r for r in rows if r["item_id"] == "GHOST"]
    assert len(ghost) == 1
    assert ghost[0]["error"] == ERR_ID_UNEXPECTED
    assert ghost[0]["translation"] is None
    assert meta["id_unexpected_count"] == 1


def test_runner_one_exploding_chunk_does_not_discard_finished_chunks(tmp_path, monkeypatch):
    """The 139-lost-rows failure mode, pinned."""
    from versed_translator.harness.adapters import ollama_adapter

    calls = {"n": 0}

    def fake(items, template, **cfg):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("malformed everything")
        return [
            TranslationResult(item_id=i["id"], translation="EN", source_tokens=1,
                              output_tokens=1, latency_s=0.1)
            for i in items
        ]

    monkeypatch.setattr(ollama_adapter, "translate_batch", fake)
    meta = runner.run(adapter_name="ollama", model="m", items_path=_items_file(tmp_path, 6),
                      out_dir=tmp_path / "runs", batch_size=2)
    rows = [json.loads(line) for line in (tmp_path / "runs" / meta["run_id"] / "results.jsonl").read_text().splitlines()]
    assert len(rows) == 6
    assert meta["batch_failure_count"] == 1
    assert sum(1 for r in rows if r["error"] and r["error"].startswith("batch_failed:")) == 2
    assert sum(1 for r in rows if not r["error"]) == 4


def test_runner_still_raises_on_a_configuration_failure(tmp_path, monkeypatch):
    """A missing API key blocks the whole run; it must not become N error rows."""
    from versed_translator.harness.adapters import ollama_adapter

    def fake(items, template, **cfg):
        raise AdapterError("no credentials")

    monkeypatch.setattr(ollama_adapter, "translate_batch", fake)
    with pytest.raises(AdapterError):
        runner.run(adapter_name="ollama", model="m", items_path=_items_file(tmp_path),
                   out_dir=tmp_path / "runs")
