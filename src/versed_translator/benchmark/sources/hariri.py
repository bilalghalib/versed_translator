"""Maqama-anchored proposals for al-Hariri's *Maqamat* against Chenery and
Steingass, *The Assemblies of Al Hariri*.

The bilateral unit is the **maqama**. Arabic marks them ``# | المقامة …``
(with two recovered exceptions: the first is a paragraph inside the preface
section, the fiftieth a paragraph inside the forty-ninth). English prints
``THE NTH ASSEMBLY, CALLED …``. Both sides independently number the same
fifty encounters, so pairing by sequence is an anchor, not a length guess.

Printed Arabic numerals in this witness are dirty (two "eighths", a
"eighteenth" that is the thirty-eighth). Sequence order is the pairing key;
the printed labels are recorded, never trusted.

Every maqama is longer than the 100–600 word bands (measured: Arabic min 609,
English min ~1000). Cuts *inside* a maqama have no second structural bracket,
so they are name-refined proportional proposals and carry ``llm_required``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from versed_translator.benchmark.sources import openiti_markdown, translit

WORK_ID = "0516IbnCaliHariri.Maqamat"
TRANSLATOR = "Thomas Chenery and F. Steingass"
ENGLISH_SOURCE = (
    "The Assemblies of Al Hariri, trans. Thomas Chenery (vols. I, 1867) and "
    "F. Steingass (vol. II, 1898); archive.org the-assembly-of-al-hariri-all-50, "
    "notes-free all-50 scan"
)
RIGHTS_STATUS = "PD_US_PRE_1930_PUBLICATION"
RIGHTS_EVIDENCE = (
    "English: Chenery 1867 (Williams and Norgate) and Steingass 1898 (Oriental "
    "Translation Fund); title page read inside the all-50 scan; both published "
    "pre-1930, so US public domain by publication date. Arabic: pre-modern text "
    "(author d. 516 AH) OpenITI PRIMARY_VERSION JK009202, cleaned of paratext. "
    "Neither claim is cleared legal advice; D6b still gates commercial use."
)

RATIO_TOLERANCE = 0.45
ANCHOR_WINDOW = 4
STRONG_SKELETON = translit.NameEvidence.STRONG_MIN_LEN
N_MAQAMAT = 50

_ORDINALS: tuple[str, ...] = (
    "FIRST",
    "SECOND",
    "THIRD",
    "FOURTH",
    "FIFTH",
    "SIXTH",
    "SEVENTH",
    "EIGHTH",
    "NINTH",
    "TENTH",
    "ELEVENTH",
    "TWELFTH",
    "THIRTEENTH",
    "FOURTEENTH",
    "FIFTEENTH",
    "SIXTEENTH",
    "SEVENTEENTH",
    "EIGHTEENTH",
    "NINETEENTH",
    "TWENTIETH",
    "TWENTY-FIRST",
    "TWENTY-SECOND",
    "TWENTY-THIRD",
    "TWENTY-FOURTH",
    "TWENTY-FIFTH",
    "TWENTY-SIXTH",
    "TWENTY-SEVENTH",
    "TWENTY-EIGHTH",
    "TWENTY-NINTH",
    "THIRTIETH",
    "THIRTY-FIRST",
    "THIRTY-SECOND",
    "THIRTY-THIRD",
    "THIRTY-FOURTH",
    "THIRTY-FIFTH",
    "THIRTY-SIXTH",
    "THIRTY-SEVENTH",
    "THIRTY-EIGHTH",
    "THIRTY-NINTH",
    "FORTIETH",
    "FORTY-FIRST",
    "FORTY-SECOND",
    "FORTY-THIRD",
    "FORTY-FOURTH",
    "FORTY-FIFTH",
    "FORTY-SIXTH",
    "FORTY-SEVENTH",
    "FORTY-EIGHTH",
    "FORTY-NINTH",
    "FIFTIETH",
)
_ORDINAL_TO_N = {name: index for index, name in enumerate(_ORDINALS, start=1)}
_ORDINAL_ALT = "|".join(sorted(_ORDINALS, key=len, reverse=True))
_ASSEMBLY_HEAD_RE = re.compile(
    rf"^THE\s+(?P<ordinal>{_ORDINAL_ALT})\s+ASSEMBLY\b",
    re.IGNORECASE | re.MULTILINE,
)
_RUNNING_HEAD_RE = re.compile(
    rf"^\s*\d*\s*(?:THE\s+)?(?:{_ORDINAL_ALT})\s+ASSEMBLY\b.*$",
    re.IGNORECASE,
)
_TRANSLATION_START_RE = re.compile(
    r"^[^\S\n]*_*Al\.?\s+\S{2,14},?\s+son\.?\s+of\.?\s+Hamm\S*,?\s+(?:related|narrated)\b",
    re.IGNORECASE | re.MULTILINE,
)
_ARGUMENT_LEAD_RE = re.compile(
    r"^(?:In this Assembly|This Assembly|This last|The scene of this Assembly|"
    r"The only reason for calling this Asse)\b",
    re.IGNORECASE,
)
_MAQAMA_OPENER_RE = re.compile(r"^المقامة")
_MAQAMA_FIFTY_RE = re.compile(r"^المقامة\s*الخمسون")
_HARITH_OPENER_RE = re.compile(r"^(?:حكى|حدث|قال|أخبر|روى)\s+الحارث\s+بن\s+همام")


@dataclass
class EnglishParagraph:
    index: int
    text: str

    @property
    def word_count(self) -> int:
        return len(self.text.split())


@dataclass
class Maqama:
    number: int
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
    maqama_number: int
    arabic_title: str
    english_title: str
    arabic_range: tuple[int, int]
    english_range: tuple[int, int]
    arabic: str
    english: str
    arabic_word_count: int
    english_word_count: int
    maqama_complete: bool
    structural_confidence: float
    confidence: float
    method: str = "maqama_anchored_proportional_cut"
    flags: list[str] = field(default_factory=lambda: ["llm_required"])
    llm_verdict: dict | None = None

    @property
    def native_id(self) -> str:
        start, end = self.arabic_range
        return f"m{self.maqama_number:02d}-a{start:03d}_{end:03d}"

    @property
    def word_ratio(self) -> float:
        return self.english_word_count / max(1, self.arabic_word_count)


@dataclass
class ExtractionReport:
    arabic_maqamat: int
    english_maqamat: int
    paired: int
    used: list[int]
    rejected: list[tuple[int, str]]
    passages: list[Passage]


def parse_english_ordinal(heading: str) -> int | None:
    match = _ASSEMBLY_HEAD_RE.search(heading)
    if not match:
        return None
    return _ORDINAL_TO_N.get(match.group("ordinal").upper().replace(" ", "-"))


def strip_running_heads(text: str) -> str:
    kept = [line for line in text.splitlines() if not _RUNNING_HEAD_RE.match(line)]
    return "\n".join(kept)


def drop_english_argument(body: str) -> str:
    """Drop Chenery's/Steingass's synopsis; keep from Al Harith's narration."""
    match = _TRANSLATION_START_RE.search(body)
    if match:
        return body[match.start() :]
    # One assembly (33) starts in media res with no Harith formula.
    blocks = [block for block in re.split(r"\n\s*\n", body) if block.strip()]
    dropped = 0
    while dropped < max(0, len(blocks) - 1):
        text = blocks[dropped].strip()
        title_remainder = len(text.split()) <= 12 and bool(
            re.search(r"CALLED|[“\"'](?:OF|THE) ", text, re.IGNORECASE)
        )
        if title_remainder or _ARGUMENT_LEAD_RE.match(text):
            dropped += 1
            continue
        break
    return "\n\n".join(blocks[dropped:]) if dropped else body


