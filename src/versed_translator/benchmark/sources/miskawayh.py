"""Year-anchored proposals for Miskawayh's *Tajarib al-Umam* against
Margoliouth's English in *The Eclipse of the 'Abbasid Caliphate* (1921).

The anchor here is the **hijri year**, and it is a real one rather than a
length heuristic: Miskawayh organises the annalistic portion of the *Tajarib*
under headings of the form ``ودخلت سنة خمس وتسعين ومائتين``, and Margoliouth's
edition prints ``A.H. 295`` in the verso running head of every page. Both sides
independently state which year the text belongs to, so a year block is an
anchor-to-anchor unit on both sides at once.

What is *not* evidence is where a passage begins and ends **inside** a year, nor
is the year anchor exact: the verso running head belongs to a *page*, and a year
that starts halfway down a page is headed with the previous year until the page
turns. Measured on this edition that lag runs to a couple of paragraphs, which
is enough to wreck a 300-word passage while leaving it looking plausible.

So the year gives the coarse anchor and **transliterated proper names give the
fine one**: every boundary, including the year's own opening, is searched within
a window for the English cut that best accounts for the names in the facing
Arabic (`translit.name_evidence`). Names are shared evidence; cumulative word
counts are not. Even after that, boundaries remain proposals -- every passage
carries ``llm_required`` and is adjudicated for content before selection.

Two facts constrain how far the year anchor can be trusted, and both are
checked rather than assumed:

- The English is Margoliouth & Amedroz's edition; the OpenITI witness is
  Shamela 0012396, a **six-volume edition with different pagination**
  (``PageV01P047``..``PageV06P467``). The Arabic page numbers Margoliouth
  prints inline as ``(43)`` therefore do *not* address the OpenITI text. They
  are still extracted, because within one English passage they must form an
  increasing run -- a free contiguity check on the English side.
- Year headings can be missed on either side (the Arabic phrasing varies, and
  a running head can lag a page). A missed heading silently merges two years,
  which shows up as a wrong English:Arabic word ratio for that year. Years
  whose ratio departs from the work-level ratio by more than
  `RATIO_TOLERANCE` are dropped and reported, not quietly used.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from versed_translator.benchmark.sources import eclipse_ocr, openiti_markdown, translit

WORK_ID = "0421Miskawayh.Tajarib"
TRANSLATOR = "D. S. Margoliouth and H. F. Amedroz"
ENGLISH_SOURCE = (
    "The Eclipse of the 'Abbasid Caliphate, ed. and trans. H. F. Amedroz and "
    "D. S. Margoliouth, vols IV-V (Oxford: Basil Blackwell, 1921); archive.org "
    "eclipseofabbasid04ameduoft, eclipseofabbasid05ameduoft"
)
RIGHTS_STATUS = "PD_US_PRE_1930_PUBLICATION"
RIGHTS_EVIDENCE = (
    "English: Margoliouth & Amedroz, Basil Blackwell, Oxford, 1921 -- title "
    "page read inside both scans; published pre-1930, so US public domain by "
    "publication date. Arabic: pre-modern text (author d. 421 AH) digitised by "
    "OpenITI from Shamela 0012396. Neither claim is cleared legal advice; D6b "
    "still gates commercial use."
)

# Miskawayh's annalistic years, as the English volumes cover them. Volume VI of
# the set is Rudhrawari's continuation (AH 370-393) -- a different author's
# work, and out of scope for this slice.
FIRST_YEAR = 295
LAST_YEAR = 369

# A year whose English:Arabic word ratio is this far off the work-level ratio
# is evidence that a year heading was missed on one side, so the year is not
# used. 0.35 keeps the tight cluster (most years land within 1.4-2.1 against a
# work ratio near 1.68) and rejects the merged-year cases, which land near 0.9.
RATIO_TOLERANCE = 0.35

# How far either side of the length-proportional guess a boundary is searched
# for a better name-anchor fit. Wide enough to absorb the running head's page
# lag, narrow enough that the search cannot walk off into a different khabar.
ANCHOR_WINDOW = 4
# Skeletons this short match a long Arabic slice by chance; `translit` makes
# the same cut for the same reason.
STRONG_SKELETON = translit.NameEvidence.STRONG_MIN_LEN

_ARABIC_YEAR_HEADING_RE = re.compile(r"دخلت\s+سنة")
_ARABIC_TOKEN_RE = re.compile(r"[؀-ۿ]+")

_ONES = {
    "إحدى": 1, "احدى": 1, "واحدة": 1,
    "اثنتين": 2, "ثنتين": 2, "اثنين": 2, "ثنتان": 2,
    "ثلاث": 3, "أربع": 4, "اربع": 4, "خمس": 5, "ست": 6, "سبع": 7,
    "ثمان": 8, "ثماني": 8, "تسع": 9,
}
_TENS = {
    "عشرة": 10, "عشر": 10, "عشرين": 20, "ثلاثين": 30, "أربعين": 40,
    "اربعين": 40, "خمسين": 50, "ستين": 60, "سبعين": 70, "ثمانين": 80,
    "تسعين": 90,
}
_HUNDREDS = {
    "مائة": 100, "مئة": 100, "مائتين": 200, "مئتين": 200,
    "ثلاثمائة": 300, "ثلثمائة": 300, "أربعمائة": 400, "اربعمائة": 400,
}
_YEAR_WORDS = {**_HUNDREDS, **_TENS, **_ONES}


def parse_arabic_year(title: str) -> int | None:
    """Read a spelled-out hijri year out of an Arabic section heading.

    ``ودخلت سنة خمس وتسعين ومائتين`` -> 295. Returns None when the heading
    carries no year, and stops at the first non-numeral word after a numeral
    so that ``سنة خمس وثلاثين فيها كان ظهور السبائية`` does not absorb the
    rest of the title.
    """
    position = title.find("سنة")
    if position < 0:
        return None
    total = 0
    seen = False
    for raw in _ARABIC_TOKEN_RE.findall(title[position + 3 : position + 70]):
        word = raw[1:] if raw.startswith("و") and raw[1:] in _YEAR_WORDS else raw
        if word in _YEAR_WORDS:
            total += _YEAR_WORDS[word]
            seen = True
        elif seen:
            break
    return total if seen else None


@dataclass
class ArabicYearBlock:
    ah_year: int
    section_range: tuple[int, int]
    paragraphs: list[openiti_markdown.Paragraph] = field(default_factory=list)

    @property
    def word_count(self) -> int:
        return sum(paragraph.word_count for paragraph in self.paragraphs)


@dataclass
class Passage:
    ah_year: int
    arabic_range: tuple[int, int]
    """Indices into the year's Arabic paragraph list."""
    english_range: tuple[int, int]
    """Indices into the year's English paragraph list."""
    arabic: str
    english: str
    arabic_word_count: int
    english_word_count: int
    arabic_pages: list[int]
    """Amedroz Arabic-edition page numbers printed inline in this English."""
    year_complete: bool
    """True when the passage is the whole year on both sides."""
    structural_confidence: float
    confidence: float
    method: str = "year_anchored_proportional_cut"
    flags: list[str] = field(default_factory=lambda: ["llm_required"])
    llm_verdict: dict | None = None

    @property
    def native_id(self) -> str:
        start, end = self.arabic_range
        return f"ah{self.ah_year:03d}-a{start:03d}_{end:03d}"

    @property
    def word_ratio(self) -> float:
        return self.english_word_count / max(1, self.arabic_word_count)


