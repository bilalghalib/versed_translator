"""Fixture tests for paragraph / sentence / chunk layers. No corpus text."""

from versed_translator.benchmark import layers, spine_align


def test_three_layers_are_not_the_same_cuts():
    unit = spine_align.ArabicUnit(
        1,
        "المقامة البلخية",
        0,
        0,
        (
            "قال عيسى بن هشام. ثم سار إلى بلخ.",
            "وذكر أصفهان بعد ذلك بكلام طويل يملأ الميزانية هنا حتى يتجاوز الميزانية.",
        ),
    )
    layered = layers.layer_arabic(unit, max_words=8)
    assert [span.word_count for span in layered.paragraphs] != [
        span.word_count for span in layered.sentences
    ]
    assert len(layered.paragraphs) == 2
    assert len(layered.sentences) == 3
    assert len(layered.chunks) > len(layered.paragraphs)
    assert all(span.parent_paragraph in {1, 2} for span in layered.sentences)
    assert all(span.parent_paragraph in {1, 2} for span in layered.chunks)


def test_english_paragraphs_drop_running_heads_and_join_hyphens():
    lines = [
        "THE MAQAMAT OF BADI",
        "Isa ibn Hisham related to us and said: I was at Balkh-",
        "town when a man arrived.",
        "",
        "Then he mentioned Isfahan.",
    ]
    paragraphs = layers.english_paragraphs(lines)
    assert len(paragraphs) == 2
    assert "Balkhtown" in paragraphs[0]
    assert "Isfahan" in paragraphs[1]


def test_name_monotone_pairs_one_arabic_sentence_to_two_english():
    arabic = (
        layers.Span(1, "sentence", "حدثنا عيسى بن هشام قال بلغنا بلخ"),
        layers.Span(2, "sentence", "ثم ذكر أصفهان"),
    )
    english = (
        layers.Span(1, "sentence", "Isa ibn Hisham related."),
        layers.Span(2, "sentence", "I reached Balkh."),
        layers.Span(3, "sentence", "Then he mentioned Isfahan."),
    )
    pairs = layers.pair_layer(arabic, english, min_mass=3)
    assert len(pairs) == 2
    assert [span.index for span in pairs[0].english] == [1, 2]
    assert [span.index for span in pairs[1].english] == [3]


def test_layer_report_keeps_unpaired_when_names_miss():
    arabic = layers.layer_arabic(
        spine_align.ArabicUnit(1, "x", 0, 0, ("كلام بلا أسماء واضحة هنا.",)),
        max_words=8,
    )
    english = layers.layer_english(
        spine_align.EnglishUnit(1, "x", "I", 1, "A sentence with no shared names."),
        max_words=8,
    )
    report = layers.layer_report(arabic, english)
    assert report["paired_sentences"] == 0
    assert report["arabic"]["sentences"] == 1
    assert report["english"]["sentences"] == 1
