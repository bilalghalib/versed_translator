"""Per-work alignment: al-Baladhuri, *Futuh al-Buldan* <-> Hitti, *The Origins
of the Islamic State* (1916).

Why this work. The roadmap's D1e verification pass ranked eight PD candidates
and warned that "section structure is per-work, not uniform -- segmentation
is a per-work task, not one parser". The criterion that actually matters for
a first vertical slice is **bilateral** structure -- anchors on BOTH sides --
and Baladhuri/Hitti is the only candidate with three independent layers of it:

1. **Chapter layer.** The OpenITI text carries 90 ``### |`` sections with
   descriptive Arabic titles; Hitti's volume carries 68 ``PART n /
   CHAPTER n`` headings whose titles are transliterations or translations of
   those same Arabic titles (``فتح فدك`` / ``Fadak``, ``ذكر حفائر مكة`` /
   ``The Wells of Makkah``). The two sequences can therefore be matched AND
   independently checked, rather than assumed to run in parallel.
2. **Khabar layer.** Baladhuri's text is a chain of akhbar, each opening with
   an isnad; Hitti keeps one paragraph per khabar and opens each with the
   isnad abridged to its first and last authority (he says so in his own
   footnote on p. 16). Those transmitter names are the same names in two
   scripts -- see `translit.py` -- which gives a **checkable** anchor rather
   than a length heuristic.
3. **Bracketing.** Because anchors land on named transmitters, a passage
   whose first AND last khabar are both anchor-confirmed cannot be
   off-by-one: a systematic shift would have to move both bracket names at
   once and still match. This is the property the whole design is built to
   get, since a length-proportional aligner produces exactly the shifted
   output that looks plausible row by row.

Genre also decides it: ``021.BookSUBJ`` is ``التاريخ`` (history), a genre the
v0.1-draft benchmark does not contain at all, and ``011.AuthorDIED`` is 279 AH.
Neither is inferred here; both are read from the OpenITI header.

Assumptions this module makes, stated so the next work can be judged against
them:

- **A1.** The Arabic sections and English chapters run in the same order.
  Verified, not assumed: the matcher is a monotone chain over title-name
  evidence and reports every section it could not confirm.
- **A2.** The two sides are not 1:1 at chapter level. They are not -- the
  Shamela edition splits the Mesopotamian frontier into two sections where
  Hitti has one chapter. Unconfirmed sections are dropped, never guessed.
- **A3.** Hitti's paragraph = one khabar; the Shamela edition's ``#``
  paragraph sometimes fuses two or three. Alignment is therefore N:M and is
  expressed as spans between cut points, not as paragraph pairs.
- **A4.** Hitti's run-in topical headings are his own editorial addition and
  are stripped (see hitti_ocr.split_run_in_heading), because a reference
  translation containing material absent from the source penalises a
  faithful model.
- **A5.** Volume 1 (Hitti) is used alone. Volume 2 (Murgotten) is a separate
  scan with its own pagination and front matter; adding it is a config
  change, not a code change, but it has NOT been validated here.

RIGHTS: Hitti 1916, Columbia University Press -- published before 1930, US
public domain. The Arabic is OpenITI's digitisation of a 1988 Dar wa-Maktabat
al-Hilal printing of a pre-modern text. Per the standing rule, no text from
either side is ever written into the repo; see `emit.py`.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from versed_translator.benchmark.sources import hitti_ocr, openiti_markdown
from versed_translator.benchmark.sources.hitti_ocr import EnglishChapter, EnglishParagraph
from versed_translator.benchmark.sources.openiti_markdown import OpenITIText, Section
from versed_translator.benchmark.sources.translit import NameEvidence, name_evidence

WORK_ID = "0279Baladhuri.FutuhBuldan"
ENGLISH_SOURCE = (
    "Philip K. Hitti, The Origins of the Islamic State, vol. 1 "
    "(New York: Columbia University Press, 1916); archive.org "
    "originsofislamic01albauoft"
)
TRANSLATOR = "Philip K. Hitti"
RIGHTS_STATUS = "PD_US_PRE_1930_PUBLICATION"
RIGHTS_EVIDENCE = (
    "English: Hitti 1916, Columbia University Press, published pre-1930 -- "
    "US public domain by publication date. Arabic: pre-modern text (author "
    "d. 279 AH) digitised by OpenITI from Shamela 0012221. Neither claim is "
    "cleared legal advice; D6b still gates commercial use."
)

# --- anchor thresholds -----------------------------------------------------
# An anchor must clear BOTH: enough of the English names present, and enough
# total skeleton characters matched. `mass` matters independently of `score`
# because a 2-consonant skeleton found in a 400-word Arabic paragraph is
# nearly free, while a 5-consonant one is not.
MIN_ANCHOR_SCORE = 0.6
MIN_ANCHOR_MASS = 8
# At least two names long enough to be real evidence. One long name can be
# a coincidence in a 400-word paragraph; two, in the right order, is not.
MIN_ANCHOR_STRONG_NAMES = 2

# A cut claims that an English paragraph STARTS where an Arabic paragraph
# starts, so it is tested HEAD AGAINST HEAD: the English isnad must match
# the opening of the Arabic paragraph, not merely occur somewhere inside it.
#
# Both weaker tests were tried and both failed on real pairs. Matching names
# anywhere in the Arabic paragraph put a Hamadhan passage's Arabic side one
# khabar ahead of its English side. Requiring only the *earliest* match to
# be near the head then let a Baghdad passage through on the strength of
# "al-Mansur" appearing in the first line by coincidence while the English
# actually began with ar-Rusafah, halfway down. Both showed word ratios of
# 1.3-1.5, i.e. exactly the healthy-looking number a shifted alignment
# produces. Head-against-head separates them cleanly.
ARABIC_HEAD_WORDS = 45

# Chapter-title thresholds are deliberately LOOSE. Titles alone are not
# sufficient evidence and are not used as such: Hitti translates rather than
# transliterates half of them ("The Wells of Makkah" for ذكر حفائر مكة), so
# the only word that can ever match is the place name -- which the adjacent
# chapter ("The Floods in Makkah") shares. Matching on titles alone put the
# Floods section against the Wells chapter in an earlier version of this
# module: a one-chapter shift that every downstream count looked fine under.
# Titles therefore only PROPOSE candidates; khabar-level cut counts decide.
MIN_TITLE_SCORE = 0.5
MIN_TITLE_MASS = 2
CUT_WEIGHT = 2.0
TITLE_WEIGHT = 3.0

# Hitti runs about 1.2-1.6 English words per Arabic word. Anything far
# outside that band means the span is not actually parallel, whatever the
# name anchors say, so it is flagged rather than trusted.
RATIO_LOW, RATIO_HIGH = 0.85, 2.30


# ---------------------------------------------------------------------------
# Chapter-level mapping
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChapterMatch:
    section_index: int
    chapter_index: int
    evidence: NameEvidence
    cuts: tuple[Cut, ...] = ()

    @property
    def confidence(self) -> float:
        return self.evidence.score


def _monotone_chain(
    candidates: list[tuple[int, int, float]],
) -> list[tuple[int, int, float]]:
    """Highest-scoring chain that is non-decreasing in both coordinates.

    Plain O(n^2) DP -- the inputs here are at most a few hundred candidates,
    and a clear implementation is worth more than the speed.
    """
    if not candidates:
        return []
    ordered = sorted(candidates, key=lambda c: (c[0], c[1]))
    best = [c[2] for c in ordered]
    prev = [-1] * len(ordered)
    for idx in range(len(ordered)):
        for earlier in range(idx):
            if ordered[earlier][0] > ordered[idx][0] or ordered[earlier][1] > ordered[idx][1]:
                continue
            if ordered[earlier] == ordered[idx]:
                continue
            if best[earlier] + ordered[idx][2] > best[idx]:
                best[idx] = best[earlier] + ordered[idx][2]
                prev[idx] = earlier
    tail = max(range(len(ordered)), key=lambda i: best[i])
    out: list[tuple[int, int, float]] = []
    while tail != -1:
        out.append(ordered[tail])
        tail = prev[tail]
    return list(reversed(out))


def match_chapters(
    arabic: OpenITIText, chapters: list[EnglishChapter]
) -> list[ChapterMatch]:
    """Match Arabic ``### |`` sections to Hitti's chapters, and say so.

    Two stages, because titles alone are provably not enough (see the
    MIN_TITLE_SCORE comment):

    1. Title-name evidence proposes candidate (section, chapter) pairs on a
       loose threshold.
    2. Every candidate is then aligned at khabar level and scored by how
       many CUTS it yields -- how many transmitter names line up inside the
       body. A wrong-but-adjacent chapter shares its place name but shares
       almost no isnads, so the cut count separates them decisively.

    The winning set is the best monotone chain over that combined score.
    Sections with no confirmable chapter are simply absent from the result;
    they are never assigned to "the next chapter along", which is how a
    whole-book off-by-one starts.
    """
    candidates: list[tuple[int, int, float]] = []
    evidence_by_pair: dict[tuple[int, int], NameEvidence] = {}
    cuts_by_pair: dict[tuple[int, int], list[Cut]] = {}
    for si, section in enumerate(arabic.sections):
        if section.is_paratext or not section.title or not section.paragraphs:
            continue
        for ci, chapter in enumerate(chapters):
            if not chapter.title or not chapter.paragraphs:
                continue
            evidence = name_evidence(chapter.title, section.title)
            if evidence.score < MIN_TITLE_SCORE or evidence.mass < MIN_TITLE_MASS:
                continue
            cuts = find_cuts(section, chapter)
            # A single shared place name and no shared isnad at all is not
            # evidence of anything; require one or the other to be strong.
            if not cuts and evidence.mass < 5:
                continue
            evidence_by_pair[(si, ci)] = evidence
            cuts_by_pair[(si, ci)] = cuts
            candidates.append(
                (si, ci, CUT_WEIGHT * len(cuts) + TITLE_WEIGHT * evidence.score)
            )

    chain = _monotone_chain(candidates)
    matches: list[ChapterMatch] = []
    used_sections: set[int] = set()
    used_chapters: set[int] = set()
    for si, ci, _score in chain:
        # One-to-one at chapter level: a section already spoken for cannot be
        # claimed again, nor can a chapter.
        if si in used_sections or ci in used_chapters:
            continue
        used_sections.add(si)
        used_chapters.add(ci)
        matches.append(
            ChapterMatch(
                section_index=si,
                chapter_index=ci,
                evidence=evidence_by_pair[(si, ci)],
                cuts=tuple(cuts_by_pair[(si, ci)]),
            )
        )
    return matches


# ---------------------------------------------------------------------------
# Khabar-level alignment inside one chapter
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Cut:
    """A confirmed alignment point: Arabic paragraph i starts where English
    paragraph j starts."""

    arabic_index: int
    english_index: int
    evidence: NameEvidence

    @property
    def confidence(self) -> float:
        if self.evidence.total == 0:
            return 0.0
        mass_factor = 1.0 if self.evidence.mass >= 12 else 0.85 if self.evidence.mass >= 8 else 0.7
        return round(self.evidence.score * mass_factor, 3)


def arabic_head(text: str, words: int = ARABIC_HEAD_WORDS) -> str:
    """The opening of an Arabic paragraph: isnad plus the first clause."""
    return " ".join(text.split()[:words])


def find_cuts(section: Section, chapter: EnglishChapter) -> list[Cut]:
    """Confirmed alignment points between one Arabic section and one chapter.

    A *cut* is a point where a new Arabic paragraph and a new English
    paragraph start together. Only transitions where BOTH indices advance
    are cuts: when Hitti splits one Arabic khabar into two paragraphs, the
    second English paragraph is not a cut, it is interior to the span; and
    when the Shamela edition fuses two akhbar, the second English paragraph
    matches material inside the Arabic paragraph rather than its head, and
    is likewise not a cut. Both fall out of testing head against head.
    """
    candidates: list[tuple[int, int, float]] = []
    evidence_by_pair: dict[tuple[int, int], NameEvidence] = {}
    for ei, english in enumerate(chapter.paragraphs):
        for ai, arabic in enumerate(section.paragraphs):
            evidence = name_evidence(english.isnad_head, arabic_head(arabic.text))
            if (
                evidence.score >= MIN_ANCHOR_SCORE
                and evidence.mass >= MIN_ANCHOR_MASS
                and evidence.strong_matches >= MIN_ANCHOR_STRONG_NAMES
            ):
                candidates.append((ai, ei, evidence.score * evidence.mass))
                evidence_by_pair[(ai, ei)] = evidence

    chain = _monotone_chain(candidates)
    cuts: list[Cut] = []
    for ai, ei, _ in chain:
        if cuts and (ai <= cuts[-1].arabic_index or ei <= cuts[-1].english_index):
            continue
        cuts.append(Cut(arabic_index=ai, english_index=ei, evidence=evidence_by_pair[(ai, ei)]))
    return cuts


@dataclass
class Span:
    """Text between two consecutive cuts, on both sides."""

    arabic_start: int
    arabic_end: int
    english_start: int
    english_end: int
    open_confidence: float
    close_confidence: float
    open_names: tuple[str, ...] = ()
    close_names: tuple[str, ...] = ()


def build_spans(section: Section, chapter: EnglishChapter, cuts: list[Cut]) -> list[Span]:
    """Spans running from each cut to the next.

    The final span runs from the last cut to the end of both sides. That
    tail is NOT bracketed on its right-hand side, so its close_confidence is
    0.0 and it is expected to be filtered out downstream -- an unbracketed
    tail is exactly the case where a silent truncation would hide.
    """
    if not cuts:
        return []
    spans: list[Span] = []
    for idx, cut in enumerate(cuts):
        if idx + 1 < len(cuts):
            nxt = cuts[idx + 1]
            spans.append(
                Span(
                    arabic_start=cut.arabic_index,
                    arabic_end=nxt.arabic_index,
                    english_start=cut.english_index,
                    english_end=nxt.english_index,
                    open_confidence=cut.confidence,
                    close_confidence=nxt.confidence,
                    open_names=cut.evidence.matched,
                    close_names=nxt.evidence.matched,
                )
            )
        else:
            spans.append(
                Span(
                    arabic_start=cut.arabic_index,
                    arabic_end=len(section.paragraphs),
                    english_start=cut.english_index,
                    english_end=len(chapter.paragraphs),
                    open_confidence=cut.confidence,
                    close_confidence=0.0,
                    open_names=cut.evidence.matched,
                )
            )
    return spans


# ---------------------------------------------------------------------------
# Passage assembly
# ---------------------------------------------------------------------------

# Target the two bands the current benchmark is thin on (schema.LENGTH_BANDS).
TARGET_MIN_WORDS = 100
TARGET_MAX_WORDS = 600
PREFERRED_MIN = 100


@dataclass
class Passage:
    work_id: str
    section_index: int
    section_title: str
    chapter_label: str
    chapter_title: str
    arabic: str
    english: str
    arabic_word_count: int
    english_word_count: int
    method: str
    confidence: float
    open_names: tuple[str, ...]
    close_names: tuple[str, ...]
    n_spans: int
    arabic_range: tuple[int, int]
    english_range: tuple[int, int]
    headings_stripped: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)

    @property
    def native_id(self) -> str:
        return (
            f"s{self.section_index:02d}"
            f"-a{self.arabic_range[0]:03d}_{self.arabic_range[1]:03d}"
            f"-e{self.english_range[0]:03d}_{self.english_range[1]:03d}"
        )

    @property
    def word_ratio(self) -> float:
        return (
            self.english_word_count / self.arabic_word_count
            if self.arabic_word_count
            else 0.0
        )


def _span_confidence(open_conf: float, close_conf: float, ratio: float) -> tuple[float, list[str]]:
    flags: list[str] = []
    confidence = min(open_conf, close_conf)
    if not (RATIO_LOW <= ratio <= RATIO_HIGH):
        flags.append(f"word_ratio_out_of_band:{ratio:.2f}")
        confidence *= 0.7
    return round(confidence, 3), flags


def assemble_passages(
    section: Section,
    chapter: EnglishChapter,
    spans: list[Span],
    min_words: int = TARGET_MIN_WORDS,
    max_words: int = TARGET_MAX_WORDS,
) -> list[Passage]:
    """Merge consecutive spans into band-sized passages.

    A passage always begins at a cut and ends at a cut, so both of its
    boundaries carry independent name evidence. Spans are merged greedily
    until the Arabic side reaches `min_words`; a merge that would exceed
    `max_words` is not taken, and a passage that never reaches `min_words`
    before running out of spans is dropped rather than emitted short.
    """
    # Only spans closed on the right can end a passage.
    usable = [s for s in spans if s.close_confidence > 0.0]
    passages: list[Passage] = []
    idx = 0
    while idx < len(usable):
        start = usable[idx]
        end_idx = idx
        arabic_words = 0
        while end_idx < len(usable):
            candidate_end = usable[end_idx]
            if candidate_end.arabic_start < start.arabic_start:
                break
            words = sum(
                p.word_count
                for p in section.paragraphs[start.arabic_start : candidate_end.arabic_end]
            )
            if words > max_words and arabic_words >= min_words:
                break
            arabic_words = words
            if arabic_words >= min_words:
                break
            end_idx += 1
        if end_idx >= len(usable) or arabic_words < min_words or arabic_words > max_words:
            idx = end_idx + 1
            continue

        end = usable[end_idx]
        ar_paras = section.paragraphs[start.arabic_start : end.arabic_end]
        en_paras = chapter.paragraphs[start.english_start : end.english_end]
        if not ar_paras or not en_paras:
            idx = end_idx + 1
            continue

        arabic_text = "\n\n".join(p.text for p in ar_paras)
        english_text = "\n\n".join(p.text for p in en_paras)
        en_words = sum(p.word_count for p in en_paras)
        ratio = en_words / arabic_words if arabic_words else 0.0
        confidence, flags = _span_confidence(
            start.open_confidence, end.close_confidence, ratio
        )
        passages.append(
            Passage(
                work_id=WORK_ID,
                section_index=section.index,
                section_title=section.title,
                chapter_label=chapter.label,
                chapter_title=chapter.title,
                arabic=arabic_text,
                english=english_text,
                arabic_word_count=arabic_words,
                english_word_count=en_words,
                method="structural",
                confidence=confidence,
                open_names=start.open_names,
                close_names=end.close_names,
                n_spans=end_idx - idx + 1,
                arabic_range=(start.arabic_start, end.arabic_end),
                english_range=(start.english_start, end.english_end),
                headings_stripped=[
                    p.heading_stripped for p in en_paras if p.heading_stripped
                ],
                flags=flags,
            )
        )
        idx = end_idx + 1
    return passages


# ---------------------------------------------------------------------------
# Top level
# ---------------------------------------------------------------------------


@dataclass
class ExtractionReport:
    arabic_sections: int
    english_chapters: int
    chapters_matched: int
    cuts_found: int
    passages: list[Passage]
    unmatched_sections: list[str]
    per_chapter: list[dict] = field(default_factory=list)


def _sanity_check_scripts(passages: list[Passage]) -> None:
    """Flag any passage whose 'Arabic' is not Arabic or 'English' not Latin.

    Cheap, but it is the check that catches the failure mode where a parser
    silently emits the wrong column and every downstream count still looks
    right.
    """
    arabic_re = re.compile(r"[؀-ۿ]")
    latin_re = re.compile(r"[A-Za-z]")
    for passage in passages:
        ar_chars = len(arabic_re.findall(passage.arabic))
        en_chars = len(latin_re.findall(passage.english))
        if ar_chars < 0.5 * len(passage.arabic.replace(" ", "")):
            passage.flags.append("arabic_side_not_arabic")
        if en_chars < 0.5 * len(passage.english.replace(" ", "")):
            passage.flags.append("english_side_not_latin")
        if arabic_re.search(passage.english):
            passage.flags.append("arabic_chars_in_english_side")


def extract(
    arabic_path: str | Path,
    english_path: str | Path,
    min_words: int = TARGET_MIN_WORDS,
    max_words: int = TARGET_MAX_WORDS,
) -> tuple[OpenITIText, list[EnglishChapter], ExtractionReport]:
    """Run the whole pipeline and return the parsed sides plus a report."""
    arabic = openiti_markdown.read(arabic_path)
    english_text = Path(english_path).read_text(encoding="utf-8", errors="replace")
    chapters = hitti_ocr.parse_chapters(english_text)

    matches = match_chapters(arabic, chapters)
    matched_sections = {m.section_index for m in matches}

    passages: list[Passage] = []
    per_chapter: list[dict] = []
    total_cuts = 0
    for match in matches:
        section = arabic.sections[match.section_index]
        chapter = chapters[match.chapter_index]
        cuts = list(match.cuts)
        total_cuts += len(cuts)
        spans = build_spans(section, chapter, cuts)
        chapter_passages = assemble_passages(
            section, chapter, spans, min_words=min_words, max_words=max_words
        )
        passages.extend(chapter_passages)
        per_chapter.append(
            {
                "section_index": match.section_index,
                "section_title": section.title,
                "chapter": chapter.label,
                "chapter_title": chapter.title,
                "title_confidence": round(match.confidence, 3),
                "arabic_paragraphs": len(section.paragraphs),
                "english_paragraphs": len(chapter.paragraphs),
                "cuts": len(cuts),
                "passages": len(chapter_passages),
            }
        )

    _sanity_check_scripts(passages)
    report = ExtractionReport(
        arabic_sections=len(arabic.sections),
        english_chapters=len(chapters),
        chapters_matched=len(matches),
        cuts_found=total_cuts,
        passages=passages,
        unmatched_sections=[
            s.title
            for s in arabic.sections
            if s.index not in matched_sections and not s.is_paratext and s.title
        ],
        per_chapter=per_chapter,
    )
    return arabic, chapters, report


def iter_pairs(
    arabic_path: str | Path,
    english_path: str | Path,
    min_confidence: float = 0.0,
) -> Iterator[dict]:
    """Yield benchmark candidate pairs, in the shared schema.

    Imported lazily inside the function so this module can be used for
    alignment work without pulling in the assembly stack.
    """
    from versed_translator.benchmark.sources.schema import make_pair

    _arabic, _chapters, report = extract(arabic_path, english_path)
    text = openiti_markdown.read(arabic_path)
    genre = text.book_subject
    died = text.author_died
    for passage in report.passages:
        if passage.confidence < min_confidence:
            continue
        yield make_pair(
            source="baladhuri_hitti",
            source_native_id=passage.native_id,
            work_id=WORK_ID,
            author=text.author_name,
            genre=genre,
            date_or_century=f"{died} AH" if died else None,
            arabic=passage.arabic,
            reference_english=passage.english,
            translator=TRANSLATOR,
            english_source=ENGLISH_SOURCE,
            rights_status=RIGHTS_STATUS,
            source_split=None,
            notes=(
                f"method={passage.method};confidence={passage.confidence};"
                f"section={passage.section_index};chapter={passage.chapter_label};"
                f"anchors_open={'/'.join(passage.open_names)};"
                f"anchors_close={'/'.join(passage.close_names)};"
                f"word_ratio={passage.word_ratio:.2f}"
                + (f";flags={','.join(passage.flags)}" if passage.flags else "")
            ),
        )


__all__ = [
    "ENGLISH_SOURCE",
    "RIGHTS_EVIDENCE",
    "RIGHTS_STATUS",
    "TRANSLATOR",
    "WORK_ID",
    "ChapterMatch",
    "Cut",
    "ExtractionReport",
    "Passage",
    "Span",
    "assemble_passages",
    "build_spans",
    "extract",
    "find_cuts",
    "iter_pairs",
    "match_chapters",
]

# Re-exported for callers that only want the paragraph type.
EnglishParagraph = EnglishParagraph
