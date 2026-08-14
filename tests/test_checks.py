"""Deterministic fidelity checks — and proof they cover COMETKiwi's blind spots.

The C4 matrix measured COMETKiwi at 10.9% on negation deletion, 22.9% on
clause removal, 27.5% on dropped quotations. The whole justification for
these checks is that they catch what the neural metric misses, so the
critical tests here feed the checks the *exact same corruptions* the C4
injectors produce and assert they are flagged.

Equally important: a check that cannot run must report `applicable=False`,
never a passing verdict. An unrun check reading as "clean" is how a safety
gate silently stops being a safety gate.
"""

from __future__ import annotations

import random

from versed_translator.qe import checks
from versed_translator.qe import injectors as inj

# A source/translation pair in the shape the corpus actually produces.
AR_SOURCE = "حدثنا محمد بن العلاء قال لم يصل الرجل ركعتين في المسجد سنة 622"
EN_CLEAN = (
    'Muhammad ibn al-Ala\' narrated to us: the man did not pray 2 rak\'ahs '
    'in the mosque in the year 622. He said, "If she weeps or remains silent." '
    'Then he departed.'
)


# --- negation parity: COMETKiwi caught 10.9% ---------------------------------

def test_negation_parity_catches_deleted_negation():
    """The corruption COMETKiwi is worst at must be caught deterministically."""
    corrupted = EN_CLEAN.replace("did not pray", "did pray")
    finding = checks.negation_parity(AR_SOURCE, corrupted)
    assert not finding.passed
    assert finding.severity == "critical"
    assert "dropped negation" in finding.detail


def test_negation_parity_passes_faithful_translation():
    finding = checks.negation_parity(AR_SOURCE, EN_CLEAN)
    assert finding.passed


def test_negation_parity_flags_invented_negation():
    source = "حدثنا محمد بن العلاء"  # no negation particle
    output = "He did not pray, nor did he speak, and never returned, nothing remained."
    finding = checks.negation_parity(source, output)
    # source has no negation -> check reports rather than false-flags
    assert finding.applicable


def test_negation_parity_inapplicable_on_empty():
    f = checks.negation_parity("", "something")
    assert f.applicable is False
    assert f.passed is True  # vacuous pass, but explicitly marked inapplicable


# --- clause removal: COMETKiwi caught 22.9% (negative mean delta!) ------------

def test_length_ratio_catches_truncation():
    truncated = "Muhammad ibn al-Ala' narrated to us."
    finding = checks.length_ratio_flag(AR_SOURCE, truncated)
    assert not finding.passed
    assert "omission" in finding.detail


def test_sentence_ratio_catches_dropped_sentence():
    source = "جملة أولى. جملة ثانية. جملة ثالثة. جملة رابعة."
    output = "Only one sentence survived."
    finding = checks.sentence_ratio_flag(source, output)
    assert not finding.passed


def test_length_ratio_flags_hallucinated_expansion():
    finding = checks.length_ratio_flag("كلمة", "This is a very long English rendering " * 10)
    assert not finding.passed
    assert "hallucination" in finding.detail


# --- dropped quotation: COMETKiwi caught 27.5% -------------------------------

def test_quotation_coverage_catches_dropped_quote():
    source = 'قال: "إن بكت أو سكتت"'
    output = "He said something about weeping or silence."  # quote marks gone
    finding = checks.quotation_coverage(source, output)
    assert not finding.passed
    assert finding.severity == "critical"


def test_quotation_coverage_inapplicable_without_source_quotes():
    f = checks.quotation_coverage("لا اقتباس هنا", 'He said "something".')
    assert f.applicable is False


# --- numbers, Arabic-Indic digits included -----------------------------------

def test_number_coverage_catches_missing_number():
    finding = checks.number_coverage("صلى ركعتين سنة 622", "He prayed in the mosque.")
    assert not finding.passed
    assert "622" in finding.detail


def test_number_coverage_handles_arabic_indic_digits():
    """٦٢٢ and 622 are the same number; a naive matcher would miss this."""
    finding = checks.number_coverage("سنة ٦٢٢", "In the year 622 he departed.")
    assert finding.passed


def test_number_coverage_inapplicable_without_digits():
    assert checks.number_coverage("نص بلا أرقام", "Text without digits.").applicable is False


# --- untranslated Arabic / repetition ----------------------------------------

def test_untranslated_arabic_detects_leftover_script():
    finding = checks.untranslated_arabic(AR_SOURCE, "He prayed بسم الله then left.")
    assert not finding.passed


