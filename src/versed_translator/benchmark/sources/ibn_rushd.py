"""Treatise-anchored proposals for Ibn Rushd's *Fasl al-Maqal* and *Damima*
against Jamil-ur-Rehman's 1921 *Philosophy and Theology of Averroes*.

The bilateral unit is the **treatise**. English Gutenberg #65708 prints three:
Fasl, Damima (appendix), and Kashf. OpenITI ``0595IbnRushdHafid.FaslMaqal``
PRIMARY_VERSION JK010686 is Fasl + Damima only. Kashf is unpaired and dropped.
Do not invent Arabic.

Arabic marks the Damima by the salutation ``أدام الله عزتكم`` after Fasl.
English prints ``APPENDIX.`` then ``May God perpetuate your honour``. Pairing
by those independently recovered treatise identities is an anchor, not a
length guess.

Cuts *inside* a treatise have no second structural bracket, so they are
name-refined proportional proposals and carry ``llm_required``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from versed_translator.benchmark.sources import openiti_markdown, translit

WORK_ID = "0595IbnRushdHafid.FaslMaqal"
TRANSLATOR = "Mohammad Jamil-ur-Rehman"
ENGLISH_SOURCE = (
    "The Philosophy and Theology of Averroes, trans. Mohammad Jamil-ur-Rehman "
    "(Baroda: Gaekwad Studies in Religion and Philosophy XI, 1 January 1921); "
    "Project Gutenberg ebook 65708"
)
RIGHTS_STATUS = "PD_US_PRE_1930_PUBLICATION"
RIGHTS_EVIDENCE = (
    "English: Gutenberg #65708 title page reads Printed by Manibhai Mathurbhai "
    "Gupta at the Arya Sudharak Printing Press, Raopura, Baroda, and Published "
    "by A. G. Widgery, the College, Baroda, 1-1-1921; translator Mohammad "
    "Jamil-ur-Rehman. Published 1921, so US public domain by publication date. "
    "Arabic: pre-modern text (author d. 595 AH) OpenITI PRIMARY_VERSION "
    "JK010686, cleaned of paratext. Neither claim is cleared legal advice; "
    "D6b still gates commercial use."
)

RATIO_TOLERANCE = 0.45
ANCHOR_WINDOW = 4
STRONG_SKELETON = translit.NameEvidence.STRONG_MIN_LEN
PAIRABLE = ("fasl", "damima")
HEADING_MAX_WORDS = 8

_GUTENBERG_START_RE = re.compile(
    r"\*\*\*\s*START OF (?:THE PROJECT GUTENBERG EBOOK|THIS PROJECT GUTENBERG EBOOK).*\*\*\*",
    re.IGNORECASE,
)
_GUTENBERG_END_RE = re.compile(
    r"\*\*\*\s*END OF (?:THE PROJECT GUTENBERG EBOOK|THIS PROJECT GUTENBERG EBOOK).*\*\*\*",
    re.IGNORECASE,
)
_FOOTNOTE_MARK_RE = re.compile(r"\[(?:\d+|Footnote[^\]]*)\]", re.IGNORECASE)
_FOOTNOTES_RE = re.compile(r"(?m)^[^\S\n]*FOOTNOTES[^\S\n]*$")
_WS_RE = re.compile(r"\s+")

_FASL_OPEN = "And after: Praise be to God for all His praiseworthy"
_DAMIMA_OPEN = "May God perpetuate your honour"
_KASHF_OPEN = "And after--Praise be to God, who sets apart"
_DAMIMA_AR_RE = re.compile(r"أدام الله عزت")
_BASMALA_RE = re.compile(r"^بسم الله")


@dataclass
class EnglishParagraph:
    index: int
    text: str

    @property
    def word_count(self) -> int:
        return len(self.text.split())


@dataclass
class EnglishTreatise:
    treatise_id: str
    title: str
    text: str

    @property
    def word_count(self) -> int:
        return len(self.text.split())


@dataclass
class ArabicTreatise:
    treatise_id: str
    title: str
    paragraphs: list[str]

    @property
    def word_count(self) -> int:
        return sum(len(paragraph.split()) for paragraph in self.paragraphs)


@dataclass
class Treatise:
    treatise_id: str
    arabic_title: str
    english_title: str
    arabic_paragraphs: list[str]
    english_paragraphs: list[EnglishParagraph]

    @property
    def arabic_word_count(self) -> int:
        return sum(len(paragraph.split()) for paragraph in self.arabic_paragraphs)

    @property
    def english_word_count(self) -> int:
        return sum(paragraph.word_count for paragraph in self.english_paragraphs)


@dataclass
class Passage:
    treatise_id: str
    arabic_title: str
    english_title: str
    arabic_range: tuple[int, int]
    english_range: tuple[int, int]
    arabic: str
    english: str
    arabic_word_count: int
    english_word_count: int
    treatise_complete: bool
    structural_confidence: float
    confidence: float
    method: str = "treatise_anchored_proportional_cut"
    flags: list[str] = field(default_factory=lambda: ["llm_required"])
    llm_verdict: dict | None = None

    @property
    def native_id(self) -> str:
        start, end = self.arabic_range
        return f"{self.treatise_id}-a{start:03d}_{end:03d}"

    @property
    def word_ratio(self) -> float:
        return self.english_word_count / max(1, self.arabic_word_count)


@dataclass
class ExtractionReport:
    arabic_treatises: int
    english_treatises: int
    paired: int
    used: list[str]
    rejected: list[tuple[str, str]]
    unpaired_english: list[str]
    passages: list[Passage]


def gutenberg_body(text: str) -> str:
    """Keep the ebook body; drop the license wrapper when present."""
    start = _GUTENBERG_START_RE.search(text)
    end = _GUTENBERG_END_RE.search(text)
    if start and end and end.start() > start.end():
        return text[start.end() : end.start()]
    return text


def _clean_english(text: str) -> str:
    text = _FOOTNOTE_MARK_RE.sub(" ", text)
    text = text.replace("_", "")
    return _WS_RE.sub(" ", text).strip()


def parse_english_treatises(text: str) -> list[EnglishTreatise]:
    """Return Fasl, Damima, and Kashf bodies when those openers are present."""
    body = gutenberg_body(text)
    specs = (
        ("fasl", "A Decisive Discourse", _FASL_OPEN),
        ("damima", "Appendix: On Eternal Knowledge", _DAMIMA_OPEN),
        ("kashf", "An Exposition of the Methods of Argument", _KASHF_OPEN),
    )
    found: list[tuple[str, str, int]] = []
    for treatise_id, title, opener in specs:
        index = body.find(opener)
        if index >= 0:
            found.append((treatise_id, title, index))
    treatises: list[EnglishTreatise] = []
    for index, (treatise_id, title, start) in enumerate(found):
        end = len(body)
        for later_start in (item[2] for item in found[index + 1 :]):
            end = min(end, later_start)
        footnotes = _FOOTNOTES_RE.search(body, start + 1)
        if footnotes:
            end = min(end, footnotes.start())
        cleaned = _clean_english(body[start:end])
        if cleaned:
            treatises.append(EnglishTreatise(treatise_id, title, cleaned))
    return treatises


def _is_editorial_heading(text: str) -> bool:
    if _DAMIMA_AR_RE.search(text) or text.startswith("أما بعد"):
        return False
    if _BASMALA_RE.match(text):
        return True
    return len(text.split()) <= HEADING_MAX_WORDS


def _body_paragraphs(paragraphs: list[str]) -> list[str]:
    return [
        paragraph for paragraph in paragraphs if not _is_editorial_heading(paragraph)
    ]


def arabic_treatises(text: openiti_markdown.OpenITIText) -> list[ArabicTreatise]:
    """Fasl, then Damima when the salutation is present. Headings dropped."""
    paragraphs = [
        paragraph.text for paragraph in text.all_paragraphs if paragraph.text.strip()
    ]
    if not paragraphs:
        return []
    damima_at = next(
        (
            index
            for index, paragraph in enumerate(paragraphs)
            if _DAMIMA_AR_RE.search(paragraph)
        ),
        None,
    )
    if damima_at is None:
        body = _body_paragraphs(paragraphs)
        return [ArabicTreatise("fasl", "Fasl al-Maqal", body)] if body else []

    fasl_end = damima_at
    while fasl_end > 0 and _is_editorial_heading(paragraphs[fasl_end - 1]):
        fasl_end -= 1
    fasl = _body_paragraphs(paragraphs[:fasl_end])
    damima = _body_paragraphs(paragraphs[damima_at:])
    out: list[ArabicTreatise] = []
    if fasl:
        out.append(ArabicTreatise("fasl", "Fasl al-Maqal", fasl))
    if damima:
        out.append(ArabicTreatise("damima", "Damima", damima))
    return out


def _paragraphs_from_body(body: str, start_index: int) -> list[EnglishParagraph]:
    blocks = [block.strip() for block in re.split(r"\n\s*\n", body) if block.strip()]
    if not blocks:
        cleaned = _clean_english(body)
        return [EnglishParagraph(index=start_index, text=cleaned)] if cleaned else []
    # parse_english_treatises already collapsed whitespace, so one block is typical.
    if len(blocks) == 1:
        sentences = re.split(r"(?<=[.!?])\s+", blocks[0])
        grouped: list[str] = []
        bucket: list[str] = []
        count = 0
        for sentence in sentences:
            bucket.append(sentence)
            count += len(sentence.split())
            if count >= 40:
                grouped.append(" ".join(bucket))
                bucket, count = [], 0
        if bucket:
            grouped.append(" ".join(bucket))
        blocks = grouped or blocks
    return [
        EnglishParagraph(index=start_index + offset, text=_clean_english(block))
        for offset, block in enumerate(blocks)
        if _clean_english(block)
    ]


def _prefix(weights: list[int]) -> list[int]:
    out = [0]
    for weight in weights:
        out.append(out[-1] + weight)
    return out


def _nearest_boundary(prefix: list[int], total: int, fraction: float, low: int) -> int:
    best = low + 1
    best_gap = float("inf")
    for index in range(low + 1, len(prefix)):
        gap = abs(prefix[index] / max(1, total) - fraction)
        if gap < best_gap:
            best_gap = gap
            best = index
    return best


def _anchor_gain(english_text: str, arabic_text: str) -> float:
    evidence = translit.name_evidence(english_text, arabic_text)
    matched = sum(len(s) for s in evidence.matched if len(s) >= STRONG_SKELETON)
    missed = sum(len(s) for s in evidence.missed if len(s) >= STRONG_SKELETON)
    return float(matched - missed)


def _refine_boundary(
    english: list[EnglishParagraph],
    guess: int,
    low: int,
    high: int,
    arabic_before: str,
    arabic_after: str,
    window: int = ANCHOR_WINDOW,
) -> int:
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
        if score > best_score or (
            score == best_score and abs(candidate - guess) < abs(best_index - guess)
        ):
            best_score = score
            best_index = candidate
    return best_index


def _cut_treatise(
    treatise: Treatise,
    targets: tuple[int, ...],
    min_words: int,
) -> list[Passage]:
    arabic_weights = [
        len(paragraph.split()) for paragraph in treatise.arabic_paragraphs
    ]
    english = treatise.english_paragraphs
    english_weights = [paragraph.word_count for paragraph in english]
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
                guess,
                e_start + 1,
                len(english_weights),
                "\n".join(treatise.arabic_paragraphs[a_start:a_end]),
                "\n".join(treatise.arabic_paragraphs[a_end:]),
            )
        if e_end <= e_start:
            break
        arabic_text = "\n\n".join(treatise.arabic_paragraphs[a_start:a_end])
        english_text = "\n\n".join(p.text for p in english[e_start:e_end])
        complete = a_start == 0 and a_end == len(arabic_weights)
        structural = (
            0.85
            if complete
            else (0.7 if a_start == 0 or a_end == len(arabic_weights) else 0.6)
        )
        passages.append(
            Passage(
                treatise_id=treatise.treatise_id,
                arabic_title=treatise.arabic_title,
                english_title=treatise.english_title,
                arabic_range=(a_start, a_end),
                english_range=(e_start, e_end),
                arabic=arabic_text,
                english=english_text,
                arabic_word_count=len(arabic_text.split()),
                english_word_count=len(english_text.split()),
                treatise_complete=complete,
                structural_confidence=structural,
                confidence=structural,
            )
        )
        a_start, e_start = a_end, e_end
        step += 1
    return passages


def extract(
    arabic_path: str | Path,
    english_path: str | Path,
    *,
    targets: tuple[int, ...] = (170, 330),
    min_words: int = 100,
) -> tuple[openiti_markdown.OpenITIText, ExtractionReport]:
    metadata = openiti_markdown.read(arabic_path)
    arabic = arabic_treatises(metadata)
    english_raw = Path(english_path).read_text(encoding="utf-8", errors="replace")
    english = parse_english_treatises(english_raw)

    by_ar = {item.treatise_id: item for item in arabic}
    by_en: dict[str, tuple[EnglishTreatise, list[EnglishParagraph]]] = {}
    cursor = 0
    for item in english:
        paras = _paragraphs_from_body(item.text, cursor)
        by_en[item.treatise_id] = (item, paras)
        cursor += len(paras)

    paired = [key for key in PAIRABLE if key in by_ar and key in by_en]
    unpaired_english = [
        item.treatise_id for item in english if item.treatise_id not in by_ar
    ]
    english_words = sum(p.word_count for key in paired for p in by_en[key][1])
    arabic_words = sum(by_ar[key].word_count for key in paired)
    work_ratio = english_words / max(1, arabic_words)

    used: list[str] = []
    rejected: list[tuple[str, str]] = []
    passages: list[Passage] = []
    for treatise_id in paired:
        ar = by_ar[treatise_id]
        en_item, en_paras = by_en[treatise_id]
        treatise = Treatise(
            treatise_id,
            ar.title,
            en_item.title,
            ar.paragraphs,
            en_paras,
        )
        if (
            treatise.arabic_word_count < min_words
            or treatise.english_word_count < min_words
        ):
            rejected.append((treatise_id, "treatise too short on one side"))
            continue
        ratio = treatise.english_word_count / max(1, treatise.arabic_word_count)
        if work_ratio and abs(ratio - work_ratio) / work_ratio > RATIO_TOLERANCE:
            rejected.append(
                (treatise_id, f"word ratio {ratio:.2f} vs work {work_ratio:.2f}")
            )
            continue
        cuts = _cut_treatise(treatise, targets, min_words)
        if not cuts:
            rejected.append((treatise_id, "no passage could be cut"))
            continue
        used.append(treatise_id)
        passages.extend(cuts)

    return metadata, ExtractionReport(
        arabic_treatises=len(arabic),
        english_treatises=len(english),
        paired=len(paired),
        used=used,
        rejected=rejected,
        unpaired_english=unpaired_english,
        passages=passages,
    )


__all__ = [
    "ENGLISH_SOURCE",
    "PAIRABLE",
    "RIGHTS_EVIDENCE",
    "RIGHTS_STATUS",
    "TRANSLATOR",
    "WORK_ID",
    "ArabicTreatise",
    "EnglishParagraph",
    "EnglishTreatise",
    "ExtractionReport",
    "Passage",
    "Treatise",
    "arabic_treatises",
    "extract",
    "gutenberg_body",
    "parse_english_treatises",
]
