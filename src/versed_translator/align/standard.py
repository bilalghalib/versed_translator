"""Book-agnostic zipper: distinctive names first, then monotone cover.

No Hayy regexes. English ``dh`` is tried as ``z``/``d`` because 18th-c.
transliteration and Arabic ``ظ``/``ذ`` disagree (Yokdhan vs يقظان). That is
a spelling variant, not a work-specific lock.
"""

from __future__ import annotations

from versed_translator.benchmark.sources import monotone_length
from versed_translator.benchmark.sources.translit import (
    arabic_skeleton,
    english_name_skeletons,
)

MIN_ANCHOR_MASS = 3


def _latin_variants(skeleton: str) -> tuple[str, ...]:
    variants = {skeleton}
    if "dh" in skeleton:
        variants.add(skeleton.replace("dh", "z"))
        variants.add(skeleton.replace("dh", "d"))
    if "th" in skeleton:
        variants.add(skeleton.replace("th", "t"))
    return tuple(variants)


def _usable_name(token: str) -> bool:
    """18th-c. prose capitalises Island/Body/Spirit; those are not anchors."""
    if len(token) >= 7:
        return True
    lower = token.lower()
    return any(marker in lower for marker in ("dh", "kh", "gh", "qā", "ibn"))


def name_mass(english: str, arabic: str) -> int:
    blobs = (arabic_skeleton(arabic, "h"), arabic_skeleton(arabic, "t"))
    mass = 0
    for raw in english.split():
        token = raw.strip(".,;:!?\"“”")
        if not token or not _usable_name(token):
            continue
        for skeleton in english_name_skeletons(token, min_len=3):
            for variant in _latin_variants(skeleton):
                if len(variant) < 3:
                    continue
                if any(variant in blob for blob in blobs):
                    mass += len(variant)
                    break
    return mass


def anchors(arabic: list[str], english: list[str]) -> list[tuple[int, int]]:
    """Monotone (arabic_index, english_index) pairs with enough name mass."""
    pairs: list[tuple[int, int]] = []
    en_cursor = 0
    for ar_index, ar_text in enumerate(arabic):
        limit = min(len(english), en_cursor + 8)
        for en_index in range(en_cursor, limit):
            mass = name_mass(english[en_index], ar_text)
            if mass >= MIN_ANCHOR_MASS:
                pairs.append((ar_index, en_index))
                en_cursor = en_index + 1
                break
    return pairs


def _proportional(n_english: int, n_arabic: int) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for index in range(n_english):
        start = index * n_arabic // n_english
        end = (index + 1) * n_arabic // n_english
        ranges.append((start, max(end, start + 1) if start < n_arabic else start))
    if ranges:
        last_start, _ = ranges[-1]
        ranges[-1] = (last_start, n_arabic)
    return ranges


def _cover_region(arabic: list[str], english: list[str]) -> list[tuple[int, int]]:
    """English-unit -> arabic [start, end) inside this region."""
    if not english:
        return []
    if not arabic:
        return [(0, 0) for _ in english]
    if len(english) == 1:
        return [(0, len(arabic))]
    if len(arabic) == 1:
        return [(0, 1) for _ in english]
    max_fragments = max(8, (len(arabic) + len(english) - 1) // len(english))
    try:
        return monotone_length.partition(
            [max(1, len(text.split())) for text in english],
            [max(1, len(text.split())) for text in arabic],
            min_fragments=1,
            max_fragments=max_fragments,
        )
    except ValueError:
        return _proportional(len(english), len(arabic))


def zip_units(arabic: list[str], english: list[str]) -> list[tuple[int, int]]:
    """Map each Arabic unit to an English [start, end) index range."""
    mapping = [(0, 0) for _ in arabic]
    if not arabic or not english:
        return mapping

    locks = [(0, 0), *anchors(arabic, english), (len(arabic), len(english))]
    # Drop duplicate lock points so empty intervals disappear.
    compact: list[tuple[int, int]] = [locks[0]]
    for pair in locks[1:]:
        if pair[0] < compact[-1][0] or pair[1] < compact[-1][1]:
            continue
        if pair == compact[-1]:
            continue
        compact.append(pair)

    for (ar_a, en_a), (ar_b, en_b) in zip(compact, compact[1:]):
        region_ar = arabic[ar_a:ar_b]
        region_en = english[en_a:en_b]
        covers = _cover_region(region_ar, region_en)
        for en_offset, (local_start, local_end) in enumerate(covers):
            for local in range(local_start, local_end):
                ar_index = ar_a + local
                if ar_index >= ar_b:
                    continue
                start, end = mapping[ar_index]
                new_start = en_a + en_offset
                new_end = new_start + 1
                if start == end == 0:
                    mapping[ar_index] = (new_start, new_end)
                else:
                    mapping[ar_index] = (min(start, new_start), max(end, new_end))
    return mapping


def section_hit(
    gold: tuple[int, int],
    predicted: tuple[int, int],
    *,
    window: int,
) -> bool:
    gold_start, gold_end = gold
    pred_start, pred_end = predicted
    return pred_start - window < gold_end and pred_end + window > gold_start
