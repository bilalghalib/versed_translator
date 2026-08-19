"""Block segmentation for the structured-block translation contract (D2e/D4c).

WHY BLOCKS EXIST. Two separately-measured failures are retired by one
architectural change, which is why D2e and D4c were decided together:

1. **A dropped clause is invisible; a dropped block is countable.** On
   unpunctuated classical Arabic, partial clause removal cannot be detected
   from (source, output) alone -- COMETKiwi catches it 22.9% of the time
   *with a negative mean delta* (it scores the truncated text HIGHER), and
   MetricX 33.3%. Once every block carries an id that must come back, an
   omission at block granularity becomes a missing key, not a judgment call.
2. **Long passages break the QE model.** 37.5% of QE inputs (859/2,288) blew
   past MetricX's 1536-token window in the full C4 study, roughly doubling
   apparent error on exactly the long passages where omission matters most.
   Short blocks stay inside the window.

THE INVARIANT THAT MAKES THIS SAFE. ``segment`` must never lose text: this
module exists to make omission observable, so a segmenter that silently
dropped a clause would defeat its own purpose in the quietest possible way.
Hence ``" ".join(segment(t)) == " ".join(t.split())`` holds for every input,
and ``tests/test_blocks.py`` pins it (including against the real dev_bakeoff
slice's shape, without quoting any corpus text here).

Segmentation is deliberately dumb and deterministic -- no model, no
language ID, no learned splitter. It cuts on the punctuation classical
Arabic editions actually carry (full stops, then commas), packs the pieces
greedily up to a word budget, and hard-splits only a piece that has no
internal boundary at all. Determinism matters because block ids are derived
from position: re-segmenting the same source must reproduce the same ids or
every downstream artifact silently re-keys.

RIGHTS NOTE: no corpus text lives here. This module only transforms text
handed to it at run time.
"""

from __future__ import annotations

import statistics

#: Separator between an item id and its zero-padded block index.
#: ``lk_hadith:AbuDaud_ch12_h1960`` -> ``lk_hadith:AbuDaud_ch12_h1960#b0001``.
#: Chosen because ``#`` does not occur in any benchmark id; ``blockify``
#: refuses ids that contain it rather than minting an ambiguous block id.
BLOCK_ID_SEP = "#b"
BLOCK_INDEX_WIDTH = 4

#: Word budget per block. Sized from the measured mT5 tokenization of the
#: v0.1-draft slice: diacritized classical Arabic runs ~5.8 mT5 tokens per
#: word (max 7.3), so a 60-word block is ~350 source tokens; with its English
#: candidate the MetricX QE input lands near ~500 of the 1536-token budget,
#: leaving room for the length-increasing injectors that biased the previous
#: matrix. It is also a plausible unit of meaning in hadith prose (an isnad
#: link, a matn clause), which matters because blocks are what a translator
#: sees and what a reviewer would have to re-read.
DEFAULT_MAX_BLOCK_WORDS = 60

#: Sentence-ending punctuation, tried first.
HARD_BOUNDARY_CHARS = ".!?؟؛۔"
#: Clause-level punctuation, used only to break a hard-unit that is too long.
SOFT_BOUNDARY_CHARS = "،,:"


class BlockIdError(ValueError):
    """An item id cannot be turned into (or recovered from) a block id."""


def block_id(item_id: str, index: int) -> str:
    """Deterministic block id: ``<item_id>#b0001`` (1-based)."""
    if BLOCK_ID_SEP in str(item_id):
        raise BlockIdError(
            f"item id {item_id!r} already contains {BLOCK_ID_SEP!r}; block ids "
            "would be ambiguous. Rename the item rather than nesting blocks."
        )
    return f"{item_id}{BLOCK_ID_SEP}{index:0{BLOCK_INDEX_WIDTH}d}"


def parse_block_id(bid: str) -> tuple[str, int]:
    """Inverse of ``block_id``. Raises BlockIdError on anything else."""
    parent, sep, suffix = str(bid).rpartition(BLOCK_ID_SEP)
    if not sep or not suffix.isdigit():
        raise BlockIdError(f"{bid!r} is not a block id (expected <item_id>{BLOCK_ID_SEP}NNNN)")
    return parent, int(suffix)


def is_block_id(bid: str) -> bool:
    try:
        parse_block_id(bid)
    except BlockIdError:
        return False
    return True


def _split_on(words: list[str], boundary_chars: str) -> list[list[str]]:
    """Group `words` into runs, cutting after any word ending in a boundary char."""
    units: list[list[str]] = []
    current: list[str] = []
    for word in words:
        current.append(word)
        if word[-1] in boundary_chars:
            units.append(current)
            current = []
    if current:
        units.append(current)
    return units


