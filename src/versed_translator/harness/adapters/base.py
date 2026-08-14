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

# Defined in harness.results, not here: harness.structured also constructs
# TranslationResults, and importing this module from there would initialise
# the adapters package -> every adapter -> harness.structured, a cycle. The
# names are re-exported so this stays the canonical import site for adapters.
from versed_translator.harness.results import AdapterError, TranslationResult

__all__ = ["AdapterError", "TranslationResult"]
