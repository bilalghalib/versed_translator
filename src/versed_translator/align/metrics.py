"""Independent-gold scoring for sentence alignment bundles."""

from __future__ import annotations

from collections.abc import Iterable
from statistics import mean
from typing import Any

from versed_translator.align.models import AlignmentResult, Sentence


def _sentence_index(sentences: Iterable[Sentence]) -> dict[str, Sentence]:
    return {sentence.id: sentence for sentence in sentences}


def _fraction(value: int, total: int) -> float:
    return round(value / total, 6) if total else 0.0


def score_sentence_gold(
    result: AlignmentResult,
    gold_rows: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Score exact, buffered, paragraph, catastrophic, and re-anchor behavior.

    Gold rows use stable IDs rather than text:

    ``{"id": "g1", "arabic_sentence_ids": [...],
       "english_sentence_ids": [...]}``
    """
    rows = list(gold_rows)
    if not rows:
        return {
            "status": "unscored",
            "reason": "gold file contained no sentence links",
            "coverage_diagnostics_are_not_accuracy": True,
        }

    ar_sentences = _sentence_index(result.arabic_sentences)
    en_sentences = _sentence_index(result.english_sentences)
    predicted_by_ar: dict[str, set[str]] = {}
    for link in result.sentence_links:
        targets = set(link.english_sentence_ids)
        for source_id in link.arabic_sentence_ids:
            predicted_by_ar.setdefault(source_id, set()).update(targets)

    exact = buffer_1 = buffer_2 = paragraph = catastrophic = 0
    details: list[dict[str, Any]] = []
    ordered: list[tuple[int, bool]] = []
    for position, row in enumerate(rows, start=1):
        row_id = str(row.get("id") or f"gold-{position}")
        gold_ar = tuple(str(item) for item in row.get("arabic_sentence_ids") or ())
        gold_en = tuple(str(item) for item in row.get("english_sentence_ids") or ())
        if not gold_ar or not gold_en:
            raise ValueError(f"gold row {row_id!r} must name Arabic and English sentences")
        missing_ar = [item for item in gold_ar if item not in ar_sentences]
        missing_en = [item for item in gold_en if item not in en_sentences]
        if missing_ar or missing_en:
            raise ValueError(
                f"gold row {row_id!r} references unknown sentence ids: "
                f"arabic={missing_ar[:3]} english={missing_en[:3]}"
            )

        predicted = set().union(
            *(predicted_by_ar.get(source_id, set()) for source_id in gold_ar)
        )
        gold_set = set(gold_en)
        is_exact = predicted == gold_set
        pred_positions = sorted(en_sentences[item].global_sequence for item in predicted)
        gold_positions = sorted(en_sentences[item].global_sequence for item in gold_set)
        in_buffer_1 = bool(pred_positions) and (
            gold_positions[0] >= pred_positions[0] - 1
            and gold_positions[-1] <= pred_positions[-1] + 1
        )
        in_buffer_2 = bool(pred_positions) and (
            gold_positions[0] >= pred_positions[0] - 2
            and gold_positions[-1] <= pred_positions[-1] + 2
        )
        predicted_paragraphs = {
            en_sentences[item].paragraph_id for item in predicted
        }
        gold_paragraphs = {en_sentences[item].paragraph_id for item in gold_set}
        paragraph_hit = bool(predicted_paragraphs & gold_paragraphs)
        is_catastrophic = not paragraph_hit

        exact += int(is_exact)
        buffer_1 += int(is_exact or in_buffer_1)
        buffer_2 += int(is_exact or in_buffer_2)
        paragraph += int(paragraph_hit)
        catastrophic += int(is_catastrophic)
        ar_position = min(ar_sentences[item].global_sequence for item in gold_ar)
        ordered.append((ar_position, is_exact or in_buffer_2))
        details.append(
            {
                "id": row_id,
                "exact": is_exact,
                "buffer_1": is_exact or in_buffer_1,
                "buffer_2": is_exact or in_buffer_2,
                "paragraph_correct": paragraph_hit,
                "catastrophic": is_catastrophic,
                "predicted_english_sentence_ids": sorted(predicted),
            }
        )

    # Distance in Arabic sentence positions from a miss to the next ±2 hit.
    ordered.sort()
    reanchor_distances: list[int] = []
    for index, (start, good) in enumerate(ordered):
        if good:
            continue
        next_good = next(
            (position for position, ok in ordered[index + 1 :] if ok),
            None,
        )
        if next_good is not None:
            reanchor_distances.append(next_good - start)

    total = len(rows)
    return {
        "status": "scored",
        "gold_links": total,
        "exact": _fraction(exact, total),
        "buffer_1": _fraction(buffer_1, total),
        "buffer_2": _fraction(buffer_2, total),
        "paragraph_correct": _fraction(paragraph, total),
        "catastrophic": _fraction(catastrophic, total),
        "reanchor_distance_mean": (
            round(mean(reanchor_distances), 3) if reanchor_distances else None
        ),
        "reanchor_distance_max": max(reanchor_distances, default=None),
        "details": details,
    }

