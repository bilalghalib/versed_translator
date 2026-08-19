"""Standard zipper: name anchors + monotone DP, no book-specific regex."""

from versed_translator.align.standard import section_hit, zip_units


def test_name_anchor_keeps_preface_english_off_the_story():
    arabic = [
        "كلام عن خط الاستواء والحرارة والشمس في تلك الجزيرة.",
        "وكان له قريب يسمى يقظان فتزوجها سرا على وجه جائز.",
        "ثم سار في الجزيرة حتى أبصر النار.",
    ]
    english = [
        "A long preface about the Equinoctial Line and the heat of the sun.",
        "Yokdhan married his kinswoman secretly according to their law.",
        "Then he walked the island until he saw a fire among the reeds.",
    ]
    mapping = zip_units(arabic, english)
    assert mapping[0] == (0, 1)
    assert mapping[1][0] >= 1
    assert mapping[0] != mapping[1]


def test_later_decoy_name_does_not_teleport_the_lock():
    arabic = [
        "كلام عن الشمس.",
        "وكان له قريب يسمى يقظان فتزوجها سرا.",
        "ثم سار.",
    ]
    english = [
        "Preface about the sun.",
        "Yokdhan married his kinswoman secretly.",
        "Asal afterwards met Hayy on the island of Waqwaq somewhere far away.",
    ]
    mapping = zip_units(arabic, english)
    assert mapping[1][0] == 1


def test_section_hit_buffer_is_overlap_not_exact_match():
    gold = (21, 23)
    assert section_hit(gold, (20, 24), window=1)
    assert section_hit(gold, (21, 23), window=0)
    assert not section_hit(gold, (0, 2), window=2)
