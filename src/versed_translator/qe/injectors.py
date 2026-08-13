"""Adversarial error injectors — roadmap C4 / master-plan Phase 5.

Deliberately corrupt a *good* English translation in one specific, known way
so we can measure whether a QE system detects that exact failure. Passive
observation of naturally-occurring errors can't do this: you never know what
you failed to catch, because you don't have labels. Injection gives labels.

Design rules (each exists because the measurement is worthless otherwise):

1. **One injector, one failure mode.** No injector may introduce a second
   kind of corruption as a side effect, or the detection matrix stops
   attributing sensitivity correctly.
2. **Report failure honestly.** An injector returns ``None`` when the input
   doesn't contain the thing it corrupts (no numbers to change, no negation
   to delete). A "corruption" that silently changed nothing would be scored
   as an undetected error and would understate QE sensitivity — the single
   most dangerous bug this module could have.
3. **Deterministic.** Seeded RNG only; the same input yields the same
   corruption every run, so the matrix is reproducible.
4. **Substantive by construction.** Every injector changes *meaning* (or
   demonstrably breaks fidelity), never only style. A QE system that misses
   these is missing real errors, not cosmetic ones.

Severity reflects what a corpus-scale failure would cost a reader:
``critical`` inverts or fabricates meaning, ``major`` loses or distorts
material content, ``moderate`` degrades fidelity without erasing content.
"""

from __future__ import annotations

import random
import re
import warnings
from dataclasses import dataclass

# --- taxonomy ---------------------------------------------------------------
# Codes match the master plan's error taxonomy so the detection matrix and the
# QE router speak the same vocabulary.
OMISSION = "OMISSION"
ADDITION = "ADDITION"
NEGATION = "NEGATION"
ENTITY = "ENTITY"
NUMBER = "NUMBER"
TERMINOLOGY = "TERMINOLOGY"
QUOTATION = "QUOTATION"
REFERENCE = "REFERENCE"
STRUCTURE = "STRUCTURE"
REGISTER = "REGISTER"
FLUENCY = "FLUENCY"


@dataclass(frozen=True)
class Injection:
    """One corrupted variant of a source translation."""

    injector: str          # which injector produced it
    taxonomy: str          # error-taxonomy code
    severity: str          # critical | major | moderate
    original: str
    corrupted: str
    note: str              # human-readable description of what changed

    def changed(self) -> bool:
        return self.original != self.corrupted


# --- helpers ----------------------------------------------------------------

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")

# Negations whose deletion flips the claim. Deliberately excludes "no" as a
# bare token (too often part of a name or "no one" restructuring) — precision
# matters more than coverage here.
_NEGATIONS = ["not ", "never ", "cannot ", "n't ", " no longer "]

_NUMBER_RE = re.compile(r"\b\d+\b")

# Capitalised multi-word names, incl. Arabic transliteration particles. Used to
# find people to remove; the isnad injector reuses it for narrator chains.
_NAME_RE = re.compile(
    r"\b(?:[A-Z][a-z'’āīūḥṣḍṭẓ]+"
    r"(?:\s+(?:ibn|bin|bint|al-|b\.)\s*)?){2,}"
)

_HEDGES = [
    ("it is said that ", ""),
    ("it is reported that ", ""),
    ("perhaps ", ""),
    ("possibly ", ""),
    ("it seems ", ""),
    ("may be", "is"),
    ("might be", "is"),
    ("could be", "is"),
]

# Technical terms whose mistranslation is a real, documented failure mode for
# this corpus (seeded from versed's local_translation fidelity rules).
_TERM_SWAPS = [
    ("messenger", "prophet"),
    ("Messenger", "Prophet"),
    ("prayer", "supplication"),
    ("ablution", "washing"),
    ("pilgrimage", "journey"),
    ("charity", "donation"),
    ("faith", "religion"),
    ("mosque", "temple"),
]

_ARABIC_SAMPLE = "بسم الله"  # "bismillah"


def _sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_RE.split(text.strip()) if s.strip()]


# --- injectors --------------------------------------------------------------
# Every injector: (text, rng) -> Injection | None


def delete_negation(text: str, rng: random.Random) -> Injection | None:
    """Flip a claim by removing its negation. The highest-stakes corruption."""
    present = [n for n in _NEGATIONS if n in text]
    if not present:
        return None
    token = rng.choice(present)
    corrupted = text.replace(token, " " if token.startswith(" ") else "", 1)
    return Injection("delete_negation", NEGATION, "critical", text, corrupted,
                     f"removed negation {token.strip()!r}")


def change_number(text: str, rng: random.Random) -> Injection | None:
    """Alter a quantity — dates, counts, rak'ahs, hadith numbers."""
    matches = list(_NUMBER_RE.finditer(text))
    if not matches:
        return None
    m = rng.choice(matches)
    original_val = int(m.group())
    new_val = original_val + rng.choice([1, 2, 3, 10])
    corrupted = text[: m.start()] + str(new_val) + text[m.end():]
    return Injection("change_number", NUMBER, "major", text, corrupted,
                     f"changed {original_val} -> {new_val}")


