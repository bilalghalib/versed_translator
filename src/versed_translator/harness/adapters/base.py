"""Shared adapter interface every backend module implements.

Each adapter module exposes a single function:

    translate_batch(items, template, exemplar=None, **cfg) -> list[TranslationResult]

``items`` is a list of ``{"id": ..., "arabic": ...}`` dicts. ``template``
is a ``harness.prompts.PromptTemplate``. For a non-structured template,
adapters call the model once per item; for a structured template they
issue one call for the whole batch and split the parsed response back
into one ``TranslationResult`` per item (marking any item whose id did
not come back in the response as an error).

No network calls happen at import time. HTTP is done with the stdlib
(``urllib.request``) rather than a new third-party dependency, since this
harness package must not touch pyproject.toml (owned elsewhere).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TranslationResult:
    item_id: str
    translation: str | None
    source_tokens: int | None
    output_tokens: int | None
    latency_s: float | None
    error: str | None = None
    # Adapters that know their provider's prices fill this in (see each
    # adapter's PRICE_TABLE); local/self-hosted adapters leave it None and
    # the run's GPU-hour cost is accounted for separately in throughput/.
    cost_estimate: float | None = None


class AdapterError(RuntimeError):
    """Raised for adapter-level setup failures (e.g. missing API key).

    Adapters should fail loudly (raise) for configuration problems that
    block the whole run, but capture per-item failures (a single bad
    response, a network hiccup on one call) as an ``error`` string on that
    item's TranslationResult instead of raising, so one bad item doesn't
    abort an entire batch.
    """
