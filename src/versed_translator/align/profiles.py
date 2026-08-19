"""Input adapters for recurring bilingual structural shapes.

Profiles discover units; they do not implement alignment.  The first reusable
profile is maqama-shaped books, covering both Hamadhani and Hariri rather than
encoding one title or one story boundary.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path

from versed_translator.align.models import (
    Document,
    Paragraph,
    StructuralLink,
    StructuralUnit,
    sha256_text,
)
from versed_translator.benchmark import spine_align
from versed_translator.benchmark.sources import openiti_markdown

MAX_INPUT_BYTES = 256 * 1024 * 1024
_PAGE_NUMBER_RE = re.compile(r"^\s*[ivxlcdm]*\s*\d+\s*$", re.IGNORECASE)
_FOOTNOTE_RE = re.compile(r"^\s*\d{1,3}\s+\S.{0,100}?\s[:;]", re.DOTALL)
_BACK_MATTER_RE = re.compile(r"^\s*(?:INDEX|GLOSSARY|BIBLIOGRAPHY)\s*$", re.IGNORECASE)
_RUNNING_HEADER_RE = re.compile(r"^[A-Z0-9'’*?.\- ]{4,70}\s+\d{1,4}$")
_SCHOLARLY_NOTE_RE = re.compile(
    r"\b(?:ibid|freytag|arab\s+proverbs|literally|proper\s+name|"
    r"reference\s+to|for\s+a\s+list|the\s+metre|the\s+meter|"
    r"qur.?an|a\.h\.|a\.d\.|ob\.|vol\.|p\.\s*\d|pp\.\s*\d|"
    r"see\s+[A-Z]|another\s+reading|arabici[sz]ed|sanskrit|"
    r"dictionary|lexicon|manuscript|commentator|a\s+figure\s+for|"
    r"there\s+is\s+a\s+tradition|was\s+founded|died\s+(?:about|in)|"
    r"the\s+name\s+(?:of|applied)|the\s+person\s+referred|"
    r"the\s+(?:thief|swindler|sharper|robber)\b|"
    r"this\s+is\s+a\s+species|the\s+plan\s+is|the\s+practice\s+of|"
    r"would\s+make\s+better\s+sense|him\s+who.{0,80}[:;]|"
    r"allusion\s+to|means\s+the|signifies\s+the)\b",
    re.IGNORECASE,
)
_OCR_JUNK_RE = re.compile(r"^[\W_]*[A-Za-z]?[\W_]*$")
_FOOTNOTE_PREFIX_RE = re.compile(r"^\s*\([a-z0-9]{1,3}\)\s+", re.IGNORECASE)


def read_limited_text(path: Path, *, max_bytes: int = MAX_INPUT_BYTES) -> str:
    resolved = path.expanduser().resolve()
    size = resolved.stat().st_size
    if size > max_bytes:
        raise ValueError(f"input exceeds {max_bytes} bytes: {resolved}")
    return resolved.read_text(encoding="utf-8", errors="replace")


def _dehyphenate(lines: list[str]) -> str:
    out: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if out and out[-1].endswith("-") and line[:1].islower():
            out[-1] = out[-1][:-1] + line
        else:
            out.append(line)
    return " ".join(out)


def _repeated_running_heads(lines: list[str]) -> set[str]:
    candidates = [
        " ".join(line.split()).casefold()
        for line in lines
        if line.strip()
        and len(line) <= 80
        and len(line.strip()) >= 8
        and len(line.split()) >= 2
        and len(line.split()) <= 8
        and any(character.isalpha() for character in line)
        and line.upper() == line
    ]
    return {line for line, count in Counter(candidates).items() if count >= 3}


def _english_body_paragraphs(
    lines: list[str],
    *,
    start_line: int,
    end_line: int,
    repeated_heads: set[str],
    unit_id: str,
) -> tuple[Paragraph, ...]:
    selected: list[str] = []
    for raw in lines[start_line:end_line]:
        normalized = " ".join(raw.split()).casefold()
        if _BACK_MATTER_RE.match(raw):
            break
        if (
            normalized in repeated_heads
            or _PAGE_NUMBER_RE.match(raw)
            or (len(raw) <= 80 and _RUNNING_HEADER_RE.match(raw.strip()))
        ):
            continue
        selected.append(raw.rstrip())

    blocks = [block for block in re.split(r"\n\s*\n", "\n".join(selected)) if block.strip()]
    paragraphs: list[Paragraph] = []
    previous_was_footnote = False
    for block in blocks:
        text = _dehyphenate(block.splitlines())
        if not text:
            continue
        flags: list[str] = []
        word_count = len(text.split())
        explicit_note = bool(_FOOTNOTE_RE.match(text))
        scholarly_note = bool(_SCHOLARLY_NOTE_RE.search(text)) and word_count <= 180
        ocr_junk = word_count <= 4 and (
            bool(_OCR_JUNK_RE.fullmatch(text))
            or sum(character.isalnum() for character in text) <= 3
        )
        footnote_prefix = bool(_FOOTNOTE_PREFIX_RE.match(text))
        continued_note = previous_was_footnote and word_count <= 12
        if (
            explicit_note
            or scholarly_note
            or ocr_junk
            or footnote_prefix
            or continued_note
        ):
            flags.extend(("possible_footnote", "exclude_from_alignment"))
        previous_was_footnote = "possible_footnote" in flags
        paragraphs.append(
            Paragraph.create(
                paragraph_id=f"{unit_id}:p{len(paragraphs):04d}",
                sequence=len(paragraphs),
                text=text,
                flags=flags,
            )
        )
    return tuple(paragraphs)


def _plain_english_paragraphs(text: str) -> tuple[Paragraph, ...]:
    blocks = [
        _dehyphenate(block.splitlines())
        for block in re.split(r"\n\s*\n", text.lstrip("\ufeff"))
        if block.strip()
    ]
    paragraphs = tuple(
        Paragraph.create(
            paragraph_id=f"en:u0000:p{index:04d}",
            sequence=index,
            text=block,
        )
        for index, block in enumerate(blocks)
        if block
    )
    if not paragraphs:
        raise ValueError("English source contains no paragraphs")
    return paragraphs


def load_plain_pair(
    arabic_path: Path,
    english_path: Path,
    *,
    work_id: str | None = None,
) -> tuple[Document, Document, tuple[StructuralLink, ...], dict]:
    """Load an arbitrary OpenITI source and prepared plain-English translation.

    No bilateral spine is inferred. OpenITI structure is retained for audit,
    while one low-confidence whole-book link makes the lack of anchors explicit.
    """
    arabic_text = read_limited_text(arabic_path)
    english_text = read_limited_text(english_path)
    parsed = openiti_markdown.parse(arabic_text, uri=arabic_path.stem)
    resolved_work_id = work_id or parsed.book_uri or parsed.uri
    if not resolved_work_id:
        raise ValueError("could not determine work id; pass --work-id")

    source_units: list[tuple[str, list]] = []
    if parsed.preamble:
        source_units.append(("", parsed.preamble))
    source_units.extend(
        (section.title, section.paragraphs)
        for section in parsed.sections
        if not section.is_paratext and section.paragraphs
    )
    if not source_units:
        raise ValueError("OpenITI source contains no alignable paragraphs")

    ar_structures: list[StructuralUnit] = []
    for heading, source_paragraphs in source_units:
        structure_id = f"ar:u{len(ar_structures):04d}"
        paragraphs = tuple(
            Paragraph.create(
                paragraph_id=f"{structure_id}:p{index:04d}",
                sequence=index,
                text=paragraph.text,
                metadata={"source_line": paragraph.line_no},
            )
            for index, paragraph in enumerate(source_paragraphs)
            if paragraph.text.strip()
        )
        if paragraphs:
            ar_structures.append(
                StructuralUnit(
                    id=structure_id,
                    sequence=len(ar_structures),
                    heading=heading,
                    anchor_key=heading,
                    paragraphs=paragraphs,
                )
            )
    if not ar_structures:
        raise ValueError("OpenITI source contains no alignable paragraphs")

    english_paragraphs = _plain_english_paragraphs(english_text)
    en_structure = StructuralUnit(
        id="en:u0000",
        sequence=0,
        heading="",
        anchor_key="",
        paragraphs=english_paragraphs,
    )
    arabic_document = Document(
        work_id=resolved_work_id,
        language="ar",
        source_name=arabic_path.name,
        source_hash=sha256_text(arabic_text),
        structures=tuple(ar_structures),
        metadata={"profile": "plain", "openiti_meta": parsed.meta},
    )
    english_document = Document(
        work_id=resolved_work_id,
        language="en",
        source_name=english_path.name,
        source_hash=sha256_text(english_text),
        structures=(en_structure,),
        metadata={"profile": "plain"},
    )
    link = StructuralLink(
        arabic_structure_ids=tuple(unit.id for unit in ar_structures),
        english_structure_ids=(en_structure.id,),
        method="whole_book_unanchored",
        confidence=0.2,
        flags=("unanchored", "review_required"),
    )
    report = {
        "profile": "plain",
        "arabic_structures_retained": len(ar_structures),
        "arabic_paragraphs": sum(len(unit.paragraphs) for unit in ar_structures),
        "english_paragraphs": len(english_paragraphs),
        "bilateral_structural_anchors": 0,
    }
    return arabic_document, english_document, (link,), report


def load_maqama_pair(
    arabic_path: Path,
    english_path: Path,
    *,
    work_id: str | None = None,
) -> tuple[Document, Document, tuple[StructuralLink, ...], dict]:
    """Load any OpenITI/English pair whose bilateral unit is the maqama."""
    arabic_text = read_limited_text(arabic_path)
    english_text = read_limited_text(english_path)
    parsed = openiti_markdown.parse(arabic_text, uri=arabic_path.stem)
    resolved_work_id = work_id or parsed.book_uri or parsed.uri
    if not resolved_work_id:
        raise ValueError("could not determine work id; pass --work-id")

    arabic_units = spine_align.arabic_maqama_units(parsed)
    english_units = spine_align.english_maqama_units(english_text)
    if not arabic_units or not english_units:
        raise ValueError(
            "maqama profile found no bilateral units: "
            f"arabic={len(arabic_units)} english={len(english_units)}"
        )

    ar_structures: list[StructuralUnit] = []
    for unit in arabic_units:
        structure_id = f"ar:u{unit.index:04d}"
        paragraphs = tuple(
            Paragraph.create(
                paragraph_id=f"{structure_id}:p{index:04d}",
                sequence=index,
                text=text,
            )
            for index, text in enumerate(unit.paragraphs)
            if text.strip()
        )
        if not paragraphs:
            raise ValueError(f"Arabic maqama {unit.index} has no paragraphs")
        ar_structures.append(
            StructuralUnit(
                id=structure_id,
                sequence=len(ar_structures),
                heading=unit.title,
                anchor_key=unit.title,
                paragraphs=paragraphs,
                metadata={"profile_unit_index": unit.index},
            )
        )

    lines = english_text.splitlines()
    repeated_heads = _repeated_running_heads(lines)
    en_structures: list[StructuralUnit] = []
    for index, unit in enumerate(english_units):
        structure_id = f"en:u{unit.index:04d}"
        next_line = (
            english_units[index + 1].line_no - 1
            if index + 1 < len(english_units)
            else len(lines)
        )
        paragraphs = _english_body_paragraphs(
            lines,
            start_line=unit.line_no,
            end_line=next_line,
            repeated_heads=repeated_heads,
            unit_id=structure_id,
        )
        if not paragraphs:
            raise ValueError(f"English maqama {unit.index} has no body paragraphs")
        en_structures.append(
            StructuralUnit(
                id=structure_id,
                sequence=len(en_structures),
                heading=unit.title,
                anchor_key=unit.title,
                paragraphs=paragraphs,
                metadata={
                    "profile_unit_index": unit.index,
                    "printed_label": unit.printed_label,
                    "source_line": unit.line_no,
                },
            )
        )

    indexed = spine_align.pair_by_sequence(arabic_units, english_units)
    confirmed = [pair for pair in indexed if pair.confirmation]
    minimum_confirmation = max(3, math.ceil(min(len(arabic_units), len(english_units)) * 0.25))
    if len(arabic_units) != len(english_units):
        raise ValueError(
            "maqama counts differ; refusing a guessed sequence zip: "
            f"arabic={len(arabic_units)} english={len(english_units)}. "
            "Supply an explicit structural map."
        )
    if len(confirmed) < minimum_confirmation:
        raise ValueError(
            "equal unit counts are not enough evidence for a spine zip: "
            f"confirmed={len(confirmed)} required={minimum_confirmation}"
        )

    structural_links = tuple(
        StructuralLink(
            arabic_structure_ids=(ar_structures[index].id,),
            english_structure_ids=(en_structures[index].id,),
            method="bilateral_maqama_sequence",
            confidence=0.98 if pair.confirmation else 0.82,
            evidence=tuple(
                value
                for value in (
                    f"arabic_heading:{pair.arabic.title}",
                    f"english_heading:{pair.english.title}",
                    f"confirmation:{pair.confirmation}" if pair.confirmation else "",
                )
                if value
            ),
            flags=() if pair.confirmation else ("bounded_by_confirmed_neighbors",),
        )
        for index, pair in enumerate(indexed)
    )

    arabic_document = Document(
        work_id=resolved_work_id,
        language="ar",
        source_name=arabic_path.name,
        source_hash=sha256_text(arabic_text),
        structures=tuple(ar_structures),
        metadata={
            "profile": "maqama",
            "openiti_meta": parsed.meta,
        },
    )
    english_document = Document(
        work_id=resolved_work_id,
        language="en",
        source_name=english_path.name,
        source_hash=sha256_text(english_text),
        structures=tuple(en_structures),
        metadata={"profile": "maqama"},
    )
    report = {
        "profile": "maqama",
        "arabic_units": len(arabic_units),
        "english_units": len(english_units),
        "sequence_pairs": len(indexed),
        "sequence_confirmed": len(confirmed),
        "minimum_confirmation": minimum_confirmation,
        "repeated_running_heads_removed": sorted(repeated_heads),
        "english_possible_footnotes": sum(
            "possible_footnote" in paragraph.flags
            for structure in en_structures
            for paragraph in structure.paragraphs
        ),
    }
    return arabic_document, english_document, structural_links, report