@dataclass
class ExtractionReport:
    arabic_years: int
    english_years: int
    shared_years: int
    used_years: list[int]
    rejected_years: list[tuple[int, str]]
    passages: list[Passage]


def arabic_year_blocks(text: openiti_markdown.OpenITIText) -> list[ArabicYearBlock]:
    """Split the annalistic portion into one block per hijri year.

    Only the first heading for a year opens a block; Miskawayh returns to
    ``وفى هذه السنة`` sub-headings repeatedly, and those belong to the year
    already open. A block runs to the next year's opening heading.
    """
    marks: list[tuple[int, int]] = []
    seen: set[int] = set()
    for section in text.sections:
        if not _ARABIC_YEAR_HEADING_RE.search(section.title):
            continue
        year = parse_arabic_year(section.title)
        if year is None or year in seen or not FIRST_YEAR <= year <= LAST_YEAR:
            continue
        seen.add(year)
        marks.append((section.index, year))

    blocks: list[ArabicYearBlock] = []
    for position, (section_index, year) in enumerate(marks):
        end = (
            marks[position + 1][0]
            if position + 1 < len(marks)
            else len(text.sections)
        )
        paragraphs = [
            paragraph
            for section in text.sections[section_index:end]
            for paragraph in section.paragraphs
        ]
        blocks.append(
            ArabicYearBlock(
                ah_year=year,
                section_range=(section_index, end),
                paragraphs=paragraphs,
            )
        )
    return blocks


def _prefix(weights: list[int]) -> list[int]:
    out = [0]
    for weight in weights:
        out.append(out[-1] + weight)
    return out


