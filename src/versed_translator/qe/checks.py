"""Deterministic fidelity checks — roadmap C5, targeted by the C4 matrix.

Every check here exists because COMETKiwi measurably failed to detect that
corruption (see `~/versed-translator-data/qe/tg27b-full/detection_matrix.md`):

| corruption            | COMETKiwi | check that covers it            |
|-----------------------|----------:|---------------------------------|
| mistranslate_term     |      0.8% | `terminology_violations`        |
| reverse_agent_patient |      9.1% | (not deterministically checkable — needs human/LLM review) |
| delete_negation       |     10.9% | `negation_parity`               |
| remove_isnad_narrator |     22.8% | `entity_coverage`               |
| remove_clause         |     22.9% | `length_ratio_flag`, `sentence_ratio_flag` |
| omit_quotation        |     27.5% | `quotation_coverage`            |
| leave_arabic_untr.    |     35.3% | `untranslated_arabic`           |
| duplicate_sentence    |     71.9% | `repetition_flag`               |

Design constraints, all learned the hard way this project:

* **Source-aware.** A check that only reads the output can't tell "the source
  had no negation" from "the translation dropped one". Every fidelity check
  compares source against output.
* **Arabic-aware counting.** Arabic negates with particles (لا/ما/لم/لن/ليس/غير)
  and English with a different set; a naive token diff is meaningless across
  languages. We compare *counts of negation markers*, which is crude but
  directionally sound and cheap.
* **Flag, never fail silently.** Each check returns a structured finding with
  a reason string. A check that can't run (missing source, empty output) says
  so via `applicable=False` rather than returning a passing verdict — the same
  rule that keeps the C4 injectors honest.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# --- shared patterns --------------------------------------------------------

_ARABIC_CHAR_RE = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_WORD_RE = re.compile(r"\b[\w'’-]+\b", re.UNICODE)

# English negation markers. Word-boundary matched so "cannot" and "can not"
# both count and "notable"/"nothing" do not.
_EN_NEGATIONS = re.compile(
    r"\b(?:not|no|never|neither|nor|none|cannot|without|nothing|nobody|nowhere)\b|n['’]t\b",
    re.IGNORECASE,
)

# Arabic negation particles. لا ما لم لن ليس غير بلا دون
_AR_NEGATIONS = re.compile(r"(?:\bلا\b|\bما\b|\bلم\b|\bلن\b|\bليس|\bغير\b|\bبلا\b|\bدون\b)")

# Digits: Western plus Arabic-Indic (٠-٩) and extended (۰-۹).
_WESTERN_DIGITS = re.compile(r"\d+")
_ARABIC_INDIC = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

_QUOTE_RE = re.compile(r"[\"“”«»‘’']")

# Capitalised runs = candidate named entities in the English output.
_EN_NAME_RE = re.compile(r"\b[A-Z][\w'’Ā-ſḀ-ỿ-]+(?:\s+(?:ibn|bin|bint|b\.|al-)\s*[\w'’-]+)*")


@dataclass
class Finding:
    """One check's verdict on one (source, output) pair."""

    check: str
    passed: bool
    applicable: bool = True
    severity: str = "major"      # critical | major | moderate
    detail: str = ""
    value: float | None = None

    def as_dict(self) -> dict:
        return {
            "check": self.check,
            "passed": self.passed,
            "applicable": self.applicable,
            "severity": self.severity,
            "detail": self.detail,
            "value": self.value,
        }


@dataclass
class CheckReport:
    findings: list[Finding] = field(default_factory=list)

    @property
    def failures(self) -> list[Finding]:
        return [f for f in self.findings if f.applicable and not f.passed]

    @property
    def critical_failures(self) -> list[Finding]:
        return [f for f in self.failures if f.severity == "critical"]

    def as_dict(self) -> dict:
        return {
            "n_checks": len(self.findings),
            "n_applicable": sum(1 for f in self.findings if f.applicable),
            "n_failed": len(self.failures),
            "n_critical_failed": len(self.critical_failures),
            "findings": [f.as_dict() for f in self.findings],
        }


# --- helpers ----------------------------------------------------------------

def _normalize_digits(text: str) -> str:
    return text.translate(_ARABIC_INDIC)


def _numbers(text: str) -> list[int]:
    return [int(m) for m in _WESTERN_DIGITS.findall(_normalize_digits(text))]


def _sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_SPLIT_RE.split(text.strip()) if s.strip()]


