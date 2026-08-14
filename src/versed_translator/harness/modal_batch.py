"""Prompt construction and response parsing for the Modal vLLM batch path.

WHY THIS MODULE EXISTS, AND WHY IT IS HERE AND NOT THERE.

``throughput/serve_translategemma.py`` used to hardcode its own
``DEFAULT_TEMPLATE`` and never import the prompt registry. That is how both
TranslateGemma legs came to record ``prompt_template_id: "v1"`` while sending
a three-sentence instruction carrying none of the six fidelity rules -- a
mislabel nobody could see, because the label and the prompt had no shared
source of truth.

The Modal *image* genuinely cannot import this package (it is a CUDA/vLLM
image, and adding the package to it would drag the whole dependency tree onto
a paid GPU). But the Modal **local entrypoint runs on the local machine**,
where this package is installed. So prompt construction, labelling and
response parsing all live here, in the package, under test; the container is
handed nothing but finished strings and hands back nothing but text.

That inverts the old failure: the label cannot drift from the prompt, because
``build_chunks`` derives both from the same registry lookup and returns them
together in one object. ``tests/test_prompts_modal_parity.py`` asserts exactly
that, and that the serving module defines no structured prompt of its own.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from versed_translator.harness.prompts import (
    MODAL_MINIMAL_V1_ID,
    MODAL_MINIMAL_V1_TEXT,
    get_template,
    parse_structured_response,
)
from versed_translator.harness.structured import (
    ERR_EMPTY,
    ERR_ID_DUPLICATE,
    ERR_ID_MISSING,
    ERR_ID_UNEXPECTED,
    ERR_PARSE_PREFIX,
)

#: The structured contract (D2e) on the Modal path.
STRUCTURED_TEMPLATE_ID = "structured_blocks_v1"
#: The known-good raw-completion fallback: exactly what both prior
#: TranslateGemma legs sent, now under its honest label.
FALLBACK_TEMPLATE_ID = MODAL_MINIMAL_V1_ID

#: Blocks per structured generation. Deliberately small: with <=60-word blocks
#: this is ~600 prompt tokens and ~500 output tokens, well inside the serving
#: class's 4096-token window, and it bounds how much work one malformed JSON
#: response can cost.
DEFAULT_STRUCTURED_CHUNK = 4

#: Appended to the structured prompt. vLLM is being driven as a completion
#: engine here; without an explicit cue to start the array, an instruction-
#: tuned model often narrates before it emits JSON.
STRUCTURED_OUTPUT_CUE = "JSON output:"


@dataclass(frozen=True)
class PromptChunk:
    """One generation request, with the label of the template that built it.

    ``template_id`` and ``prompt_sha256`` travel with the prompt so whatever
    writes the run summary records what was *sent*, not what someone believed
    was sent.
    """

    template_id: str
    structured: bool
    ids: tuple[str, ...]
    system: str | None
    user: str
    #: True when the container should apply the model's chat template.
    chat: bool = True
    prompt_sha256: str = field(default="", compare=False)

    def to_request(self) -> dict:
        """The wire form the Modal container consumes (plain JSON, no imports)."""
        return {"system": self.system, "user": self.user, "chat": self.chat}


def _sha(system: str | None, user: str) -> str:
    return hashlib.sha256(f"{system or ''}\n\n{user}".encode()).hexdigest()


def build_structured_chunks(
    items: list[dict],
    *,
    template_id: str = STRUCTURED_TEMPLATE_ID,
    chunk_size: int = DEFAULT_STRUCTURED_CHUNK,
    exemplar: str | None = None,
) -> list[PromptChunk]:
    """Chunk `items` into structured JSON-in/JSON-out generation requests."""
    template = get_template(template_id)
    if not template.structured:
        raise ValueError(f"{template_id!r} is not a structured template")
    chunk_size = max(1, chunk_size)
    chunks: list[PromptChunk] = []
    for start in range(0, len(items), chunk_size):
        group = items[start : start + chunk_size]
        user = f"{template.render_batch(group, exemplar=exemplar)}\n\n{STRUCTURED_OUTPUT_CUE}"
        chunks.append(
            PromptChunk(
                template_id=template.template_id,
                structured=True,
                ids=tuple(i["id"] for i in group),
                system=template.system,
                user=user,
                chat=True,
                prompt_sha256=_sha(template.system, user),
            )
        )
    return chunks


def build_fallback_chunks(items: list[dict]) -> list[PromptChunk]:
    """One raw-completion request per block, using ``modal_minimal_v1``.

    Byte-identical in form to what the 27B and 12B legs sent, so a fallback
    run stays comparable to them -- the only change is that the unit is a
    block rather than a whole passage. Ids are still preserved, structurally:
    one prompt in, one translation out, position-matched.
    """
    return [
        PromptChunk(
            template_id=FALLBACK_TEMPLATE_ID,
            structured=False,
            ids=(item["id"],),
            system=None,
            user=MODAL_MINIMAL_V1_TEXT.format(arabic=item["arabic"]),
            chat=False,
            prompt_sha256=_sha(None, MODAL_MINIMAL_V1_TEXT.format(arabic=item["arabic"])),
        )
        for item in items
    ]


def parse_chunk_output(chunk: PromptChunk, text: str, **extra) -> list[dict]:
    """Turn one generation's text into raw run_batch rows, one per sent id.

    Rows are ``{"id", "english", ...}`` on success and
    ``{"id", "english": None, "error": ...}`` otherwise -- the shape
    ``harness.ingest_modal`` already reads. Every id in ``chunk.ids`` gets
    exactly one row, plus one extra error row per id the model invented.
    Nothing raises: a malformed response degrades the chunk, never the run.
    """
    if not chunk.structured:
        english = (text or "").strip()
        row = {"id": chunk.ids[0], "english": english or None, **extra}
        if not english:
            row["error"] = ERR_EMPTY
        return [row]

    try:
        parsed = parse_structured_response(text or "")
    except (ValueError, TypeError) as exc:
        return [
            {"id": i, "english": None, "error": f"{ERR_PARSE_PREFIX}: {exc}", **extra}
            for i in chunk.ids
        ]

    seen: dict[str, object] = {}
    duplicated: set[str] = set()
    for obj in parsed:
        oid = obj.get("id")
        if oid in seen:
            duplicated.add(oid)
            continue
        seen[oid] = obj.get("english")

    rows: list[dict] = []
    for item_id in chunk.ids:
        english = seen.get(item_id)
        if item_id in duplicated:
            rows.append({"id": item_id, "english": None, "error": ERR_ID_DUPLICATE, **extra})
        elif item_id not in seen:
            rows.append({"id": item_id, "english": None, "error": ERR_ID_MISSING, **extra})
        elif not isinstance(english, str) or not english.strip():
            rows.append({"id": item_id, "english": None, "error": ERR_EMPTY, **extra})
        else:
            rows.append({"id": item_id, "english": english.strip(), **extra})

    expected = set(chunk.ids)
    rows.extend(
        {"id": str(oid), "english": None, "error": ERR_ID_UNEXPECTED, **extra}
        for oid in seen
        if oid not in expected
    )
    return rows


def probe_ok(rows: list[dict]) -> bool:
    """True if a structured probe came back with every id honoured.

    Used to decide once, before spending the rest of a paid GPU job, whether
    the model can actually hold the JSON contract -- rather than discovering
    it 139 blocks later.
    """
    return bool(rows) and all(r.get("error") is None and r.get("english") for r in rows)
