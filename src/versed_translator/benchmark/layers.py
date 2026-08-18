"""Three independent layers inside a locked spine unit.

Paragraphs are the edition's units (OpenITI ``# ``, English blank-line
blocks). Sentences are punctuation cuts. Chunks are the factory pack of
those sentences to a word budget. None of the three is a proxy for another.

Alignment is monotone name/keyword evidence, 1:1 or 1:N, never a page
number and never a guessed zip when counts differ. Unconfirmed spans stay
unpaired rather than smeared onto a neighbour.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from versed_translator.benchmark.spine_align import ArabicUnit, EnglishUnit, _mass
from versed_translator.harness.blocks import DEFAULT_MAX_BLOCK_WORDS, segment, sentences

_RUNNING_HEAD_RE = re.compile(
    r"^\s*\d*\s*the\s+maq[a-z]{3,8}\s+of\s+",
    re.IGNORECASE,
)
_WS_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class Span:
    index: int
    layer: str
    text: str
    parent_paragraph: int | None = None

    @property
    def word_count(self) -> int:
        return len(self.text.split())


@dataclass(frozen=True)
class LayeredUnit:
    spine_index: int
    title: str
    side: str
    paragraphs: tuple[Span, ...]
    sentences: tuple[Span, ...]
    chunks: tuple[Span, ...]


@dataclass(frozen=True)
class LayerPair:
    arabic: Span
    english: tuple[Span, ...]
    evidence_mass: int
    method: str


def english_paragraphs(lines: list[str]) -> list[str]:
    """Recover edition paragraphs from OCR lines. Running heads are dropped.

    Hyphenated line-wraps are joined. If the scan has no blank line, the
    whole body is one paragraph — sentences and chunks still split it.
    """
    cleaned: list[list[str]] = [[]]
    for raw in lines:
        line = raw.strip()
        if not line:
            if cleaned[-1]:
                cleaned.append([])
            continue
        if _RUNNING_HEAD_RE.match(line):
            continue
        current = cleaned[-1]
        if current and current[-1].endswith("-"):
            current[-1] = current[-1][:-1] + line
        else:
            current.append(line)
    return [_WS_RE.sub(" ", " ".join(block)).strip() for block in cleaned if block]


def attach_english_bodies(text: str, units: list[EnglishUnit]) -> list[EnglishUnit]:
    lines = text.splitlines()
    attached: list[EnglishUnit] = []
    for index, unit in enumerate(units):
        start = unit.line_no
        end = units[index + 1].line_no - 1 if index + 1 < len(units) else len(lines)
        paragraphs = english_paragraphs(lines[start:end])
        attached.append(replace(unit, body="\n\n".join(paragraphs)))
    return attached


def _spans(texts: list[str], layer: str, parents: list[int | None] | None = None) -> tuple[Span, ...]:
    return tuple(
        Span(index=i, layer=layer, text=text, parent_paragraph=None if parents is None else parents[i])
        for i, text in enumerate(texts, start=1)
        if text.strip()
    )


def _sentences_under_paragraphs(paragraphs: list[str]) -> tuple[Span, ...]:
    spans: list[Span] = []
    for para_index, paragraph in enumerate(paragraphs, start=1):
        for sent in sentences(paragraph):
            spans.append(
                Span(
                    index=len(spans) + 1,
                    layer="sentence",
                    text=sent,
                    parent_paragraph=para_index,
                )
            )
    return tuple(spans)


def _chunks_under_paragraphs(
    paragraphs: list[str], max_words: int
) -> tuple[Span, ...]:
    """Pack each paragraph on its own so a chunk never crosses a paragraph."""
    spans: list[Span] = []
    for para_index, paragraph in enumerate(paragraphs, start=1):
        for chunk in segment(paragraph, max_words=max_words):
            spans.append(
                Span(
                    index=len(spans) + 1,
                    layer="chunk",
                    text=chunk,
                    parent_paragraph=para_index,
                )
            )
    return tuple(spans)


def layer_arabic(
    unit: ArabicUnit, *, max_words: int = DEFAULT_MAX_BLOCK_WORDS
) -> LayeredUnit:
    paragraphs = [text for text in unit.paragraphs if text.strip()]
    return LayeredUnit(
        spine_index=unit.index,
        title=unit.title,
        side="arabic",
        paragraphs=_spans(paragraphs, "paragraph"),
        sentences=_sentences_under_paragraphs(paragraphs),
        chunks=_chunks_under_paragraphs(paragraphs, max_words),
    )


def layer_english(
    unit: EnglishUnit, *, max_words: int = DEFAULT_MAX_BLOCK_WORDS
) -> LayeredUnit:
    paragraphs = [block for block in unit.body.split("\n\n") if block.strip()]
    return LayeredUnit(
        spine_index=unit.index,
        title=unit.title,
        side="english",
        paragraphs=_spans(paragraphs, "paragraph"),
        sentences=_sentences_under_paragraphs(paragraphs),
        chunks=_chunks_under_paragraphs(paragraphs, max_words),
    )


def pair_layer(
    arabic: tuple[Span, ...],
    english: tuple[Span, ...],
    *,
    min_mass: int = 3,
) -> list[LayerPair]:
    """Greedy monotone 1:N. One Arabic span may take consecutive English
    spans that all hit it; English is never reordered. No hit, no pair.
    """
    pairs: list[LayerPair] = []
    en_cursor = 0
    for ar in arabic:
        rest = english[en_cursor:]
        if not rest:
            break
        if _mass(ar.text, " ".join(span.text for span in rest)) < min_mass:
            continue
        matched: list[Span] = []
        masses: list[int] = []
        while en_cursor < len(english):
            mass = _mass(ar.text, english[en_cursor].text)
            if mass < min_mass:
                if matched:
                    break
                en_cursor += 1
                continue
            matched.append(english[en_cursor])
            masses.append(mass)
            en_cursor += 1
        if matched:
            pairs.append(
                LayerPair(ar, tuple(matched), max(masses), "name_monotone")
            )
    return pairs


def layer_report(arabic: LayeredUnit, english: LayeredUnit) -> dict:
    para = pair_layer(arabic.paragraphs, english.paragraphs)
    sent = pair_layer(arabic.sentences, english.sentences)
    chunk = pair_layer(arabic.chunks, english.chunks)
    return {
        "spine_index": arabic.spine_index,
        "arabic": {
            "paragraphs": len(arabic.paragraphs),
            "sentences": len(arabic.sentences),
            "chunks": len(arabic.chunks),
        },
        "english": {
            "paragraphs": len(english.paragraphs),
            "sentences": len(english.sentences),
            "chunks": len(english.chunks),
        },
        "paired_paragraphs": len(para),
        "paired_sentences": len(sent),
        "paired_chunks": len(chunk),
        "sentence_1_to_n": sum(1 for pair in sent if len(pair.english) > 1),
        "layers_distinct": not (
            len(arabic.paragraphs) == len(arabic.sentences) == len(arabic.chunks)
            and len(english.paragraphs) == len(english.sentences) == len(english.chunks)
        ),
    }
