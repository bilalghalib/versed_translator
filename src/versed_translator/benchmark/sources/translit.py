"""Consonant-skeleton matching between Arabic script and 19th/20th-c. English
scholarly transliteration.

Why this exists: in Baladhuri/Hitti (and every other isnad-bearing work in
``corpus/PD_TRANSLATIONS.md``) the one thing that is genuinely shared between
the Arabic and the English sides of a passage is **proper names**. Hitti
transliterates ``الحسين بن الأسود`` as ``al-Husain ibn-al-Aswad``. Matching
those gives an alignment anchor that is *checkable* -- unlike a length-ratio
heuristic, which produces a systematically-shifted alignment that looks
perfectly plausible row by row.

The trick that makes this cheap: romanise Arabic letters to the SAME digraph
spellings the English side uses (``ث`` -> ``th``, ``خ`` -> ``kh``, ``ش`` ->
``sh``, ...), then delete vowels, ``w``/``y`` (long vowels far more often
than consonants in names), and hamza/'ayn from BOTH sides. Ambiguity that
would need special-casing then cancels out on its own:

    إسحاق -> s + h + k  = "shk"        Ishak  -> s,h,k         = "shk"
    هيثم  -> h + th + m = "hthm"       Haitham -> h,th,m       = "hthm"
    الخطاب -> kh + t + b = "khtb"      Khattab -> kh,t,t,b -> "khtb" (deduped)

Doubled letters are collapsed on both sides because Arabic script does not
write shadda in these texts while the transliteration doubles the letter.

Matching is by SUBSTRING CONTAINMENT of an English name skeleton inside the
Arabic head's concatenated skeleton. That is deliberate: it makes
``'Abdallah`` (one English token) match ``عبد الله`` (two Arabic tokens)
without any token-joining logic.

Nothing here is a general-purpose transliterator. It throws away enough
information to be useless for display and is only fit for anchor matching.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

# Arabic letter -> the spelling an English scholarly transliteration uses.
# Emphatics collapse onto their plain counterparts because Hitti's OCR'd
# text carries no underdots (ص and س are both "s" on the page).
_ARABIC_MAP: dict[str, str] = {
    "ب": "b",
    "ت": "t",
    "ث": "th",
    "ج": "j",
    "ح": "h",
    "خ": "kh",
    "د": "d",
    "ذ": "dh",
    "ر": "r",
    "ز": "z",
    "س": "s",
    "ش": "sh",
    "ص": "s",
    "ض": "d",
    "ط": "t",
    "ظ": "z",
    "ع": "",
    "غ": "gh",
    "ف": "f",
    "ق": "k",
    "ك": "k",
    "ل": "l",
    "م": "m",
    "ن": "n",
    "ه": "h",
    "ة": "h",  # see arabic_search_blob: also rendered "t" in a second pass
    "و": "",
    "ي": "",
    "ى": "",
    "ئ": "",
    "ؤ": "",
    "ء": "",
    "ا": "",
    "أ": "",
    "إ": "",
    "آ": "",
    "ٱ": "",
    "پ": "b",
    "چ": "j",
    "ژ": "z",
    "گ": "k",
}

_ARABIC_DIACRITICS_RE = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")
_ARABIC_TOKEN_RE = re.compile(r"[؀-ۿ]+")
_LATIN_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z'’ʿʻ-]*")
_LATIN_DROP_RE = re.compile(r"[aeiouwy'’ʿʻâîûāīū-]")
_DEDUPE_RE = re.compile(r"(.)\1+")

# Name-chain connectives and honorifics carry no identifying signal, so they
# are dropped before scoring. Keeping them would let every isnad "match"
# every other isnad on `ibn`/`al`/`abu` alone.
STOPWORD_SKELETONS: frozenset[str] = frozenset(
    {
        "",
        "b",
        "bn",
        "l",
        "n",
        "d",
        "t",
        "s",
        "m",
        "h",
        "f",
        "r",
        "k",
        # explicit chain words after skeletonisation
        "bd",  # abu / abi / abd on its own
        "mm",  # umm
        "bnt",  # bint
        "mwl",  # mawla
        "thn",  # 'an -> ""; guarded anyway by the length floor
    }
)

# English function words that appear inside Hitti's abridged isnad heads.
_FUNCTION_WORDS = """
    a an the and or of on in to us by from with for said says say related
    reported transmitted communicated authority tradition similar same
    ibn bin ben abu abi abd umm bint banu bani banul who whom which that
    was were is are has have had following certain men learned one his her
    their my me our we they he she it its also according quoted quoting
    version account another added addition further al el as at
