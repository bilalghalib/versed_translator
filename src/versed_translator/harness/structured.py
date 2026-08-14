"""The structured-block response contract: named errors for every way ids
can fail to come back.

ID preservation is the entire point of the structured template (D2e). So an
id problem is a *first-class, named, countable error*, never a silent drop:

* an id that was sent but did not come back  -> ``id_missing_from_structured_response``
* an id that came back but was never sent    -> ``id_unexpected_in_structured_response``
* an id that came back more than once        -> ``id_duplicated_in_structured_response``
* an id that came back with empty English    -> ``structured_empty_translation``
* a response that will not parse at all      -> ``structured_parse_error: ...`` for every id in the batch

That last one is why this module owns ``batch_error_results``: a malformed
response must degrade to one error row per item in the batch, never raise.
There is precedent for getting this wrong -- a single invalid row once
raised out of the writer and lost all 139 buffered results of a finished
run. Losing completed work to a downstream formatting problem is worse than
any error rate.

The three adapters previously each carried their own copy of the id-splitting
loop, and only the "missing" case was named; extra and duplicate ids were
silently discarded by the ``{obj["id"]: obj["english"]}`` dict comprehension.
Centralising it here is what makes those cases countable at all.
"""

from __future__ import annotations

from collections.abc import Iterable

from versed_translator.harness.adapters.base import TranslationResult

ERR_ID_MISSING = "id_missing_from_structured_response"
ERR_ID_UNEXPECTED = "id_unexpected_in_structured_response"
ERR_ID_DUPLICATE = "id_duplicated_in_structured_response"
ERR_EMPTY = "structured_empty_translation"
ERR_PARSE_PREFIX = "structured_parse_error"

#: Every error name that means "the id contract was broken". ``score`` and
#: ``runner`` count these as ID loss; anything else is an ordinary failure.
ID_CONTRACT_ERRORS: frozenset[str] = frozenset(
    {ERR_ID_MISSING, ERR_ID_UNEXPECTED, ERR_ID_DUPLICATE}
)


def batch_error_results(
    item_ids: Iterable[str],
    error: str,
    *,
    source_tokens: int | None = None,
    output_tokens: int | None = None,
    latency_s: float | None = None,
) -> list[TranslationResult]:
    """One error row per id -- the standard degradation for a failed batch."""
    return [
        TranslationResult(
            item_id=item_id,
            translation=None,
            source_tokens=source_tokens,
            output_tokens=output_tokens,
            latency_s=latency_s,
            error=error,
        )
        for item_id in item_ids
    ]


def split_structured_results(
    parsed: list[dict],
    item_ids: Iterable[str],
    *,
    source_tokens: int | None = None,
    output_tokens: int | None = None,
    latency_s: float | None = None,
    cost_estimate: float | None = None,
) -> list[TranslationResult]:
    """Split a parsed structured response into one result per *sent* id, plus
    one extra error result per *unsent* id the model invented.

    Per-item token/latency figures aren't separable from a batched call, so
    the whole call's totals are attributed to each item. That over-counts if
    summed per item and is stated here rather than silently assumed: run-level
    aggregates stay meaningful for cost tracking, per-item ones do not.
    """
    ids = list(item_ids)
    expected = set(ids)

    seen: dict[str, object] = {}
    duplicated: set[str] = set()
    unexpected: list[str] = []
    for obj in parsed:
        oid = obj.get("id")
        if oid in seen:
            duplicated.add(oid)
            continue
        seen[oid] = obj.get("english")
        if oid not in expected:
            unexpected.append(oid)

    results: list[TranslationResult] = []
    for item_id in ids:
        english = seen.get(item_id)
        if item_id in duplicated:
            error: str | None = ERR_ID_DUPLICATE
        elif item_id not in seen:
            error = ERR_ID_MISSING
        elif not isinstance(english, str) or not english.strip():
            error = ERR_EMPTY
        else:
            error = None
        results.append(
            TranslationResult(
                item_id=item_id,
                translation=english if error is None else None,
                source_tokens=source_tokens,
                output_tokens=output_tokens,
                latency_s=latency_s,
                cost_estimate=cost_estimate if error is None else None,
                error=error,
            )
        )

    # Ids the model invented are reported, not dropped: an unrecognised id is
    # evidence the model rewrote the keys, which is exactly the failure the
    # id contract is meant to surface.
    results.extend(
        batch_error_results(
            [str(oid) for oid in unexpected],
            ERR_ID_UNEXPECTED,
            source_tokens=source_tokens,
            output_tokens=output_tokens,
            latency_s=latency_s,
        )
    )
    return results


def id_error_counts(rows: Iterable[dict]) -> dict:
    """Count id-contract violations over result rows (or TranslationResults).

    Accepts dicts (schema rows) or anything with an ``error`` attribute.
    """
    counts = {
        "id_missing_count": 0,
        "id_unexpected_count": 0,
        "id_duplicate_count": 0,
        "structured_empty_count": 0,
    }
    for row in rows:
        error = row.get("error") if isinstance(row, dict) else getattr(row, "error", None)
        if error == ERR_ID_MISSING:
            counts["id_missing_count"] += 1
        elif error == ERR_ID_UNEXPECTED:
            counts["id_unexpected_count"] += 1
        elif error == ERR_ID_DUPLICATE:
            counts["id_duplicate_count"] += 1
        elif error == ERR_EMPTY:
            counts["structured_empty_count"] += 1
    return counts
