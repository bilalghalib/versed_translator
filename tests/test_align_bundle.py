"""Generic alignment result, gold scoring, and portable archive contract."""

from __future__ import annotations

import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from versed_translator.align.bundle import verify_bundle, write_bundle
from versed_translator.align.engine import align_documents, with_metrics
from versed_translator.align.metrics import score_sentence_gold
from versed_translator.align.models import (
    Document,
    Paragraph,
    StructuralLink,
    StructuralUnit,
    sha256_text,
)


def _document(language: str, paragraphs: list[str]) -> Document:
    prefix = language
    unit = StructuralUnit(
        id=f"{prefix}:u0001",
        sequence=0,
        heading="one",
        anchor_key="one",
        paragraphs=tuple(
            Paragraph.create(
                paragraph_id=f"{prefix}:u0001:p{index:04d}",
                sequence=index,
                text=text,
            )
            for index, text in enumerate(paragraphs)
        ),
    )
    source = "\n\n".join(paragraphs)
    return Document(
        work_id="work",
        language=language,
        source_name=f"{language}.txt",
        source_hash=sha256_text(source),
        structures=(unit,),
    )


def _result():
    arabic = _document("ar", ["قال حي هذا. ثم سار."])
    english = _document("en", ["Hayy said this. Then he walked."])
    structural = StructuralLink(
        arabic_structure_ids=("ar:u0001",),
        english_structure_ids=("en:u0001",),
        method="fixture",
        confidence=1.0,
    )
    return align_documents(arabic, english, structural_links=(structural,))


def test_engine_preserves_three_layers_and_stable_ids():
    result = _result()
    assert len(result.structural_links) == 1
    assert len(result.paragraph_links) == 1
    assert len(result.sentence_links) == 2
    assert [sentence.id for sentence in result.arabic_sentences] == [
        "ar:u0001:p0000:s0000",
        "ar:u0001:p0000:s0001",
    ]
    assert result.metrics["status"] == "unscored"


def test_gold_metrics_distinguish_accuracy_from_coverage():
    result = _result()
    gold = [
        {
            "id": "g1",
            "arabic_sentence_ids": [result.arabic_sentences[0].id],
            "english_sentence_ids": [result.english_sentences[0].id],
        },
        {
            "id": "g2",
            "arabic_sentence_ids": [result.arabic_sentences[1].id],
            "english_sentence_ids": [result.english_sentences[1].id],
        },
    ]
    metrics = score_sentence_gold(result, gold)
    assert metrics["status"] == "scored"
    assert metrics["exact"] == 1.0
    assert metrics["catastrophic"] == 0.0


def test_bundle_is_deterministic_and_checksum_verified(tmp_path: Path):
    result = _result()
    metrics = score_sentence_gold(
        result,
        [
            {
                "id": "g1",
                "arabic_sentence_ids": [result.arabic_sentences[0].id],
                "english_sentence_ids": [result.english_sentences[0].id],
            }
        ],
    )
    result = with_metrics(result, metrics)
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    write_bundle(result, first)
    write_bundle(result, second)
    assert first.read_bytes() == second.read_bytes()
    manifest = verify_bundle(first)
    assert manifest["accuracy_status"] == "scored"
    assert manifest["rights_policy"] == "not_evaluated_by_aligner"


def test_bundle_identity_changes_when_alignment_payload_changes(tmp_path: Path):
    original = _result()
    changed = replace(
        original,
        diagnostics={**original.diagnostics, "semantic_model": "fixture/model"},
    )
    original_manifest = write_bundle(original, tmp_path / "original.zip")
    changed_manifest = write_bundle(changed, tmp_path / "changed.zip")
    assert original_manifest["bundle_id"] != changed_manifest["bundle_id"]


def test_bundle_refuses_overwrite(tmp_path: Path):
    output = tmp_path / "book.zip"
    write_bundle(_result(), output)
    with pytest.raises(FileExistsError):
        write_bundle(_result(), output)


def test_bundle_verifier_rejects_undeclared_member(tmp_path: Path):
    output = tmp_path / "book.zip"
    write_bundle(_result(), output)
    with zipfile.ZipFile(output, "a") as archive:
        archive.writestr("unexpected.txt", "no")
    with pytest.raises(ValueError, match="do not match manifest"):
        verify_bundle(output)


def test_overlapping_structural_links_fail_loud():
    arabic = _document("ar", ["قال حي هذا."])
    english = _document("en", ["Hayy said this."])
    link = StructuralLink(
        arabic_structure_ids=("ar:u0001",),
        english_structure_ids=("en:u0001",),
        method="fixture",
        confidence=1.0,
    )
    with pytest.raises(ValueError, match="overlap"):
        align_documents(arabic, english, structural_links=(link, replace(link)))


def test_document_rejects_non_contiguous_sequence():
    document = _document("ar", ["نص عربي."])
    broken = replace(
        document,
        structures=(replace(document.structures[0], sequence=3),),
    )
    with pytest.raises(ValueError, match="not contiguous"):
        broken.validate()


def test_document_rejects_non_contiguous_paragraph_sequence():
    document = _document("ar", ["نص عربي."])
    paragraph = replace(document.structures[0].paragraphs[0], sequence=2)
    broken = replace(
        document,
        structures=(replace(document.structures[0], paragraphs=(paragraph,)),),
    )
    with pytest.raises(ValueError, match="paragraph sequence is not contiguous"):
        broken.validate()


def test_asymmetric_confirmed_section_reaches_sentence_alignment():
    arabic = _document("ar", ["قال كلاما طويلا، ثم سار إلى بيته، ثم نام."])
    english = _document(
        "en",
        [
            "He spoke at length.",
            "Then he walked home.",
            "Then he slept.",
            "A translator's note.",
            "Another note.",
            "One more note.",
        ],
    )
    structural = StructuralLink(
        arabic_structure_ids=("ar:u0001",),
        english_structure_ids=("en:u0001",),
        method="fixture",
        confidence=1.0,
    )
    result = align_documents(arabic, english, structural_links=(structural,))
    assert result.paragraph_links[0].operation == "1-6"
    assert "coarse_asymmetric_paragraph_container" in result.paragraph_links[0].flags
    assert {
        sentence.id for sentence in result.english_sentences
    } == {
        "en:u0001:p0000:s0000",
        "en:u0001:p0001:s0000",
        "en:u0001:p0002:s0000",
        "en:u0001:p0003:s0000",
        "en:u0001:p0004:s0000",
        "en:u0001:p0005:s0000",
    }