"""

# Titles, epithets and religious vocabulary. Capitalised in Hitti but they
# are not identifying names -- "Prophet" occurs in nearly every paragraph on
# both sides and would inflate every anchor score.
_TITLE_WORDS = """
    allah god prophet messenger apostle caliph caliphate commander believers
    moslem moslems muslim muslims islam islamic jew jews jewish christian
    christians koran quran ansar emigrants companions lord day night year
    years month monday tuesday wednesday thursday friday saturday sunday
    only now thus then when whenever therefore however hence
"""

ENGLISH_STOPWORDS: frozenset[str] = frozenset(
    _FUNCTION_WORDS.split()
) | frozenset(_TITLE_WORDS.split())


def arabic_skeleton(text: str, ta_marbuta: str = "h") -> str:
    """Consonant skeleton of an Arabic string, all tokens concatenated.

    `ta_marbuta` controls how ``ة`` is rendered. It is genuinely ambiguous in
    transliteration -- ``عروة`` is "Urwah" but ``دومة الجندل`` is "Dumat
    al-Jandal", the construct state surfacing the t -- so callers that need
    to match either spelling should use `arabic_search_blob`.
    """
    text = _ARABIC_DIACRITICS_RE.sub("", text)
    out: list[str] = []
    for char in text:
        if char == "ة":
            out.append(ta_marbuta)
        elif char in _ARABIC_MAP:
            out.append(_ARABIC_MAP[char])
    return _DEDUPE_RE.sub(r"\1", "".join(out))


@lru_cache(maxsize=8192)
def arabic_search_blob(text: str) -> str:
    """Both ta-marbuta renderings of `text`, joined by a separator.

    Containment against this blob accepts either transliteration without the
    caller having to know which one Hitti reached for. The ``|`` separator
    is not in any skeleton, so no match can straddle the join.
    """
    return f"{arabic_skeleton(text, 'h')}|{arabic_skeleton(text, 't')}"


def arabic_token_skeletons(text: str) -> list[str]:
    """Per-token skeletons of an Arabic string (order preserved)."""
    text = _ARABIC_DIACRITICS_RE.sub("", text)
    return [arabic_skeleton(tok) for tok in _ARABIC_TOKEN_RE.findall(text)]


def latin_skeleton(token: str) -> str:
    """Consonant skeleton of one transliterated Latin token."""
    token = token.lower()
    token = _LATIN_DROP_RE.sub("", token)
    token = re.sub(r"[^a-z]", "", token)
    return _DEDUPE_RE.sub(r"\1", token)


def _is_name_cased(word: str) -> bool:
    """True if `word` reads as a proper name in this edition's typography.

    Normally that means an initial capital. The scan also sets some headings
    in full caps and drops the odd letter to lower case (``AL-jANDAL``), so a
    token that is mostly upper case counts too.
    """
    if word[0].isupper():
        return True
    uppers = sum(1 for c in word if c.isupper())
    return len(word) >= 3 and uppers >= len(word) / 2


@lru_cache(maxsize=8192)
def english_name_skeletons(text: str, min_len: int = 2) -> tuple[str, ...]:
    """Skeletons of the proper-name tokens in an English isnad head.

    Only name-cased tokens are considered: in Hitti's transliteration every
    proper name is capitalised and nothing else is, so this one test removes
    ordinary prose ("supposed", "father", "remnant") without needing an
    ever-growing stopword list. Chain particles are hyphen-separated
    (``ibn-al-Haitham``) and split before the test, so ``Haitham`` is kept
    while ``ibn`` and ``al`` are dropped.

    Skeletons shorter than `min_len` are dropped -- a single consonant
    matches almost any Arabic paragraph by chance and so is not evidence.
    """
    out: list[str] = []
    for raw in _LATIN_TOKEN_RE.findall(text):
        for part in raw.split("-"):
            word = part.strip("'’ʿʻ")
            if not word or word.lower() in ENGLISH_STOPWORDS:
                continue
            if not _is_name_cased(word):
                continue
            skeleton = latin_skeleton(word)
            if len(skeleton) < min_len or skeleton in STOPWORD_SKELETONS:
                continue
            out.append(skeleton)
    return tuple(out)


@dataclass(frozen=True)
class NameEvidence:
    """How much name evidence links an English head to an Arabic paragraph."""

    matched: tuple[str, ...]
    missed: tuple[str, ...]
    first_offset: int = -1
    """Skeleton-character offset of the earliest matched name in the Arabic,
    or -1 if nothing matched. Used to tell "this English paragraph opens the
    Arabic one" from "this English paragraph corresponds to something buried
    in the middle of it"."""
    blob_length: int = 0
    """Length of the Arabic skeleton the offset is measured against."""

    @property
    def head_fraction(self) -> float:
        """Where the earliest match sits, as a fraction of the Arabic
        paragraph. 0.0 means the very start; 1.0 means the very end."""
        if self.first_offset < 0 or self.blob_length <= 0:
            return 1.0
        return self.first_offset / self.blob_length

    @property
    def total(self) -> int:
        return len(self.matched) + len(self.missed)

    @property
    def score(self) -> float:
        """Fraction of English names found in the Arabic, 0.0-1.0."""
        return len(self.matched) / self.total if self.total else 0.0

    #: Skeletons shorter than this match a long Arabic paragraph by chance
    #: often enough to be worthless as evidence. Measured, not guessed: an
    #: anchor built from ('mt', 'fn', 'ld') -- Mu'ait, 'Affan, Walid -- once
    #: attached a Kufa-governors paragraph to an unrelated khabar about the
    #: Jund Shahanshah, and every count downstream still looked right.
    STRONG_MIN_LEN = 3

    @property
    def mass(self) -> int:
        """Skeleton characters matched, counting only strong skeletons.

        Used instead of a raw token count because a 2-consonant skeleton is
        far weaker evidence than a 5-consonant one, and counting tokens
        treats them alike.
        """
        return sum(len(s) for s in self.matched if len(s) >= self.STRONG_MIN_LEN)

    @property
    def strong_matches(self) -> int:
        """How many matched skeletons are long enough to be evidence."""
        return sum(1 for s in self.matched if len(s) >= self.STRONG_MIN_LEN)


