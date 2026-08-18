from versed_translator.corpus.extract_train import (
    extract_ithra_odes,
    extract_johnson_quotes,
)


def test_ithra_groups_numbered_english_and_labels_imru():
    text = """
garbage Arabic هنا نص عربي طويل

1. Stop, my friends, and we will weep
over the memory of a loved one

2. Then Tudih, then al-Miqrat, whose trace
was not effaced

هنا تعليق عربي
1. Traces of Khawlah loom
in the stony plain
"""
    odes = extract_ithra_odes(text)
    assert len(odes) == 2
    assert odes[0]["poet"] == "imru_al_qays"
    assert odes[0]["n_verses"] == 2
    assert "memory of a loved one" in odes[0]["verses"][0]["text"]
    assert odes[1]["poet"] == "tarafah"
    assert odes[0]["usage_policy"] == "train_ok"


def test_johnson_keeps_quoted_english_drops_apparatus():
    text = '''
THE FIRST POEM.
This poem is written by Imra-ul-Qais.

" Stop, oh my two friends, let us weep on account of the remembrance of my beloved, and her abode situated on the edge of a sandy desert between Dakhool and Howmal."

1st per. pi. of the aorist from the verb.

" On the morning of separation, the day they parted it was as if I, standing near the acacia shrubs in the gardens of the tribe, were breaking the pods of the colocynth."

THE SECOND POEM.
Ascribed to Tarafah.

" There are traces of Kholah in the stony, sandy plain of Thahmad, which appear like the marks of tattooing on the back of the hand."
'''
    poems = extract_johnson_quotes(text)
    assert [row["poem_index"] for row in poems] == [1, 2]
    assert poems[0]["n_lines"] == 2
    assert poems[0]["lines"][0].startswith("Stop, oh my two friends")
def test_johnson_ignores_duplicate_headers():
    text = '''
THE FIRST POEM.
" Stop, oh my two friends, let us weep on account of the remembrance of my beloved, and her abode situated on the edge of a sandy desert between Dakhool and Howmal."
THE FIRST POEM.
END OF THE FIRST POEM.
'''
    poems = extract_johnson_quotes(text)
    assert len(poems) == 1
    assert poems[0]["poem_index"] == 1