def parse_english_assemblies(text: str) -> list[tuple[int, str, str]]:
    """Return (number, heading, body) for each THE NTH ASSEMBLY block."""
    matches = list(_ASSEMBLY_HEAD_RE.finditer(text))
    assemblies: list[tuple[int, str, str]] = []
    seen: set[int] = set()
    for index, match in enumerate(matches):
        number = _ORDINAL_TO_N[match.group("ordinal").upper().replace(" ", "-")]
        if number in seen:
            continue
        seen.add(number)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        heading = text[match.start() : match.end()]
        body = drop_english_argument(strip_running_heads(text[match.end() : end]))
        assemblies.append((number, heading, body))
    return assemblies


def _paragraphs_from_body(body: str, start_index: int) -> list[EnglishParagraph]:
    blocks = [block.strip() for block in re.split(r"\n\s*\n", body) if block.strip()]
    return [
        EnglishParagraph(index=start_index + offset, text=re.sub(r"\s+", " ", block))
        for offset, block in enumerate(blocks)
    ]


def arabic_maqamat(
    text: openiti_markdown.OpenITIText,
) -> list[tuple[int, str, list[str]]]:
    """Fifty maqamat in document order, recovering the two unheaded ones."""
    if not text.sections:
        return []
    first_section = text.sections[0]
    split_at = next(
        (
            index
            for index, paragraph in enumerate(first_section.paragraphs)
            if _MAQAMA_OPENER_RE.match(paragraph.text)
            or _HARITH_OPENER_RE.match(paragraph.text)
        ),
        None,
    )
    maqamat: list[tuple[int, str, list[str]]] = []
    if split_at is not None:
        opener = first_section.paragraphs[split_at].text
        title = re.split(r"(?:حدث|حكى|قال|أخبر|روى)\s+الحارث", opener, maxsplit=1)[0]
        title = title.replace("$", " ").strip() or "المقامة الصنعانية"
        maqamat.append(
            (
                1,
                title,
                [paragraph.text for paragraph in first_section.paragraphs[split_at:]],
            )
        )

    if len(text.sections) == 1:
        return maqamat

    next_number = len(maqamat) + 1
    for section in text.sections[1:-1]:
        maqamat.append(
            (
                next_number,
                section.title,
                [paragraph.text for paragraph in section.paragraphs],
            )
        )
        next_number += 1

    last = text.sections[-1]
    fifty_at = next(
        (
            index
            for index, paragraph in enumerate(last.paragraphs)
            if _MAQAMA_FIFTY_RE.match(paragraph.text)
        ),
        None,
    )
    if fifty_at is None:
        maqamat.append((next_number, last.title, [p.text for p in last.paragraphs]))
        return maqamat
    maqamat.append(
        (
            49,
            last.title,
            [paragraph.text for paragraph in last.paragraphs[:fifty_at]],
        )
    )
    maqamat.append(
        (
            50,
            "المقامة الخمسون البصرية",
            [paragraph.text for paragraph in last.paragraphs[fifty_at:]],
        )
    )
    return maqamat


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


