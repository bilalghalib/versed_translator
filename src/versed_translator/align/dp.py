"""Variable-span monotonic DP. Length is a prior, not the alignment."""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass

from versed_translator.benchmark.sources.translit import anchor_score

_NUMBER_RE = re.compile(r"\d+")

# (arabic_count, english_count) moves. Skips last so they lose to a real match.
MOVES: tuple[tuple[int, int], ...] = (
    (1, 1),
    (1, 2),
    (2, 1),
    (2, 2),
    (1, 3),
    (3, 1),
    (1, 0),
    (0, 1),
)

SKIP_COST = 2.4
LENGTH_RATIO = 1.55  # English words per Arabic word, Hayy/Ockley-ish


@dataclass(frozen=True)
class Link:
    arabic_start: int
    arabic_end: int  # exclusive
    english_start: int
    english_end: int
    operation: str
    score: float
    confidence: float
    uncertainty_radius: int
    flags: tuple[str, ...] = ()

    @property
    def arabic_span(self) -> tuple[int, int]:
        return (self.arabic_start, self.arabic_end)

    @property
    def english_span(self) -> tuple[int, int]:
        return (self.english_start, self.english_end)


def _join(sentences: list[str], start: int, end: int) -> str:
    return " ".join(sentences[start:end])


def _length_cost(ar_words: int, en_words: int) -> float:
    expected = max(1.0, ar_words * LENGTH_RATIO)
    observed = max(1.0, float(en_words))
    return abs(math.log(observed / expected))


def _number_score(arabic: str, english: str) -> float:
    def normalized_numbers(text: str) -> set[str]:
        return {
            "".join(str(unicodedata.digit(character)) for character in raw)
            for raw in _NUMBER_RE.findall(text)
        }

    ar = normalized_numbers(arabic)
    en = normalized_numbers(english)
    if not ar and not en:
        return 0.0
    if not ar or not en:
        return 0.0
    return len(ar & en) / len(ar | en)


def pair_score(arabic: str, english: str) -> float:
    """Higher is better. Crude mix until embeddings earn a seat."""
    if not arabic.strip() or not english.strip():
        return -SKIP_COST
    ar_words = max(1, len(arabic.split()))
    en_words = max(1, len(english.split()))
    entity = anchor_score(english, arabic)
    numbers = _number_score(arabic, english)
    length = math.exp(-_length_cost(ar_words, en_words))
    return 0.20 * entity + 0.10 * numbers + 0.10 * length + 0.60 * min(1.0, entity + length)


SpanScorer = Callable[[list[str], int, int, list[str], int, int], float]


def _default_span_score(
    arabic: list[str],
    ar_start: int,
    ar_end: int,
    english: list[str],
    en_start: int,
    en_end: int,
) -> float:
    return pair_score(
        _join(arabic, ar_start, ar_end),
        _join(english, en_start, en_end),
    )


def align(
    arabic: list[str],
    english: list[str],
    *,
    span_scorer: SpanScorer | None = None,
    max_cells: int = 2_000_000,
    moves: tuple[tuple[int, int], ...] = MOVES,
    skip_cost: float = SKIP_COST,
) -> list[Link]:
    """Return the best variable-span monotone path.

    ``max_cells`` is a hard resource boundary.  Whole books must first be
    divided by structural anchors instead of allocating an unbounded DP table.
    """
    n, m = len(arabic), len(english)
    if n == 0 and m == 0:
        return []
    if n == 0:
        return [
            Link(0, 0, j, j + 1, "0-1", -skip_cost, 0.15, 3, ("english_addition",))
            for j in range(m)
        ]
    if m == 0:
        return [
            Link(i, i + 1, 0, 0, "1-0", -skip_cost, 0.15, 3, ("arabic_omission",))
            for i in range(n)
        ]

    cells = (n + 1) * (m + 1)
    if cells > max_cells:
        raise ValueError(
            f"alignment window is too large ({n}x{m}={cells} cells); "
            "add structural anchors or raise max_cells deliberately"
        )

    score_span = span_scorer or _default_span_score

    neg_inf = float("-inf")
    best = [[neg_inf] * (m + 1) for _ in range(n + 1)]
    prev: list[list[tuple[int, int, str, float] | None]] = [
        [None] * (m + 1) for _ in range(n + 1)
    ]
    best[0][0] = 0.0

    for i in range(n + 1):
        for j in range(m + 1):
            if best[i][j] == neg_inf:
                continue
            for da, de in moves:
                ni, nj = i + da, j + de
                if ni > n or nj > m:
                    continue
                if da == 0 and de == 0:
                    continue
                if da and de:
                    score = score_span(arabic, i, ni, english, j, nj)
                    # Slight penalty for fatter spans so 1-1 wins when equal.
                    score -= 0.05 * (da + de - 2)
                    op = f"{da}-{de}"
                else:
                    score = -skip_cost
                    op = f"{da}-{de}"
                cand = best[i][j] + score
                if cand > best[ni][nj]:
                    best[ni][nj] = cand
                    prev[ni][nj] = (i, j, op, score)

    links: list[Link] = []
    i, j = n, m
    while (i, j) != (0, 0):
        step = prev[i][j]
        if step is None:
            raise ValueError(
                f"alignment moves cannot reach the terminal cell ({n}, {m})"
            )
        pi, pj, op, score = step
        da, de = i - pi, j - pj
        conf = max(0.12, min(0.97, 0.5 + score / 4.0))
        radius = 0 if conf >= 0.9 else (1 if conf >= 0.75 else 2)
        flags: list[str] = []
        if op in {"1-0", "0-1"}:
            flags.append("skip")
            radius = max(radius, 2)
        links.append(
            Link(
                arabic_start=pi,
                arabic_end=i,
                english_start=pj,
                english_end=j,
                operation=op,
                score=score,
                confidence=conf,
                uncertainty_radius=radius,
                flags=tuple(flags),
            )
        )
        i, j = pi, pj
    links.reverse()
    return links


def buffer_hit(gold_en: int, predicted: Link, *, window: int) -> bool:
    """Is gold English sentence index inside predicted span widened by window."""
    return predicted.english_start - window <= gold_en < predicted.english_end + window