def _nearest_boundary(prefix: list[int], total: int, fraction: float, low: int) -> int:
    """Index > `low` whose cumulative fraction is closest to `fraction`."""
    best = low + 1
    best_gap = float("inf")
    for index in range(low + 1, len(prefix)):
        gap = abs(prefix[index] / max(1, total) - fraction)
        if gap < best_gap:
            best_gap = gap
            best = index
    return best


def _anchor_gain(english_text: str, arabic_text: str) -> float:
    """Name-skeleton mass this English text finds in the Arabic, minus what it
    fails to find.

    Positive means the paragraph's proper names are accounted for by this
    Arabic slice; negative means they are not, so the paragraph belongs on the
    other side of the boundary. Only skeletons long enough to be evidence are
    counted, in either direction.
    """
    evidence = translit.name_evidence(english_text, arabic_text)
    matched = sum(len(s) for s in evidence.matched if len(s) >= STRONG_SKELETON)
    missed = sum(len(s) for s in evidence.missed if len(s) >= STRONG_SKELETON)
    return float(matched - missed)


def _refine_boundary(
    english: list[eclipse_ocr.EnglishParagraph],
    guess: int,
    low: int,
    high: int,
    arabic_before: str,
    arabic_after: str,
    window: int = ANCHOR_WINDOW,
) -> int:
    """Move an English cut point to where the proper names say it belongs.

    Scores every candidate boundary in ``[guess - window, guess + window]`` by
    how well the paragraphs on each side are explained by the Arabic on that
    side, and returns the best. Ties keep the length-proportional guess, so
    absent name evidence this is a no-op rather than a random walk.
    """
    lower = max(low, guess - window)
    upper = min(high, guess + window)
    if upper <= lower or not (arabic_before or arabic_after):
        return guess
    before = [_anchor_gain(p.text, arabic_before) for p in english[lower:upper]]
    after = [_anchor_gain(p.text, arabic_after) for p in english[lower:upper]]

    best_index = guess
    best_score = float("-inf")
    for candidate in range(lower, upper + 1):
        split = candidate - lower
        score = sum(before[:split]) + sum(after[split:])
        # Strictly-better wins; equal scores fall back to the closest-to-guess
        # candidate, which on a tie is the guess itself.
        if score > best_score or (
            score == best_score and abs(candidate - guess) < abs(best_index - guess)
        ):
            best_score = score
            best_index = candidate
    return best_index


def _cut_year(
    arabic: ArabicYearBlock,
    english: list[eclipse_ocr.EnglishParagraph],
    english_range: tuple[int, int],
    targets: tuple[int, ...],
    min_words: int,
) -> list[Passage]:
    """Propose passages inside one year: proportional cut, name-refined."""
    arabic_weights = [paragraph.word_count for paragraph in arabic.paragraphs]
    english_low, english_high = english_range
    english_weights = [p.word_count for p in english[english_low:english_high]]
    if not arabic_weights or not english_weights:
        return []
    arabic_prefix = _prefix(arabic_weights)
    english_prefix = _prefix(english_weights)
    arabic_total = arabic_prefix[-1]
    english_total = english_prefix[-1]

    passages: list[Passage] = []
    a_start = 0
    e_start = 0
    step = 0
    while a_start < len(arabic_weights) and e_start < len(english_weights):
        target = targets[step % len(targets)]
        a_end = a_start
        while (
            a_end < len(arabic_weights)
            and arabic_prefix[a_end] - arabic_prefix[a_start] < target
        ):
            a_end += 1
        # Absorb a final scrap rather than emitting a stub.
        if arabic_prefix[-1] - arabic_prefix[a_end] < min_words:
            a_end = len(arabic_weights)
        if a_end <= a_start:
            break

        if a_end >= len(arabic_weights):
            e_end = len(english_weights)
        else:
            guess = min(
                _nearest_boundary(
                    english_prefix,
                    english_total,
                    arabic_prefix[a_end] / max(1, arabic_total),
                    e_start,
                ),
                len(english_weights),
            )
            e_end = _refine_boundary(
                english,
                english_low + guess,
                english_low + e_start + 1,
                english_high,
                "\n".join(p.text for p in arabic.paragraphs[a_start:a_end]),
                "\n".join(p.text for p in arabic.paragraphs[a_end:]),
            ) - english_low
        if e_end <= e_start:
            break

        arabic_text = "\n\n".join(
            paragraph.text for paragraph in arabic.paragraphs[a_start:a_end]
        )
        slice_ = english[english_low + e_start : english_low + e_end]
        english_raw = "\n\n".join(paragraph.text for paragraph in slice_)
        pages = [page for paragraph in slice_ for page in paragraph.arabic_pages]
        english_text = eclipse_ocr.strip_arabic_page_markers(english_raw)
        complete = a_start == 0 and a_end == len(arabic_weights)
        flags = ["llm_required"]
        if pages != sorted(pages):
            flags.append("page_markers_nonmonotone")
        # A whole-year passage is bounded by the anchor on both sides; an
        # interior cut is bounded by it on one side at most.
        structural = (
            0.85 if complete
            else (0.7 if a_start == 0 or a_end == len(arabic_weights) else 0.6)
        )
        passages.append(
            Passage(
                ah_year=arabic.ah_year,
                arabic_range=(a_start, a_end),
                english_range=(english_low + e_start, english_low + e_end),
                arabic=arabic_text,
                english=english_text,
                arabic_word_count=len(arabic_text.split()),
                english_word_count=len(english_text.split()),
                arabic_pages=pages,
                year_complete=complete,
                structural_confidence=structural,
                confidence=structural,
                flags=flags,
            )
        )
        a_start, e_start = a_end, e_end
        step += 1
    return passages