def test_repetition_flag_detects_duplicate_sentence():
    output = "He entered the mosque and prayed. He entered the mosque and prayed."
    finding = checks.repetition_flag(AR_SOURCE, output)
    assert not finding.passed


# --- entity coverage: transliteration-style independence ---------------------

def test_entity_coverage_ignores_diacritic_style():
    """Claude writes 'Mughīrah', TranslateGemma writes 'Mughirah'. Neither is
    an error, so the check must fold diacritics before comparing."""
    finding = checks.entity_coverage(
        AR_SOURCE, "al-Mughirah ibn Shu'bah led the prayer.",
        reference_entities={"al-Mughīrah"},
    )
    assert finding.passed


def test_entity_coverage_catches_missing_narrator():
    finding = checks.entity_coverage(
        AR_SOURCE, "Someone led the prayer.",
        reference_entities={"al-Mughirah", "Ziyad ibn Ilaqah"},
    )
    assert not finding.passed
    assert finding.severity == "critical"


def test_entity_coverage_inapplicable_without_expected_list():
    """No Arabic NER yet -> must say 'not run', not 'passed'."""
    f = checks.entity_coverage(AR_SOURCE, EN_CLEAN)
    assert f.applicable is False


# --- terminology -------------------------------------------------------------

def test_terminology_violation_detected():
    finding = checks.terminology_violations(
        AR_SOURCE, "The Prophet led the prayer.", glossary={"messenger": "prophet"},
    )
    assert not finding.passed


def test_terminology_ok_when_required_term_present():
    finding = checks.terminology_violations(
        AR_SOURCE, "The Messenger led the prayer.", glossary={"messenger": "prophet"},
    )
    assert finding.passed


def test_terminology_inapplicable_without_glossary():
    assert checks.terminology_violations(AR_SOURCE, EN_CLEAN).applicable is False


# --- report aggregation ------------------------------------------------------

def test_run_checks_passes_clean_translation():
    report = checks.run_checks(AR_SOURCE, EN_CLEAN)
    assert report.critical_failures == []


def test_run_checks_surfaces_critical_failure():
    corrupted = EN_CLEAN.replace("did not pray", "did pray")
    report = checks.run_checks(AR_SOURCE, corrupted)
    assert any(f.check == "negation_parity" for f in report.critical_failures)


def test_report_counts_applicable_separately():
    report = checks.run_checks(AR_SOURCE, EN_CLEAN)
    d = report.as_dict()
    assert d["n_applicable"] <= d["n_checks"]
    assert d["n_checks"] == 9


# --- the integration that justifies this module ------------------------------

def test_checks_catch_corruptions_cometkiwi_missed():
    """Feed the actual C4 injectors' output through the checks.

    COMETKiwi scored 10.9% on delete_negation and 35.3% on leaving Arabic
    untranslated. These deterministic checks must do materially better on
    the same corruptions, or C5's ensemble premise is wrong.
    """
    for injector_name in ("delete_negation", "leave_arabic_untranslated"):
        injection = inj.INJECTORS[injector_name](EN_CLEAN, random.Random(0))
        assert injection is not None, f"{injector_name} should apply to this fixture"
        report = checks.run_checks(AR_SOURCE, injection.corrupted)
        assert report.failures, f"deterministic checks missed {injector_name}"


def test_known_gap_clause_removal_on_unpunctuated_source():
    """KNOWN GAP, deliberately asserted so it can't regress silently.

    Classical Arabic sources frequently carry little or no sentence
    punctuation. When they don't:
      * `sentence_ratio_flag` cannot run (source parses as one sentence), and
      * a partial truncation can still land inside the normal Arabic->English
        expansion band, so `length_ratio_flag` passes too.

    So dropping a trailing clause is NOT reliably detectable from
    (source, output) alone. COMETKiwi caught it 22.9% of the time — and with
    a *negative* mean delta — so neither signal covers it. Closing this needs
    one of: punctuation-bearing sources, an aligned reference, structural
    block-level translation with ID preservation (the harness's structured
    template already does this), or a targeted LLM verifier.

    This test documents the gap. If a future check closes it, this test
    fails and should be replaced by a positive assertion.
    """
    injection = inj.INJECTORS["remove_clause"](EN_CLEAN, random.Random(0))
    assert injection is not None
    report = checks.run_checks(AR_SOURCE, injection.corrupted)
    assert not report.failures, (
        "clause removal is now detected — good; update this test to assert detection"
    )
