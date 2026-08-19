"""Compose an alignment bundle with OpenITI audio timing identities.

This module is deliberately offline and rights-neutral.  It reads a verified
alignment bundle and a portable OpenITI ``edition.sqlite3`` ledger, then emits
a deterministic reader-timeline JSON artifact.  It does not publish, mutate
the ledger, or write to Supabase.

The bridge has one strict responsibility chain::

    audio word timing -> ledger word -> Arabic sentence -> alignment link
        -> English sentence/paragraph display payload

Structural containment is asserted while the artifact is built and exposed as
``assert_event_structural_clamp`` so a reader adapter can assert it again.
"""

from __future__ import annotations

import bisect
import hashlib
import json
import os
import sqlite3
import tempfile
import unicodedata
import zipfile
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from versed_translator.align.bundle import verify_bundle

READER_TIMELINE_SCHEMA = "versed.align.reader-timeline.v1"
_MAX_MEMBER_BYTES = 256 * 1024 * 1024
_REQUIRED_MEMBERS = (
    "documents/ar.structures.jsonl",
    "documents/en.structures.jsonl",
    "documents/ar.sentences.jsonl",
    "documents/en.sentences.jsonl",
    "alignments/structural.jsonl",
    "alignments/paragraphs.jsonl",
    "alignments/sentences.jsonl",
)
_MODE_ONE_MAX_ENGLISH_SENTENCES = 3
_MODE_ONE_MAX_RADIUS = 1
_REVIEW_FLAGS = frozenset({"review_required", "unanchored"})
_LOW_SIGNAL_FLAGS = frozenset(
    {
        "heuristic_only",
        "skip",
        "weak_arabic_sentence_boundaries",
        "low_signal",
    }
)
_FOOTNOTE_FLAGS = frozenset({"possible_footnote", "exclude_from_alignment"})


@dataclass(frozen=True)
class LedgerWord:
    id: str
    block_id: str
    block_sequence: int
    word_sequence: int
    text: str