def extract(
    arabic_path: str | Path,
    english_paths: str | Path | list[str | Path],
    *,
    targets: tuple[int, ...] = (170, 330),
    min_words: int = 100,
) -> tuple[openiti_markdown.OpenITIText, ExtractionReport]:
    """Build year-anchored passage proposals for the whole slice."""
    if isinstance(english_paths, (str, Path)):
        english_paths = [english_paths]
    metadata = openiti_markdown.read(arabic_path)
    arabic_blocks = {block.ah_year: block for block in arabic_year_blocks(metadata)}

    # One ordered English paragraph list across the volumes, so a year's
    # opening boundary can be pulled back into the previous year's run -- which
    # is exactly where the running head's page lag puts it.
    english: list[eclipse_ocr.EnglishParagraph] = []
    for path in english_paths:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        paragraphs, _heads = eclipse_ocr.parse_paragraphs(text)
        english.extend(p for p in paragraphs if p.ah_year is not None)
    for position, paragraph in enumerate(english):
        paragraph.index = position

    stated: dict[int, tuple[int, int]] = {}
    for position, paragraph in enumerate(english):
        year = paragraph.ah_year
        if year is None:
            continue
        low, _high = stated.get(year, (position, position))
        stated[year] = (low, position + 1)

    shared = sorted(set(arabic_blocks) & set(stated))
    work_ratio = sum(
        sum(p.word_count for p in english[slice(*stated[year])]) for year in shared
    ) / max(1, sum(arabic_blocks[year].word_count for year in shared))

    used: list[int] = []
    rejected: list[tuple[int, str]] = []
    passages: list[Passage] = []
    for position, year in enumerate(shared):
        arabic = arabic_blocks[year]
        low, high = stated[year]
        english_words = sum(p.word_count for p in english[low:high])
        if arabic.word_count < min_words or english_words < min_words:
            rejected.append((year, "year too short on one side"))
            continue
        ratio = english_words / arabic.word_count
        if abs(ratio - work_ratio) / work_ratio > RATIO_TOLERANCE:
            rejected.append(
                (year, f"word ratio {ratio:.2f} vs work {work_ratio:.2f}")
            )
            continue
        previous = arabic_blocks.get(shared[position - 1]) if position else None
        low = _refine_boundary(
            english,
            low,
            max(0, low - ANCHOR_WINDOW),
            high,
            "\n".join(p.text for p in previous.paragraphs[-6:]) if previous else "",
            "\n".join(p.text for p in arabic.paragraphs[:6]),
        )
        year_passages = _cut_year(arabic, english, (low, high), targets, min_words)
        if not year_passages:
            rejected.append((year, "no passage could be cut"))
            continue
        used.append(year)
        passages.extend(year_passages)

    return metadata, ExtractionReport(
        arabic_years=len(arabic_blocks),
        english_years=len(stated),
        shared_years=len(shared),
        used_years=used,
        rejected_years=rejected,
        passages=passages,
    )


__all__ = [
    "ENGLISH_SOURCE",
    "RIGHTS_EVIDENCE",
    "RIGHTS_STATUS",
    "TRANSLATOR",
    "WORK_ID",
    "ArabicYearBlock",
    "ExtractionReport",
    "Passage",
    "arabic_year_blocks",
    "extract",
    "parse_arabic_year",
]