def omit_person(text: str, rng: random.Random) -> Injection | None:
    """Delete a named person — attribution loss."""
    names = [m.group().strip() for m in _NAME_RE.finditer(text)]
    names = [n for n in names if len(n.split()) >= 2]
    if not names:
        return None
    name = rng.choice(names)
    corrupted = text.replace(name, "", 1)
    corrupted = re.sub(r"\s{2,}", " ", corrupted).strip()
    return Injection("omit_person", ENTITY, "major", text, corrupted,
                     f"removed person {name!r}")


def remove_isnad_narrator(text: str, rng: random.Random) -> Injection | None:
    """Break a chain of transmission by dropping one link.

    Distinct from ``omit_person``: targets the "X from Y" / "X narrated to us"
    scaffolding specifically, which is what makes a hadith chain auditable.
    """
    pattern = re.compile(
        r"(from\s+|on the authority of\s+)([A-Z][\w'’-]+(?:\s+(?:ibn|bin|b\.|al-)\s*[\w'’-]+)*)"
    )
    matches = list(pattern.finditer(text))
    if not matches:
        return None
    m = rng.choice(matches)
    corrupted = text[: m.start()] + text[m.end():]
    corrupted = re.sub(r"\s{2,}", " ", corrupted).strip()
    return Injection("remove_isnad_narrator", ENTITY, "critical", text, corrupted,
                     f"removed isnad link {m.group().strip()!r}")


def remove_clause(text: str, rng: random.Random) -> Injection | None:
    """Drop a whole sentence — the classic silent omission."""
    sents = _sentences(text)
    if len(sents) < 2:
        return None
    idx = rng.randrange(len(sents))
    dropped = sents.pop(idx)
    return Injection("remove_clause", OMISSION, "critical", text, " ".join(sents),
                     f"removed sentence {dropped[:60]!r}")


def mistranslate_term(text: str, rng: random.Random) -> Injection | None:
    """Swap a technical term for a plausible-but-wrong near-synonym."""
    applicable = [(a, b) for a, b in _TERM_SWAPS if re.search(rf"\b{re.escape(a)}\b", text)]
    if not applicable:
        return None
    src, dst = rng.choice(applicable)
    corrupted = re.sub(rf"\b{re.escape(src)}\b", dst, text, count=1)
    return Injection("mistranslate_term", TERMINOLOGY, "major", text, corrupted,
                     f"{src!r} -> {dst!r}")


def reverse_agent_patient(text: str, rng: random.Random) -> Injection | None:
    """Swap who did what to whom in an 'A ... to B' construction."""
    pattern = re.compile(
        r"([A-Z][\w'’-]+(?:\s+(?:ibn|bin|b\.)\s*[\w'’-]+)*)"
        r"(\s+\w+ed\s+(?:to|from)\s+)"
        r"([A-Z][\w'’-]+(?:\s+(?:ibn|bin|b\.)\s*[\w'’-]+)*)"
    )
    m = pattern.search(text)
    if not m:
        return None
    a, mid, b = m.group(1), m.group(2), m.group(3)
    corrupted = text[: m.start()] + b + mid + a + text[m.end():]
    return Injection("reverse_agent_patient", STRUCTURE, "critical", text, corrupted,
                     f"swapped {a!r} and {b!r}")


def hallucinate_prose(text: str, rng: random.Random) -> Injection | None:
    """Append confident explanatory content absent from the source."""
    additions = [
        " This ruling is unanimously agreed upon by all the schools of law.",
        " Scholars consider this the strongest opinion on the matter.",
        " This event took place in the second year after the migration.",
    ]
    return Injection("hallucinate_prose", ADDITION, "major", text,
                     text.rstrip() + rng.choice(additions),
                     "appended unsupported explanatory sentence")


def omit_quotation(text: str, rng: random.Random) -> Injection | None:
    """Drop quoted speech / scripture — a citation vanishing silently."""
    pattern = re.compile(r"[\"“‘']([^\"”’']{15,})[\"”’']")
    matches = list(pattern.finditer(text))
    if not matches:
        return None
    m = rng.choice(matches)
    corrupted = text[: m.start()] + text[m.end():]
    corrupted = re.sub(r"\s{2,}", " ", corrupted).strip()
    return Injection("omit_quotation", QUOTATION, "critical", text, corrupted,
                     f"removed quotation {m.group(1)[:50]!r}")


def duplicate_sentence(text: str, rng: random.Random) -> Injection | None:
    """Repeat a sentence — a degenerate-generation signature."""
    sents = _sentences(text)
    if not sents:
        return None
    idx = rng.randrange(len(sents))
    sents.insert(idx + 1, sents[idx])
    return Injection("duplicate_sentence", FLUENCY, "moderate", text, " ".join(sents),
                     "duplicated a sentence")