def _even_chunks(words: list[str], max_words: int) -> list[list[str]]:
    """Cut `words` into the fewest chunks of at most `max_words`, evenly sized.

    Evenly, not greedily: greedy leaves a runt tail (61 words at a 60 budget
    becomes 60 + 1), and a one-word block is a bad unit to hand a translator,
    a bad unit to score, and a bad unit to ask a reviewer to re-read.
    """
    if not words:
        return []
    n_chunks = -(-len(words) // max_words)  # ceil
    size = -(-len(words) // n_chunks)
    return [words[i : i + size] for i in range(0, len(words), size)]


def sentences(text: str) -> list[str]:
    """Split on sentence punctuation only. Does not pack, merge, or budget.

    Chunks are packed sentences (and leftover clauses). Paragraphs are an
    edition's ``# `` / blank-line units. This function is neither. A source
    with no sentence punctuation returns one span — the whole text — rather
    than inventing cuts.

    Guarantees ``" ".join(sentences(t)) == " ".join(t.split())``.
    """
    words = text.split()
    if not words:
        return []
    return [" ".join(unit) for unit in _split_on(words, HARD_BOUNDARY_CHARS)]


def segment(text: str, max_words: int = DEFAULT_MAX_BLOCK_WORDS) -> list[str]:
    """Split `text` into blocks of at most `max_words` whitespace-separated words.

    Guarantees ``" ".join(segment(t)) == " ".join(t.split())`` -- no word is
    dropped, duplicated, or reordered. Returns ``[]`` only for whitespace-only
    input.

    Cut preference, strongest first: sentence punctuation, then clause
    punctuation, then a blunt word-count cut. The resulting pieces are packed
    twice (see below) so a three-word clause does not become its own block and
    a passage one word over the budget becomes two halves rather than a full
    block plus a one-word runt.

    Evening is best-effort, not guaranteed: punctuation pieces are
    indivisible, so a source whose last sentence ends exactly at the budget
    followed by a two-word sentence still yields a short tail block. That is
    cosmetic -- every block is still id-bearing, translated and accounted
    for -- and on the real v0.1-draft slice it leaves 4 blocks under 10 words
    out of 522.
    """
    if max_words < 1:
        raise ValueError(f"max_words must be >= 1, got {max_words}")
    words = text.split()
    if not words:
        return []

    pieces: list[list[str]] = []
    for hard_unit in _split_on(words, HARD_BOUNDARY_CHARS):
        if len(hard_unit) <= max_words:
            pieces.append(hard_unit)
            continue
        for soft_unit in _split_on(hard_unit, SOFT_BOUNDARY_CHARS):
            if len(soft_unit) <= max_words:
                pieces.append(soft_unit)
            else:
                pieces.extend(_even_chunks(soft_unit, max_words))

    # Pack twice. The first pass at the full budget establishes how few blocks
    # the pieces actually fit into; the second evens them out at that count.
    # Deriving the target from total/max_words instead (the obvious shortcut)
    # under-counts, because punctuation pieces are indivisible: three 30-word
    # sentences plus a 10-word one fit in 2 blocks of 60, but a target of 50
    # splits them into 3 -- more blocks, more calls, no benefit. If evening
    # ever costs a block, keep the tighter packing.
    packed = _pack(pieces, max_words)
    evened = _pack(pieces, -(-len(words) // len(packed)))
    blocks = evened if len(evened) <= len(packed) else packed
    return [" ".join(block) for block in blocks]


def _pack(pieces: list[list[str]], limit: int) -> list[list[str]]:
    """Greedily merge consecutive pieces while they fit under `limit`.

    A piece already larger than `limit` becomes its own block rather than
    being split -- splitting happens earlier, at punctuation.
    """
    blocks: list[list[str]] = []
    for piece in pieces:
        if blocks and len(blocks[-1]) + len(piece) <= limit:
            blocks[-1].extend(piece)
        else:
            blocks.append(list(piece))
    return blocks


def blockify(
    items: list[dict],
    max_words: int = DEFAULT_MAX_BLOCK_WORDS,
) -> list[dict]:
    """Expand ``{id, arabic}`` items into block items, in source order.

    Each output row is ``{id, arabic, parent_id, block_index, block_count}``.
    ``id``/``arabic`` are exactly the fields the harness and the QE study
    already consume, so a block file is a drop-in items file; the extra
    fields are what ``reassemble`` needs and what makes a dropped block
    attributable to its passage.

    An item whose Arabic is empty yields no blocks -- and is therefore
    absent from the block file, which the caller can detect by comparing
    ``block_count``s against the source item count. It is not silently
    emitted as an empty block, because an empty block would be
    indistinguishable from a block the model returned empty.
    """
    out: list[dict] = []
    for item in items:
        texts = segment(item["arabic"], max_words=max_words)
        for index, text in enumerate(texts, start=1):
            out.append(
                {
                    "id": block_id(item["id"], index),
                    "arabic": text,
                    "parent_id": item["id"],
                    "block_index": index,
                    "block_count": len(texts),
                }
            )
    return out


def block_stats(blocks: list[dict]) -> dict:
    """Aggregate shape of a block file. Counts only -- never block text."""
    if not blocks:
        return {"blocks": 0, "items": 0}
    words = [len(b["arabic"].split()) for b in blocks]
    per_item: dict[str, int] = {}
    for b in blocks:
        per_item[b["parent_id"]] = per_item.get(b["parent_id"], 0) + 1
    counts = sorted(per_item.values())
    return {
        "blocks": len(blocks),
        "items": len(per_item),
        "blocks_per_item_mean": round(statistics.fmean(counts), 3),
        "blocks_per_item_median": statistics.median(counts),
        "blocks_per_item_max": max(counts),
        "block_words_mean": round(statistics.fmean(words), 2),
        "block_words_median": statistics.median(words),
        "block_words_min": min(words),
        "block_words_max": max(words),
    }


def reassemble(
    rows: list[dict],
    joiner: str = " ",
    expected_counts: dict[str, int] | None = None,
) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Join block-level result rows back into one translation per source item.

    `rows` are harness result rows (``schema.ROW_FIELDS`` shape) whose
    ``item_id`` is a block id. Returns ``(translations, incomplete)`` where
    ``translations`` maps parent item id -> joined English for the items whose
    every block came back clean, and ``incomplete`` maps parent item id -> the
    block ids that are missing or failed.

    Splitting the return this way is the whole point: an item with a failed
    block must never quietly appear as a shorter translation, which is the
    exact silent-omission failure blocks exist to expose.

    THREE WAYS A BLOCK CAN BE ABSENT, and all three must be caught. An earlier
    version checked only the first and would happily join ``#b0001`` to
    ``#b0003`` and report the item clean:

    1. a row is present and carries an error (or a blank translation);
    2. a row is **entirely absent from the middle**, leaving a gap in the
       index sequence -- caught by requiring indices to be exactly
       ``1..n`` with no holes;
    3. a row is absent from the **end**, which leaves no gap and is therefore
       invisible to a contiguity check. Only an external count can catch it,
       so pass `expected_counts` (parent id -> block count, straight off the
       block items file, which records ``block_count`` per block). Without it
       trailing loss is undetectable and this function says so rather than
       pretending otherwise.
    """
    by_parent: dict[str, list[tuple[int, dict]]] = {}
    for row in rows:
        parent, index = parse_block_id(row["item_id"])
        by_parent.setdefault(parent, []).append((index, row))

    parents = set(by_parent) | set(expected_counts or {})
    translations: dict[str, str] = {}
    incomplete: dict[str, list[str]] = {}
    for parent in parents:
        entries = sorted(by_parent.get(parent, []), key=lambda pair: pair[0])
        expected = (expected_counts or {}).get(parent, len(entries))
        present = {index for index, _row in entries}

        bad = [
            row["item_id"]
            for _i, row in entries
            if row.get("error") or not (row.get("translation") or "").strip()
        ]
        # Absent block ids are named the same way a failed one is, so a caller
        # counting `incomplete[parent]` gets the true number of lost blocks.
        bad += [block_id(parent, i) for i in range(1, expected + 1) if i not in present]

        if bad:
            incomplete[parent] = sorted(set(bad))
            continue
        translations[parent] = joiner.join(
            (row["translation"] or "").strip() for _i, row in entries
        )
    return translations, incomplete


def expected_block_counts(block_items: list[dict]) -> dict[str, int]:
    """parent id -> number of blocks, from a block items file.

    The authoritative answer to "how many blocks should this item have",
    which ``reassemble`` cannot infer from the results alone (a missing
    trailing block leaves no gap). ``blockify`` writes ``block_count`` on
    every row; this falls back to counting rows per parent if it is absent.
    """
    counts: dict[str, int] = {}
    for block in block_items:
        parent = block.get("parent_id")
        if parent is None:
            parent, _index = parse_block_id(block["id"])
        declared = block.get("block_count")
        if isinstance(declared, int) and declared > 0:
            counts[parent] = declared
        else:
            counts[parent] = counts.get(parent, 0) + 1
    return counts
