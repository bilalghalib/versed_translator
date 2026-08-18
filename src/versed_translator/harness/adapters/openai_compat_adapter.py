"""Adapter for any OpenAI-compatible chat-completions endpoint.

Serves the future Modal vLLM endpoint (C2 checkpoint 3), DashScope,
DeepSeek, Gemini's OpenAI-compat surface, and similar later. Talks to
`{base_url}/chat/completions` via urllib -- no new third-party dependency.
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

_RETRY_STATUSES = {408, 429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 5


def _post(base_url: str, path: str, payload: dict, api_key: str | None, timeout: float) -> dict:
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    url = f"{base_url.rstrip('/')}{path}"
    last_err: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")[:500]
            last_err = AdapterError(f"HTTP {exc.code}: {err_body}")
            if exc.code not in _RETRY_STATUSES or attempt == _MAX_ATTEMPTS - 1:
                raise last_err from exc
            time.sleep(min(2 ** attempt, 20))
        except (urllib.error.URLError, TimeoutError) as exc:
            last_err = AdapterError(f"openai-compatible request failed: {exc}")
            if attempt == _MAX_ATTEMPTS - 1:
                raise last_err from exc
            time.sleep(min(2 ** attempt, 20))
    raise last_err or AdapterError("openai-compatible request failed")


def translate_batch(
    items: list[dict],
    template: PromptTemplate,
    *,
    model: str,
    base_url: str,
    api_key: str | None = None,
    exemplar: str | None = None,
    timeout: float = 180.0,
    max_tokens: int | None = 4096,
    extra_body: dict | None = None,
    **_cfg,
) -> list[TranslationResult]:
    if not model or not base_url:
        raise AdapterError("openai_compat_adapter requires both 'model' and 'base_url'")

    if template.structured:
        return _translate_structured(
            items, template, model, base_url, api_key, exemplar, timeout, max_tokens, extra_body
        )
    return [
        _translate_one(
            item, template, model, base_url, api_key, exemplar, timeout, max_tokens, extra_body
        )
        for item in items
    ]


def _chat(base_url, model, api_key, system, user_content, timeout, max_tokens, extra_body):
    start = time.monotonic()
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user_content})
    payload: dict = {
        "model": model,
        "messages": messages,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if extra_body:
        payload.update(extra_body)
    try:
        data = _post(base_url, "/chat/completions", payload, api_key, timeout)
    except AdapterError:
        raise
    except (urllib.error.URLError, TimeoutError) as exc:
        raise AdapterError(f"openai-compatible request failed: {exc}") from exc
    latency_s = time.monotonic() - start
    return data, latency_s


def _message_text(data: dict) -> str | None:
    try:
        msg = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return None
    content = msg.get("content")
    if isinstance(content, str) and content.strip():
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and part.get("text"):
                parts.append(part["text"])
            elif isinstance(part, str):
                parts.append(part)
        joined = "".join(parts).strip()
        return joined or None
    return None


def _usage(data: dict) -> dict:
    usage = data.get("usage") or {}
    return {
        "source_tokens": usage.get("prompt_tokens"),
        "output_tokens": usage.get("completion_tokens"),
    }


def _translate_one(
    item, template, model, base_url, api_key, exemplar, timeout, max_tokens, extra_body
) -> TranslationResult:
    user_content = template.render_single(item["arabic"], exemplar=exemplar)
    try:
        data, latency_s = _chat(
            base_url, model, api_key, template.system, user_content, timeout, max_tokens, extra_body
        )
    except AdapterError as exc:
        return TranslationResult(
            item_id=item["id"], translation=None, source_tokens=None, output_tokens=None, latency_s=None, error=str(exc)
        )
    text = _message_text(data)
    counts = _usage(data)
    if not text:
        return TranslationResult(
            item_id=item["id"],
            translation=None,
            source_tokens=counts["source_tokens"],
            output_tokens=counts["output_tokens"],
            latency_s=latency_s,
            error="empty_or_missing_message_content",
        )
    return TranslationResult(
        item_id=item["id"],
        translation=text,
        source_tokens=counts["source_tokens"],
        output_tokens=counts["output_tokens"],
        latency_s=latency_s,
    )


def _translate_structured(
    items, template, model, base_url, api_key, exemplar, timeout, max_tokens, extra_body
) -> list[TranslationResult]:
    user_content = template.render_batch(items, exemplar=exemplar)
    ids = [i["id"] for i in items]
    try:
        data, latency_s = _chat(
            base_url, model, api_key, template.system, user_content, timeout, max_tokens, extra_body
        )
    except AdapterError as exc:
        return batch_error_results(ids, str(exc))
    text = _message_text(data)
    counts = _usage(data)
    counts["latency_s"] = latency_s
    if not text:
        return batch_error_results(ids, "empty_or_missing_message_content", **counts)
    try:
        parsed = parse_structured_response(text)
    except ValueError as exc:
        return batch_error_results(ids, f"{ERR_PARSE_PREFIX}: {exc}", **counts)

    return split_structured_results(parsed, ids, **counts)