def leave_arabic_untranslated(text: str, rng: random.Random) -> Injection | None:
    """Leave source-language text in the output."""
    sents = _sentences(text)
    if not sents:
        return None
    idx = rng.randrange(len(sents))
    sents[idx] = _ARABIC_SAMPLE
    return Injection("leave_arabic_untranslated", OMISSION, "major", text, " ".join(sents),
                     "replaced a sentence with untranslated Arabic")


def certainty_inflation(text: str, rng: random.Random) -> Injection | None:
    """Turn hedged transmission into flat assertion — a fidelity failure
    that matters enormously for hadith, where uncertainty is the claim."""
    applicable = [(a, b) for a, b in _HEDGES if a in text.lower()]
    if not applicable:
        return None
    src, dst = rng.choice(applicable)
    pattern = re.compile(re.escape(src), re.IGNORECASE)
    corrupted = pattern.sub(dst, text, count=1).strip()
    corrupted = corrupted[:1].upper() + corrupted[1:] if corrupted else corrupted
    return Injection("certainty_inflation", REGISTER, "major", text, corrupted,
                     f"removed hedge {src.strip()!r}")


def collapse_paragraphs(text: str, rng: random.Random) -> Injection | None:
    """Merge paragraph boundaries — destroys alignment for the reader."""
    if "\n" not in text.strip():
        return None
    corrupted = re.sub(r"\n+", " ", text).strip()
    return Injection("collapse_paragraphs", STRUCTURE, "moderate", text, corrupted,
                     "collapsed paragraph breaks")


def alter_date(text: str, rng: random.Random) -> Injection | None:
    """Shift a date/year. Separate from change_number: dates carry
    historical claims, and a wrong year misplaces an event entirely."""
    pattern = re.compile(r"\b(year|AH|CE|AD)\s*(\d{1,4})\b|\b(\d{3,4})\s*(AH|CE|AD)\b")
    matches = list(pattern.finditer(text))
    if not matches:
        return None
    m = rng.choice(matches)
    span = m.group()
    nums = re.findall(r"\d+", span)
    old = nums[0]
    corrupted_span = span.replace(old, str(int(old) + rng.choice([1, 5, 10])), 1)
    corrupted = text[: m.start()] + corrupted_span + text[m.end():]
    return Injection("alter_date", NUMBER, "major", text, corrupted,
                     f"date {span!r} -> {corrupted_span!r}")


def alter_citation(text: str, rng: random.Random) -> Injection | None:
    """Change a scripture/source reference (e.g. 2:255 -> 2:260)."""
    pattern = re.compile(r"\b(\d{1,3}):(\d{1,3})\b")
    matches = list(pattern.finditer(text))
    if not matches:
        return None
    m = rng.choice(matches)
    new_verse = int(m.group(2)) + rng.choice([1, 2, 5])
    corrupted = text[: m.start()] + f"{m.group(1)}:{new_verse}" + text[m.end():]
    return Injection("alter_citation", REFERENCE, "major", text, corrupted,
                     f"citation {m.group()} -> {m.group(1)}:{new_verse}")


# All 15 master-plan corruption types.
INJECTORS = {
    "delete_negation": delete_negation,
    "change_number": change_number,
    "omit_person": omit_person,
    "remove_isnad_narrator": remove_isnad_narrator,
    "remove_clause": remove_clause,
    "mistranslate_term": mistranslate_term,
    "reverse_agent_patient": reverse_agent_patient,
    "hallucinate_prose": hallucinate_prose,
    "omit_quotation": omit_quotation,
    "duplicate_sentence": duplicate_sentence,
    "leave_arabic_untranslated": leave_arabic_untranslated,
    "certainty_inflation": certainty_inflation,
    "collapse_paragraphs": collapse_paragraphs,
    "alter_date": alter_date,
    "alter_citation": alter_citation,
}


def inject_all(text: str, seed: int = 0) -> list[Injection]:
    """Every injection that actually applies to `text`.

    Injectors that don't apply are skipped, not faked — see rule 2 in the
    module docstring. An injector that returned an unchanged string would be
    counted as an undetected error and would understate QE sensitivity.
    """
    out: list[Injection] = []
    for name, fn in INJECTORS.items():
        rng = random.Random(f"{seed}:{name}")
        try:
            inj = fn(text, rng)
        except Exception as exc:  # noqa: BLE001 — one bad injector must not sink the suite
            # Warn rather than swallow: a crashing injector silently drops its
            # error type from the detection matrix, which would read as
            # "nothing to detect" instead of "we failed to test this".
            warnings.warn(
                f"injector {name!r} raised {type(exc).__name__}: {exc}",
                RuntimeWarning,
                stacklevel=2,
            )
            continue
        if inj is not None and inj.changed():
            out.append(inj)
    return out