@dataclass(frozen=True)
class Timing:
    chunk_id: str
    word_id: str
    start_ms: int
    end_ms: int
    duration_ms: int
    source: str
    chunk_block_sequence: int
    chunk_source_word_start: int


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalized_token(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().replace("ـ", "")
    normalized = "".join(
        character
        for character in normalized
        if unicodedata.category(character) != "Mn" and character.isalnum()
    )
    return normalized.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي"}))


def _text_tokens(value: str) -> tuple[str, ...]:
    return tuple(
        token
        for raw in value.split()
        if (token := _normalized_token(raw))
    )


def _read_jsonl(archive: zipfile.ZipFile, name: str) -> list[dict[str, Any]]:
    info = archive.getinfo(name)
    if info.file_size > _MAX_MEMBER_BYTES:
        raise ValueError(f"bundle member is too large for the reader bridge: {name}")
    rows: list[dict[str, Any]] = []
    for line_number, raw in enumerate(archive.read(name).splitlines(), start=1):
        if not raw.strip():
            continue
        row = json.loads(raw)
        if not isinstance(row, dict):
            raise TypeError(f"{name}:{line_number} must be a JSON object")
        rows.append(row)
    return rows


def _load_bundle(path: Path) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    manifest = verify_bundle(path)
    with zipfile.ZipFile(path.expanduser().resolve(), mode="r") as archive:
        rows = {name: _read_jsonl(archive, name) for name in _REQUIRED_MEMBERS}
    return manifest, rows


def _require_columns(
    connection: sqlite3.Connection,
    table: str,
    required: Iterable[str],
) -> None:
    # Table names are constants owned by this module, never user input.
    columns = {str(row["name"]) for row in connection.execute(f"PRAGMA table_info({table})")}
    missing = sorted(set(required) - columns)
    if missing:
        raise ValueError(f"ledger table {table!r} is missing columns: {missing}")


def _open_ledger(path: Path) -> sqlite3.Connection:
    resolved = path.expanduser().resolve(strict=True)
    connection = sqlite3.connect(f"{resolved.as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    _require_columns(connection, "blocks", {"id", "sequence", "language"})
    _require_columns(
        connection,
        "words",
        {"id", "block_id", "sequence", "text"},
    )
    _require_columns(
        connection,
        "audio_chunks",
        {
            "id",
            "language",
            "status",
            "duration_ms",
            "block_sequence",
            "source_word_start",
        },
    )
    _require_columns(
        connection,
        "audio_word_timings",
        {"chunk_id", "word_id", "start_ms", "end_ms", "source"},
    )
    return connection


def _ledger_rows(
    connection: sqlite3.Connection,
) -> tuple[list[LedgerWord], dict[str, list[Timing]], dict[str, int]]:
    words = [
        LedgerWord(
            id=str(row["id"]),
            block_id=str(row["block_id"]),
            block_sequence=int(row["block_sequence"]),
            word_sequence=int(row["word_sequence"]),
            text=str(row["text"]),
        )
        for row in connection.execute(
            """
            SELECT w.id, w.block_id, w.sequence AS word_sequence, w.text,
                   b.sequence AS block_sequence
            FROM words w
            JOIN blocks b ON b.id=w.block_id
            WHERE b.language='arabic'
            ORDER BY b.sequence, w.sequence
            """
        )
    ]
    timings: dict[str, list[Timing]] = defaultdict(list)
    chunk_durations = {
        str(row["id"]): int(row["duration_ms"])
        for row in connection.execute(
            """
            SELECT id, duration_ms
            FROM audio_chunks
            WHERE language='ar' AND status='complete'
              AND duration_ms IS NOT NULL
            """
        )
    }
    for row in connection.execute(
        """
        SELECT t.chunk_id, t.word_id, t.start_ms, t.end_ms, t.source,
               c.duration_ms, c.block_sequence, c.source_word_start
        FROM audio_word_timings t
        JOIN audio_chunks c ON c.id=t.chunk_id
        WHERE c.language='ar' AND c.status='complete'
          AND c.duration_ms IS NOT NULL
        ORDER BY c.block_sequence, c.source_word_start, t.sequence
        """
    ):
        timing = Timing(
            chunk_id=str(row["chunk_id"]),
            word_id=str(row["word_id"]),
            start_ms=int(row["start_ms"]),
            end_ms=int(row["end_ms"]),
            duration_ms=int(row["duration_ms"]),
            source=str(row["source"]),
            chunk_block_sequence=int(row["block_sequence"]),
            chunk_source_word_start=int(row["source_word_start"]),
        )
        if timing.start_ms < 0 or timing.end_ms < timing.start_ms:
            raise ValueError(f"invalid timing for word {timing.word_id!r}")
        if timing.end_ms > timing.duration_ms:
            raise ValueError(f"timing exceeds chunk duration for {timing.word_id!r}")
        timings[timing.word_id].append(timing)
        previous = chunk_durations[timing.chunk_id]
        if previous != timing.duration_ms:
            raise ValueError(f"inconsistent duration for chunk {timing.chunk_id!r}")
    return words, dict(timings), chunk_durations


def _structure_indexes(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    paragraphs: dict[str, dict[str, Any]] = {}
    paragraph_structure: dict[str, str] = {}
    structure_ids: set[str] = set()
    for structure in rows:
        structure_id = str(structure.get("id") or "")
        if not structure_id or structure_id in structure_ids:
            raise ValueError(f"invalid or duplicate structure id: {structure_id!r}")
        structure_ids.add(structure_id)
        for paragraph_value in structure.get("paragraphs") or []:
            if not isinstance(paragraph_value, dict):
                raise TypeError(f"paragraph in {structure_id!r} must be an object")
            paragraph_id = str(paragraph_value.get("id") or "")
            if not paragraph_id or paragraph_id in paragraphs:
                raise ValueError(f"invalid or duplicate paragraph id: {paragraph_id!r}")
            paragraph = dict(paragraph_value)
            source_hash = str(paragraph.get("source_hash") or "")
            if source_hash and source_hash != _sha256_text(
                str(paragraph.get("text") or "")
            ):
                raise ValueError(f"paragraph source hash mismatch: {paragraph_id!r}")
            paragraphs[paragraph_id] = paragraph
            paragraph_structure[paragraph_id] = structure_id
    return paragraphs, paragraph_structure


def _sentence_index(
    rows: Sequence[Mapping[str, Any]],
    paragraphs: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    sentences: dict[str, dict[str, Any]] = {}
    for value in rows:
        sentence_id = str(value.get("id") or "")
        paragraph_id = str(value.get("paragraph_id") or "")
        if not sentence_id or sentence_id in sentences:
            raise ValueError(f"invalid or duplicate sentence id: {sentence_id!r}")
        if paragraph_id not in paragraphs:
            raise ValueError(f"sentence references unknown paragraph: {sentence_id!r}")
        source_hash = str(value.get("source_hash") or "")
        if source_hash and source_hash != _sha256_text(str(value.get("text") or "")):
            raise ValueError(f"sentence source hash mismatch: {sentence_id!r}")
        sentences[sentence_id] = dict(value)
    return sentences


def _validate_link_contract(
    structural_links: Sequence[Mapping[str, Any]],
    paragraph_links: Sequence[Mapping[str, Any]],
    sentence_links: Sequence[Mapping[str, Any]],
    *,
    ar_structure_ids: set[str],
    en_structure_ids: set[str],
) -> None:
    for index, link in enumerate(structural_links):
        linked_ar = set(link.get("arabic_structure_ids") or ())
        linked_en = set(link.get("english_structure_ids") or ())
        if not linked_ar or not linked_en:
            raise ValueError(f"structural link {index} must reference both languages")
        if not linked_ar <= ar_structure_ids or not linked_en <= en_structure_ids:
            raise ValueError(f"structural link {index} references an unknown structure")
    for index, link in enumerate(paragraph_links):
        structural_index = int(link.get("structural_link_index", -1))
        if not 0 <= structural_index < len(structural_links):
            raise ValueError(f"paragraph link {index} has invalid structural index")
    seen_ar_sentences: set[str] = set()
    seen_en_sentences: set[str] = set()
    for index, link in enumerate(sentence_links):
        paragraph_index = int(link.get("paragraph_link_index", -1))
        if not 0 <= paragraph_index < len(paragraph_links):
            raise ValueError(f"sentence link {index} has invalid paragraph index")
        ar_ids = set(link.get("arabic_sentence_ids") or ())
        en_ids = set(link.get("english_sentence_ids") or ())
        if ar_ids & seen_ar_sentences or en_ids & seen_en_sentences:
            raise ValueError(f"sentence link {index} overlaps a prior link")
        seen_ar_sentences.update(ar_ids)
        seen_en_sentences.update(en_ids)


def _token_positions(tokens: Sequence[str]) -> dict[str, list[int]]:
    out: dict[str, list[int]] = defaultdict(list)
    for index, token in enumerate(tokens):
        out[token].append(index)
    return dict(out)


def _find_span(
    tokens: Sequence[str],
    positions: Mapping[str, Sequence[int]],
    pattern: Sequence[str],
    *,
    start: int,
    stop: int | None = None,
) -> tuple[int, int] | None:
    if not pattern:
        return None
    limit = len(tokens) if stop is None else min(stop, len(tokens))
    candidates = positions.get(pattern[0], ())
    cursor = bisect.bisect_left(candidates, start)
    for candidate in candidates[cursor:]:
        end = candidate + len(pattern)
        if end > limit:
            break
        if tuple(tokens[candidate:end]) == tuple(pattern):
            return candidate, end
    return None


def _map_arabic_sentences(
    structures: Sequence[Mapping[str, Any]],
    sentences: Mapping[str, Mapping[str, Any]],
    ledger_words: Sequence[LedgerWord],
) -> tuple[dict[str, tuple[LedgerWord, ...]], dict[str, Any]]:
    expanded_words: list[LedgerWord] = []
    ledger_tokens: list[str] = []
    for word in ledger_words:
        for token in _text_tokens(word.text):
            expanded_words.append(word)
            ledger_tokens.append(token)
    positions = _token_positions(ledger_tokens)
    sentence_by_paragraph: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sentence in sentences.values():
        sentence_by_paragraph[str(sentence["paragraph_id"])].append(dict(sentence))
    for values in sentence_by_paragraph.values():
        values.sort(key=lambda row: int(row["sequence"]))

    mapped: dict[str, tuple[LedgerWord, ...]] = {}
    paragraph_cursor = 0
    unmapped_paragraphs: list[str] = []
    unmapped_sentences: list[str] = []
    nonlexical_sentences: list[str] = []
    for structure in structures:
        for paragraph_value in structure.get("paragraphs") or []:
            paragraph = dict(paragraph_value)
            paragraph_id = str(paragraph["id"])
            pattern = _text_tokens(str(paragraph.get("text") or ""))
            paragraph_span = _find_span(
                ledger_tokens,
                positions,
                pattern,
                start=paragraph_cursor,
            )
            if paragraph_span is None:
                unmapped_paragraphs.append(paragraph_id)
                for value in sentence_by_paragraph.get(paragraph_id, ()):
                    sentence_id = str(value["id"])
                    if _text_tokens(str(value.get("text") or "")):
                        unmapped_sentences.append(sentence_id)
                    else:
                        nonlexical_sentences.append(sentence_id)
                continue
            paragraph_start, paragraph_end = paragraph_span
            paragraph_cursor = paragraph_end
            sentence_cursor = paragraph_start
            for sentence in sentence_by_paragraph.get(paragraph_id, ()):
                sentence_id = str(sentence["id"])
                sentence_pattern = _text_tokens(str(sentence.get("text") or ""))
                if not sentence_pattern:
                    nonlexical_sentences.append(sentence_id)
                    continue
                sentence_span = _find_span(
                    ledger_tokens,
                    positions,
                    sentence_pattern,
                    start=sentence_cursor,
                    stop=paragraph_end,
                )
                if sentence_span is None:
                    unmapped_sentences.append(sentence_id)
                    continue
                start, end = sentence_span
                sentence_cursor = end
                unique_words: list[LedgerWord] = []
                seen: set[str] = set()
                for word in expanded_words[start:end]:
                    if word.id not in seen:
                        unique_words.append(word)
                        seen.add(word.id)
                mapped[sentence_id] = tuple(unique_words)
    lexical_sentence_count = len(sentences) - len(nonlexical_sentences)
    diagnostics = {
        "ledger_words": len(ledger_words),
        "arabic_sentences": len(sentences),
        "arabic_lexical_sentences": lexical_sentence_count,
        "arabic_nonlexical_sentence_ids": nonlexical_sentences,
        "arabic_sentences_mapped_to_ledger": len(mapped),
        "arabic_sentence_mapping_rate": (
            round(len(mapped) / lexical_sentence_count, 6)
            if lexical_sentence_count
            else 1.0
        ),
        "unmapped_arabic_paragraph_ids": unmapped_paragraphs,
        "unmapped_arabic_sentence_ids": unmapped_sentences,
    }
    return mapped, diagnostics


def _flags(*values: Mapping[str, Any]) -> set[str]:
    return {
        str(flag)
        for value in values
        for flag in value.get("flags") or ()
    }


def assert_event_structural_clamp(event: Mapping[str, Any]) -> None:
    """Assert that every rendered object belongs to the paired structures.

    This is suitable for calling again at render time.  It intentionally does
    not compare numeric ID prefixes: an explicit map may pair differently
    numbered but genuinely corresponding units.
    """
    clamp = event.get("structural_clamp")
    if not isinstance(clamp, Mapping):
        raise TypeError("reader event has no structural clamp")
    allowed_ar = set(clamp.get("arabic_structure_ids") or ())
    allowed_en = set(clamp.get("english_structure_ids") or ())
    actual_ar = set(clamp.get("rendered_arabic_structure_ids") or ())
    actual_en = set(clamp.get("rendered_english_structure_ids") or ())
    if not actual_ar or not actual_ar <= allowed_ar:
        raise ValueError(
            "Arabic reader payload crosses its structural alignment boundary"
        )
    if actual_en and not actual_en <= allowed_en:
        raise ValueError(
            "English reader payload crosses its structural alignment boundary"
        )
    if event.get("display_mode") in {1, 2} and not actual_en:
        raise ValueError("sentence/paragraph display mode has no English structure")


def _display_mode(
    structural: Mapping[str, Any],
    paragraph_link: Mapping[str, Any],
    sentence_link: Mapping[str, Any],
    target_paragraphs: Sequence[Mapping[str, Any]],
) -> tuple[int, str]:
    combined = _flags(structural, paragraph_link, sentence_link)
    paragraph_flags = {
        str(flag)
        for paragraph in target_paragraphs
        for flag in paragraph.get("flags") or ()
    }
    if combined & _REVIEW_FLAGS:
        return 3, "structural_review_required"
    if paragraph_flags & _FOOTNOTE_FLAGS:
        return 3, "target_paragraph_excluded"
    english_ids = tuple(sentence_link.get("english_sentence_ids") or ())
    alignable_paragraphs = [
        paragraph
        for paragraph in target_paragraphs
        if "exclude_from_alignment" not in set(paragraph.get("flags") or ())
    ]
    if not english_ids or not alignable_paragraphs:
        return 3, "no_renderable_english_target"
    radius = int(sentence_link.get("uncertainty_radius", 3))
    widened_count = len(english_ids) + 2 * radius
    if combined & _LOW_SIGNAL_FLAGS:
        return 2, "low_signal"
    if "coarse_asymmetric_paragraph_container" in combined:
        return 2, "coarse_container"
    if radius > _MODE_ONE_MAX_RADIUS:
        return 2, "radius_over_budget"
    if widened_count > _MODE_ONE_MAX_ENGLISH_SENTENCES:
        return 2, "sentence_budget_exceeded"
    return 1, "tight_sentence_link"


def _target_paragraph_payload(
    ids: Iterable[str],
    paragraphs: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for paragraph_id in ids:
        paragraph = paragraphs.get(paragraph_id)
        if paragraph is None:
            raise ValueError(f"link references unknown English paragraph {paragraph_id!r}")
        flags = sorted(str(flag) for flag in paragraph.get("flags") or ())
        payload.append(
            {
                "id": paragraph_id,
                "text": str(paragraph.get("text") or ""),
                "source_hash": str(paragraph.get("source_hash") or ""),
                "flags": flags,
                "exclude_from_alignment": "exclude_from_alignment" in flags,
            }
        )
    return payload


def _events_for_link(
    *,
    link_index: int,
    sentence_link: Mapping[str, Any],
    paragraph_links: Sequence[Mapping[str, Any]],
    structural_links: Sequence[Mapping[str, Any]],
    ar_sentences: Mapping[str, Mapping[str, Any]],
    en_sentences: Mapping[str, Mapping[str, Any]],
    ar_paragraph_structure: Mapping[str, str],
    en_paragraphs: Mapping[str, Mapping[str, Any]],
    en_paragraph_structure: Mapping[str, str],
    sentence_words: Mapping[str, Sequence[LedgerWord]],
    timings: Mapping[str, Sequence[Timing]],
) -> list[dict[str, Any]]:
    paragraph_index = int(sentence_link["paragraph_link_index"])
    if not 0 <= paragraph_index < len(paragraph_links):
        raise ValueError(f"sentence link {link_index} has invalid paragraph index")
    paragraph_link = paragraph_links[paragraph_index]
    structural_index = int(paragraph_link["structural_link_index"])
    if not 0 <= structural_index < len(structural_links):
        raise ValueError(f"paragraph link {paragraph_index} has invalid structural index")
    structural = structural_links[structural_index]

    ar_ids = tuple(str(value) for value in sentence_link.get("arabic_sentence_ids") or ())
    en_ids = tuple(str(value) for value in sentence_link.get("english_sentence_ids") or ())
    try:
        ar_sentence_rows = [ar_sentences[value] for value in ar_ids]
        en_sentence_rows = [en_sentences[value] for value in en_ids]
    except KeyError as exc:
        raise ValueError(
            f"sentence link {link_index} references unknown sentence {exc.args[0]!r}"
        ) from exc
    ar_structure_ids = sorted(
        {
            ar_paragraph_structure[str(sentence["paragraph_id"])]
            for sentence in ar_sentence_rows
        }
    )
    en_structure_ids = sorted(
        {
            en_paragraph_structure[str(sentence["paragraph_id"])]
            for sentence in en_sentence_rows
        }
    )
    paragraph_ids = tuple(
        str(value) for value in paragraph_link.get("english_paragraph_ids") or ()
    )
    paragraph_payload = _target_paragraph_payload(paragraph_ids, en_paragraphs)
    mode, reason = _display_mode(
        structural,
        paragraph_link,
        sentence_link,
        paragraph_payload,
    )
    linked_ar_paragraphs = tuple(
        str(value) for value in paragraph_link.get("arabic_paragraph_ids") or ()
    )
    try:
        paragraph_ar_structures = {
            ar_paragraph_structure[paragraph_id]
            for paragraph_id in linked_ar_paragraphs
        }
        paragraph_en_structures = {
            en_paragraph_structure[paragraph_id] for paragraph_id in paragraph_ids
        }
    except KeyError as exc:
        raise ValueError(
            f"paragraph link {paragraph_index} references unknown paragraph "
            f"{exc.args[0]!r}"
        ) from exc
    allowed_ar_structures = list(structural.get("arabic_structure_ids") or ())
    allowed_en_structures = list(structural.get("english_structure_ids") or ())
    structural_clamp = {
        "structural_link_index": structural_index,
        "arabic_structure_ids": allowed_ar_structures,
        "english_structure_ids": allowed_en_structures,
        "rendered_arabic_structure_ids": sorted(
            set(ar_structure_ids) | paragraph_ar_structures
        ),
        "rendered_english_structure_ids": sorted(
            set(en_structure_ids) | paragraph_en_structures
        ),
    }
    if not set(structural_clamp["rendered_arabic_structure_ids"]) <= set(
        allowed_ar_structures
    ) or not set(structural_clamp["rendered_english_structure_ids"]) <= set(
        allowed_en_structures
    ):
        raise ValueError(
            f"alignment link {link_index} crosses its paired structural units"
        )
    # English-only additions have no Arabic playback position and therefore
    # produce no reader event. Their containment was still checked above.
    if not ar_ids:
        return []
    # This assertion runs even when no audio word from this link is timed.
    assert_event_structural_clamp(
        {"display_mode": mode, "structural_clamp": structural_clamp}
    )

    by_chunk: dict[str, list[Timing]] = defaultdict(list)
    block_ids: list[str] = []
    seen_blocks: set[str] = set()
    for sentence_id in ar_ids:
        for word in sentence_words.get(sentence_id, ()):
            if word.block_id not in seen_blocks:
                seen_blocks.add(word.block_id)
                block_ids.append(word.block_id)
            by_chunk_rows = timings.get(word.id, ())
            for timing in by_chunk_rows:
                by_chunk[timing.chunk_id].append(timing)

    events: list[dict[str, Any]] = []
    for chunk_id, chunk_timings in sorted(
        by_chunk.items(), key=lambda item: min(row.start_ms for row in item[1])
    ):
        start_ms = min(value.start_ms for value in chunk_timings)
        end_ms = max(value.end_ms for value in chunk_timings)
        event = {
            "id": f"link-{link_index:06d}:{chunk_id}:{start_ms}-{end_ms}",
            "sentence_link_index": link_index,
            "chunk_id": chunk_id,
            "chunk_block_sequence": min(
                value.chunk_block_sequence for value in chunk_timings
            ),
            "chunk_source_word_start": min(
                value.chunk_source_word_start for value in chunk_timings
            ),
            "start_ms": start_ms,
            "end_ms": end_ms,
            "duration_ms": end_ms - start_ms,
            "timing_sources": sorted({value.source for value in chunk_timings}),
            "arabic_block_ids": block_ids,
            "arabic_sentence_ids": list(ar_ids),
            "english_sentence_ids": list(en_ids),
            "english_sentences": [
                {
                    "id": str(sentence["id"]),
                    "paragraph_id": str(sentence["paragraph_id"]),
                    "text": str(sentence.get("text") or ""),
                    "source_hash": str(sentence.get("source_hash") or ""),
                }
                for sentence in en_sentence_rows
            ],
            "english_paragraphs": paragraph_payload,
            "display_mode": mode,
            "display_reason": reason,
            "score_confidence": float(sentence_link.get("confidence", 0.0)),
            "uncertainty_radius": int(sentence_link.get("uncertainty_radius", 3)),
            "operation": str(sentence_link.get("operation") or ""),
            "flags": sorted(_flags(structural, paragraph_link, sentence_link)),
            "structural_clamp": structural_clamp,
        }
        assert_event_structural_clamp(event)
        events.append(event)
    return events


def _merged_milliseconds(intervals: Sequence[tuple[int, int]]) -> int:
    if not intervals:
        return 0
    total = 0
    ordered = sorted(intervals)
    start, end = ordered[0]
    for next_start, next_end in ordered[1:]:
        if next_start <= end:
            end = max(end, next_end)
        else:
            total += end - start
            start, end = next_start, next_end
    return total + end - start


def _coverage(events: Sequence[Mapping[str, Any]], chunk_durations: Mapping[str, int]) -> dict[str, Any]:
    modes_by_link: dict[int, int] = {}
    intervals: dict[tuple[str, int], list[tuple[int, int]]] = defaultdict(list)
    for event in events:
        link_index = int(event["sentence_link_index"])
        mode = int(event["display_mode"])
        previous = modes_by_link.setdefault(link_index, mode)
        if previous != mode:
            raise ValueError(f"sentence link {link_index} has inconsistent display modes")
        intervals[(str(event["chunk_id"]), mode)].append(
            (int(event["start_ms"]), int(event["end_ms"]))
        )
    link_counts = Counter(modes_by_link.values())
    total_links = len(modes_by_link)
    audio_ms_by_mode = Counter()
    for (chunk_id, mode), values in intervals.items():
        audio_ms_by_mode[mode] += _merged_milliseconds(values)
    total_audio_ms = sum(chunk_durations.values())
    return {
        "timed_sentence_links": total_links,
        "link_count_by_mode": {str(mode): link_counts.get(mode, 0) for mode in (1, 2, 3)},
        "mode_1_link_coverage": (
            round(link_counts.get(1, 0) / total_links, 6) if total_links else 0.0
        ),
        "complete_arabic_audio_ms": total_audio_ms,
        "mapped_audio_ms_by_mode": {
            str(mode): audio_ms_by_mode.get(mode, 0) for mode in (1, 2, 3)
        },
        "mode_1_audio_time_coverage": (
            round(audio_ms_by_mode.get(1, 0) / total_audio_ms, 6)
            if total_audio_ms
            else 0.0
        ),
    }


def build_reader_timeline(bundle_path: Path, ledger_path: Path) -> dict[str, Any]:
    """Build and validate a reader timeline without mutating either input."""
    manifest, rows = _load_bundle(bundle_path)
    ar_structures = rows["documents/ar.structures.jsonl"]
    en_structures = rows["documents/en.structures.jsonl"]
    ar_paragraphs, ar_paragraph_structure = _structure_indexes(ar_structures)
    en_paragraphs, en_paragraph_structure = _structure_indexes(en_structures)
    ar_sentences = _sentence_index(
        rows["documents/ar.sentences.jsonl"], ar_paragraphs
    )
    en_sentences = _sentence_index(
        rows["documents/en.sentences.jsonl"], en_paragraphs
    )
    structural_links = rows["alignments/structural.jsonl"]
    paragraph_links = rows["alignments/paragraphs.jsonl"]
    sentence_links = rows["alignments/sentences.jsonl"]
    _validate_link_contract(
        structural_links,
        paragraph_links,
        sentence_links,
        ar_structure_ids=set(ar_paragraph_structure.values()),
        en_structure_ids=set(en_paragraph_structure.values()),
    )

    connection = _open_ledger(ledger_path)
    try:
        ledger_words, timings, chunk_durations = _ledger_rows(connection)
    finally:
        connection.close()
    sentence_words, mapping_diagnostics = _map_arabic_sentences(
        ar_structures,
        ar_sentences,
        ledger_words,
    )

    events: list[dict[str, Any]] = []
    for index, sentence_link in enumerate(sentence_links):
        events.extend(
            _events_for_link(
                link_index=index,
                sentence_link=sentence_link,
                paragraph_links=paragraph_links,
                structural_links=structural_links,
                ar_sentences=ar_sentences,
                en_sentences=en_sentences,
                ar_paragraph_structure=ar_paragraph_structure,
                en_paragraphs=en_paragraphs,
                en_paragraph_structure=en_paragraph_structure,
                sentence_words=sentence_words,
                timings=timings,
            )
        )
    events.sort(
        key=lambda row: (
            row["chunk_block_sequence"],
            row["chunk_source_word_start"],
            row["start_ms"],
            row["sentence_link_index"],
        )
    )
    ledger_hasher = hashlib.sha256()
    with ledger_path.expanduser().resolve().open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            ledger_hasher.update(chunk)
    ledger_digest = ledger_hasher.hexdigest()
    result = {
        "schema": READER_TIMELINE_SCHEMA,
        "bundle_id": manifest["bundle_id"],
        "work_id": manifest["work_id"],
        "ledger_sha256": ledger_digest,
        "policy": {
            "version": "provisional-three-mode-v1",
            "mode_1_max_uncertainty_radius": _MODE_ONE_MAX_RADIUS,
            "mode_1_max_english_sentences_with_radius": _MODE_ONE_MAX_ENGLISH_SENTENCES,
            "confidence_semantics": "uncalibrated_score_not_probability",
            "accuracy_status": manifest.get("accuracy_status", "unscored"),
        },
        "diagnostics": {
            **mapping_diagnostics,
            "timed_ledger_words": len(timings),
            "complete_arabic_chunks": len(chunk_durations),
            "reader_events": len(events),
        },
        "coverage": _coverage(events, chunk_durations),
        "events": events,
    }
    identity = {
        "schema": result["schema"],
        "bundle_id": result["bundle_id"],
        "ledger_sha256": result["ledger_sha256"],
        "policy": result["policy"],
        "diagnostics": result["diagnostics"],
        "coverage": result["coverage"],
        "events": result["events"],
    }
    result["timeline_id"] = _sha256_bytes(_json_bytes(identity))
    return result


def write_reader_timeline(
    timeline: Mapping[str, Any],
    output_path: Path,
    *,
    force: bool = False,
) -> None:
    """Atomically write a deterministic timeline JSON file."""
    output = output_path.expanduser().resolve()
    if output.exists() and not force:
        raise FileExistsError(f"refusing to overwrite reader timeline: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = _json_bytes(dict(timeline))
    with tempfile.NamedTemporaryFile(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.chmod(temporary, 0o644)
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()