def _strip_diacritics(text: str) -> str:
    """Fold transliteration diacritics so 'Mughīrah' == 'Mughirah'.

    Models differ in transliteration style (Claude uses ī/ḥ, TranslateGemma
    doesn't); entity coverage must not punish a stylistic choice.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


# --- checks -----------------------------------------------------------------
# Each: (source_arabic, output_english) -> Finding


def negation_parity(source: str, output: str) -> Finding:
    """Catch a dropped (or invented) negation — COMETKiwi's worst blind spot.

    Counts negation markers on each side. Languages don't map 1:1, so this
    flags only a *material* mismatch: the English side carrying fewer than
    half the source's negations (dropped) or more than double (invented).
    """
    if not source.strip() or not output.strip():
        return Finding("negation_parity", passed=True, applicable=False,
                       severity="critical", detail="empty source or output")

    ar = len(_AR_NEGATIONS.findall(source))
    en = len(_EN_NEGATIONS.findall(output))

    if ar == 0 and en == 0:
        return Finding("negation_parity", passed=True, severity="critical",
                       detail="no negation on either side", value=0.0)
    if ar == 0:
        return Finding("negation_parity", passed=True, severity="critical",
                       detail=f"source has no negation marker; output has {en} (not necessarily wrong)",
                       value=float(en))

    ratio = en / ar
    if ratio < 0.5:
        return Finding("negation_parity", passed=False, severity="critical",
                       detail=f"possible dropped negation: {ar} in source, {en} in output",
                       value=round(ratio, 3))
    if ratio > 2.5:
        return Finding("negation_parity", passed=False, severity="critical",
                       detail=f"possible invented negation: {ar} in source, {en} in output",
                       value=round(ratio, 3))
    return Finding("negation_parity", passed=True, severity="critical",
                   detail=f"{ar} source / {en} output negation markers", value=round(ratio, 3))


def number_coverage(source: str, output: str) -> Finding:
    """Every number in the source should survive into the output.

    Handles Arabic-Indic digits. Numbers spelled as words in either language
    are out of scope — this deliberately under-claims rather than guessing.
    """
    src_nums = set(_numbers(source))
    if not src_nums:
        return Finding("number_coverage", passed=True, applicable=False,
                       severity="major", detail="no digits in source")
    out_nums = set(_numbers(output))
    missing = src_nums - out_nums
    if missing:
        return Finding("number_coverage", passed=False, severity="major",
                       detail=f"source numbers absent from output: {sorted(missing)}",
                       value=round(len(src_nums - missing) / len(src_nums), 3))
    return Finding("number_coverage", passed=True, severity="major",
                   detail=f"all {len(src_nums)} source numbers present", value=1.0)


def length_ratio_flag(source: str, output: str, low: float = 0.5, high: float = 3.0) -> Finding:
    """Gross length mismatch — the cheapest signal for a dropped clause.

    Arabic→English typically expands (measured mean ~1.5 on the TG27B run),
    so a ratio below ~0.5 suggests the output lost material.
    """
    src_words = len(_WORD_RE.findall(source))
    out_words = len(_WORD_RE.findall(output))
    if src_words == 0:
        return Finding("length_ratio_flag", passed=True, applicable=False,
                       severity="major", detail="empty source")
    ratio = out_words / src_words
    if ratio < low:
        return Finding("length_ratio_flag", passed=False, severity="major",
                       detail=f"output unusually short ({out_words}/{src_words} words) — possible omission",
                       value=round(ratio, 3))
    if ratio > high:
        return Finding("length_ratio_flag", passed=False, severity="moderate",
                       detail=f"output unusually long ({out_words}/{src_words} words) — possible hallucination",
                       value=round(ratio, 3))
    return Finding("length_ratio_flag", passed=True, severity="major",
                   detail=f"length ratio {ratio:.2f}", value=round(ratio, 3))


def untranslated_arabic(source: str, output: str) -> Finding:
    """Arabic script in the English output = untranslated fragment."""
    if not output.strip():
        return Finding("untranslated_arabic", passed=True, applicable=False,
                       severity="major", detail="empty output")
    hits = _ARABIC_CHAR_RE.findall(output)
    if hits:
        return Finding("untranslated_arabic", passed=False, severity="major",
                       detail=f"{len(hits)} Arabic characters remain in the English output",
                       value=float(len(hits)))
    return Finding("untranslated_arabic", passed=True, severity="major",
                   detail="no Arabic script in output", value=0.0)


def repetition_flag(source: str, output: str, min_len: int = 25) -> Finding:
    """Repeated sentences — degenerate generation."""
    sents = [s.strip().lower() for s in _sentences(output) if len(s.strip()) >= min_len]
    if len(sents) < 2:
        return Finding("repetition_flag", passed=True, applicable=False,
                       severity="moderate", detail="fewer than 2 scoreable sentences")
    dupes = len(sents) - len(set(sents))
    if dupes:
        return Finding("repetition_flag", passed=False, severity="moderate",
                       detail=f"{dupes} duplicated sentence(s) in output", value=float(dupes))
    return Finding("repetition_flag", passed=True, severity="moderate",
                   detail="no duplicated sentences", value=0.0)


def quotation_coverage(source: str, output: str) -> Finding:
    """Quotation marks present in the source should appear in the output.

    Crude by design: it counts quote characters rather than matching quoted
    spans across languages. Catches a wholesale dropped quotation, which is
    the failure the matrix showed COMETKiwi missing 72% of the time.
    """
    src_q = len(_QUOTE_RE.findall(source))
    if src_q == 0:
        return Finding("quotation_coverage", passed=True, applicable=False,
                       severity="critical", detail="no quotation marks in source")
    out_q = len(_QUOTE_RE.findall(output))
    if out_q == 0:
        return Finding("quotation_coverage", passed=False, severity="critical",
                       detail=f"source has {src_q} quote marks; output has none — possible dropped quotation",
                       value=0.0)
    return Finding("quotation_coverage", passed=True, severity="critical",
                   detail=f"{src_q} source / {out_q} output quote marks",
                   value=round(out_q / src_q, 3))


def sentence_ratio_flag(source: str, output: str, low: float = 0.5) -> Finding:
    """Output with far fewer sentences than the source suggests a dropped clause."""
    src_s = len(_sentences(source))
    out_s = len(_sentences(output))
    if src_s < 2:
        return Finding("sentence_ratio_flag", passed=True, applicable=False,
                       severity="major", detail="source has fewer than 2 sentences")
    ratio = out_s / src_s
    if ratio < low:
        return Finding("sentence_ratio_flag", passed=False, severity="major",
                       detail=f"output has {out_s} sentences vs {src_s} in source — possible omission",
                       value=round(ratio, 3))
    return Finding("sentence_ratio_flag", passed=True, severity="major",
                   detail=f"{src_s} source / {out_s} output sentences", value=round(ratio, 3))


def entity_coverage(
    source: str,
    output: str,
    reference_entities: set[str] | None = None,
) -> Finding:
    """Named entities that should appear in the output.

    Without an Arabic NER model we can't extract names from the source
    directly, so this is only applicable when the caller supplies expected
    entities (e.g. from an aligned reference or a prior clean translation).
    Returning `applicable=False` rather than a vacuous pass is deliberate:
    an unrun check must never read as a clean bill of health.
    """
    if not reference_entities:
        return Finding("entity_coverage", passed=True, applicable=False,
                       severity="critical",
                       detail="no expected-entity list supplied (needs Arabic NER or a reference)")
    folded_output = _strip_diacritics(output).lower()
    missing = {
        e for e in reference_entities
        if _strip_diacritics(e).lower() not in folded_output
    }
    if missing:
        return Finding("entity_coverage", passed=False, severity="critical",
                       detail=f"expected entities absent from output: {sorted(missing)}",
                       value=round(1 - len(missing) / len(reference_entities), 3))
    return Finding("entity_coverage", passed=True, severity="critical",
                   detail=f"all {len(reference_entities)} expected entities present", value=1.0)


def terminology_violations(
    source: str,
    output: str,
    glossary: dict[str, str] | None = None,
) -> Finding:
    """Glossary-conditioned terminology check.

    `glossary` maps a required English rendering -> a forbidden near-synonym
    (e.g. {"messenger": "prophet"}). Only applicable when a glossary is
    supplied; C12 builds the real versioned one.
    """
    if not glossary:
        return Finding("terminology_violations", passed=True, applicable=False,
                       severity="major", detail="no glossary supplied")
    lowered = output.lower()
    violations = [
        f"{forbidden!r} used where {required!r} expected"
        for required, forbidden in glossary.items()
        if re.search(rf"\b{re.escape(forbidden.lower())}\b", lowered)
        and not re.search(rf"\b{re.escape(required.lower())}\b", lowered)
    ]
    if violations:
        return Finding("terminology_violations", passed=False, severity="major",
                       detail="; ".join(violations), value=float(len(violations)))
    return Finding("terminology_violations", passed=True, severity="major",
                   detail="no glossary violations", value=0.0)


# Checks that need only (source, output).
CORE_CHECKS = [
    negation_parity,
    number_coverage,
    length_ratio_flag,
    untranslated_arabic,
    repetition_flag,
    quotation_coverage,
    sentence_ratio_flag,
]


def run_checks(
    source: str,
    output: str,
    reference_entities: set[str] | None = None,
    glossary: dict[str, str] | None = None,
) -> CheckReport:
    """Run every deterministic check over one (source, output) pair."""
    findings = [check(source, output) for check in CORE_CHECKS]
    findings.append(entity_coverage(source, output, reference_entities))
    findings.append(terminology_violations(source, output, glossary))
    return CheckReport(findings=findings)
