"""Local Ollama HTTP adapter (http://localhost:11434 by default).

Ollama has no official Python SDK requirement here (it's a local inference
server, not one of the hosted LLM providers) -- talks to its REST API
directly via urllib, no new third-party dependency. Cost is always 0.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from versed_translator.harness.adapters.base import AdapterError, TranslationResult
from versed_translator.harness.prompts import PromptTemplate, parse_structured_response

DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "translategemma:12b"


def _post(base_url: str, path: str, payload: dict, timeout: float) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def translate_batch(
    items: list[dict],
    template: PromptTemplate,
    *,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_BASE_URL,
    exemplar: str | None = None,
    timeout: float = 180.0,
    **_cfg,
) -> list[TranslationResult]:
    if template.structured:
        return _translate_structured(items, template, model, base_url, exemplar, timeout)
    return [_translate_one(item, template, model, base_url, exemplar, timeout) for item in items]


def _generate(base_url: str, model: str, system: str, prompt: str, timeout: float) -> tuple[dict, float]:
    start = time.monotonic()
    payload = {
        "model": model,
        "system": system,
        "prompt": prompt,
        "stream": False,
    }
    try:
        data = _post(base_url, "/api/generate", payload, timeout)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise AdapterError(f"ollama request failed: {exc}") from exc
    latency_s = time.monotonic() - start
    return data, latency_s


def _translate_one(item, template, model, base_url, exemplar, timeout) -> TranslationResult:
    prompt = template.render_single(item["arabic"], exemplar=exemplar)
    try:
        data, latency_s = _generate(base_url, model, template.system, prompt, timeout)
    except AdapterError as exc:
        return TranslationResult(
            item_id=item["id"], translation=None, source_tokens=None, output_tokens=None, latency_s=None, error=str(exc)
        )
    return TranslationResult(
        item_id=item["id"],
        translation=data.get("response", ""),
        source_tokens=data.get("prompt_eval_count"),
        output_tokens=data.get("eval_count"),
        latency_s=latency_s,
    )


def _translate_structured(items, template, model, base_url, exemplar, timeout) -> list[TranslationResult]:
    prompt = template.render_batch(items, exemplar=exemplar)
    ids = [i["id"] for i in items]
    try:
        data, latency_s = _generate(base_url, model, template.system, prompt, timeout)
    except AdapterError as exc:
        return [
            TranslationResult(item_id=i, translation=None, source_tokens=None, output_tokens=None, latency_s=None, error=str(exc))
            for i in ids
        ]

    source_tokens = data.get("prompt_eval_count")
    output_tokens = data.get("eval_count")
    try:
        parsed = parse_structured_response(data.get("response", ""))
    except ValueError as exc:
        err = f"structured_parse_error: {exc}"
        return [
            TranslationResult(item_id=i, translation=None, source_tokens=source_tokens, output_tokens=output_tokens, latency_s=latency_s, error=err)
            for i in ids
        ]

    by_id = {obj["id"]: obj["english"] for obj in parsed if isinstance(obj, dict) and "id" in obj}
    results = []
    for item_id in ids:
        if item_id in by_id:
            results.append(
                TranslationResult(
                    item_id=item_id,
                    translation=by_id[item_id],
                    source_tokens=source_tokens,
                    output_tokens=output_tokens,
                    latency_s=latency_s,
                )
            )
        else:
            results.append(
                TranslationResult(
                    item_id=item_id,
                    translation=None,
                    source_tokens=source_tokens,
                    output_tokens=output_tokens,
                    latency_s=latency_s,
                    error="id_missing_from_structured_response",
                )
            )
    return results
