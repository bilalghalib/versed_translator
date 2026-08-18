"""Hayy English must hang off the same Arabic ledger blocks the audio uses."""

from versed_translator.align.hayy_blocks import Block, to_import_rows


def test_climate_english_stays_on_climate_blocks_not_the_story():
    blocks = [
        Block(
            id="b-climate",
            sequence=3,
            text="أن جزيرة من جزائر الهند التي تحت خط الاستواء وهي الجزيرة التي يتولد بها الإنسان.",
            text_hash="hash-climate",
        ),
        Block(
            id="b-title",
            sequence=13,
            text="حي بن يقظان",
            text_hash="hash-title",
        ),
        Block(
            id="b-story",
            sequence=14,
            text="وكان له قريب يسمى يقظان فتزوجها سرا على وجه جائز في مذهبهم المشهور في زمنهم.",
            text_hash="hash-story",
        ),
    ]
    english = [
        "Our island lies under the Equinoctial Line, where the sun heats the earth.",
        "They say Yokdhan married the king's sister secretly according to their law.",
    ]
    rows = to_import_rows(blocks, english)
    by_id = {row["block_id"]: row for row in rows}

    assert by_id["b-climate"]["source_hash"] == "hash-climate"
    assert "Equinoctial" in by_id["b-climate"]["translated_text"]
    assert "Yokdhan" in by_id["b-story"]["translated_text"]
    assert "Equinoctial" not in by_id["b-story"]["translated_text"]
    assert "Yokdhan" not in by_id["b-climate"]["translated_text"]
    assert all(row["translated_text"].strip() for row in rows)


def test_omits_blocks_that_received_no_english():
    blocks = [
        Block(id="b1", sequence=1, text="كلام بلا مقابل واضح جدا هنا.", text_hash="h1"),
        Block(id="b2", sequence=2, text="وكان له قريب يسمى يقظان فتزوجها سرا.", text_hash="h2"),
    ]
    rows = to_import_rows(
        blocks,
        ["Yokdhan married his kinswoman secretly."],
    )
    assert [row["block_id"] for row in rows] == ["b2"]
