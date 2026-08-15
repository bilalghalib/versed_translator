"""OCR cleanup + structure detection for *The Eclipse of the 'Abbasid
Caliphate* (Oxford: Basil Blackwell, 1921), archive.org
``eclipseofabbasid04ameduoft`` / ``eclipseofabbasid05ameduoft``.

Volumes IV and V of the seven-volume set are volumes I and II of Margoliouth's
English translation of Miskawayh's *Tajarib al-Umam* for AH 295-369. (Volume VI
is Abu Shuja' al-Rudhrawari's continuation -- a different work by a different
author, and deliberately not handled here.)

Like `hitti_ocr`, this is per-edition logic and only ever validated against
these two scans. What this edition carries:

- **Two alternating running heads.** Verso pages read
  ``48  A.H.  304.     Caliphate  of  Muqtadir.`` -- printed page number first,
  then the hijri year of the events on that page. Recto pages read
  ``Second  Vizierate  of  Ibn  al-Furat.  49`` -- section title, page number
  last. Both are single blank-line-delimited lines.
- **The verso head is evidence, not just noise.** Its ``A.H. NNN`` is the
  translator's own statement of which year the page belongs to, and Miskawayh's
  Arabic is itself organised by year. That makes it the alignment anchor, so it
  is parsed before it is stripped.
- **Margoliouth prints the Arabic edition's pagination inline** as ``(43)``,
  fused into the running text. Those are kept in place through cleaning and
  extracted afterwards; they are the finest-grained ordered checkpoints the
  pair has.
- **Footnotes** sit at the page foot as short blocks led by ``^`` (the OCR's
  rendering of the reference mark) or by a numeral.
- Marginal bleed-through drops stray single characters (``^``, ``L``, ``j``)
  at line ends.
- Words hyphenate across line breaks, colliding with real chain hyphens --
  handled by reusing `hitti_ocr.dehyphenate`.

Nothing is dropped that a rule did not positively classify.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from versed_translator.benchmark.sources.hitti_ocr import dehyphenate

# Verso head: printed page number, "A.H. NNN", then the section title.
_VERSO_HEAD_RE = re.compile(
    r"^\s*(?P<page>\d{1,3})\s+A\.?\s*H\.?\s*(?P<year>\d{3})\s*\.?\s*(?P<title>.*?)\s*$"
)
# Recto head: section title, then the printed page number. Constrained hard --
# a body line ending in a number ("...45,000 dinars every lunar month, 12")
# must not match, so the line has to be short, title-shaped and unpunctuated.
_RECTO_HEAD_RE = re.compile(
    r"^\s*(?P<title>[A-Z][A-Za-z'’ʻʿ .,&/âîû-]{3,58}?)"
    r"\s{1,}(?P<page>\d{1,3})\s*$"
)
_RECTO_MAX_WORDS = 10

# Footnote openers as this scan renders them. The caret is the OCR's usual
# reading of the reference mark; numerals appear where the mark survived.
_FOOTNOTE_START_RE = re.compile(r"^\s*(?:[\^*†§]\s*|\d{1,2}[.\s]\s*)(?=[A-Z\"'(\[])")
_FOOTNOTE_MAX_LINES = 6
_FOOTNOTE_MAX_WORDS = 90
_CITATION_HINT_RE = re.compile(
    r"\bvol\.|\bpp?\.|\bibid|\bcf\.|\bop\.\s*cit|\bi\.?e\.|\btext\b|\bMS+\b|\bArabic\b"
    r"|\bQur|\bKoran|\bYaqut|\bYakut|\breading\b|\bomit|\bliterally\b",
    re.IGNORECASE,
)

# Single stray characters left at a line end by marginal bleed-through.
_MARGIN_JUNK_RE = re.compile(r"\s+[\^`|LljJ‘’'\"&]\s*$")
_ARABIC_PAGE_RE = re.compile(r"\((\d{1,4})\)")
_WS_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class RunningHead:
    """One printed page head, with whatever it states about the page."""

    line_no: int
    printed_page: int
    ah_year: int | None
    title: str


@dataclass
class EnglishParagraph:
    index: int
    text: str
    ah_year: int | None
    """Hijri year from the nearest preceding verso running head."""
    printed_page: int | None
    """Printed page of the volume the paragraph starts on."""
    section_title: str
    """Nearest preceding running-head title, e.g. "Vizierate of Ibn al-Furat"."""

    @property
    def word_count(self) -> int:
        return len(self.text.split())

    @property
    def arabic_pages(self) -> list[int]:
        """Amedroz Arabic-edition page numbers Margoliouth prints inline."""
        return [int(m.group(1)) for m in _ARABIC_PAGE_RE.finditer(self.text)]


def strip_arabic_page_markers(text: str) -> str:
    """Remove the inline ``(43)`` Arabic-edition pagination from a passage.

    Kept through parsing because it is the alignment evidence; removed before
    the text becomes a reference translation, since the Arabic side has no
    counterpart to it and a model would be penalised for not inventing one.
    """
    return _WS_RE.sub(" ", _ARABIC_PAGE_RE.sub(" ", text)).strip()


def parse_running_head(line: str) -> RunningHead | None:
    """Classify a line as a verso or recto running head, or not a head."""
    verso = _VERSO_HEAD_RE.match(line.rstrip())
    if verso:
        title = re.sub(r"\s+", " ", verso.group("title")).strip(" .")
        return RunningHead(
            line_no=-1,
            printed_page=int(verso.group("page")),
            ah_year=int(verso.group("year")),
            title=title,
        )
    stripped = line.rstrip()
    if len(stripped.split()) > _RECTO_MAX_WORDS:
        return None
    recto = _RECTO_HEAD_RE.match(stripped)
    if recto:
        title = re.sub(r"\s+", " ", recto.group("title")).strip(" .")
        # A one-word "title" is far more likely a body fragment than a head.
        if len(title.split()) < 2:
            return None
        return RunningHead(
            line_no=-1,
            printed_page=int(recto.group("page")),
            ah_year=None,
            title=title,
        )
    return None


def _looks_like_footnote(block: list[str]) -> bool:
    if not block or len(block) > _FOOTNOTE_MAX_LINES:
        return False
    if not _FOOTNOTE_START_RE.match(block[0]):
        return False
    joined = " ".join(block)
    if len(joined.split()) > _FOOTNOTE_MAX_WORDS:
        return False
    return bool(_CITATION_HINT_RE.search(joined)) or len(joined.split()) <= 30


def _blocks(lines: list[str]) -> list[list[str]]:
    out: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if line.strip():
            current.append(line)
        elif current:
            out.append(current)
            current = []
    if current:
        out.append(current)
    return out


def _join_blocks(blocks: list[tuple[str, RunningHead | None]]) -> list[tuple[str, RunningHead | None]]:
    """Rejoin paragraph fragments split by a page break.

    A fragment continues the previous one when the previous does not end in
    terminal punctuation, or the fragment opens lowercase. The running-head
    state of the *first* fragment is kept: a paragraph belongs to the page it
    started on.
    """
    merged: list[tuple[str, RunningHead | None]] = []
    for text, head in blocks:
        if merged:
            prev, prev_head = merged[-1]
            prev = prev.rstrip()
            starts_lower = bool(text[:1]) and text[0].islower()
            unterminated = not re.search(r"[.!?][\"'”’)\]]?$", prev)
            if starts_lower or unterminated:
                merged[-1] = (f"{prev} {text.lstrip()}", prev_head)
                continue
        merged.append((text, head))
    return merged


def parse_paragraphs(text: str) -> tuple[list[EnglishParagraph], list[RunningHead]]:
    """Clean a whole volume into paragraphs carrying their page/year state."""
    lines = text.split("\n")
    heads: list[RunningHead] = []
    tagged: list[tuple[str, bool, RunningHead | None]] = []
    for line_no, raw in enumerate(lines, start=1):
        head = parse_running_head(raw)
        if head is not None:
            head = RunningHead(
                line_no=line_no,
                printed_page=head.printed_page,
                ah_year=head.ah_year,
                title=head.title,
            )
            heads.append(head)
            tagged.append(("", True, head))
            continue
        tagged.append((_MARGIN_JUNK_RE.sub("", raw), False, None))

    # Walk the tagged lines into blank-line-delimited blocks, remembering the
    # running-head state in force when each block opened.
    blocks: list[tuple[list[str], int | None, int | None, str]] = []
    current: list[str] = []
    year: int | None = None
    page: int | None = None
    title = ""
    opened: tuple[int | None, int | None, str] = (None, None, "")
    for line, is_head, head in tagged:
        if is_head and head is not None:
            if head.ah_year is not None:
                year = head.ah_year
            if head.title:
                title = head.title
            page = head.printed_page
            if current:
                blocks.append((current, *opened))
                current = []
            continue
        if line.strip():
            if not current:
                opened = (year, page, title)
            current.append(line)
        elif current:
            blocks.append((current, *opened))
            current = []
    if current:
        blocks.append((current, *opened))

    body: list[tuple[str, tuple[int | None, int | None, str]]] = []
    for block, blk_year, blk_page, blk_title in blocks:
        if _looks_like_footnote(block):
            continue
        joined = _WS_RE.sub(" ", " ".join(block)).strip()
        if joined:
            body.append((joined, (blk_year, blk_page, blk_title)))

    merged = _join_blocks([(t, RunningHead(-1, s[1] or 0, s[0], s[2])) for t, s in body])
    paragraphs = [
        EnglishParagraph(
            index=index,
            text=dehyphenate(text_),
            ah_year=head.ah_year if head else None,
            printed_page=head.printed_page if head else None,
            section_title=head.title if head else "",
        )
        for index, (text_, head) in enumerate(merged)
    ]
    return paragraphs, heads


@dataclass
class YearBlock:
    """The run of English paragraphs the running heads assign to one AH year."""

    ah_year: int
    paragraphs: list[EnglishParagraph] = field(default_factory=list)

    @property
    def word_count(self) -> int:
        return sum(p.word_count for p in self.paragraphs)

    @property
    def arabic_pages(self) -> list[int]:
        out: list[int] = []
        for paragraph in self.paragraphs:
            out.extend(paragraph.arabic_pages)
        return out


def year_blocks(paragraphs: list[EnglishParagraph]) -> list[YearBlock]:
    """Group paragraphs into maximal runs sharing one AH year.

    Runs are merged when the same year recurs later in the volume (the running
    head can flip back and forth across a page turn), so each year appears at
    most once and in first-appearance order.
    """
    order: list[int] = []
    grouped: dict[int, YearBlock] = {}
    for paragraph in paragraphs:
        if paragraph.ah_year is None:
            continue
        block = grouped.get(paragraph.ah_year)
        if block is None:
            block = YearBlock(ah_year=paragraph.ah_year)
            grouped[paragraph.ah_year] = block
            order.append(paragraph.ah_year)
        block.paragraphs.append(paragraph)
    return [grouped[year] for year in order]


__all__ = [
    "EnglishParagraph",
    "RunningHead",
    "YearBlock",
    "parse_paragraphs",
    "parse_running_head",
    "strip_arabic_page_markers",
    "year_blocks",
]