def _cut_maqama(
    maqama: Maqama,
    targets: tuple[int, ...],
    min_words: int,
) -> list[Passage]:
    arabic_weights = [len(paragraph.split()) for paragraph in maqama.arabic_paragraphs]
    english = maqama.english_paragraphs
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
                "\n".join(maqama.arabic_paragraphs[a_start:a_end]),
                "\n".join(maqama.arabic_paragraphs[a_end:]),
            )
        if e_end <= e_start:
            break
        arabic_text = "\n\n".join(maqama.arabic_paragraphs[a_start:a_end])
        english_text = "\n\n".join(p.text for p in english[e_start:e_end])
        complete = a_start == 0 and a_end == len(arabic_weights)
        structural = (
            0.85
            if complete
            else (0.7 if a_start == 0 or a_end == len(arabic_weights) else 0.6)
        )
        passages.append(
            Passage(
                maqama_number=maqama.number,
                arabic_title=maqama.arabic_title,
                english_title=maqama.english_title,
                arabic_range=(a_start, a_end),
                english_range=(e_start, e_end),
                arabic=arabic_text,
                english=english_text,
                arabic_word_count=len(arabic_text.split()),
                english_word_count=len(english_text.split()),
                maqama_complete=complete,
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
    arabic = arabic_maqamat(metadata)
    english_raw = Path(english_path).read_text(encoding="utf-8", errors="replace")
    english = parse_english_assemblies(english_raw)

    by_ar = {number: (title, paras) for number, title, paras in arabic}
    by_en: dict[int, tuple[str, list[EnglishParagraph]]] = {}
    cursor = 0
    for number, heading, body in english:
        paras = _paragraphs_from_body(body, cursor)
        by_en[number] = (heading.strip(), paras)
        cursor += len(paras)

    paired = sorted(set(by_ar) & set(by_en))
    english_words = sum(p.word_count for n in paired for p in by_en[n][1])
    arabic_words = sum(len(" ".join(by_ar[n][1]).split()) for n in paired)
    work_ratio = english_words / max(1, arabic_words)

    used: list[int] = []
    rejected: list[tuple[int, str]] = []
    passages: list[Passage] = []
    for number in paired:
        ar_title, ar_paras = by_ar[number]
        en_title, en_paras = by_en[number]
        maqama = Maqama(number, ar_title, en_title, ar_paras, en_paras)
        if (
            maqama.arabic_word_count < min_words
            or maqama.english_word_count < min_words
        ):
            rejected.append((number, "maqama too short on one side"))
            continue
        ratio = maqama.english_word_count / max(1, maqama.arabic_word_count)
        if work_ratio and abs(ratio - work_ratio) / work_ratio > RATIO_TOLERANCE:
            rejected.append(
                (number, f"word ratio {ratio:.2f} vs work {work_ratio:.2f}")
            )
            continue
        cuts = _cut_maqama(maqama, targets, min_words)
        if not cuts:
            rejected.append((number, "no passage could be cut"))
            continue
        used.append(number)
        passages.extend(cuts)

    return metadata, ExtractionReport(
        arabic_maqamat=len(arabic),
        english_maqamat=len(english),
        paired=len(paired),
        used=used,
        rejected=rejected,
        passages=passages,
    )


__all__ = [
    "ENGLISH_SOURCE",
    "N_MAQAMAT",
    "RIGHTS_EVIDENCE",
    "RIGHTS_STATUS",
    "TRANSLATOR",
    "WORK_ID",
    "EnglishParagraph",
    "ExtractionReport",
    "Maqama",
    "Passage",
    "arabic_maqamat",
    "drop_english_argument",
    "extract",
    "parse_english_assemblies",
    "parse_english_ordinal",
    "strip_running_heads",
]
