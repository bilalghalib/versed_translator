"""Versioned prompt registry for the C2 translation harness.

Two template families:

* ``v1`` -- free-text Classical Arabic -> scholarly, faithful English,
  one item per call. Carries the fidelity rules distilled from real model
  failure analysis (see TRANSLATION_EXPERIMENTS.md EXP-2026Q2-03 and
  VERSED_TRANSLATION_ARCHITECTURE.md's local_translation section): divine
  names, rasul vs. nabi, no added honorifics, no summarizing, preserve
  numbers/names/quotations/repetition, preserve hedging.
* ``structured_blocks_v1`` -- batched call: input a JSON list of
  ``{id, arabic}`` objects, output a JSON list of ``{id, english}``
  objects with ids preserved exactly. The harness (not this module)
  validates id preservation on the response; see
  ``harness.score.id_preservation_report``.

RIGHTS NOTE: an optional few-shot exemplar (the "few-shot-Ormsby" finding:
one register-setting example measurably shifts output register, see
TRANSLATION_EXPERIMENTS.md EXP-20260326-01) may be loaded from a *local
file path* named by the ``VERSED_EXEMPLAR_PATH`` environment variable.
Nothing under that path is ever read into this repo, committed, or
embedded in source here -- the loader only opens whatever path the
environment points at, at run time, on the machine running the harness.
If the env var is unset, prompts render with no exemplar and callers get
plain zero-shot.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

PROMPT_VERSION = "harness-v1"

# Fidelity rules seeded from local_translation/prompts.py's DeepSeek/Gemma
# failure-mode analysis (EXP-2026Q2-03). These are instructions to the
# model, not corpus text, so they are fine to keep verbatim in this public
# repo -- they don't quote any source Arabic or copyrighted English.
FIDELITY_RULES: tuple[str, ...] = (
    (
        "Preserve divine names and attributes exactly as given; do not "
        "paraphrase, substitute, or omit them."
    ),
    (
        "Distinguish rasul (messenger) from nabi (prophet) consistently; do "
        "not collapse the two into one English word."
    ),
    (
        "Do not add honorifics, blessings, or epithets that are not present "
        "in the source text."
    ),
    (
        "Translate every clause. Do not summarize, compress, or silently "
        "drop material for length or fluency."
    ),
    (
        "Preserve numbers, proper names, quotations, and rhetorical "
        "repetition exactly as structured in the source -- do not vary "
        "wording to avoid repeating a word the source itself repeats."
    ),
    (
        "Preserve hedging and epistemic uncertainty markers in the source "
        "(e.g. 'it is said', 'God knows best', reported-speech framing) "
        "rather than flattening them into confident assertions."
    ),
)

_FIDELITY_BLOCK = "\n".join(f"- {rule}" for rule in FIDELITY_RULES)

_V1_SYSTEM = (
    "You are a scholarly translator of Classical Arabic into English. "
    "Produce a faithful, scholarly-register translation suitable for "
    "specialists in Islamic and Arabic intellectual history. Follow "
    "these fidelity rules strictly:\n" + _FIDELITY_BLOCK
)

_STRUCTURED_SYSTEM = (
    "You are a scholarly translator of Classical Arabic into English. "
    "You will receive a JSON array of objects, each with an 'id' and an "
    "'arabic' field. Translate each 'arabic' field into faithful, "
    "scholarly-register English and return a JSON array of objects, each "
    "with the SAME 'id' (copied exactly, unchanged) and an 'english' "
    "field holding its translation. Return ONLY the JSON array, no other "
    "text. Follow these fidelity rules strictly:\n" + _FIDELITY_BLOCK
)


@dataclass(frozen=True)
class PromptTemplate:
    template_id: str
    system: str
    structured: bool  # True: batched JSON-in/JSON-out; False: one item per call.

    def render_single(self, arabic: str, exemplar: str | None = None) -> str:
        if self.structured:
            raise ValueError(f"{self.template_id} is a structured template; use render_batch")
        parts = []
        if exemplar:
            parts.append(
                "Here is one example translation illustrating the target "
                f"register:\n{exemplar}\n"
            )
        parts.append(f"Translate the following Classical Arabic text:\n\n{arabic}")
        return "\n".join(parts)

    def render_batch(self, items: list[dict], exemplar: str | None = None) -> str:
        if not self.structured:
            raise ValueError(f"{self.template_id} is not a structured template; use render_single")
        payload = [{"id": item["id"], "arabic": item["arabic"]} for item in items]
        parts = []
        if exemplar:
            parts.append(
                "Here is one example translation illustrating the target "
                f"register:\n{exemplar}\n"
            )
        parts.append(json.dumps(payload, ensure_ascii=False))
        return "\n".join(parts)


TEMPLATES: dict[str, PromptTemplate] = {
    "v1": PromptTemplate(template_id="v1", system=_V1_SYSTEM, structured=False),
    "structured_blocks_v1": PromptTemplate(
        template_id="structured_blocks_v1", system=_STRUCTURED_SYSTEM, structured=True
    ),
}


def get_template(template_id: str) -> PromptTemplate:
    try:
        return TEMPLATES[template_id]
    except KeyError as exc:
        raise ValueError(
            f"unknown prompt template_id {template_id!r}; known: {sorted(TEMPLATES)}"
        ) from exc


def load_exemplar() -> str | None:
    """Load an optional few-shot exemplar from VERSED_EXEMPLAR_PATH.

    Returns None if the env var is unset or the file cannot be read.
    Never call this to write exemplar content anywhere inside this repo.
    """
    path = os.environ.get("VERSED_EXEMPLAR_PATH")
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def parse_structured_response(raw: str) -> list[dict]:
    """Parse a structured-blocks model response into a list of {id, english}.

    Tolerates responses wrapped in markdown code fences. Raises ValueError
    on anything that isn't a JSON array of objects with 'id' and 'english'
    keys -- callers turn that into a per-batch error, not a crash.
    """
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.removeprefix("json")
        text = text.strip()
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("structured response is not a JSON array")  # noqa: TRY004
    for obj in data:
        if not isinstance(obj, dict) or "id" not in obj or "english" not in obj:
            raise ValueError("structured response item missing 'id' or 'english'")
    return data