def name_evidence(english_head: str, arabic_text: str, min_len: int = 2) -> NameEvidence:
    """Which English proper names occur in `arabic_text`.

    `arabic_text` should be the WHOLE Arabic paragraph, not just its head:
    the Shamela edition routinely fuses two or three akhbar into one
    paragraph, so a matching name can sit hundreds of words in.
    """
    variants = (arabic_skeleton(arabic_text, "h"), arabic_skeleton(arabic_text, "t"))
    matched: list[str] = []
    missed: list[str] = []
    first_offset = -1
    for skeleton in english_name_skeletons(english_head, min_len=min_len):
        offsets = [v.find(skeleton) for v in variants]
        found = [o for o in offsets if o >= 0]
        if found:
            matched.append(skeleton)
            best = min(found)
            if first_offset < 0 or best < first_offset:
                first_offset = best
        else:
            missed.append(skeleton)
    return NameEvidence(
        matched=tuple(matched),
        missed=tuple(missed),
        first_offset=first_offset,
        blob_length=len(variants[0]),
    )


def name_overlap(english_head: str, arabic_text: str, min_len: int = 2) -> tuple[int, int]:
    """(matched, total) English name skeletons found in the Arabic text."""
    evidence = name_evidence(english_head, arabic_text, min_len=min_len)
    return (len(evidence.matched), evidence.total)


def anchor_score(english_head: str, arabic_text: str, min_len: int = 2) -> float:
    """Fraction of English isnad names present in the Arabic text, 0.0-1.0.

    Returns 0.0 when the English head carries no usable names at all, so
    "no evidence" and "evidence says no" both score zero -- callers must
    look at `name_evidence` if they need to tell those apart.
    """
    return name_evidence(english_head, arabic_text, min_len=min_len).score
