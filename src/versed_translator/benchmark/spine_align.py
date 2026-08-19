"""Option 1 probe: pair OpenITI ``### |`` units to English heading lines.

A heading is not a passage. This module only tests whether a bilateral
spine exists. Interior cuts stay out of scope.

Printed English numerals are recorded and not trusted (Hariri: two
"eighths"; Hamadhani OCR: XX for XI, XXXHX, XUV). After the running
headers and OCR wreckage are stripped, document order is the pairing
key — the same rule as Hariri. Transliteration and a small epithet
table only *confirm* those pairs; they do not invent them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from versed_translator.benchmark.sources.openiti_markdown import OpenITIText
from versed_translator.benchmark.sources.translit import (
    arabic_skeleton,
    latin_skeleton,
    name_evidence,
)

_ARABIC_MAQAMA_RE = re.compile(r"المقامة")
# Dirty roman (H/U for I/L), optional leading bullet, OF/OP, MAQAMA/MAQARIA.
_ENGLISH_HEAD_RE = re.compile(
    r"^\s*[•·\-*]?\s*"
    r"(?P<numeral>[IVXLCHU]+)\s*[.)]?\s*"
    r"(?:THE\s+)?MAQ[A-Z]{3,8}"
    r"(?:\s+O[FP])?\s+"
    r"(?P<title>.+?)\s*$",
    re.IGNORECASE,
)
_NOISE_RE = re.compile(
    r"\b(?:laid in|note on|text p|while the|origin and character)\b",
    re.IGNORECASE,
)
_AUTHOR_TITLE_RE = re.compile(
    r"\b(?:badi|badl|badt|bade|badf|badp|radi|zaman|hamadh|iskanderi)\b",
    re.IGNORECASE,
)
_TRAILING_JUNK_RE = re.compile(r"[\d*·•.,;:'’]+$")
_LATIN_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z'’ʿʻ-]*")

# English heading word -> Arabic letters expected in the OpenITI title.
# Metaphorical titles (Lion, Date, Poesie) never survive vowel-stripping.
_EPITHET_ARABIC: dict[str, str] = {
    "foesie": "القريض",
    "date": "الأزاذ",
    "lion": "الأسد",
    "blind": "المكفوف",
    "ape": "القرد",
    "amulet": "الحرز",
    "asylum": "المارستان",
    "famine": "المجاع",
    "exhortation": "الوعظ",
    "spindle": "المغزل",
    "butter": "النهيد",
    "knowledge": "العلم",
    "advice": "الوصي",
    "dinar": "الدينار",
    "dijsak": "الدينار",
    "poetry": "الشعر",
    "kings": "الملوك",
    "yellow": "الصفر",
    "wine": "الخمر",
    "quest": "المطلب",
    "tamin": "التميم",
    "nisiiarue": "النيسابور",  # OCR of Nishapur
}


@dataclass(frozen=True)
class ArabicUnit:
    index: int
    title: str
    word_count: int
    paragraph_count: int
    paragraphs: tuple[str, ...] = ()


@dataclass(frozen=True)
class EnglishUnit:
    index: int
    title: str
    printed_label: str
    line_no: int
    body: str = ""


@dataclass(frozen=True)
class Pair:
    arabic: ArabicUnit
    english: EnglishUnit
    evidence_mass: int
    method: str
    confirmation: str = ""


def _paragraph_texts(section) -> tuple[str, ...]:
    return tuple(paragraph.text for paragraph in section.paragraphs if paragraph.text.strip())


def _with_paragraphs(unit: ArabicUnit, extra: tuple[str, ...]) -> ArabicUnit:
    paragraphs = unit.paragraphs + extra
    return ArabicUnit(
        unit.index,
        unit.title,
        sum(len(text.split()) for text in paragraphs),
        len(paragraphs),
        paragraphs,
    )


def arabic_maqama_units(doc: OpenITIText) -> list[ArabicUnit]:
    """Keep ``### | ( المقامة … )`` headings. Fold a following body-only
    heading (no ``المقامة``) into the previous unit when that unit is empty.
    """
    units: list[ArabicUnit] = []
    pending: tuple[str, ...] = ()
    for section in doc.sections:
        if _ARABIC_MAQAMA_RE.search(section.title):
            if units and pending:
                units[-1] = _with_paragraphs(units[-1], pending)
                pending = ()
            texts = _paragraph_texts(section)
            units.append(
                ArabicUnit(
                    len(units) + 1,
                    section.title.strip(),
                    sum(len(text.split()) for text in texts),
                    len(texts),
                    texts,
                )
            )
        elif units:
            pending = pending + _paragraph_texts(section)
    if units and pending:
        units[-1] = _with_paragraphs(units[-1], pending)
    return units


def english_maqama_units(text: str) -> list[EnglishUnit]:
    """Chapter heads in document order. Page-number running headers, notes,
    and author-title lines are dropped. Dirty roman is kept as a label only.
    """
    units: list[EnglishUnit] = []
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or _NOISE_RE.search(line) or len(line) > 80:
            continue
        match = _ENGLISH_HEAD_RE.match(line)
        if not match:
            continue
        title = _TRAILING_JUNK_RE.sub("", match.group("title")).strip()
        if not title or _AUTHOR_TITLE_RE.search(title):
            continue
        units.append(
            EnglishUnit(
                index=len(units) + 1,
                title=title,
                printed_label=match.group("numeral") or "",
                line_no=line_no,
            )
        )
    return units


def _mass(arabic_title: str, english_title: str) -> int:
    return name_evidence(english_title, arabic_title, min_len=3).mass


def _epithet_hit(arabic_title: str, english_title: str) -> bool:
    blob = arabic_skeleton(arabic_title)
    for token in _LATIN_TOKEN_RE.findall(english_title):
        arabic = _EPITHET_ARABIC.get(token.lower().strip("'’ʿʻ"))
        if arabic and arabic_skeleton(arabic) in blob:
            return True
    return False


def _short_or_qaf_hit(arabic_title: str, english_title: str) -> bool:
    """Title-only: 2-consonant toponyms (KUFA) and qaf spelled Q (QAZWIN)."""
    blob_h = arabic_skeleton(arabic_title, "h")
    blob_t = arabic_skeleton(arabic_title, "t")
    for token in _LATIN_TOKEN_RE.findall(english_title):
        word = token.strip("'’ʿʻ")
        if len(word) < 3:
            continue
        for skeleton in {latin_skeleton(word), latin_skeleton(word).replace("q", "k")}:
            if len(skeleton) < 2:
                continue
            if skeleton in blob_h or skeleton in blob_t:
                return True
    return False


def confirm_pair(arabic_title: str, english_title: str) -> str:
    if _mass(arabic_title, english_title) >= 3:
        return "translit"
    if _epithet_hit(arabic_title, english_title):
        return "epithet"
    if _short_or_qaf_hit(arabic_title, english_title):
        return "short_or_qaf"
    return ""


def pair_by_index(
    arabic: list[ArabicUnit], english: list[EnglishUnit]
) -> list[Pair]:
    n = min(len(arabic), len(english))
    return [
        Pair(
            arabic[i],
            english[i],
            _mass(arabic[i].title, english[i].title),
            "index",
            confirm_pair(arabic[i].title, english[i].title),
        )
        for i in range(n)
    ]


def pair_by_sequence(
    arabic: list[ArabicUnit], english: list[EnglishUnit]
) -> list[Pair]:
    """Zip in document order. Safe only after both sides are the same unit."""
    return [
        Pair(
            ar,
            en,
            _mass(ar.title, en.title),
            "sequence",
            confirm_pair(ar.title, en.title),
        )
        for ar, en in zip(arabic, english, strict=False)
    ]


def pair_monotone(
    arabic: list[ArabicUnit],
    english: list[EnglishUnit],
    *,
    min_mass: int = 3,
) -> list[Pair]:
    """Greedy increasing match. Unconfirmed units are dropped, never guessed."""
    pairs: list[Pair] = []
    en_cursor = 0
    for ar in arabic:
        best_j = -1
        best_mass = 0
        for j in range(en_cursor, len(english)):
            mass = _mass(ar.title, english[j].title)
            if mass >= min_mass and mass > best_mass:
                best_mass = mass
                best_j = j
        if best_j >= 0:
            pairs.append(
                Pair(
                    ar,
                    english[best_j],
                    best_mass,
                    "translit_monotone",
                    "translit",
                )
            )
            en_cursor = best_j + 1
    return pairs


def report(arabic: list[ArabicUnit], english: list[EnglishUnit]) -> dict:
    indexed = pair_by_index(arabic, english)
    sequence = pair_by_sequence(arabic, english)
    monotone = pair_monotone(arabic, english)
    index_hits = sum(1 for pair in indexed if pair.evidence_mass >= 3)
    sequence_confirmed = sum(1 for pair in sequence if pair.confirmation)
    monotone_titles = {(p.arabic.index, p.english.title) for p in monotone}
    sequence_agrees = sum(
        1
        for pair in sequence
        if (pair.arabic.index, pair.english.title) in monotone_titles
    )
    return {
        "arabic_units": len(arabic),
        "english_units": len(english),
        "index_pairs": len(indexed),
        "index_translit_hits": index_hits,
        "sequence_pairs": len(sequence),
        "sequence_confirmed": sequence_confirmed,
        "sequence_unconfirmed": len(sequence) - sequence_confirmed,
        "monotone_pairs": len(monotone),
        "sequence_agrees_monotone": sequence_agrees,
        "arabic_unpaired": max(0, len(arabic) - len(sequence)),
        "english_unpaired": max(0, len(english) - len(sequence)),
        "empty_arabic": sum(1 for unit in arabic if unit.word_count == 0),
        "same_count": len(arabic) == len(english),
        "indexed": indexed,
        "sequence": sequence,
        "monotone": monotone,
    }
