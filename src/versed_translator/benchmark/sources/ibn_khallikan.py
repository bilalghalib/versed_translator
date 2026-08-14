"""Per-work alignment for Ibn Khallikan's biographical dictionary.

The Arabic edition marks every biography with an OpenITI ``$BIO_*`` heading.
De Slane's four-volume translation prints the same biographies under
standalone romanised headings and in the same order.  Heading names therefore
provide bilateral structural evidence without translating either side or
assuming that similarly sized passages correspond.

Only complete biographies between two matched headings are emitted.  Entries
outside the benchmark's 100--600 Arabic-word bands remain visible in the
extraction report but are not cut internally: unlike Baladhuri's isnads, these
biographies do not provide a second trustworthy anchor inside an entry.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from versed_translator.benchmark.sources import openiti_markdown
from versed_translator.benchmark.sources.translit import NameEvidence, name_evidence

WORK_ID = "0681IbnKhallikan.WafayatAcyan"
TRANSLATOR = "William Mac Guckin de Slane"
ENGLISH_SOURCE = (
    "Ibn Khallikan's Biographical Dictionary, trans. William Mac Guckin "
    "de Slane, 4 vols. (Paris, 1842-1871)"
)
RIGHTS_STATUS = "PD_US_PRE_1930_PUBLICATION"
RIGHTS_EVIDENCE = (
    "English: de Slane, published 1842-1871 and marked NOT_IN_COPYRIGHT by "
    "Internet Archive. Arabic: pre-modern text (author d. 681 AH) digitised "
    "by OpenITI. Neither claim is cleared legal advice; D6b still gates "
    "commercial use."
)

_BIO_RE = re.compile(
    r"^###\s+\$(?P<kind>BIO_[A-Z_]+)\$\s+"
    r"(?:ms\d+\s+)?\[?(?P<number>\d+)(?:ب)?(?:\s+ms\d+)?\s*"
    r"(?:-\]?|\]\s*-)\s*(?P<title>.*)$"
)
_PARAGRAPH_RE = re.compile(r"^#\s+(?P<text>.*)$")
_CONTINUATION_RE = re.compile(r"^~~(?P<text>.*)$")
_PAGE_RE = re.compile(r"PageV\d+P\d+")
_MILESTONE_RE = re.compile(r"\bms\d+\b")
_WS_RE = re.compile(r"\s+")

_ENGLISH_NOISE = re.compile(
    r"^(?:\d+\s+)?(?:IBN\s+KH[A-Z'’ .-]+|BIOGRAPHICAL\s+DICTIONAR[A-Z .-]*|"
    r"VOL\.?\s+[IVX0-9. -]+|DIGITIZED\s+BY\s+GOOGLE|THE\s+AUTHOR'?S?\s+PREFACE)$",
    re.IGNORECASE,
)
_FOOTNOTE_START = re.compile(r"^\s*[\[(]\s*(?:\d+|[A-Z])\s*[\])]\s+")


def _clean_arabic(text: str) -> str:
    text = _PAGE_RE.sub(" ", text)
    text = _MILESTONE_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


@dataclass(frozen=True)
class ArabicEntry:
    index: int
    number: int
    kind: str
    title: str
    paragraphs: tuple[str, ...]

    @property
    def text(self) -> str:
        return "\n\n".join(self.paragraphs)

    @property
    def word_count(self) -> int:
        return len(self.text.split())


@dataclass(frozen=True)
class EnglishHeading:
    volume: int
    candidate_index: int
    start: int
    end: int
    title: str


@dataclass(frozen=True)
class EntryMatch:
    arabic_index: int
    heading: EnglishHeading
    evidence: NameEvidence

    @property
    def confidence(self) -> float:
        mass_factor = 1.0 if self.evidence.mass >= 8 else 0.9
        return round(self.evidence.score * mass_factor, 3)


@dataclass
class Passage:
    entry_index: int
    entry_number: int
    volume: int
    arabic: str
    english: str
    arabic_word_count: int
    english_word_count: int
    confidence: float
    structural_confidence: float
    anchors_open: tuple[str, ...]
    flags: list[str] = field(default_factory=list)
    method: str = "structural_entry"
    llm_verdict: dict | None = None

    @property
    def native_id(self) -> str:
        # Some edition headings are numbered 107/107b. The source index keeps
        # those supplements distinct without inventing a new printed number.
        return f"v{self.volume}-bio-{self.entry_number:04d}-i{self.entry_index:04d}"

    @property
    def word_ratio(self) -> float:
        return self.english_word_count / self.arabic_word_count


@dataclass
class ExtractionReport:
    arabic_entries: int
    english_heading_candidates: int
    entries_matched: int
    passages: list[Passage]
    matches: list[EntryMatch]
    unmatched_arabic_entries: int


def parse_arabic_entries(text: str) -> list[ArabicEntry]:
    entries: list[ArabicEntry] = []
    current: dict | None = None
    paragraphs: list[str] = []
    pending: list[str] = []

    def flush_paragraph() -> None:
        nonlocal pending
        cleaned = _clean_arabic(" ".join(pending))
        if cleaned:
            paragraphs.append(cleaned)
        pending = []

    def flush_entry() -> None:
        nonlocal current, paragraphs
        if current is None:
            return
        flush_paragraph()
        entries.append(
            ArabicEntry(
                index=len(entries),
                number=current["number"],
                kind=current["kind"],
                title=current["title"],
                paragraphs=tuple(paragraphs),
            )
        )
        current = None
        paragraphs = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        match = _BIO_RE.match(line)
        if match:
            flush_entry()
            current = {
                "number": int(match.group("number")),
                "kind": match.group("kind"),
                "title": _clean_arabic(match.group("title")),
            }
            continue
        if current is None:
            continue
        paragraph = _PARAGRAPH_RE.match(line)
        if paragraph:
            flush_paragraph()
            pending = [paragraph.group("text")]
            continue
        continuation = _CONTINUATION_RE.match(line)
        if continuation and pending:
            pending.append(continuation.group("text"))
    flush_entry()
    return entries


def _looks_like_heading(line: str) -> bool:
    title = _WS_RE.sub(" ", line).strip(" .")
    letters = [char for char in title if char.isalpha()]
    if not 4 <= len(title) <= 90 or len(letters) < 4:
        return False
    if any(char.islower() for char in letters):
        return False
    if _ENGLISH_NOISE.match(title) or title in {"PARIS", "LONDON", "INTRODUCTION"}:
        return False
    return 1 <= len(title.split()) <= 12


def parse_english_headings(text: str, volume: int) -> list[EnglishHeading]:
    headings: list[EnglishHeading] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        title = _WS_RE.sub(" ", line).strip(" .\n\r")
        if _looks_like_heading(title):
            headings.append(
                EnglishHeading(
                    volume=volume,
                    candidate_index=len(headings),
                    start=offset,
                    end=offset + len(line),
                    title=title,
                )
            )
        offset += len(line)
    return headings


def match_entries(
    arabic_entries: list[ArabicEntry],
    english_by_volume: list[tuple[int, str]],
    lookahead: int = 80,
) -> list[EntryMatch]:
    """Greedily match heading names while preserving the book's order.

    The search window prevents a generic name such as ``IBN SAAD`` from
    jumping hundreds of entries. Unmatched OCR headings are skipped; Arabic
    entries can be skipped only within the bounded lookahead.
    """
    matches: list[EntryMatch] = []
    arabic_cursor = 0
    for volume, text in english_by_volume:
        for heading in parse_english_headings(text, volume):
            best: tuple[tuple[int, float, int], int, NameEvidence] | None = None
            stop = min(len(arabic_entries), arabic_cursor + lookahead)
            for index in range(arabic_cursor, stop):
                evidence = name_evidence(heading.title, arabic_entries[index].title)
                # A single shared token from a multi-token heading (usually
                # Ibrahim, Muhammad, or a nisba) is cheap enough to create a
                # plausible but shifted match. Accept one-token headings only
                # when that token matches exactly; otherwise demand that most
                # of the printed heading survives the OCR and transliteration.
                if (
                    evidence.strong_matches < 1
                    or evidence.mass < 4
                    or evidence.score < 0.75
                ):
                    continue
                rank = (evidence.mass, evidence.score, -index)
                if best is None or rank > best[0]:
                    best = (rank, index, evidence)
            if best is None:
                continue
            _, index, evidence = best
            matches.append(EntryMatch(index, heading, evidence))
            arabic_cursor = index + 1
    return matches


def _clean_english_body(text: str) -> str:
    blocks: list[str] = []
    for block in re.split(r"\n\s*\n", text):
        lines = []
        for raw_line in block.splitlines():
            line = _WS_RE.sub(" ", raw_line).strip()
            if not line or _ENGLISH_NOISE.match(line):
                continue
            if re.fullmatch(r"[/0-9 .-]+", line):
                continue
            lines.append(line)
        cleaned = " ".join(lines).strip()
        if not cleaned or _FOOTNOTE_START.match(cleaned):
            continue
        blocks.append(cleaned)
    return "\n\n".join(blocks)


def extract(
    arabic_path: str | Path,
    english_paths: list[str | Path],
    min_words: int = 100,
    max_words: int = 600,
) -> tuple[openiti_markdown.OpenITIText, ExtractionReport]:
    arabic_path = Path(arabic_path)
    raw_arabic = arabic_path.read_text(encoding="utf-8", errors="replace")
    metadata = openiti_markdown.parse(raw_arabic, uri=arabic_path.stem)
    arabic_entries = parse_arabic_entries(raw_arabic)
    english_by_volume = [
        (volume, Path(path).read_text(encoding="utf-8", errors="replace"))
        for volume, path in enumerate(english_paths, start=1)
    ]
    matches = match_entries(arabic_entries, english_by_volume)

    passages: list[Passage] = []
    for position, match in enumerate(matches):
        entry = arabic_entries[match.arabic_index]
        if not min_words <= entry.word_count <= max_words:
            continue
        volume_text = english_by_volume[match.heading.volume - 1][1]
        next_start = len(volume_text)
        if position + 1 < len(matches):
            following = matches[position + 1]
            if following.heading.volume == match.heading.volume:
                next_start = following.heading.start
        english = _clean_english_body(volume_text[match.heading.end:next_start])
        english_words = len(english.split())
        if not english_words:
            continue
        ratio = english_words / entry.word_count
        flags: list[str] = []
        confidence = match.confidence
        if not 0.65 <= ratio <= 2.8:
            flags.append(f"word_ratio_out_of_band:{ratio:.2f}")
            confidence = round(confidence * 0.7, 3)
        if re.search(r"[؀-ۿ]", english):
            flags.append("arabic_chars_in_english_side")
        passages.append(
            Passage(
                entry_index=entry.index,
                entry_number=entry.number,
                volume=match.heading.volume,
                arabic=entry.text,
                english=english,
                arabic_word_count=entry.word_count,
                english_word_count=english_words,
                confidence=confidence,
                structural_confidence=match.confidence,
                anchors_open=match.evidence.matched,
                flags=flags,
            )
        )

    report = ExtractionReport(
        arabic_entries=len(arabic_entries),
        english_heading_candidates=sum(
            len(parse_english_headings(text, volume))
            for volume, text in english_by_volume
        ),
        entries_matched=len(matches),
        passages=passages,
        matches=matches,
        unmatched_arabic_entries=len(arabic_entries) - len(matches),
    )
    return metadata, report


__all__ = [
    "ENGLISH_SOURCE",
    "RIGHTS_EVIDENCE",
    "RIGHTS_STATUS",
    "TRANSLATOR",
    "WORK_ID",
    "ArabicEntry",
    "EnglishHeading",
    "EntryMatch",
    "ExtractionReport",
    "Passage",
    "extract",
    "match_entries",
    "parse_arabic_entries",
    "parse_english_headings",
]
