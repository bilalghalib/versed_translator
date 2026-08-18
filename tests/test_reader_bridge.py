"""Offline audio-time → bilingual-reader identity bridge tests."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from versed_translator.align.bundle import write_bundle
from versed_translator.align.engine import align_documents
from versed_translator.align.models import (
    Document,
    Paragraph,
    StructuralLink,
    StructuralUnit,
    sha256_text,
)
from versed_translator.align.reader_bridge import (
    assert_event_structural_clamp,
    build_reader_timeline,
    write_reader_timeline,
)


def _document(language: str, unit_number: int, text: str) -> Document:
    unit_id = f"{language}:u{unit_number:04d}"
    paragraph = Paragraph.create(
        paragraph_id=f"{unit_id}:p0000",
        sequence=0,
        text=text,
    )
    return Document(
        work_id="bridge-work",
        language=language,
        source_name=f"{language}.txt",
        source_hash=sha256_text(text),
        structures=(
            StructuralUnit(
                id=unit_id,
                sequence=0,
                heading="fixture",
                paragraphs=(paragraph,),
            ),
        ),
    )


def _bundle(tmp_path: Path, *, structural_flags=()) -> Path:
    arabic = _document("ar", 1, "قال حي هذا. ثم سار.")
    # Deliberately use a different unit number. Explicit structural mappings
    # are containment assertions, not numeric-prefix equality assertions.
    english = _document("en", 9, "Hayy said this. Then he walked.")
    result = align_documents(
        arabic,
        english,
        structural_links=(
            StructuralLink(
                arabic_structure_ids=("ar:u0001",),
                english_structure_ids=("en:u0009",),
                method="explicit_fixture",
                confidence=1.0,
                flags=tuple(structural_flags),
            ),
        ),
    )
    # The fixture has exact known links; remove the engine's honest
    # heuristic-only marker so mode 1 can be exercised independently.
    result = replace(
        result,
        paragraph_links=tuple(
            replace(link, flags=(), confidence=0.95, uncertainty_radius=0)
            for link in result.paragraph_links
        ),
        sentence_links=tuple(
            replace(link, flags=(), confidence=0.95, uncertainty_radius=0)
            for link in result.sentence_links
        ),
    )
    path = tmp_path / "alignment.zip"
    write_bundle(result, path)
    return path


def _ledger(tmp_path: Path, *, invalid_timing: bool = False) -> Path:
    path = tmp_path / "edition.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE blocks (
            id TEXT PRIMARY KEY, sequence INTEGER, language TEXT
        );
        CREATE TABLE words (
            id TEXT PRIMARY KEY, block_id TEXT, sequence INTEGER, text TEXT
        );
        CREATE TABLE audio_chunks (
            id TEXT PRIMARY KEY, language TEXT, status TEXT,
            duration_ms INTEGER, block_sequence INTEGER,
            source_word_start INTEGER
        );
        CREATE TABLE audio_word_timings (
            chunk_id TEXT, word_id TEXT, sequence INTEGER, text TEXT,
            start_ms INTEGER, end_ms INTEGER, source TEXT
        );
        """
    )
    connection.execute(
        "INSERT INTO blocks(id,sequence,language) VALUES ('b1',0,'arabic')"
    )
    words = [
        ("w1", "b1", 0, "قال"),
        ("w2", "b1", 1, "حي"),
        ("w3", "b1", 2, "هذا"),
        ("w4", "b1", 3, "ثم"),
        ("w5", "b1", 4, "سار"),
    ]
    connection.executemany(
        "INSERT INTO words(id,block_id,sequence,text) VALUES (?,?,?,?)", words
    )
    connection.execute(
        """
        INSERT INTO audio_chunks(
            id,language,status,duration_ms,block_sequence,source_word_start
        ) VALUES ('c1','ar','complete',1000,0,0)
        """
    )
    ends = [100, 200, 300, 450, 600]
    if invalid_timing:
        ends[-1] = 1100
    connection.executemany(
        """
        INSERT INTO audio_word_timings(
            chunk_id,word_id,sequence,text,start_ms,end_ms,source
        ) VALUES ('c1',?,?,?,?,?,'fish_native')
        """,
        [
            (word[0], index, word[3], 0 if index == 0 else ends[index - 1], ends[index])
            for index, word in enumerate(words)
        ],
    )
    connection.commit()
    connection.close()
    return path


