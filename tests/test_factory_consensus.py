from versed_translator.factory.consensus import classify_row


def test_yn_flip_is_disputed_and_unresolved():
    out = classify_row(
        first_publishable="Y",
        first_flags="OK",
        first_confidence="high",
        second_publishable="N",
        second_flags="TERM",
        second_confidence="med",
    )
    assert out["consensus_label_status"] == "disputed"
    assert out["future_human_priority"] == "P1"
    assert out["agreement"] == "N"
    assert out["consensus_publishable"] == ""
    assert "flip" in out["disagreement_reason"]


def test_disjoint_blocking_class_is_disputed():
    out = classify_row(
        first_publishable="N",
        first_flags="TERM",
        first_confidence="high",
        second_publishable="N",
        second_flags="ROLE",
        second_confidence="high",
    )
    assert out["consensus_label_status"] == "disputed"
    assert out["future_human_priority"] == "P1"
    assert out["agreement"] == "Y"
    assert out["consensus_publishable"] == ""


def test_translation_corrupt_word_is_not_source_dispute():
    out = classify_row(
        first_publishable="N",
        first_flags="NUMBER",
        first_confidence="med",
        second_publishable="N",
        second_flags="NUMBER",
        second_confidence="high",
        first_notes="birth year corrupted into a non-number",
    )
    assert out["consensus_label_status"] == "silver_consensus_med"
    assert out["agreement"] == "Y"


def test_high_agreement_is_p3():
    out = classify_row(
        first_publishable="N",
        first_flags="TERM",
        first_confidence="high",
        second_publishable="N",
        second_flags="TERM",
        second_confidence="high",
    )
    assert out["consensus_label_status"] == "silver_consensus_high"
    assert out["future_human_priority"] == "P3"
    assert out["consensus_publishable"] == "N"
    assert out["consensus_blocking_flags"] == "TERM"


def test_medium_confidence_or_ambiguity_is_p2():
    med = classify_row(
        first_publishable="Y",
        first_flags="OK",
        first_confidence="med",
        second_publishable="Y",
        second_flags="OK",
        second_confidence="high",
    )
    assert med["consensus_label_status"] == "silver_consensus_med"
    assert med["future_human_priority"] == "P2"

    amb = classify_row(
        first_publishable="Y",
        first_flags="OK",
        first_confidence="high",
        second_publishable="Y",
        second_flags="OK",
        second_confidence="high",
        second_notes="defensible reading of a genuinely obscure clause",
    )
    assert amb["consensus_label_status"] == "silver_consensus_med"
    assert amb["future_human_priority"] == "P2"


def test_never_emits_human_gold():
    out = classify_row(
        first_publishable="Y",
        first_flags="OK",
        first_confidence="high",
        second_publishable="Y",
        second_flags="OK",
        second_confidence="high",
    )
    assert "human" not in out["consensus_label_status"]
    assert out["consensus_label_status"] != "human_gold"
