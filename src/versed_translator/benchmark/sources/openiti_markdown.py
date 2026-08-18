"""Light, read-only reader for OpenITI mARkdown (``######OpenITI#``) texts.

Deliberately NOT the factory parser. `versed_core/ingestion/openiti_ingest.py`
is coupled to Supabase and writes the v2 graph; the lab needs plain read-only
passage extraction with no side effects, so this is a separate ~200-line
module that only ever reads.

What it handles (verified against `0279Baladhuri.FutuhBuldan.txt`, whose
1.1 MB decompose into exactly: 1 `######OpenITI#` magic line, 33 `#META#`
lines, 90 `### |` section headings, 1,320 `# ` paragraph openers, 7,993 `~~`
continuation lines, 444 `PageV##P###` page markers, 387 `msNNN` milestones
and 249 `%~%` hemistich separators):

- ``#META# key :: value`` header block terminated by ``#META#Header#End#``.
  Keys are the numbered OpenITI field names (``011.AuthorDIED``,
  ``021.BookSUBJ``, ...). Values equal to ``NODATA``/``NOTGIVEN``/``NOCODE``
  are normalised to ``None`` -- OpenITI uses those as explicit nulls, and
  carrying them through as strings has burned downstream code before.
- ``### | Title`` section headings (any number of leading ``#``). The
  literal OpenITI sentinel ``### |PARATEXT|`` marks editorial matter that is
  not part of the work; such sections are flagged ``is_paratext`` so callers
  can drop them rather than translate an editor's note.
- ``# text`` paragraph openers and ``~~text`` continuation lines, rejoined
  into one logical paragraph.
- Inline noise stripped from paragraph text: ``PageV01P038`` page markers,
  ``ms024`` milestone markers, and ``%~%`` hemistich separators (replaced by
  a space, since they separate the two halves of a verse line).

What it does NOT do: no normalisation of Arabic orthography, no diacritic
stripping, no sentence splitting, no rights reasoning. Callers do that.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

MAGIC = "######OpenITI#"
META_PREFIX = "#META#"
META_END = "#META#Header#End#"
PARATEXT_SENTINEL = "PARATEXT"

# OpenITI's explicit null values. Treated as missing rather than as text.
NULL_VALUES = frozenset({"NODATA", "NOTGIVEN", "NOCODE", "NONE", ""})

_META_RE = re.compile(r"^#META#\s*(?P<key>[^:]+?)\s*::\s*(?P<value>.*)$")
_SECTION_RE = re.compile(r"^(?P<hashes>#{1,6})\s*\|\s*(?P<title>.*)$")
_PARAGRAPH_RE = re.compile(r"^#\s+(?P<text>.*)$")
_CONTINUATION_RE = re.compile(r"^~~(?P<text>.*)$")

_PAGE_MARKER_RE = re.compile(r"PageV\d+P\d+")
_MILESTONE_RE = re.compile(r"\bms\d+\b")
_HEMISTICH_RE = re.compile(r"%~%")
_WS_RE = re.compile(r"\s+")


def _clean_inline(text: str) -> str:
    """Strip page markers, milestones and hemistich separators from a line."""
    text = _PAGE_MARKER_RE.sub(" ", text)
    text = _MILESTONE_RE.sub(" ", text)
    text = _HEMISTICH_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


@dataclass
class Paragraph:
    """One logical ``# ...`` paragraph, continuations already rejoined."""

    index: int
    """0-based index within the whole text."""
    section_index: int
    """Index into OpenITIText.sections, or -1 for pre-section preamble."""
    line_no: int
    """1-based line number of the ``# `` opener in the source file."""
    text: str

    @property
    def word_count(self) -> int:
        return len(self.text.split())


@dataclass
class Section:
    """One ``### | ...`` section heading and the paragraphs beneath it."""

    index: int
    title: str
    line_no: int
    level: int
    """Number of leading ``#`` characters (3 for the common ``### |``)."""
    is_paratext: bool = False
    paragraphs: list[Paragraph] = field(default_factory=list)

    @property
    def word_count(self) -> int:
        return sum(p.word_count for p in self.paragraphs)

    @property
    def text(self) -> str:
        return "\n".join(p.text for p in self.paragraphs)


