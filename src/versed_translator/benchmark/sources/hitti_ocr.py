"""OCR cleanup + structure detection for Hitti's *The Origins of the Islamic
State* (1916), archive.org ``originsofislamic01albauoft_djvu.txt``.

This is per-edition logic, not a general djvu cleaner, and it is honest about
that: every rule below was written against, and only validated against, this
one scan. The specific damage this scan carries is:

- Running heads bleed into the text stream mid-paragraph, sometimes
  lowercased by the OCR (``j6 the origins of the islamic state``) and
  sometimes with the page number fused on (``FADAK  $j``, ``AL-MADINAH  jy``).
- Footnotes are inlined at each page break as a run of short blocks whose
  markers the OCR mangles (``1``, ``2``, ``J-``, ``s"``, ``*``).
- Hitti prints de Goeje's Arabic-edition pagination in the right margin; the
  OCR fuses those 2-3 digit numbers into the running text
  (``...for the 30 / Moslems...``).
- Words are hyphenated across line breaks, which collides with the fact that
  Hitti's name chains are themselves hyphenated (``'Umar ibn-al- / Khattab``).
- Paragraphs are split by the page break itself and must be rejoined.
- Hitti inserts his own italic run-in topical headings (``Fadak demanded by
  Fatimah.``) that have no counterpart in the Arabic. Left in place they
  would make the reference translation contain material the source does not,
  i.e. they would punish a faithful model, so they are stripped and the fact
  is recorded per paragraph.

Nothing here silently discards text it cannot classify: anything not matched
by a rule stays in the body.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

ROMAN_RE = re.compile(r"^[IVXLCDM]+$")

_PART_RE = re.compile(r"^\s*PART\s+([IVXLCDM]+)\s*$")
_CHAPTER_RE = re.compile(r"^\s*CHAPTER\s+([IVXLCDM]+)\s*$")

# The running head of this edition, as the OCR variously mangles it. Letters
# are allowed to be separated by spaces because the scan does exactly that:
# "THE ORIGIXS OF THE ISLAMIC ST A TE".
def _spaced(word: str) -> str:
    return r"\s*".join(word)


_RUNNING_TITLE_RE = re.compile(
    _spaced("or") + r"[il]" + _spaced("g") + r"[iI][nx]" + _spaced("s")
    + r"\s+" + _spaced("of") + r"\s+" + _spaced("the") + r"\s+"
    + r"[il]" + _spaced("slam") + r"[il]" + _spaced("c") + r"\s+" + _spaced("state"),
    re.IGNORECASE,
)
# A page-number-only line. The OCR renders digits as letters often enough
# ($j for 51, jy for 57, j6 for 36) that a pure-digit test is not enough.
_PAGENUM_RE = re.compile(r"^[\s.\dIVXLivxlijJyx$&lo]{1,8}$")
_DIGIT_RE = re.compile(r"\d")

# Footnote block openers as this scan renders them: a numeral, a symbol, or
# whatever letter the OCR turned the marker into, then a separator, then the
# note. The separator is REQUIRED for letter-shaped markers, otherwise a body
# paragraph beginning "It was..." reads as footnote "I".
_FOOTNOTE_START_RE = re.compile(
    r"""^\s*(?:\d{1,2}[-.\s"']+|[*•§]\s*|[JjxXsSlI'"&]{1,2}[-.\s"']+)[A-Za-z"'(\[]"""
)
# A block this short that opens with a footnote marker is a footnote even
# when the page-break sentinel around it was mangled beyond recognition.
_STANDALONE_FOOTNOTE_MAX_LINES = 3
_STANDALONE_FOOTNOTE_MAX_WORDS = 35
_CITATION_HINT_RE = re.compile(
    r"\bvol\.|\bpp?\.|\bibid|\bcf\.|\bop\.\s*cit|\bsee\b|Koran|Yakut|Ibn-|Wustenfeld",
    re.IGNORECASE,
)

_MARGIN_NUM_RE = re.compile(r"^(?P<body>.*\S)\s+(?P<num>\d{2,3})\s*$")
# The de Goeje marginal numbers climb by 1-3 through the volume. Allowing a
# little slack absorbs the ones the OCR drops outright.
_MARGIN_MAX_STEP = 6
_MARGIN_MIN_RUN = 20

# Hitti's abridged isnad head ends at a colon followed by a dash.
_ISNAD_END_RE = re.compile(r":\s*[—–-]{1,2}")

_RUNIN_HEADING_RE = re.compile(r"^(?P<head>[^.?!]{4,70}[.?])\s+(?P<rest>[A-Z'\"(\[].*)$", re.DOTALL)


def _is_running_head(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    # The book's own running title, however mangled and however much page
    # furniture the OCR fused onto it, is never body text.
    if _RUNNING_TITLE_RE.search(stripped):
        return True
    alpha = [c for c in stripped if c.isalpha()]
    if not alpha or len(stripped.split()) > 8:
        return False
    upper_ratio = sum(1 for c in alpha if c.isupper()) / len(alpha)
    # A short, overwhelmingly-uppercase line inside the body is a running
    # head; genuine body text is never set that way in this edition.
    return upper_ratio >= 0.8 and len(alpha) >= 3


def _is_page_number(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > 8:
        return False
    if ROMAN_RE.match(stripped):
        return True
    if not _PAGENUM_RE.match(stripped):
        return False
    # Require at least one digit-ish glyph so a stray word is not eaten.
    return bool(_DIGIT_RE.search(stripped)) or stripped.lower() in {
        "$j",
        "jy",
        "j6",
        "jo",
        "io",
        "il",
    }


def _looks_like_footnote(block: list[str]) -> bool:
    if not block or len(block) > 4:
        return False
    first = block[0]
    if not _FOOTNOTE_START_RE.match(first):
        return False
    joined = " ".join(block)
    # Either it cites something, or it is a very short gloss (Hitti's
    # explanatory footnotes run to a line or two).
    return bool(_CITATION_HINT_RE.search(joined)) or len(joined.split()) <= 25


def mask_margin_page_numbers(lines: list[str]) -> list[str]:
    """Remove Hitti's fused de Goeje marginal page numbers, volume-wide.

    Hitti prints the pagination of de Goeje's Arabic edition in the right
    margin; the OCR fuses those into the running text ("...for the 30 /
    Moslems..."). Deciding line by line whether a trailing number is margin
    furniture or real ("gave him 500 dirhams") is guesswork.

    What is not guesswork is that the marginal numbers form one long,
    strictly increasing, small-stepped sequence running the length of the
    volume, and numbers belonging to the text do not. So: collect every
    line-final 2-3 digit number, take the longest increasing subsequence
    whose consecutive steps are at most `_MARGIN_MAX_STEP`, and delete only
    those. A number in the body survives unless it happens to fall inside
    the margin's own run, which costs at most a stray digit.

    If no long enough run is found the input is returned untouched -- better
    to leave the numbers in than to start deleting text on no evidence.
    """
    candidates: list[tuple[int, int, str]] = []
    for idx, line in enumerate(lines):
        match = _MARGIN_NUM_RE.match(line.rstrip())
        if match:
            candidates.append((idx, int(match.group("num")), match.group("body")))
    if len(candidates) < _MARGIN_MIN_RUN:
        return lines

    best = [1] * len(candidates)
    prev = [-1] * len(candidates)
    for i in range(len(candidates)):
        for j in range(i):
            step = candidates[i][1] - candidates[j][1]
            if 0 < step <= _MARGIN_MAX_STEP and best[j] + 1 > best[i]:
                best[i] = best[j] + 1
                prev[i] = j
    tail = max(range(len(candidates)), key=lambda i: best[i])
    if best[tail] < _MARGIN_MIN_RUN:
        return lines

    out = list(lines)
    while tail != -1:
        idx, _value, body = candidates[tail]
        out[idx] = body
        tail = prev[tail]
    return out


def dehyphenate(text: str) -> str:
    """Rejoin words broken across lines, preserving real chain hyphens.

    ``ex-\\npelled`` -> ``expelled`` but ``ibn-al-\\nKhattab`` ->
    ``ibn-al-Khattab``: if the fragment before the break is a name-chain
    particle, or the token already carries a hyphen, the hyphen is real.
    """
    chain = {
        "ibn",
        "abu",
        "abi",
        "abd",
        "umm",
        "bint",
        "banu",
        "bani",
        "al",
        "an",
        "ar",
        "as",
        "at",
        "az",
        "ad",
        "ash",
        "ath",
        "dhu",
        "bin",
    }

    def repl(match: re.Match[str]) -> str:
        left, right = match.group("left"), match.group("right")
        tail = left.split()[-1] if left.split() else left
        particle = tail.split("-")[-1].lower().strip("'’")
        # A chain hyphen is real only if a particle is followed by a
        # capitalised name; "at-/tempt" is a broken word, "ibn-al-/Khattab"
        # is not.
        keep = particle in chain and right[:1].isupper()
        return f"{left}-{right}" if keep else f"{left}{right}"

    return re.sub(
        r"(?P<left>\S*?)-[ \t]*\n[ \t]*(?P<right>\S+)",
        repl,
        text,
    )


@dataclass
class EnglishParagraph:
    index: int
    text: str
    heading_stripped: str | None = None
    """Hitti's run-in topical heading, removed from `text` and kept here."""

    @property
    def isnad_head(self) -> str:
        """The abridged isnad at the head of the paragraph.

        Up to the ``: —`` marker if present, else the first 18 words --
        long enough to cover a two-name chain, short enough that body prose
        does not flood the anchor matcher with incidental names.
        """
        match = _ISNAD_END_RE.search(self.text[:400])
        if match:
            return self.text[: match.start()]
        return " ".join(self.text.split()[:18])

    @property
    def word_count(self) -> int:
        return len(self.text.split())


@dataclass
class EnglishChapter:
    part_roman: str
    part_title: str
    chapter_roman: str
    title: str
    line_no: int
    paragraphs: list[EnglishParagraph] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"PART {self.part_roman} / CHAPTER {self.chapter_roman}"

    @property
    def word_count(self) -> int:
        return sum(p.word_count for p in self.paragraphs)


def split_run_in_heading(text: str) -> tuple[str | None, str]:
    """Split Hitti's italic run-in topical heading off the paragraph body.

    Conservative: the heading must be <= 8 words, must not itself look like
    an isnad (no ``from``/colon), and at least 25 words of body must remain.
    """
    match = _RUNIN_HEADING_RE.match(text.strip())
    if not match:
        return None, text
    head, rest = match.group("head").strip(), match.group("rest").strip()
    words = head.split()
    if not (1 <= len(words) <= 8):
        return None, text
    if ":" in head or re.search(r"\bfrom\b|\bsaid\b|\bsays\b", head, re.IGNORECASE):
        return None, text
    if len(rest.split()) < 25:
        return None, text
    return head, rest


def clean_body_lines(lines: list[str]) -> list[str]:
    """Remove running heads, page numbers and footnote blocks from a slice.

    Blocks are blank-line separated. A trailing run of footnote-looking
    blocks immediately before a page-number line is dropped, which is where
    this edition puts them.
    """
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if line.strip():
            current.append(line)
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)

    keep = [True] * len(blocks)
    for idx, block in enumerate(blocks):
        # Short marker-led blocks are footnotes wherever they turn up. The
        # walk-back below only catches the ones whose page break survived
        # OCR intact, and several did not.
        if (
            len(block) <= _STANDALONE_FOOTNOTE_MAX_LINES
            and _FOOTNOTE_START_RE.match(block[0])
            and len(" ".join(block).split()) <= _STANDALONE_FOOTNOTE_MAX_WORDS
        ):
            keep[idx] = False
            continue
        if all(_is_page_number(ln) or _is_running_head(ln) for ln in block):
            keep[idx] = False
            # Walk back over the footnote run that precedes the page break.
            back = idx - 1
            while back >= 0 and keep[back] and _looks_like_footnote(blocks[back]):
                keep[back] = False
                back -= 1
            continue
        # Running heads sometimes lead a block that also starts the next
        # paragraph; drop just the offending line in that case.
        while block and (_is_running_head(block[0]) or _is_page_number(block[0])):
            block.pop(0)
        if not block:
            keep[idx] = False

    out: list[str] = []
    for idx, block in enumerate(blocks):
        if not keep[idx]:
            continue
        out.extend(block)
        out.append("")
    return out


def _join_blocks(blocks: list[str]) -> list[str]:
    """Rejoin paragraph fragments separated by a page break.

    A fragment continues the previous one when the previous does not end in
    terminal punctuation, or the fragment opens lowercase.
    """
    merged: list[str] = []
    for block in blocks:
        if merged:
            prev = merged[-1].rstrip()
            starts_lower = bool(block[:1]) and block[0].islower()
            unterminated = not re.search(r"[.!?][\"'”’)\]]?$", prev)
            if starts_lower or unterminated:
                merged[-1] = f"{prev} {block.lstrip()}"
                continue
        merged.append(block)
    return merged


def parse_paragraphs(lines: list[str]) -> list[EnglishParagraph]:
    """Clean a chapter's raw lines into paragraph objects."""
    cleaned = clean_body_lines(lines)
    text = dehyphenate("\n".join(cleaned))
    raw_blocks = [
        re.sub(r"\s+", " ", block).strip()
        for block in re.split(r"\n\s*\n", text)
        if block.strip()
    ]
    paragraphs: list[EnglishParagraph] = []
    for idx, block in enumerate(_join_blocks(raw_blocks)):
        heading, body = split_run_in_heading(block)
        if body:
            paragraphs.append(
                EnglishParagraph(index=idx, text=body, heading_stripped=heading)
            )
    for position, paragraph in enumerate(paragraphs):
        paragraph.index = position
    return paragraphs


def parse_chapters(text: str) -> list[EnglishChapter]:
    """Split the whole volume into Part/Chapter units with clean paragraphs.

    Only the ALL-CAPS body headings (``CHAPTER  IV``) are treated as
    structure; the table of contents uses mixed case (``Chapter  IV``) and
    the em-dash form (``PART  I— ARABIA``), so it is skipped without needing
    a hard-coded front-matter offset.
    """
    lines = mask_margin_page_numbers(text.split("\n"))
    marks: list[tuple[int, str, str]] = []
    for idx, line in enumerate(lines):
        part = _PART_RE.match(line)
        if part:
            marks.append((idx, "part", part.group(1)))
            continue
        chapter = _CHAPTER_RE.match(line)
        if chapter:
            marks.append((idx, "chapter", chapter.group(1)))

    chapters: list[EnglishChapter] = []
    part_roman, part_title = "", ""
    for position, (idx, kind, roman) in enumerate(marks):
        # The heading title is the next non-blank, non-numeric line.
        title = ""
        scan = idx + 1
        while scan < len(lines) and scan < idx + 5:
            candidate = lines[scan].strip()
            if candidate and not _is_page_number(candidate):
                title = re.sub(r"\s+", " ", candidate)
                break
            scan += 1
        if kind == "part":
            part_roman, part_title = roman, title
            continue
        end = marks[position + 1][0] if position + 1 < len(marks) else len(lines)
        chapter = EnglishChapter(
            part_roman=part_roman,
            part_title=part_title,
            chapter_roman=roman,
            title=re.sub(r"\s*\d+\s*$", "", title).strip(),
            line_no=idx + 1,
        )
        chapter.paragraphs = parse_paragraphs(lines[scan + 1 : end])
        chapters.append(chapter)
    return chapters
