"""Versioned, rights-neutral contracts for bilingual book alignment.

The aligner owns correspondence, not publication policy.  Callers may attach
arbitrary provenance metadata, but the core never decides whether a text may be
redistributed.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from typing import Any

INPUT_SCHEMA = "versed.align.document.v1"
BUNDLE_SCHEMA = "versed.align.bundle.v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Paragraph:
    id: str
    sequence: int
    text: str
    source_hash: str
    flags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        paragraph_id: str,
        sequence: int,
        text: str,
        flags: Iterable[str] = (),
        metadata: dict[str, Any] | None = None,
    ) -> Paragraph:
        cleaned = " ".join(text.split()).strip()
        if not paragraph_id.strip():
            raise ValueError("paragraph id must not be blank")
        if sequence < 0:
            raise ValueError("paragraph sequence must be non-negative")
        if not cleaned:
            raise ValueError(f"paragraph {paragraph_id!r} has no text")
        return cls(
            id=paragraph_id,
            sequence=sequence,
            text=cleaned,
            source_hash=sha256_text(cleaned),
            flags=tuple(sorted(set(flags))),
            metadata=dict(metadata or {}),
        )


@dataclass(frozen=True)
class StructuralUnit:
    id: str
    sequence: int
    heading: str
    paragraphs: tuple[Paragraph, ...]
    anchor_key: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return "\n\n".join(paragraph.text for paragraph in self.paragraphs)

    @property
    def word_count(self) -> int:
        return sum(len(paragraph.text.split()) for paragraph in self.paragraphs)


@dataclass(frozen=True)
class Document:
    work_id: str
    language: str
    source_name: str
    source_hash: str
    structures: tuple[StructuralUnit, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
    schema: str = INPUT_SCHEMA

    def validate(self) -> None:
        if self.schema != INPUT_SCHEMA:
            raise ValueError(f"unsupported document schema: {self.schema!r}")
        if not self.work_id.strip():
            raise ValueError("work_id must not be blank")
        if self.language not in {"ar", "en"}:
            raise ValueError(f"unsupported alignment language: {self.language!r}")
        if not self.source_name.strip():
            raise ValueError("source_name must not be blank")
        if not _SHA256_RE.fullmatch(self.source_hash):
            raise ValueError("source_hash must be a lowercase SHA-256 digest")
        if not self.structures:
            raise ValueError(f"{self.language} document has no structural units")
        structure_ids: set[str] = set()
        paragraph_ids: set[str] = set()
        for expected, structure in enumerate(self.structures):
            if not structure.id.strip():
                raise ValueError("structural unit id must not be blank")
            if structure.id in structure_ids:
                raise ValueError(f"duplicate structural unit id: {structure.id}")
            if structure.sequence != expected:
                raise ValueError(
                    f"structural sequence is not contiguous at {structure.id}: "
                    f"expected {expected}, got {structure.sequence}"
                )
            structure_ids.add(structure.id)
            if not structure.paragraphs:
                raise ValueError(f"structural unit {structure.id!r} has no paragraphs")
            for paragraph_expected, paragraph in enumerate(structure.paragraphs):
                if paragraph.id in paragraph_ids:
                    raise ValueError(f"duplicate paragraph id: {paragraph.id}")
                if paragraph.sequence != paragraph_expected:
                    raise ValueError(
                        f"paragraph sequence is not contiguous at {paragraph.id}: "
                        f"expected {paragraph_expected}, got {paragraph.sequence}"
                    )
                if paragraph.source_hash != sha256_text(paragraph.text):
                    raise ValueError(
                        f"paragraph source hash mismatch: {paragraph.id!r}"
                    )
                paragraph_ids.add(paragraph.id)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StructuralLink:
    arabic_structure_ids: tuple[str, ...]
    english_structure_ids: tuple[str, ...]
    method: str
    confidence: float
    evidence: tuple[str, ...] = ()
    flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class ParagraphLink:
    arabic_paragraph_ids: tuple[str, ...]
    english_paragraph_ids: tuple[str, ...]
    operation: str
    confidence: float
    uncertainty_radius: int
    structural_link_index: int
    flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class Sentence:
    id: str
    paragraph_id: str
    sequence: int
    global_sequence: int
    text: str
    source_hash: str


@dataclass(frozen=True)
class SentenceLink:
    arabic_sentence_ids: tuple[str, ...]
    english_sentence_ids: tuple[str, ...]
    operation: str
    confidence: float
    uncertainty_radius: int
    paragraph_link_index: int
    flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class AlignmentResult:
    arabic: Document
    english: Document
    structural_links: tuple[StructuralLink, ...]
    paragraph_links: tuple[ParagraphLink, ...]
    arabic_sentences: tuple[Sentence, ...]
    english_sentences: tuple[Sentence, ...]
    sentence_links: tuple[SentenceLink, ...]
    diagnostics: dict[str, Any]
    metrics: dict[str, Any]
