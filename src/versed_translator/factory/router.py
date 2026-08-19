"""Factory cascade: source gate, deterministic check, escalate without overwrite.

The learned *source* router stays parked. This module is the implementable
policy: verse/sajʿ/metalinguistic → Flash; otherwise Lite; if checks fail,
keep Lite *and* fetch Flash. Non-nested errors (Lite pass / Flash fail)
mean escalation must not blindly replace Lite.

The first classifier is this check layer, not a neural publishable-Y/N
model. Fable/Gemini labels are analysis-only (`train_eligible=false`).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from versed_translator.factory.glossary import (
    GlossaryEntry,
    glossary_contradictions,
    retrieve_for_passage,
)
from versed_translator.qe.checks import run_checks

VERSE_HINTS = {"verse", "saj_maqama", "metalinguistic"}

CHECK_FLAG = {
    "untranslated_arabic": "ARABIC_LEAK",
    "length_ratio_flag": "LENGTH",
    "number_coverage": "NUMBER_DIGIT",
    "sentence_ratio_flag": "OMISSION_STRUCT",
    "negation_parity": "NEGATION",
    "repetition_flag": "REPETITION",
    "quotation_coverage": "QUOTE",
}


@dataclass
class RouteDecision:
    primary: str  # flash_lite | flash
    reason: str
    escalate: bool
    keep_alternate: bool
    check_fails: list[str] = field(default_factory=list)
    glossary_hits: int = 0


def source_route(register_hint: str) -> RouteDecision:
    hint = (register_hint or "").strip().lower()
    if hint in VERSE_HINTS or "verse" in hint or "maqama" in hint:
        return RouteDecision(
            primary="flash",
            reason="source_gate_verse_or_saj",
            escalate=False,
            keep_alternate=False,
        )
    return RouteDecision(
        primary="flash_lite",
        reason="default_lite",
        escalate=False,
        keep_alternate=False,
    )


def _empty_english(english: str) -> bool:
    text = (english or "").strip()
    return (not text) or text.lower() in {"nan", "none", "null", "n/a"}


def check_output(
    arabic: str,
    english: str,
    *,
    book: str = "",
    glossary: list[GlossaryEntry] | None = None,
) -> list[str]:
    """Deterministic publication-risk flags. Empty list ≠ human-gold OK."""
    fails: list[str] = []
    if _empty_english(english):
        fails.append("MISSING")
    report = run_checks(arabic or "", english or "")
    for finding in report.findings:
        if finding.check in {"entity_coverage", "terminology_violations"}:
            continue
        if finding.applicable and not finding.passed:
            fails.append(CHECK_FLAG.get(finding.check, finding.check.upper()))
    hits = retrieve_for_passage(glossary or [], arabic, book=book or None)
    if glossary_contradictions(english, hits):
        fails.append("GLOSSARY_WRONG")
    return fails


def cascade_after_lite(
    arabic: str,
    lite_english: str,
    *,
    register_hint: str = "",
    book: str = "",
    glossary: list[GlossaryEntry] | None = None,
) -> RouteDecision:
    """Decide whether to *also* run Flash. Never silently drop Lite."""
    source = source_route(register_hint)
    if source.primary == "flash":
        return source
    fails = check_output(arabic, lite_english, book=book, glossary=glossary)
    hits = retrieve_for_passage(glossary or [], arabic, book=book or None)
    if fails:
        return RouteDecision(
            primary="flash_lite",
            reason="lite_check_fail_keep_both",
            escalate=True,
            keep_alternate=True,
            check_fails=fails,
            glossary_hits=len(hits),
        )
    return RouteDecision(
        primary="flash_lite",
        reason="lite_checks_clean",
        escalate=False,
        keep_alternate=False,
        glossary_hits=len(hits),
    )


def pick_auto(
    decision: RouteDecision,
    *,
    flash_check_fails: list[str] | None = None,
) -> tuple[str, str]:
    """Implementable pick. Returns (system_id, queue) with queue auto|human.

    Does not consult gold labels. Ships Flash after a Lite-check fail only
    when Flash's own checks are clean. If both look dirty, keep Lite and
    queue a human — do not overwrite.
    """
    if decision.primary == "flash" and not decision.escalate:
        return "flash", "auto"
    if not decision.escalate:
        return "flash_lite", "auto"
    if not (flash_check_fails or []):
        return "flash", "auto"
    return "flash_lite", "human"


def pick_accepted(
    decision: RouteDecision,
    *,
    lite_ok: bool | None,
    flash_ok: bool | None,
) -> str:
    """Oracle pick using known ok flags. Not an implementable cascade."""
    if decision.primary == "flash" and not decision.escalate:
        return "flash"
    if not decision.escalate:
        return "flash_lite"
    if lite_ok is False and flash_ok is True:
        return "flash"
    if lite_ok is True:
        return "flash_lite"
    if flash_ok is True:
        return "flash"
    return "flash_lite"