@dataclass
class OpenITIText:
    """A parsed mARkdown text: metadata header + sections + paragraphs."""

    uri: str
    """Filename stem, e.g. ``0279Baladhuri.FutuhBuldan``."""
    meta: dict[str, str]
    sections: list[Section]
    preamble: list[Paragraph]
    """Paragraphs appearing before the first section heading."""

    # -- convenience accessors over the numbered OpenITI meta keys ---------

    def meta_get(self, *keys: str) -> str | None:
        """First non-null value among `keys`, else None."""
        for key in keys:
            value = self.meta.get(key)
            if value is not None:
                return value
        return None

    @property
    def author_name(self) -> str | None:
        return self.meta_get("010.AuthorNAME", "010.AuthorAKA")

    @property
    def author_died(self) -> int | None:
        """Author death year in AH (`011.AuthorDIED`), or None."""
        raw = self.meta_get("011.AuthorDIED", "019.AuthorDIED")
        if raw is None:
            return None
        digits = re.search(r"\d+", raw)
        return int(digits.group()) if digits else None

    @property
    def book_title(self) -> str | None:
        return self.meta_get("020.BookTITLE")

    @property
    def book_subject(self) -> str | None:
        """Genre as OpenITI records it (`021.BookSUBJ`), verbatim Arabic.

        Never inferred. If the header does not carry it, this is None and
        the caller must not invent a genre (schema.py rule).
        """
        return self.meta_get("021.BookSUBJ")

    @property
    def book_uri(self) -> str | None:
        return self.meta_get("000.BookURI")

    @property
    def all_paragraphs(self) -> list[Paragraph]:
        out = list(self.preamble)
        for section in self.sections:
            out.extend(section.paragraphs)
        return sorted(out, key=lambda p: p.index)


def parse_meta_value(raw: str) -> str | None:
    """Normalise one `#META#` value: strip, map OpenITI nulls to None."""
    value = raw.strip()
    return None if value.upper() in NULL_VALUES else value


def parse(text: str, uri: str = "") -> OpenITIText:
    """Parse mARkdown source text. Never raises on odd input."""
    meta: dict[str, str] = {}
    sections: list[Section] = []
    preamble: list[Paragraph] = []

    in_header = False
    header_done = False
    current_section: Section | None = None
    current_paragraph: Paragraph | None = None
    pending: list[str] = []
    para_index = 0

    def flush_paragraph() -> None:
        nonlocal current_paragraph, pending
        if current_paragraph is None:
            return
        current_paragraph.text = _clean_inline(" ".join(pending))
        if current_paragraph.text:
            target = (
                current_section.paragraphs if current_section is not None else preamble
            )
            target.append(current_paragraph)
        current_paragraph = None
        pending = []

    for line_no, raw_line in enumerate(text.split("\n"), start=1):
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped == MAGIC:
            in_header = True
            continue
        if stripped == META_END:
            in_header = False
            header_done = True
            continue
        if stripped.startswith(META_PREFIX):
            # Tolerate a #META# line even without a magic line above it.
            match = _META_RE.match(stripped)
            if match:
                value = parse_meta_value(match.group("value"))
                if value is not None:
                    meta[match.group("key").strip()] = value
            continue
        if in_header and not header_done:
            # Free-text lines inside the header block (some LAL texts wrap
            # editorial declarations) are not content -- ignore them.
            continue
        if not stripped:
            continue

        section_match = _SECTION_RE.match(stripped)
        if section_match:
            flush_paragraph()
            title = _clean_inline(section_match.group("title"))
            is_paratext = title.strip("|").strip().upper() == PARATEXT_SENTINEL
            current_section = Section(
                index=len(sections),
                title="" if is_paratext else title,
                line_no=line_no,
                level=len(section_match.group("hashes")),
                is_paratext=is_paratext,
            )
            sections.append(current_section)
            continue

        continuation_match = _CONTINUATION_RE.match(stripped)
        if continuation_match:
            # Some editions put the opening prose in a level-1 ``# |``
            # heading and continue it with ``~~`` lines. Preserve that prose
            # as a paragraph instead of silently discarding the continuation.
            if (
                current_paragraph is None
                and current_section is not None
                and current_section.level == 1
            ):
                current_paragraph = Paragraph(
                    index=para_index,
                    section_index=current_section.index,
                    line_no=current_section.line_no,
                    text="",
                )
                para_index += 1
                pending = [current_section.title]
            if current_paragraph is not None:
                pending.append(continuation_match.group("text"))
            continue

        paragraph_match = _PARAGRAPH_RE.match(stripped)
        if paragraph_match:
            flush_paragraph()
            current_paragraph = Paragraph(
                index=para_index,
                section_index=current_section.index if current_section else -1,
                line_no=line_no,
                text="",
            )
            para_index += 1
            pending = [paragraph_match.group("text")]
            continue

        # A bare "#" (section-less divider) or unrecognised line: treat any
        # text on it as a continuation if a paragraph is open, else ignore.
        if stripped != "#" and current_paragraph is not None:
            pending.append(stripped.lstrip("#").strip())

    flush_paragraph()
    return OpenITIText(uri=uri, meta=meta, sections=sections, preamble=preamble)


def read(path: str | Path) -> OpenITIText:
    """Parse the mARkdown file at `path`. The URI is the filename stem."""
    p = Path(path)
    return parse(p.read_text(encoding="utf-8"), uri=p.stem)
