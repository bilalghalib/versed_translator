"""Adapter for any OpenAI-compatible chat-completions endpoint.

Serves the future Modal vLLM endpoint (C2 checkpoint 3), DashScope,
DeepSeek, and similar later. Talks to `{base_url}/chat/completions` via
urllib -- no new third-party dependency, and this is explicitly a
provider-agnostic HTTP shape, not the Anthropic API, so the claude-api
skill's "use the official SDK" guidance doesn't apply here.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from versed_translator.harness.adapters.base import AdapterError, TranslationResult
from versed_translator.harness.prompts import PromptTemplate, parse_structured_response
from versed_translator.harness.structured import (
    ERR_PARSE_PREFIX,
    batch_error_results,
    split_structured_results,
)


def _post(base_url: str, path: str, payload: dict, api_key: str | None, timeout: float) -> dict:
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=body,
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def translate_batch(
    items: list[dict],
    template: PromptTemplate,
    *,
    model: str,
    base_url: str,
    api_key: str | None = None,
    exemplar: str | None = None,
    timeout: float = 180.0,
    max_tokens: int = 4096,
    **_cfg,
) -> list[TranslationResult]:
    if not model or not base_url:
        raise AdapterError("openai_compat_adapter requires both 'model' and 'base_url'")

    if template.structured:
        return _translate_structured(items, template, model, base_url, api_key, exemplar, timeout, max_tokens)
    return [
        _translate_one(item, template, model, base_url, api_key, exemplar, timeout, max_tokens) for item in items
    ]


def _chat(base_url, model, api_key, system, user_content, timeout, max_tokens):
    start = time.monotonic()
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
    }
    try:
        data = _post(base_url, "/chat/completions", payload, api_key, timeout)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise AdapterError(f"openai-compatible request failed: {exc}") from exc
    latency_s = time.monotonic() - start
    return data, latency_s


def _translate_one(item, template, model, base_url, api_key, exemplar, timeout, max_tokens) -> TranslationResult:
    user_content = template.render_single(item["arabic"], exemplar=exemplar)
    try:
        data, latency_s = _chat(base_url, model, api_key, template.system, user_content, timeout, max_tokens)
    except AdapterError as exc:
        return TranslationResult(
            item_id=item["id"], translation=None, source_tokens=None, output_tokens=None, latency_s=None, error=str(exc)
        )
    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        return TranslationResult(
            item_id=item["id"], translation=None, source_tokens=None, output_tokens=None, latency_s=latency_s,
            error=f"unexpected response shape: {exc}",
        )
    usage = data.get("usage") or {}
    return TranslationResult(
        item_id=item["id"],
        translation=text,
        source_tokens=usage.get("prompt_tokens"),
        output_tokens=usage.get("completion_tokens"),
        latency_s=latency_s,
    )


def _translate_structured(items, template, model, base_url, api_key, exemplar, timeout, max_tokens) -> list[TranslationResult]:
    user_content = template.render_batch(items, exemplar=exemplar)
    ids = [i["id"] for i in items]
    try:
        data, latency_s = _chat(base_url, model, api_key, template.system, user_content, timeout, max_tokens)
    except AdapterError as exc:
        return batch_error_results(ids, str(exc))
    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        return batch_error_results(ids, f"unexpected response shape: {exc}", latency_s=latency_s)
    usage = data.get("usage") or {}
    counts = {
        "source_tokens": usage.get("prompt_tokens"),
        "output_tokens": usage.get("completion_tokens"),
        "latency_s": latency_s,
    }
    try:
        parsed = parse_structured_response(text)
    except ValueError as exc:
        return batch_error_results(ids, f"{ERR_PARSE_PREFIX}: {exc}", **counts)

    return split_structured_results(parsed, ids, **counts)
