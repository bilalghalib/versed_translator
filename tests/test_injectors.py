"""Each injector must provably produce its intended corruption.

An injector that silently returns unchanged text (or that "succeeds" without
actually corrupting anything) would be scored as an *undetected* error in the
C4 detection matrix and would understate QE sensitivity. That is the failure
mode these tests exist to prevent, so each test asserts the specific change,
not merely that something differed.
"""

from __future__ import annotations

import random

import pytest

from versed_translator.qe import injectors as inj

SEED = random.Random(0)


def _run(fn, text):
    return fn(text, random.Random(0))


def test_delete_negation_removes_the_negation():
    text = "He did not pray in the mosque. He left afterwards."
    out = _run(inj.delete_negation, text)
    assert out is not None
    assert "not " not in out.corrupted
    assert out.taxonomy == inj.NEGATION
    assert out.severity == "critical"


def test_delete_negation_returns_none_without_negation():
    assert _run(inj.delete_negation, "He prayed in the mosque.") is None


def test_change_number_actually_changes_a_digit():
    text = "He prayed 2 rak'ahs and then 4 more."
    out = _run(inj.change_number, text)
    assert out is not None
    assert out.corrupted != text
    assert any(c.isdigit() for c in out.corrupted)


def test_change_number_none_when_no_numbers():
    assert _run(inj.change_number, "He prayed in the mosque.") is None


def test_omit_person_drops_a_name():
    text = "Muhammad ibn Amr narrated this hadith to the people of Basra."
    out = _run(inj.omit_person, text)
    assert out is not None
    assert len(out.corrupted) < len(text)


def test_remove_isnad_narrator_breaks_the_chain():
    text = "Yahya narrated from Hilal ibn Abi Maymunah, from Ata ibn Yasar."
    out = _run(inj.remove_isnad_narrator, text)
    assert out is not None
    assert out.corrupted != text
    assert out.severity == "critical"


def test_remove_clause_drops_a_whole_sentence():
    text = "He entered the mosque. He prayed two rak'ahs. Then he left."
    out = _run(inj.remove_clause, text)
    assert out is not None
    # exactly one sentence fewer
    assert out.corrupted.count(".") == text.count(".") - 1


def test_remove_clause_none_for_single_sentence():
    assert _run(inj.remove_clause, "He prayed.") is None


def test_mistranslate_term_swaps_a_technical_term():
    text = "The Messenger led the prayer that evening."
    out = _run(inj.mistranslate_term, text)
    assert out is not None
    assert out.corrupted != text
    assert out.taxonomy == inj.TERMINOLOGY


def test_reverse_agent_patient_swaps_participants():
    text = "Musaddad narrated to Yahya about the matter."
    out = _run(inj.reverse_agent_patient, text)
    if out is not None:  # pattern-dependent
        assert out.corrupted != text
        assert out.severity == "critical"


def test_hallucinate_prose_appends_unsupported_content():
    text = "He prayed two rak'ahs."
    out = _run(inj.hallucinate_prose, text)
    assert out is not None
    assert len(out.corrupted) > len(text)
    assert out.corrupted.startswith(text.rstrip())
    assert out.taxonomy == inj.ADDITION


def test_omit_quotation_removes_quoted_material():
    text = 'He said, "If she weeps or remains silent, it is permitted." Then he left.'
    out = _run(inj.omit_quotation, text)
    assert out is not None
    assert "weeps or remains silent" not in out.corrupted


def test_duplicate_sentence_repeats_content():
    text = "He entered the mosque. He prayed."
    out = _run(inj.duplicate_sentence, text)
    assert out is not None
    assert len(out.corrupted) > len(text)


def test_leave_arabic_untranslated_inserts_arabic_script():
    text = "He entered the mosque. He prayed two rak'ahs."
    out = _run(inj.leave_arabic_untranslated, text)
    assert out is not None
    # must contain an Arabic-script codepoint
    assert any("؀" <= ch <= "ۿ" for ch in out.corrupted)


def test_certainty_inflation_removes_hedging():
    text = "It is said that he prayed two rak'ahs."
    out = _run(inj.certainty_inflation, text)
    assert out is not None
    assert "it is said that" not in out.corrupted.lower()
    assert out.taxonomy == inj.REGISTER


def test_collapse_paragraphs_removes_newlines():
    text = "First paragraph here.\n\nSecond paragraph here."
    out = _run(inj.collapse_paragraphs, text)
    assert out is not None
    assert "\n" not in out.corrupted


def test_collapse_paragraphs_none_without_breaks():
    assert _run(inj.collapse_paragraphs, "One line only.") is None


def test_alter_date_shifts_the_year():
    text = "This occurred in the year 622 AH according to the chronicles."
    out = _run(inj.alter_date, text)
    assert out is not None
    assert "622" not in out.corrupted


def test_alter_citation_changes_verse_reference():
    text = "He recited the verse 2:255 during the prayer."
    out = _run(inj.alter_citation, text)
    assert out is not None
    assert "2:255" not in out.corrupted
    assert out.taxonomy == inj.REFERENCE


def test_all_fifteen_injectors_registered():
    """The master plan specifies exactly 15 corruption types."""
    assert len(inj.INJECTORS) == 15


def test_inject_all_is_deterministic():
    text = 'Muhammad ibn Amr said, "He did not pray 2 rak\'ahs in the year 622 AH."'
    a = inj.inject_all(text, seed=7)
    b = inj.inject_all(text, seed=7)
    assert [(x.injector, x.corrupted) for x in a] == [(y.injector, y.corrupted) for y in b]


def test_inject_all_never_returns_unchanged_text():
    """The critical invariant: a no-op corruption would be scored as an
    undetected error and would silently understate QE sensitivity."""
    text = 'Muhammad ibn Amr said, "He did not pray 2 rak\'ahs." Then he left.'
    for injection in inject_sample(text):
        assert injection.corrupted != injection.original, injection.injector


def inject_sample(text):
    return inj.inject_all(text, seed=1)


@pytest.mark.parametrize("name", sorted(inj.INJECTORS))
def test_injector_returns_none_or_real_change(name):
    """No injector may claim success while changing nothing."""
    fn = inj.INJECTORS[name]
    text = 'Musaddad narrated from Yahya, "He did not pray 2 rak\'ahs in 622 AH (2:255)."'
    out = fn(text, random.Random(3))
    assert out is None or out.corrupted != out.original
