"""Small monotone length partitioner for work-specific alignment proposals.

This is deliberately not treated as alignment evidence. It only proposes a
bounded search path when a work has ordered units on one side and finer
ordered fragments on the other. Every resulting passage must be adjudicated
for content before selection.
"""

from __future__ import annotations

import math


def partition(
    unit_weights: list[int],
    fragment_weights: list[int],
    *,
    min_fragments: int = 1,
    max_fragments: int = 8,
) -> list[tuple[int, int]]:
    """Assign consecutive fragments to every consecutive unit.

    The dynamic program minimises deviation from the work-level word ratio.
    It never reorders, duplicates, or drops a fragment. Callers must validate
    semantic correspondence separately; similar length is not proof.
    """
    if not unit_weights or not fragment_weights:
        return []
    if len(fragment_weights) < len(unit_weights) * min_fragments:
        raise ValueError("not enough fragments for the requested minimum")
    if len(fragment_weights) > len(unit_weights) * max_fragments:
        raise ValueError("too many fragments for the requested maximum")

    ratio = sum(fragment_weights) / max(1, sum(unit_weights))
    prefix = [0]
    for weight in fragment_weights:
        prefix.append(prefix[-1] + weight)

    infinity = float("inf")
    width = len(fragment_weights) + 1
    previous = [infinity] * width
    previous[0] = 0.0
    back: list[list[int]] = [[-1] * width for _ in unit_weights]

    for unit_index, unit_weight in enumerate(unit_weights):
        current = [infinity] * width
        remaining_units = len(unit_weights) - unit_index - 1
        for end in range(1, width):
            for count in range(min_fragments, max_fragments + 1):
                start = end - count
                if start < 0 or previous[start] == infinity:
                    continue
                remaining_fragments = len(fragment_weights) - end
                if not (
                    remaining_units * min_fragments
                    <= remaining_fragments
                    <= remaining_units * max_fragments
                ):
                    continue
                observed = prefix[end] - prefix[start]
                expected = max(1.0, unit_weight * ratio)
                cost = math.log((observed + 1) / (expected + 1)) ** 2
                candidate = previous[start] + cost
                if candidate < current[end]:
                    current[end] = candidate
                    back[unit_index][end] = start
        previous = current

    end = len(fragment_weights)
    if previous[end] == infinity:
        raise ValueError("no monotone partition satisfies the fragment bounds")
    ranges: list[tuple[int, int]] = []
    for unit_index in range(len(unit_weights) - 1, -1, -1):
        start = back[unit_index][end]
        if start < 0:
            raise RuntimeError("partition backtrace is incomplete")
        ranges.append((start, end))
        end = start
    return list(reversed(ranges))


__all__ = ["partition"]
