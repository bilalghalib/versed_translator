"""Anthropic Messages API adapter.

Uses the official `anthropic` Python SDK (not raw HTTP) per the repo's LLM
tooling convention. NOTE: this SDK is not yet declared in pyproject.toml --
this harness package cannot touch that file (owned elsewhere; see repo hard
rules), so `anthropic` was installed ad hoc into the shared venv
(`uv pip install anthropic`) rather than via `uv add`. Whoever owns
pyproject.toml should add `anthropic>=0.121` as a proper dependency; until
then, a bare `uv sync` may remove this package from the venv.

Auth: reads ANTHROPIC_API_KEY from the environment (already exported in the
parent shell per the task brief). Fails loudly if absent -- no silent
fallback to a different credential source, since this is a lab script,
not an interactive CLI session.
"""

from __future__ import annotations

import os
import time

from versed_translator.harness.adapters.base import AdapterError, TranslationResult
from versed_translator.harness.prompts import PromptTemplate, parse_structured_response

DEFAULT_MODEL = "claude-sonnet-5"

# $/million tokens, list API pricing. NEEDS VERIFICATION -- re-check against
# shared/live-sources.md's Pricing URL before trusting cost_estimate for any
# real spend decision. Sonnet 5 carries an introductory rate through
# 2026-08-31; this table uses the standard (post-intro) rate as the
# conservative default.
PRICE_TABLE: dict[str, dict[str, float]] = {
    "claude-sonnet-5": {"input": 3.00, "output": 15.00},
    "claude-opus-5": {"input": 5.00, "output": 25.00},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
}


def _get_client():
    try:
        import anthropic
    except ImportError as exc:
        raise AdapterError(
            "the 'anthropic' package is not installed in this environment "
            "(see this module's docstring)"
        ) from exc
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise AdapterError(
            "ANTHROPIC_API_KEY is not set in the environment -- refusing to "
            "guess a credential source for this lab script"
        )
    return anthropic.Anthropic(api_key=api_key)


def _cost_estimate(model: str, source_tokens: int | None, output_tokens: int | None) -> float | None:
    prices = PRICE_TABLE.get(model)
    if prices is None or source_tokens is None or output_tokens is None:
        return None
    return (source_tokens / 1_000_000) * prices["input"] + (output_tokens / 1_000_000) * prices["output"]


def translate_batch(
    items: list[dict],
    template: PromptTemplate,
    *,
    model: str = DEFAULT_MODEL,
    exemplar: str | None = None,
    max_tokens: int = 4096,
    client=None,
    **_cfg,
) -> list[TranslationResult]:
    """Translate a batch of {"id", "arabic"} items via the Anthropic API.

    For a non-structured template, issues one Messages API call per item.
    For a structured template, issues a single call for the whole batch and
    splits the parsed JSON response into one TranslationResult per item,
    flagging any item whose id is missing from the response as an error.
    """
    client = client or _get_client()

    if template.structured:
        return _translate_structured(client, items, template, model, exemplar, max_tokens)
    return [_translate_one(client, item, template, model, exemplar, max_tokens) for item in items]


def _translate_one(client, item, template, model, exemplar, max_tokens) -> TranslationResult:
    user_content = template.render_single(item["arabic"], exemplar=exemplar)
    start = time.monotonic()
    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=template.system,
            messages=[{"role": "user", "content": user_content}],
        )
    except Exception as exc:  # noqa: BLE001 -- one bad item must not abort the batch
        return TranslationResult(
            item_id=item["id"],
            translation=None,
            source_tokens=None,
            output_tokens=None,
            latency_s=time.monotonic() - start,
            error=f"{type(exc).__name__}: {exc}",
        )
    latency_s = time.monotonic() - start

    if response.stop_reason == "refusal":
        return TranslationResult(
            item_id=item["id"],
            translation=None,
            source_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            latency_s=latency_s,
            error="refusal",
        )

    text = "".join(block.text for block in response.content if block.type == "text")
    return TranslationResult(
        item_id=item["id"],
        translation=text,
        source_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        latency_s=latency_s,
    )


def _translate_structured(client, items, template, model, exemplar, max_tokens) -> list[TranslationResult]:
    user_content = template.render_batch(items, exemplar=exemplar)
    start = time.monotonic()
    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=template.system,
            messages=[{"role": "user", "content": user_content}],
        )
    except Exception as exc:  # noqa: BLE001
        err = f"{type(exc).__name__}: {exc}"
        return [
            TranslationResult(item_id=i["id"], translation=None, source_tokens=None, output_tokens=None, latency_s=None, error=err)
            for i in items
        ]
    latency_s = time.monotonic() - start

    if response.stop_reason == "refusal":
        return [
            TranslationResult(
                item_id=i["id"],
                translation=None,
                source_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                latency_s=latency_s,
                error="refusal",
            )
            for i in items
        ]

    text = "".join(block.text for block in response.content if block.type == "text")
    ids = [i["id"] for i in items]
    try:
        parsed = parse_structured_response(text)
    except ValueError as exc:
        err = f"structured_parse_error: {exc}"
        return [
            TranslationResult(
                item_id=i,
                translation=None,
                source_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                latency_s=latency_s,
                error=err,
            )
            for i in ids
        ]

    by_id = {obj["id"]: obj["english"] for obj in parsed if isinstance(obj, dict) and "id" in obj}
    # Per-item token/latency figures aren't separable from a batched call;
    # attribute the whole call's totals to each item so run-level aggregates
    # (sum of source_tokens across a run) stay meaningful for cost tracking,
    # while acknowledging this over-counts if summed per item.
    results = []
    for item_id in ids:
        if item_id in by_id:
            results.append(
                TranslationResult(
                    item_id=item_id,
                    translation=by_id[item_id],
                    source_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    latency_s=latency_s,
                )
            )
        else:
            results.append(
                TranslationResult(
                    item_id=item_id,
                    translation=None,
                    source_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    latency_s=latency_s,
                    error="id_missing_from_structured_response",
                )
            )
    return results
