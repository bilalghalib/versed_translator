"""Unit tests for the C2 translation harness: schema validation, prompt
registry, id-preservation, scoring, and adapter selection with mocked
network. No live network calls happen in this file -- the live smoke test
is run manually (see the C2 checkpoint task), not as part of pytest.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from versed_translator.harness.adapters import ADAPTERS, get_adapter
from versed_translator.harness.adapters.base import TranslationResult
from versed_translator.harness.prompts import (
    FIDELITY_RULES,
    TEMPLATES,
    get_template,
    parse_structured_response,
)
from versed_translator.harness.schema import ROW_FIELDS, make_row, validate_row
from versed_translator.harness.score import (
    chrf_score,
    flag_length_ratio,
    has_untranslated_arabic,
    id_preservation_report,
    length_ratio,
    render_markdown,
    score_run,
)

# ---------------------------------------------------------------------------
# schema.py
# ---------------------------------------------------------------------------


def test_make_row_defaults_omitted_fields_to_none():
    row = make_row(run_id="r1", item_id="AR_001", model="m", adapter="a", prompt_template_id="v1", translation="hi")
    assert set(row.keys()) == set(ROW_FIELDS)
    assert row["quantization"] is None
    assert row["error"] is None


def test_make_row_rejects_unknown_field():
    with pytest.raises(ValueError):
        make_row(not_a_real_field="x")


def test_validate_row_flags_missing_and_extra_fields():
    row = {k: None for k in ROW_FIELDS}
    del row["translation"]
    row["bogus"] = 1
    problems = validate_row(row)
    assert any("missing" in p for p in problems)
    assert any("unexpected" in p for p in problems)


def test_validate_row_requires_core_fields_on_success():
    row = make_row(run_id="r1", item_id="AR_001", model="m", adapter="a", prompt_template_id="v1", translation=None)
    problems = validate_row(row)
    assert any("translation" in p for p in problems)


def test_validate_row_ok_on_error_row_with_null_translation():
    row = make_row(run_id="r1", item_id="AR_001", model="m", adapter="a", prompt_template_id="v1", translation=None, error="boom")
    assert validate_row(row) == []


# ---------------------------------------------------------------------------
# prompts.py
# ---------------------------------------------------------------------------


def test_fidelity_rules_nonempty_and_cover_known_topics():
    assert len(FIDELITY_RULES) >= 5
    joined = " ".join(FIDELITY_RULES).lower()
    for keyword in ["divine", "rasul", "honorific", "clause", "hedging"]:
        assert keyword in joined


def test_get_template_v1_is_free_text():
    t = get_template("v1")
    assert t.structured is False
    prompt = t.render_single("بسم الله")
    assert "بسم الله" in prompt


def test_get_template_structured_renders_id_preserving_payload():
    t = get_template("structured_blocks_v1")
    assert t.structured is True
    items = [{"id": "AR_001", "arabic": "بسم الله"}, {"id": "AR_002", "arabic": "الحمد لله"}]
    prompt = t.render_batch(items)
    payload = json.loads(prompt.strip().splitlines()[-1])
    assert [p["id"] for p in payload] == ["AR_001", "AR_002"]


def test_get_template_unknown_raises():
    with pytest.raises(ValueError):
        get_template("nonexistent-template")


def test_render_single_on_structured_template_raises():
    t = TEMPLATES["structured_blocks_v1"]
    with pytest.raises(ValueError):
        t.render_single("text")


def test_parse_structured_response_valid():
    raw = json.dumps([{"id": "AR_001", "english": "In the name of God"}])
    parsed = parse_structured_response(raw)
    assert parsed[0]["id"] == "AR_001"


def test_parse_structured_response_strips_code_fence():
    raw = "```json\n" + json.dumps([{"id": "AR_001", "english": "x"}]) + "\n```"
    parsed = parse_structured_response(raw)
    assert parsed[0]["english"] == "x"


def test_parse_structured_response_rejects_non_array():
    with pytest.raises(ValueError):
        parse_structured_response(json.dumps({"id": "AR_001", "english": "x"}))


def test_parse_structured_response_rejects_missing_keys():
    with pytest.raises(ValueError):
        parse_structured_response(json.dumps([{"id": "AR_001"}]))


# ---------------------------------------------------------------------------
# score.py
# ---------------------------------------------------------------------------


def test_has_untranslated_arabic():
    assert has_untranslated_arabic("hello world") is False
    assert has_untranslated_arabic("hello السلام") is True
    assert has_untranslated_arabic(None) is False


def test_length_ratio_and_flag():
    ratio = length_ratio("one two three", "one two three four")
    assert ratio == pytest.approx(4 / 3)
    assert flag_length_ratio(ratio) is False
    assert flag_length_ratio(0.1) is True
    assert flag_length_ratio(10.0) is True
    assert flag_length_ratio(None) is False


def test_length_ratio_handles_empty_source():
    assert length_ratio("", "some text") is None
    assert length_ratio(None, "some text") is None


def test_chrf_score_perfect_match_is_high():
    score = chrf_score(["the cat sat on the mat"], ["the cat sat on the mat"])
    assert score is not None
    assert score > 90


def test_chrf_score_no_pairs_returns_none():
    assert chrf_score([], []) is None


def test_id_preservation_report_counts_violations():
    rows = [
        {"error": None},
        {"error": "id_missing_from_structured_response"},
        {"error": "some_other_error"},
    ]
    report = id_preservation_report(rows)
    assert report["total"] == 3
    assert report["id_violations"] == 1
    assert report["id_preservation_rate"] == pytest.approx(2 / 3)


def test_score_run_aggregates_error_and_success_counts():
    rows = [
        make_row(run_id="r", item_id="1", model="m", adapter="a", prompt_template_id="v1", translation="hello", latency_s=1.0),
        make_row(run_id="r", item_id="2", model="m", adapter="a", prompt_template_id="v1", translation=None, error="boom", latency_s=0.5),
    ]
    report = score_run(rows)
    assert report["total_items"] == 2
    assert report["success_count"] == 1
    assert report["error_count"] == 1
    assert report["error_rate"] == pytest.approx(0.5)


def test_score_run_flags_untranslated_arabic():
    rows = [
        make_row(run_id="r", item_id="1", model="m", adapter="a", prompt_template_id="v1", translation="still has السلام in it"),
    ]
    report = score_run(rows)
    assert report["untranslated_arabic_count"] == 1


def test_render_markdown_never_quotes_item_text():
    rows = [
        make_row(run_id="r", item_id="1", model="m", adapter="a", prompt_template_id="v1", translation="SECRET_TRANSLATION_TEXT"),
    ]
    report = score_run(rows)
    md = render_markdown(report)
    assert "SECRET_TRANSLATION_TEXT" not in md
    assert "# Harness Run Report" in md


# ---------------------------------------------------------------------------
# adapter selection (network mocked)
# ---------------------------------------------------------------------------


def test_get_adapter_known_names():
    for name in ("anthropic", "ollama", "openai_compat"):
        assert get_adapter(name) is ADAPTERS[name]


def test_get_adapter_unknown_raises():
    with pytest.raises(ValueError):
        get_adapter("not_a_real_adapter")


def test_anthropic_adapter_translate_batch_mocked(monkeypatch):
    from versed_translator.harness.adapters import anthropic_adapter
    from versed_translator.harness.prompts import get_template

    class FakeUsage:
        input_tokens = 12
        output_tokens = 7

    class FakeBlock:
        type = "text"
        text = "In the name of God"

    class FakeResponse:
        stop_reason = "end_turn"
        content = (FakeBlock(),)
        usage = FakeUsage()

    class FakeMessages:
        def create(self, **kwargs):
            return FakeResponse()

    fake_client = SimpleNamespace(messages=FakeMessages())

    template = get_template("v1")
    items = [{"id": "AR_001", "arabic": "بسم الله"}]
    results = anthropic_adapter.translate_batch(items, template, model="claude-sonnet-5", client=fake_client)
    assert len(results) == 1
    assert isinstance(results[0], TranslationResult)
    assert results[0].translation == "In the name of God"
    assert results[0].source_tokens == 12
    assert results[0].output_tokens == 7
    assert results[0].error is None


def test_anthropic_adapter_handles_refusal(monkeypatch):
    from versed_translator.harness.adapters import anthropic_adapter
    from versed_translator.harness.prompts import get_template

    class FakeUsage:
        input_tokens = 5
        output_tokens = 0

    class FakeResponse:
        stop_reason = "refusal"
        content: tuple = ()
        usage = FakeUsage()

    class FakeMessages:
        def create(self, **kwargs):
            return FakeResponse()

    fake_client = SimpleNamespace(messages=FakeMessages())
    template = get_template("v1")
    items = [{"id": "AR_001", "arabic": "text"}]
    results = anthropic_adapter.translate_batch(items, template, model="claude-sonnet-5", client=fake_client)
    assert results[0].error == "refusal"
    assert results[0].translation is None


def test_anthropic_adapter_structured_flags_missing_id(monkeypatch):
    from versed_translator.harness.adapters import anthropic_adapter
    from versed_translator.harness.prompts import get_template

    class FakeUsage:
        input_tokens = 20
        output_tokens = 10

    class FakeBlock:
        type = "text"
        text = json.dumps([{"id": "AR_001", "english": "translated one"}])

    class FakeResponse:
        stop_reason = "end_turn"
        content = (FakeBlock(),)
        usage = FakeUsage()

    class FakeMessages:
        def create(self, **kwargs):
            return FakeResponse()

    fake_client = SimpleNamespace(messages=FakeMessages())
    template = get_template("structured_blocks_v1")
    items = [{"id": "AR_001", "arabic": "x"}, {"id": "AR_002", "arabic": "y"}]
    results = anthropic_adapter.translate_batch(items, template, model="claude-sonnet-5", client=fake_client)
    by_id = {r.item_id: r for r in results}
    assert by_id["AR_001"].error is None
    assert by_id["AR_002"].error == "id_missing_from_structured_response"


def test_ollama_adapter_translate_batch_mocked(monkeypatch):
    from versed_translator.harness.adapters import ollama_adapter
    from versed_translator.harness.prompts import get_template

    def fake_post(base_url, path, payload, timeout):
        assert path == "/api/generate"
        return {"response": "translated text", "prompt_eval_count": 9, "eval_count": 4}

    monkeypatch.setattr(ollama_adapter, "_post", fake_post)
    template = get_template("v1")
    items = [{"id": "AR_001", "arabic": "text"}]
    results = ollama_adapter.translate_batch(items, template, model="translategemma:12b")
    assert results[0].translation == "translated text"
    assert results[0].source_tokens == 9
    assert results[0].output_tokens == 4


def test_ollama_adapter_network_failure_becomes_row_error(monkeypatch):
    import urllib.error

    from versed_translator.harness.adapters import ollama_adapter
    from versed_translator.harness.prompts import get_template

    def fake_post(base_url, path, payload, timeout):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(ollama_adapter, "_post", fake_post)
    template = get_template("v1")
    items = [{"id": "AR_001", "arabic": "text"}]
    results = ollama_adapter.translate_batch(items, template, model="translategemma:12b")
    assert results[0].error is not None
    assert results[0].translation is None


def test_openai_compat_adapter_translate_batch_mocked(monkeypatch):
    from versed_translator.harness.adapters import openai_compat_adapter
    from versed_translator.harness.prompts import get_template

    def fake_post(base_url, path, payload, api_key, timeout):
        return {
            "choices": [{"message": {"content": "translated"}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2},
        }

    monkeypatch.setattr(openai_compat_adapter, "_post", fake_post)
    template = get_template("v1")
    items = [{"id": "AR_001", "arabic": "text"}]
    results = openai_compat_adapter.translate_batch(
        items, template, model="deepseek-chat", base_url="https://example.com/v1"
    )
    assert results[0].translation == "translated"
    assert results[0].source_tokens == 3


def test_openai_compat_adapter_requires_model_and_base_url():
    from versed_translator.harness.adapters import openai_compat_adapter
    from versed_translator.harness.adapters.base import AdapterError
    from versed_translator.harness.prompts import get_template

    template = get_template("v1")
    with pytest.raises(AdapterError):
        openai_compat_adapter.translate_batch([{"id": "1", "arabic": "x"}], template, model="", base_url="")


# ---------------------------------------------------------------------------
# runner.py (I/O against a tmp_path scratch dir; no network)
# ---------------------------------------------------------------------------


def test_runner_writes_results_and_run_meta(tmp_path, monkeypatch):
    from versed_translator.harness import runner

    items_path = tmp_path / "items.jsonl"
    items_path.write_text(
        "\n".join(
            json.dumps(obj)
            for obj in [{"id": "AR_001", "arabic": "text one"}, {"id": "AR_002", "arabic": "text two"}]
        ),
        encoding="utf-8",
    )

    def fake_translate_batch(items, template, **cfg):
        from versed_translator.harness.adapters.base import TranslationResult

        return [
            TranslationResult(item_id=i["id"], translation=f"EN:{i['id']}", source_tokens=5, output_tokens=5, latency_s=0.01)
            for i in items
        ]

    from versed_translator.harness.adapters import ollama_adapter

    monkeypatch.setattr(ollama_adapter, "translate_batch", fake_translate_batch)

    out_dir = tmp_path / "runs"
    run_meta = runner.run(
        adapter_name="ollama",
        model="translategemma:12b",
        template_id="v1",
        items_path=items_path,
        out_dir=out_dir,
    )
    run_dir = out_dir / run_meta["run_id"]
    assert (run_dir / "results.jsonl").exists()
    assert (run_dir / "run_meta.json").exists()
    rows = [json.loads(line) for line in (run_dir / "results.jsonl").read_text().splitlines()]
    assert len(rows) == 2
    assert rows[0]["translation"] == "EN:AR_001"
    assert run_meta["item_count"] == 2
    assert run_meta["error_count"] == 0
