"""Sentence and span splitting. Keep paragraphs; sentences are extra."""

from __future__ import annotations

import re
from dataclasses import dataclass

_AR_SPLIT = re.compile(r"(?<=[.!?؟۔])\s+")
_AR_CLAUSE_SPLIT = re.compile(r"(?<=[،؛])\s+")
_AR_MAX_WORDS = 55
_EN_ABBREV = re.compile(
    r"\b(?:Mr|Mrs|Ms|Dr|St|No|vol|pp|cf|viz|i\.e|e\.g)\.$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Sentence:
    index: int
    text: str
    paragraph_index: int = -1

    @property
    def word_count(self) -> int:
        return len(self.text.split())


def split_arabic(text: str, *, paragraph_index: int = -1) -> list[Sentence]:
    terminal_parts = [p.strip() for p in _AR_SPLIT.split(text) if p.strip()]
    parts: list[str] = []
    for part in terminal_parts:
        if len(part.split()) <= _AR_MAX_WORDS:
            parts.append(part)
            continue
        clauses = [value.strip() for value in _AR_CLAUSE_SPLIT.split(part) if value.strip()]
        current: list[str] = []
        current_words = 0
        for clause in clauses:
            clause_words = len(clause.split())
            if current and current_words + clause_words > _AR_MAX_WORDS:
                parts.append(" ".join(current))
                current = []
                current_words = 0
            current.append(clause)
            current_words += clause_words
        if current:
            tail = " ".join(current)
            if parts and len(tail.split()) < 8:
                parts[-1] = f"{parts[-1]} {tail}"
            else:
                parts.append(tail)
    if not parts:
        stripped = text.strip()
        return [Sentence(0, stripped, paragraph_index)] if stripped else []
    return [Sentence(i, part, paragraph_index) for i, part in enumerate(parts)]


def split_english(text: str, *, paragraph_index: int = -1) -> list[Sentence]:
    """Split 18th/19th-c. prose without eating Mr./Dr. abbreviations."""
    stripped = text.strip()
    if not stripped:
        return []
    pieces: list[str] = []
    start = 0
    for match in re.finditer(r'[.!?]+["”’]*', stripped):
        end = match.end()
        chunk = stripped[start:end].strip()
        if not chunk:
            continue
        last = chunk.split()[-1]
        if _EN_ABBREV.search(last):
            continue
        nxt = stripped[end:].lstrip()
        if nxt and nxt[0] not in '"“‘' and not nxt[0].isupper():
            continue
        pieces.append(chunk)
        start = end
    tail = stripped[start:].strip()
    if tail:
        pieces.append(tail)
    if not pieces:
        pieces = [stripped]
    return [Sentence(i, part, paragraph_index) for i, part in enumerate(pieces)]


def split_paragraphs_arabic(paragraphs: list[str]) -> list[Sentence]:
    out: list[Sentence] = []
    for p_i, paragraph in enumerate(paragraphs):
        for sent in split_arabic(paragraph, paragraph_index=p_i):
            out.append(
                Sentence(len(out), sent.text, paragraph_index=p_i)
            )
    return out


def split_paragraphs_english(paragraphs: list[str]) -> list[Sentence]:
    out: list[Sentence] = []
    for p_i, paragraph in enumerate(paragraphs):
        for sent in split_english(paragraph, paragraph_index=p_i):
            out.append(Sentence(len(out), sent.text, paragraph_index=p_i))
    return out
