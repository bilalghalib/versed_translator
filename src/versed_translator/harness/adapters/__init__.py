"""Adapter registry: adapter name -> module exposing translate_batch()."""

from __future__ import annotations

from versed_translator.harness.adapters import (
    anthropic_adapter,
    ollama_adapter,
    openai_compat_adapter,
)

ADAPTERS = {
    "anthropic": anthropic_adapter,
    "ollama": ollama_adapter,
    "openai_compat": openai_compat_adapter,
}


def get_adapter(name: str):
    try:
        return ADAPTERS[name]
    except KeyError as exc:
        raise ValueError(f"unknown adapter {name!r}; known adapters: {sorted(ADAPTERS)}") from exc


__all__ = ["ADAPTERS", "get_adapter"]
