"""Sequence proposals for the seven Muallaqat translated by W. S. Blunt.

The OpenITI witness is al-Zawzani's commentary. Each numbered section opens
with one Arabic verse and then commentary, so only that first paragraph is
used. Blunt prints the same seven odes as verse blocks, but the OCR splits a
couplet into one or two fragments at page boundaries. A monotone length
partition reconnects those fragments to the fixed Arabic verse sequence.

Length partitioning proposes boundaries; it is not alignment evidence.
Every emitted passage is therefore marked ``llm_required`` and must receive
an aligned content verdict before it can be selected.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from versed_translator.benchmark.sources import monotone_length, openiti_markdown

WORK_ID = "0486IbnAhmadZuzani.SharhMucallaqat"
TRANSLATOR = "Lady Anne Blunt and Wilfrid Scawen Blunt"
ENGLISH_SOURCE = (
    "The Seven Golden Odes of Pagan Arabia, in The Poetical Works of "
    "Wilfrid Scawen Blunt, vol. 2 (London, 1903)"
)
RIGHTS_STATUS = "PD_US_PRE_1930_PUBLICATION"
RIGHTS_EVIDENCE = (
    "English: first published 1903; Internet Archive scan of Blunt's Poetical "
    "Works vol. 2. Arabic: pre-modern poems in an OpenITI digitisation of "
    "al-Zawzani's commentary. Neither claim is cleared legal advice; D6b "
    "still gates commercial use."
)

_NUMBERED_SECTION = re.compile(r"^\d+\s*-\s*$")
_ENGLISH_HEADINGS = {
    "imr": r"IMR\s+EL\s+KAIS",
    "tarafa": r"TARAFA",
    "zuhayr": r"ZOH\^YR",
    "labid": r"LEBID",
    "antara": r"ANTAEA",
    "amr": r"IBN\s+KOLTHUM",
    "harith": r"EL\s+HARITH",
}
_ARABIC_TITLES = {
    "imr": "معلقة امرئ القيس",
    "tarafa": "معلقة طرفة بن العبد",
    "zuhayr": "معلقة زهير",
    "labid": "معلقة لبيد بن ربيعة",
    "amr": "معلقة عمرو بن كلثوم",
    "antara": "معلقة عنترة بن شداد",
    "harith": "معلقة الحارث بن حلزة",
}
_DISPLAY_NAMES = {
    "imr": "Imru al-Qays",
    "tarafa": "Tarafa",
    "zuhayr": "Zuhayr",
    "labid": "Labid",
    "amr": "Amr ibn Kulthum",
    "antara": "Antara",
    "harith": "al-Harith ibn Hilliza",
}


@dataclass(frozen=True)
class Poem:
    key: str
    name: str
    arabic_verses: tuple[str, ...]
    english_verses: tuple[str, ...]


@dataclass
class Passage:
    poem_key: str
    poem_name: str
    verse_range: tuple[int, int]
    arabic: str
    english: str
    arabic_word_count: int
    english_word_count: int
    confidence: float = 0.6
    structural_confidence: float = 0.6
    method: str = "sequence_length_proposal"
    flags: list[str] = field(default_factory=lambda: ["llm_required"])
    llm_verdict: dict | None = None

    @property
    def native_id(self) -> str:
        start, end = self.verse_range
        return f"{self.poem_key}-v{start + 1:03d}_{end:03d}"

    @property
    def word_ratio(self) -> float:
        return self.english_word_count / self.arabic_word_count


@dataclass
class ExtractionReport:
    poems: list[Poem]
    passages: list[Passage]


def parse_arabic_poems(path: str | Path) -> dict[str, list[str]]:
    text = openiti_markdown.read(path)
    result: dict[str, list[str]] = {}
    for key, title in _ARABIC_TITLES.items():
        starts = [
            index
            for index, section in enumerate(text.sections)
            if section.title == title
        ]
        if not starts:
            continue
        verses: list[str] = []
        for section in text.sections[starts[-1] + 1 :]:
            if _NUMBERED_SECTION.match(section.title) and section.paragraphs:
                verses.append(section.paragraphs[0].text)
            elif verses:
                break
        result[key] = verses
    return result


def _english_regions(text: str) -> dict[str, str]:
    starts: list[tuple[int, int, str]] = []
    search_start = min(len(text), 80_000)
    search_end = text.find("THE  STEALING  OF  THE  MAKE", search_start)
    if search_end < 0:
        search_end = len(text)
    searchable = text[search_start:search_end]
    for key, pattern in _ENGLISH_HEADINGS.items():
        match = re.search(rf"(?m)^\s*{pattern}\s*\.?\s*$", searchable, re.IGNORECASE)
        if match:
            starts.append(
                (search_start + match.start(), search_start + match.end(), key)
            )
    starts.sort()
    regions: dict[str, str] = {}
    for index, (_start, content_start, key) in enumerate(starts):
        end = starts[index + 1][0] if index + 1 < len(starts) else search_end
        regions[key] = text[content_start:end]
    return regions


def _english_fragments(region: str) -> list[str]:
    fragments: list[str] = []
    heading_words = re.compile(
        r"GOLDEN ODES|VOL\.|^(?:IMR|TARAFA|ZOH|LEBID|ANTAEA|ANTARA|"
        r"IBN KOLTHUM|EL H[AI]RITH)",
        re.IGNORECASE,
    )
    for block in re.split(r"\n\s*\n", region):
        cleaned = " ".join(line.strip() for line in block.splitlines() if line.strip())
        letters = [character for character in cleaned if character.isalpha()]
        if len(cleaned.split()) < 4 or not letters:
            continue
        if not any(character.islower() for character in letters):
            continue
        if heading_words.search(cleaned):
            continue
        fragments.append(cleaned)
    return fragments


def parse_poems(arabic_path: str | Path, english_path: str | Path) -> list[Poem]:
    arabic = parse_arabic_poems(arabic_path)
    english_text = Path(english_path).read_text(encoding="utf-8", errors="replace")
    regions = _english_regions(english_text)
    poems: list[Poem] = []
    for key in _ARABIC_TITLES:
        arabic_verses = arabic.get(key, [])
        fragments = _english_fragments(regions.get(key, ""))
        if not arabic_verses or not fragments:
            continue
        ranges = monotone_length.partition(
            [len(verse.split()) for verse in arabic_verses],
            [len(fragment.split()) for fragment in fragments],
            min_fragments=1,
            max_fragments=3,
        )
        english_verses = [" ".join(fragments[start:end]) for start, end in ranges]
        poems.append(
            Poem(
                key=key,
                name=_DISPLAY_NAMES[key],
                arabic_verses=tuple(arabic_verses),
                english_verses=tuple(english_verses),
            )
        )
    return poems


def assemble_passages(poems: list[Poem]) -> list[Passage]:
    passages: list[Passage] = []
    for poem_index, poem in enumerate(poems):
        cursor = 0
        chunk_index = 0
        while cursor < len(poem.arabic_verses):
            target = 160 if (poem_index + chunk_index) % 2 == 0 else 320
            end = cursor
            words = 0
            while end < len(poem.arabic_verses) and words < target:
                words += len(poem.arabic_verses[end].split())
                end += 1
            if words < 100:
                break
            arabic = "\n".join(poem.arabic_verses[cursor:end])
            english = "\n".join(poem.english_verses[cursor:end])
            passages.append(
                Passage(
                    poem_key=poem.key,
                    poem_name=poem.name,
                    verse_range=(cursor, end),
                    arabic=arabic,
                    english=english,
                    arabic_word_count=len(arabic.split()),
                    english_word_count=len(english.split()),
                )
            )
            cursor = end
            chunk_index += 1
    return passages


def extract(
    arabic_path: str | Path,
    english_path: str | Path,
) -> tuple[openiti_markdown.OpenITIText, ExtractionReport]:
    metadata = openiti_markdown.read(arabic_path)
    poems = parse_poems(arabic_path, english_path)
    return metadata, ExtractionReport(poems=poems, passages=assemble_passages(poems))


__all__ = [
    "ENGLISH_SOURCE",
    "RIGHTS_EVIDENCE",
    "RIGHTS_STATUS",
    "TRANSLATOR",
    "WORK_ID",
    "ExtractionReport",
    "Passage",
    "Poem",
    "assemble_passages",
    "extract",
    "parse_arabic_poems",
    "parse_poems",
]
