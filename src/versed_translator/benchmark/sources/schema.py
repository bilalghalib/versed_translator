"""Candidate-pair schema shared by every C1-checkpoint-1 source loader.

Each loader's ``iter_pairs()`` yields plain ``dict`` objects with exactly
these keys (see PAIR_FIELDS). Fields the source does not provide are set to
``None`` -- loaders must not guess or compute values the source itself does
not carry (e.g. no genre inference from title text, no century inference
from author names).
"""

from __future__ import annotations

PAIR_FIELDS: tuple[str, ...] = (
    "source",
    "source_native_id",
    "work_id",
    "author",
    "genre",
    "date_or_century",
    "arabic",
    "reference_english",
    "translator",
    "english_source",
    "rights_status",
    "source_split",
    "notes",
)


def make_pair(**kwargs: object) -> dict:
    """Build a candidate-pair dict, defaulting any omitted field to None.

    Raises ValueError if an unknown key is passed, so loaders fail loudly
    on schema drift rather than silently emitting extra/misspelled keys.
    """
    unknown = set(kwargs) - set(PAIR_FIELDS)
    if unknown:
        raise ValueError(f"unknown pair field(s): {sorted(unknown)}")
    return {field: kwargs.get(field) for field in PAIR_FIELDS}


# Arabic-word-count length bands used by the summary CLI (C1 master-plan
# passage-size banding, minus the "near-context-limit" open top band which
# we report simply as 600+).
LENGTH_BANDS: tuple[tuple[str, int, int | None], ...] = (
    ("30-80", 30, 80),
    ("100-250", 100, 250),
    ("250-600", 250, 600),
    ("600+", 600, None),
)


def length_band(word_count: int) -> str | None:
    """Return the band label for word_count, or None if it falls in a gap
    between bands (e.g. 81-99 is intentionally uncovered by the master-plan
    bands, same as 601 falling only into 600+ is covered but 81-99 is not)."""
    for label, lo, hi in LENGTH_BANDS:
        if hi is None:
            if word_count >= lo:
                return label
        elif lo <= word_count <= hi:
            return label
    return None


def arabic_word_count(text: str | None) -> int:
    if not text:
        return 0
    return len(text.split())