def test_bridge_composes_audio_time_and_alignment_ids(tmp_path: Path):
    timeline = build_reader_timeline(_bundle(tmp_path), _ledger(tmp_path))

    assert timeline["schema"] == "versed.align.reader-timeline.v1"
    assert timeline["diagnostics"]["arabic_sentence_mapping_rate"] == 1.0
    assert len(timeline["events"]) == 2
    assert [event["display_mode"] for event in timeline["events"]] == [1, 1]
    first = timeline["events"][0]
    assert first["arabic_sentence_ids"] == ["ar:u0001:p0000:s0000"]
    assert first["english_sentence_ids"] == ["en:u0009:p0000:s0000"]
    assert first["arabic_block_ids"] == ["b1"]
    assert (first["start_ms"], first["end_ms"]) == (0, 300)
    assert first["structural_clamp"]["english_structure_ids"] == ["en:u0009"]
    assert timeline["coverage"]["mode_1_link_coverage"] == 1.0
    assert timeline["coverage"]["mode_1_audio_time_coverage"] == 0.6


def test_structural_clamp_allows_explicitly_paired_different_unit_numbers(tmp_path: Path):
    event = build_reader_timeline(_bundle(tmp_path), _ledger(tmp_path))["events"][0]
    assert_event_structural_clamp(event)


def test_structural_clamp_rejects_cross_section_render():
    event = {
        "display_mode": 1,
        "structural_clamp": {
            "arabic_structure_ids": ["ar:u0001"],
            "english_structure_ids": ["en:u0009"],
            "rendered_arabic_structure_ids": ["ar:u0001"],
            "rendered_english_structure_ids": ["en:u0010"],
        },
    }
    with pytest.raises(ValueError, match="English reader payload crosses"):
        assert_event_structural_clamp(event)


def test_review_required_demotes_to_section_anchor(tmp_path: Path):
    timeline = build_reader_timeline(
        _bundle(tmp_path, structural_flags=("review_required", "unanchored")),
        _ledger(tmp_path),
    )
    assert {event["display_mode"] for event in timeline["events"]} == {3}
    assert {event["display_reason"] for event in timeline["events"]} == {
        "structural_review_required"
    }


def test_low_signal_demotes_to_paragraph_follow(tmp_path: Path):
    bundle = _bundle(tmp_path)
    # Exercise the pure provisional policy through a valid rebuilt bundle.
    # The normal unembedded engine output carries heuristic_only.
    arabic = _document("ar", 1, "قال حي هذا. ثم سار.")
    english = _document("en", 9, "Hayy said this. Then he walked.")
    result = align_documents(
        arabic,
        english,
        structural_links=(
            StructuralLink(
                arabic_structure_ids=("ar:u0001",),
                english_structure_ids=("en:u0009",),
                method="explicit_fixture",
                confidence=1.0,
            ),
        ),
    )
    bundle.unlink()
    write_bundle(result, bundle)
    timeline = build_reader_timeline(bundle, _ledger(tmp_path))
    assert {event["display_mode"] for event in timeline["events"]} == {2}
    assert {event["display_reason"] for event in timeline["events"]} == {"low_signal"}


def test_bridge_rejects_timing_past_chunk_duration(tmp_path: Path):
    with pytest.raises(ValueError, match="timing exceeds chunk duration"):
        build_reader_timeline(
            _bundle(tmp_path),
            _ledger(tmp_path, invalid_timing=True),
        )


def test_audio_time_denominator_includes_complete_chunks_without_timings(tmp_path: Path):
    ledger = _ledger(tmp_path)
    connection = sqlite3.connect(ledger)
    connection.execute(
        """
        INSERT INTO audio_chunks(
            id,language,status,duration_ms,block_sequence,source_word_start
        ) VALUES ('c2','ar','complete',500,1,0)
        """
    )
    connection.commit()
    connection.close()
    timeline = build_reader_timeline(_bundle(tmp_path), ledger)
    assert timeline["coverage"]["complete_arabic_audio_ms"] == 1500
    assert timeline["coverage"]["mode_1_audio_time_coverage"] == 0.4


def test_timeline_write_is_deterministic_and_refuses_overwrite(tmp_path: Path):
    timeline = build_reader_timeline(_bundle(tmp_path), _ledger(tmp_path))
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    write_reader_timeline(timeline, first)
    write_reader_timeline(timeline, second)
    assert first.read_bytes() == second.read_bytes()
    assert json.loads(first.read_text())["timeline_id"] == timeline["timeline_id"]
    with pytest.raises(FileExistsError):
        write_reader_timeline(timeline, first)
