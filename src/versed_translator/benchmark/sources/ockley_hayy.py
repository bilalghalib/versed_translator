"""Sequence proposals for Ibn Tufayl's Hayy ibn Yaqzan and Ockley's 1708 text.

Ockley numbers the narrative in 120 sections. The OpenITI witness preserves
the same continuous narrative as finer Arabic paragraphs but carries no
corresponding numbers. A monotone length partition proposes which consecutive
Arabic paragraphs belong to each numbered English section. Because length is
not semantic evidence, every assembled passage requires content adjudication
before selection.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from versed_translator.benchmark.sources import monotone_length, openiti_markdown

WORK_ID = "0581IbnTufayl.HayyIbnYaqzan"
TRANSLATOR = "Simon Ockley"
ENGLISH_SOURCE = (
    "The History of Hayy Ibn Yaqzan, trans. Simon Ockley (London, 1708), "
    "Project Gutenberg ebook 16831"
)
RIGHTS_STATUS = "PD_US_PRE_1930_PUBLICATION"
RIGHTS_EVIDENCE = (
    "English: Ockley's 1708 translation, distributed by Project Gutenberg. "
    "Arabic: pre-modern text (author d. 581 AH) digitised by OpenITI. Neither "
    "claim is cleared legal advice; D6b still gates commercial use."
)

_SECTION_RE = re.compile(r"(?m)^§\.?\s*(?P<number>\d+)\.\s*")
_WS_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class EnglishSection:
    index: int
    printed_number: int
    text: str

    @property
    def word_count(self) -> int:
        return len(self.text.split())


@dataclass
class Passage:
    section_range: tuple[int, int]
    arabic_range: tuple[int, int]
    arabic: str
    english: str
    arabic_word_count: int
    english_word_count: int
    confidence: float = 0.55
    structural_confidence: float = 0.55
    method: str = "sequence_length_proposal"
    flags: list[str] = field(default_factory=lambda: ["llm_required"])
    llm_verdict: dict | None = None

    @property
    def native_id(self) -> str:
        start, end = self.section_range
        return f"sections-{start + 1:03d}_{end:03d}"

    @property
    def word_ratio(self) -> float:
        return self.english_word_count / self.arabic_word_count


@dataclass
class ExtractionReport:
    english_sections: list[EnglishSection]
    arabic_paragraphs: int
    passages: list[Passage]


def parse_english_sections(text: str) -> list[EnglishSection]:
    matches = list(_SECTION_RE.finditer(text))
    narrative: list[re.Match] = []
    for match in matches:
        number = int(match.group("number"))
        if narrative and number == 1:
            break
        if not narrative and number != 1:
            continue
        narrative.append(match)
        if number == 120:
            break

    sections: list[EnglishSection] = []
    for index, match in enumerate(narrative):
        if index + 1 < len(narrative):
            end = narrative[index + 1].start()
        else:
            finis = text.find("_FINIS_", match.end())
            end = finis if finis >= 0 else len(text)
        body = text[match.end():end]
        body = re.sub(r"\[(?:\d+|[A-Za-z]+)\]", " ", body)
        body = body.replace("_", "")
        body = _WS_RE.sub(" ", body).strip()
        sections.append(
            EnglishSection(
                index=index,
                printed_number=int(match.group("number")),
                text=body,
            )
        )
    return sections


def _arabic_narrative(path: str | Path) -> list[openiti_markdown.Paragraph]:
    text = openiti_markdown.read(path)
    section = next(section for section in text.sections if section.title == "حي بن يقظان")
    return section.paragraphs


def extract(
    arabic_path: str | Path,
    english_path: str | Path,
) -> tuple[openiti_markdown.OpenITIText, ExtractionReport]:
    metadata = openiti_markdown.read(arabic_path)
    arabic_paragraphs = _arabic_narrative(arabic_path)
    english = parse_english_sections(
        Path(english_path).read_text(encoding="utf-8", errors="replace")
    )
    ranges = monotone_length.partition(
        [section.word_count for section in english],
        [paragraph.word_count for paragraph in arabic_paragraphs],
        min_fragments=1,
        max_fragments=8,
    )

    passages: list[Passage] = []
    section_cursor = 0
    chunk_index = 0
    while section_cursor < len(english):
        target = 160 if chunk_index % 2 == 0 else 320
        section_end = section_cursor
        arabic_words = 0
        while section_end < len(english) and arabic_words < target:
            start_paragraph = ranges[section_cursor][0]
            end_paragraph = ranges[section_end][1]
            arabic_words = sum(
                paragraph.word_count
                for paragraph in arabic_paragraphs[start_paragraph:end_paragraph]
            )
            section_end += 1
        if arabic_words < 100:
            break
        start_paragraph = ranges[section_cursor][0]
        end_paragraph = ranges[section_end - 1][1]
        arabic = "\n\n".join(
            paragraph.text for paragraph in arabic_paragraphs[start_paragraph:end_paragraph]
        )
        english_text = "\n\n".join(
            section.text for section in english[section_cursor:section_end]
        )
        passages.append(
            Passage(
                section_range=(section_cursor, section_end),
                arabic_range=(start_paragraph, end_paragraph),
                arabic=arabic,
                english=english_text,
                arabic_word_count=len(arabic.split()),
                english_word_count=len(english_text.split()),
            )
        )
        section_cursor = section_end
        chunk_index += 1

    return metadata, ExtractionReport(
        english_sections=english,
        arabic_paragraphs=len(arabic_paragraphs),
        passages=passages,
    )


__all__ = [
    "ENGLISH_SOURCE",
    "RIGHTS_EVIDENCE",
    "RIGHTS_STATUS",
    "TRANSLATOR",
    "WORK_ID",
    "EnglishSection",
    "ExtractionReport",
    "Passage",
    "extract",
    "parse_english_sections",
]
