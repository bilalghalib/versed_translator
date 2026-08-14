"""Tests for the Modal batch prompt builder / parser.

These are what makes the Modal path's `prompt_template_id` trustworthy: the
label and the prompt come out of one registry lookup, in one object, so they
cannot disagree. See tests/test_prompts_modal_parity.py for the assertions
that the serving module itself defines no competing prompt.
"""

from __future__ import annotations

import json

import pytest

from versed_translator.harness.modal_batch import (
    DEFAULT_STRUCTURED_CHUNK,
    FALLBACK_TEMPLATE_ID,
    STRUCTURED_TEMPLATE_ID,
    build_fallback_chunks,
    build_structured_chunks,
    parse_chunk_output,
    probe_ok,
)
from versed_translator.harness.prompts import (
    MODAL_MINIMAL_V1_TEXT,
    TEMPLATES,
    get_template,
)
from versed_translator.harness.structured import (
    ERR_EMPTY,
    ERR_ID_DUPLICATE,
    ERR_ID_MISSING,
    ERR_ID_UNEXPECTED,
    ERR_PARSE_PREFIX,
)

ITEMS = [{"id": f"A#b{i:04d}", "arabic": f"arabic {i}"} for i in range(1, 8)]


# ---------------------------------------------------------------------------
# label == what was sent
# ---------------------------------------------------------------------------


def test_structured_chunk_label_matches_the_registry_template_it_sent():
    template = get_template(STRUCTURED_TEMPLATE_ID)
    for chunk in build_structured_chunks(ITEMS):
        assert chunk.template_id == template.template_id
        assert chunk.system == template.system
        assert chunk.structured is True


def test_fallback_chunk_label_matches_the_minimal_template_it_sent():
    for chunk, item in zip(build_fallback_chunks(ITEMS), ITEMS):
        assert chunk.template_id == FALLBACK_TEMPLATE_ID
        assert chunk.user == MODAL_MINIMAL_V1_TEXT.format(arabic=item["arabic"])
        assert chunk.system is None
        assert chunk.chat is False


def test_structured_template_id_is_registered_and_structured():
    assert STRUCTURED_TEMPLATE_ID in TEMPLATES
    assert TEMPLATES[STRUCTURED_TEMPLATE_ID].structured is True


def test_chunk_wire_form_is_plain_json_the_container_can_read():
    request = build_structured_chunks(ITEMS)[0].to_request()
    assert set(request) == {"system", "user", "chat"}
    json.dumps(request)  # must survive Modal serialization


def test_prompt_fingerprint_changes_with_the_prompt():
    a = build_structured_chunks(ITEMS[:2])[0]
    b = build_structured_chunks(ITEMS[2:4])[0]
    assert a.prompt_sha256 and a.prompt_sha256 != b.prompt_sha256


# ---------------------------------------------------------------------------
# chunking
# ---------------------------------------------------------------------------


def test_structured_chunking_covers_every_id_exactly_once():
    chunks = build_structured_chunks(ITEMS, chunk_size=3)
    assert [len(c.ids) for c in chunks] == [3, 3, 1]
    flat = [i for c in chunks for i in c.ids]
    assert flat == [i["id"] for i in ITEMS]


def test_structured_prompt_carries_the_ids_it_claims():
    chunk = build_structured_chunks(ITEMS, chunk_size=3)[0]
    payload = json.loads(next(ln for ln in chunk.user.splitlines() if ln.startswith("[")))
    assert [p["id"] for p in payload] == list(chunk.ids)


def test_default_chunk_is_small_enough_to_bound_a_bad_response():
    assert 1 <= DEFAULT_STRUCTURED_CHUNK <= 8


def test_build_structured_rejects_a_free_text_template():
    with pytest.raises(ValueError):
        build_structured_chunks(ITEMS, template_id="v1")


# ---------------------------------------------------------------------------
# parse_chunk_output: every id accounted for, nothing raises
# ---------------------------------------------------------------------------


def _chunk(n=2):
    return build_structured_chunks(ITEMS[:n], chunk_size=n)[0]


def test_parse_returns_one_row_per_sent_id():
    chunk = _chunk(2)
    text = json.dumps([{"id": i, "english": f"EN {i}"} for i in chunk.ids])
    rows = parse_chunk_output(chunk, text)
    assert [r["id"] for r in rows] == list(chunk.ids)
    assert all(r.get("error") is None for r in rows)


def test_parse_degrades_the_whole_chunk_on_malformed_json():
    chunk = _chunk(3 if len(ITEMS) >= 3 else 2)
    rows = parse_chunk_output(chunk, "Here is your translation, friend!")
    assert [r["id"] for r in rows] == list(chunk.ids)
    assert all(r["error"].startswith(ERR_PARSE_PREFIX) for r in rows)
    assert all(r["english"] is None for r in rows)


def test_parse_survives_a_code_fenced_response():
    chunk = _chunk(1)
    body = json.dumps([{"id": chunk.ids[0], "english": "EN"}])
    rows = parse_chunk_output(chunk, f"```json\n{body}\n```")
    assert rows[0]["english"] == "EN"


def test_parse_names_missing_duplicate_empty_and_invented_ids():
    chunk = _chunk(2)
    a, b = chunk.ids
    rows = {r["id"]: r for r in parse_chunk_output(chunk, json.dumps([
        {"id": a, "english": "EN"}, {"id": "GHOST", "english": "junk"},
    ]))}
    assert rows[b]["error"] == ERR_ID_MISSING
    assert rows["GHOST"]["error"] == ERR_ID_UNEXPECTED

    rows = {r["id"]: r for r in parse_chunk_output(chunk, json.dumps([
        {"id": a, "english": "EN"}, {"id": a, "english": "EN2"}, {"id": b, "english": "  "},
    ]))}
    assert rows[a]["error"] == ERR_ID_DUPLICATE
    assert rows[b]["error"] == ERR_EMPTY


def test_parse_carries_usage_fields_through():
    chunk = _chunk(1)
    text = json.dumps([{"id": chunk.ids[0], "english": "EN"}])
    row = parse_chunk_output(chunk, text, output_tokens=42, latency_s=0.5)[0]
    assert row["output_tokens"] == 42
    assert row["latency_s"] == 0.5


def test_parse_of_a_fallback_chunk_is_the_raw_text():
    chunk = build_fallback_chunks(ITEMS[:1])[0]
    rows = parse_chunk_output(chunk, "  In the name of God  ")
    assert rows == [{"id": chunk.ids[0], "english": "In the name of God"}]


def test_parse_of_an_empty_fallback_response_is_an_error_not_an_empty_string():
    chunk = build_fallback_chunks(ITEMS[:1])[0]
    assert parse_chunk_output(chunk, "   ")[0]["error"] == ERR_EMPTY


# ---------------------------------------------------------------------------
# probe
# ---------------------------------------------------------------------------


def test_probe_ok_requires_every_id_clean():
    assert probe_ok([{"id": "a", "english": "A"}]) is True
    assert probe_ok([{"id": "a", "english": "A"}, {"id": "b", "english": None, "error": "x"}]) is False
    assert probe_ok([]) is False
