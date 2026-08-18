"""Strict JSON interchange for normalized documents and structural maps."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from versed_translator.align.models import (
    Document,
    Paragraph,
    StructuralLink,
    StructuralUnit,
    sha256_text,
)
from versed_translator.align.profiles import read_limited_text


def _object(value: Any, *, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{context} must be a JSON object")
    return value


def load_document(path: Path) -> Document:
    raw = _object(json.loads(read_limited_text(path)), context=str(path))
    structures: list[StructuralUnit] = []
    for structure_raw in raw.get("structures") or []:
        structure = _object(structure_raw, context="structure")
        paragraphs: list[Paragraph] = []
        for paragraph_raw in structure.get("paragraphs") or []:
            paragraph = _object(paragraph_raw, context="paragraph")
            text = " ".join(str(paragraph.get("text") or "").split()).strip()
            source_hash = str(paragraph.get("source_hash") or "")
            if source_hash and source_hash != sha256_text(text):
                raise ValueError(
                    f"paragraph source hash mismatch: {paragraph.get('id')!r}"
                )
            paragraphs.append(
                Paragraph.create(
                    paragraph_id=str(paragraph.get("id") or ""),
                    sequence=int(paragraph.get("sequence")),
                    text=text,
                    flags=paragraph.get("flags") or (),
                    metadata=_object(
                        paragraph.get("metadata") or {}, context="paragraph.metadata"
                    ),
                )
            )
        structures.append(
            StructuralUnit(
                id=str(structure.get("id") or ""),
                sequence=int(structure.get("sequence")),
                heading=str(structure.get("heading") or ""),
                anchor_key=str(structure.get("anchor_key") or ""),
                paragraphs=tuple(paragraphs),
                metadata=_object(
                    structure.get("metadata") or {}, context="structure.metadata"
                ),
            )
        )
    document = Document(
        schema=str(raw.get("schema") or ""),
        work_id=str(raw.get("work_id") or ""),
        language=str(raw.get("language") or ""),
        source_name=str(raw.get("source_name") or path.name),
        source_hash=str(raw.get("source_hash") or ""),
        structures=tuple(structures),
        metadata=_object(raw.get("metadata") or {}, context="document.metadata"),
    )
    document.validate()
    return document


def load_structural_links(path: Path) -> tuple[StructuralLink, ...]:
    links: list[StructuralLink] = []
    for line_number, line in enumerate(read_limited_text(path).splitlines(), start=1):
        if not line.strip():
            continue
        row = _object(json.loads(line), context=f"{path}:{line_number}")
        links.append(
            StructuralLink(
                arabic_structure_ids=tuple(
                    str(value) for value in row.get("arabic_structure_ids") or ()
                ),
                english_structure_ids=tuple(
                    str(value) for value in row.get("english_structure_ids") or ()
                ),
                method=str(row.get("method") or "explicit_map"),
                confidence=float(row.get("confidence", 1.0)),
                evidence=tuple(str(value) for value in row.get("evidence") or ()),
                flags=tuple(str(value) for value in row.get("flags") or ()),
            )
        )
    if not links:
        raise ValueError(f"structural map contains no links: {path}")
    return tuple(links)


def load_gold(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(read_limited_text(path, max_bytes=32 * 1024 * 1024).splitlines(), start=1):
        if line.strip():
            rows.append(
                _object(json.loads(line), context=f"{path}:{line_number}")
            )
    return rows
