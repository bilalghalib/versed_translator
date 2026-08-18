"""Generic hierarchical alignment: structure -> paragraph -> sentence.

The engine deliberately accepts already-normalized documents.  OCR cleanup and
edition-specific heading discovery are adapters; correspondence and bundle
contracts stay book-agnostic.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import replace
from typing import Any

from versed_translator.align.dp import Link, SpanScorer, align
from versed_translator.align.models import (
    AlignmentResult,
    Document,
    Paragraph,
    ParagraphLink,
    Sentence,
    SentenceLink,
    StructuralLink,
    sha256_text,
)
from versed_translator.align.sentences import split_arabic, split_english

PARAGRAPH_MOVES: tuple[tuple[int, int], ...] = (
    (1, 1),
    (1, 2),
    (2, 1),
    (2, 2),
    (1, 3),
    (3, 1),
    (2, 3),
    (3, 2),
    (1, 4),
    (4, 1),
    (1, 5),
    (5, 1),
    (1, 0),
    (0, 1),
)

SENTENCE_MOVES: tuple[tuple[int, int], ...] = (
    (1, 1),
    (1, 2),
    (2, 1),
    (2, 2),
    (1, 3),
    (3, 1),
    (1, 4),
    (4, 1),
    (1, 5),
    (5, 1),
    (1, 0),
    (0, 1),
)


def unanchored_whole_book_link(arabic: Document, english: Document) -> StructuralLink:
    """Explicit fallback for books with no bilateral structure.

    This is a container, not evidence.  Its low confidence and flag prevent a
    caller from confusing successful execution with validated correspondence.
    """
    return StructuralLink(
        arabic_structure_ids=tuple(unit.id for unit in arabic.structures),
        english_structure_ids=tuple(unit.id for unit in english.structures),
        method="whole_book_unanchored",
        confidence=0.2,
        flags=("unanchored", "review_required"),
    )


def _paragraph_index(document: Document) -> dict[str, Paragraph]:
    return {
        paragraph.id: paragraph
        for structure in document.structures
        for paragraph in structure.paragraphs
    }


def _structure_index(document: Document):
    return {structure.id: structure for structure in document.structures}


def _selected_paragraphs(
    structure_ids: Iterable[str],
    structures,
) -> list[Paragraph]:
    paragraphs: list[Paragraph] = []
    for structure_id in structure_ids:
        if structure_id not in structures:
            raise ValueError(f"structural link references unknown unit {structure_id!r}")
        paragraphs.extend(
            paragraph
            for paragraph in structures[structure_id].paragraphs
            if "exclude_from_alignment" not in paragraph.flags
        )
    return paragraphs


def _sentences_for_paragraphs(
    paragraphs: Iterable[Paragraph],
    *,
    language: str,
    global_start: int,
) -> tuple[list[Sentence], int]:
    out: list[Sentence] = []
    global_sequence = global_start
    for paragraph in paragraphs:
        split = (
            split_arabic(paragraph.text)
            if language == "ar"
            else split_english(paragraph.text)
        )
        for sentence in split:
            sentence_id = f"{paragraph.id}:s{sentence.index:04d}"
            out.append(
                Sentence(
                    id=sentence_id,
                    paragraph_id=paragraph.id,
                    sequence=sentence.index,
                    global_sequence=global_sequence,
                    text=sentence.text,
                    source_hash=sha256_text(sentence.text),
                )
            )
            global_sequence += 1
    return out, global_sequence


def _coverage(ids: set[str], covered: set[str]) -> float:
    return round(len(ids & covered) / len(ids), 6) if ids else 1.0


def align_documents(
    arabic: Document,
    english: Document,
    *,
    structural_links: Iterable[StructuralLink] | None = None,
    paragraph_scorer: SpanScorer | None = None,
    sentence_scorer: SpanScorer | None = None,
    embedder: Any | None = None,
    max_cells: int = 2_000_000,
) -> AlignmentResult:
    """Align two normalized documents without flattening either hierarchy."""
    arabic.validate()
    english.validate()
    if arabic.language != "ar" or english.language != "en":
        raise ValueError("align_documents expects Arabic source and English target")
    if arabic.work_id != english.work_id:
        raise ValueError(
            f"work ids differ: {arabic.work_id!r} != {english.work_id!r}"
        )
    if embedder is not None and (paragraph_scorer or sentence_scorer):
        raise ValueError("pass an embedder or explicit scorers, not both")

    links = tuple(structural_links or (unanchored_whole_book_link(arabic, english),))
    if not links:
        raise ValueError("at least one structural link is required")

    ar_structures = _structure_index(arabic)
    en_structures = _structure_index(english)
    ar_paragraph_index = _paragraph_index(arabic)
    en_paragraph_index = _paragraph_index(english)
    paragraph_links: list[ParagraphLink] = []
    sentence_links: list[SentenceLink] = []
    all_ar_sentences: list[Sentence] = []
    all_en_sentences: list[Sentence] = []
    next_ar_sentence = 0
    next_en_sentence = 0

    for structural_index, structural in enumerate(links):
        ar_paragraphs = _selected_paragraphs(
            structural.arabic_structure_ids, ar_structures
        )
        en_paragraphs = _selected_paragraphs(
            structural.english_structure_ids, en_structures
        )
        ar_paragraph_texts = [paragraph.text for paragraph in ar_paragraphs]
        en_paragraph_texts = [paragraph.text for paragraph in en_paragraphs]
        active_paragraph_scorer = paragraph_scorer
        if embedder is not None and ar_paragraph_texts and en_paragraph_texts:
            active_paragraph_scorer = embedder.scorer(
                ar_paragraph_texts, en_paragraph_texts
            )
        if (
            ar_paragraph_texts
            and en_paragraph_texts
            and min(len(ar_paragraph_texts), len(en_paragraph_texts)) == 1
            and max(len(ar_paragraph_texts), len(en_paragraph_texts)) > 5
        ):
            # A confirmed structural unit may contain one source paragraph but
            # many OCR target paragraphs (or vice versa). Treat the paragraph
            # relation as a coarse container so the complete section reaches
            # sentence DP; a capped 1:N move would silently discard most of it.
            para_path = [
                Link(
                    arabic_start=0,
                    arabic_end=len(ar_paragraph_texts),
                    english_start=0,
                    english_end=len(en_paragraph_texts),
                    operation=(
                        f"{len(ar_paragraph_texts)}-{len(en_paragraph_texts)}"
                    ),
                    score=0.0,
                    confidence=0.5,
                    uncertainty_radius=2,
                    flags=("coarse_asymmetric_paragraph_container",),
                )
            ]
        else:
            para_path = align(
                ar_paragraph_texts,
                en_paragraph_texts,
                span_scorer=active_paragraph_scorer,
                max_cells=max_cells,
                moves=PARAGRAPH_MOVES,
                skip_cost=0.55 if embedder is not None else 2.4,
            )

        for paragraph_step in para_path:
            ar_slice = ar_paragraphs[
                paragraph_step.arabic_start : paragraph_step.arabic_end
            ]
            en_slice = en_paragraphs[
                paragraph_step.english_start : paragraph_step.english_end
            ]
            paragraph_flags = list(paragraph_step.flags)
            if embedder is None and paragraph_scorer is None:
                paragraph_flags.append("heuristic_only")
            paragraph_link_index = len(paragraph_links)
            paragraph_links.append(
                ParagraphLink(
                    arabic_paragraph_ids=tuple(item.id for item in ar_slice),
                    english_paragraph_ids=tuple(item.id for item in en_slice),
                    operation=paragraph_step.operation,
                    confidence=paragraph_step.confidence,
                    uncertainty_radius=paragraph_step.uncertainty_radius,
                    structural_link_index=structural_index,
                    flags=tuple(sorted(set(paragraph_flags))),
                )
            )

            ar_sentences, next_ar_sentence = _sentences_for_paragraphs(
                ar_slice,
                language="ar",
                global_start=next_ar_sentence,
            )
            en_sentences, next_en_sentence = _sentences_for_paragraphs(
                en_slice,
                language="en",
                global_start=next_en_sentence,
            )
            all_ar_sentences.extend(ar_sentences)
            all_en_sentences.extend(en_sentences)
            ar_sentence_texts = [sentence.text for sentence in ar_sentences]
            en_sentence_texts = [sentence.text for sentence in en_sentences]
            active_sentence_scorer = sentence_scorer
            if embedder is not None and ar_sentence_texts and en_sentence_texts:
                active_sentence_scorer = embedder.scorer(
                    ar_sentence_texts, en_sentence_texts
                )
            sentence_path = align(
                ar_sentence_texts,
                en_sentence_texts,
                span_scorer=active_sentence_scorer,
                max_cells=max_cells,
                moves=SENTENCE_MOVES,
                skip_cost=0.55 if embedder is not None else 2.4,
            )
            for sentence_step in sentence_path:
                ar_sentence_slice = ar_sentences[
                    sentence_step.arabic_start : sentence_step.arabic_end
                ]
                en_sentence_slice = en_sentences[
                    sentence_step.english_start : sentence_step.english_end
                ]
                sentence_flags = list(sentence_step.flags)
                if embedder is None and sentence_scorer is None:
                    sentence_flags.append("heuristic_only")
                if (
                    len(ar_sentences) <= len(ar_slice)
                    and any(len(item.text.split()) > 80 for item in ar_slice)
                ):
                    sentence_flags.append("weak_arabic_sentence_boundaries")
                sentence_links.append(
                    SentenceLink(
                        arabic_sentence_ids=tuple(
                            item.id for item in ar_sentence_slice
                        ),
                        english_sentence_ids=tuple(
                            item.id for item in en_sentence_slice
                        ),
                        operation=sentence_step.operation,
                        confidence=sentence_step.confidence,
                        uncertainty_radius=sentence_step.uncertainty_radius,
                        paragraph_link_index=paragraph_link_index,
                        flags=tuple(sorted(set(sentence_flags))),
                    )
                )

    # The same paragraph or sentence must never be emitted twice.  Overlapping
    # structural anchors would otherwise duplicate translation text downstream.
    ar_paragraph_refs = [
        item for link in paragraph_links for item in link.arabic_paragraph_ids
    ]
    en_paragraph_refs = [
        item for link in paragraph_links for item in link.english_paragraph_ids
    ]
    duplicate_ar = [item for item, count in Counter(ar_paragraph_refs).items() if count > 1]
    duplicate_en = [item for item, count in Counter(en_paragraph_refs).items() if count > 1]
    if duplicate_ar or duplicate_en:
        raise ValueError(
            "structural links overlap; duplicate paragraphs would be emitted: "
            f"arabic={duplicate_ar[:3]} english={duplicate_en[:3]}"
        )

    ar_paragraph_ids = set(ar_paragraph_index)
    en_paragraph_ids = set(en_paragraph_index)
    alignable_ar_paragraph_ids = {
        paragraph_id
        for paragraph_id, paragraph in ar_paragraph_index.items()
        if "exclude_from_alignment" not in paragraph.flags
    }
    alignable_en_paragraph_ids = {
        paragraph_id
        for paragraph_id, paragraph in en_paragraph_index.items()
        if "exclude_from_alignment" not in paragraph.flags
    }
    covered_ar_paragraphs = set(ar_paragraph_refs)
    covered_en_paragraphs = set(en_paragraph_refs)
    covered_ar_sentences = {
        item for link in sentence_links for item in link.arabic_sentence_ids
    }
    covered_en_sentences = {
        item for link in sentence_links for item in link.english_sentence_ids
    }
    all_ar_sentence_ids = {sentence.id for sentence in all_ar_sentences}
    all_en_sentence_ids = {sentence.id for sentence in all_en_sentences}
    diagnostics = {
        "structural_links": len(links),
        "paragraph_links": len(paragraph_links),
        "sentence_links": len(sentence_links),
        "arabic_paragraph_coverage": _coverage(
            ar_paragraph_ids, covered_ar_paragraphs
        ),
        "english_paragraph_coverage": _coverage(
            en_paragraph_ids, covered_en_paragraphs
        ),
        "arabic_alignable_paragraph_coverage": _coverage(
            alignable_ar_paragraph_ids, covered_ar_paragraphs
        ),
        "english_alignable_paragraph_coverage": _coverage(
            alignable_en_paragraph_ids, covered_en_paragraphs
        ),
        "arabic_excluded_paragraphs": len(
            ar_paragraph_ids - alignable_ar_paragraph_ids
        ),
        "english_excluded_paragraphs": len(
            en_paragraph_ids - alignable_en_paragraph_ids
        ),
        "arabic_sentence_coverage": _coverage(
            all_ar_sentence_ids, covered_ar_sentences
        ),
        "english_sentence_coverage": _coverage(
            all_en_sentence_ids, covered_en_sentences
        ),
        "paragraph_operations": dict(
            sorted(Counter(link.operation for link in paragraph_links).items())
        ),
        "sentence_operations": dict(
            sorted(Counter(link.operation for link in sentence_links).items())
        ),
        "warnings": sorted(
            {
                flag
                for link in (*paragraph_links, *sentence_links)
                for flag in link.flags
                if flag.endswith("only") or flag.startswith("weak_")
            }
        ),
        "semantic_model": getattr(embedder, "model_name", None),
    }
    metrics = {
        "status": "unscored",
        "reason": "no independent gold sentence links were supplied",
        "coverage_diagnostics_are_not_accuracy": True,
    }
    return AlignmentResult(
        arabic=arabic,
        english=english,
        structural_links=links,
        paragraph_links=tuple(paragraph_links),
        arabic_sentences=tuple(all_ar_sentences),
        english_sentences=tuple(all_en_sentences),
        sentence_links=tuple(sentence_links),
        diagnostics=diagnostics,
        metrics=metrics,
    )


def with_metrics(result: AlignmentResult, metrics: dict) -> AlignmentResult:
    return replace(result, metrics=metrics)
