"""Per-source summary: pair counts, genre spread, Arabic-word length bands.

Run with: uv run python -m versed_translator.benchmark.sources
"""

from __future__ import annotations

from collections import Counter

from versed_translator.benchmark.sources import DEFAULT_CORPUS_DIRS, SOURCE_MODULES
from versed_translator.benchmark.sources.schema import (
    LENGTH_BANDS,
    arabic_word_count,
    length_band,
)


def summarize(source_name: str) -> None:
    module = SOURCE_MODULES[source_name]
    corpus_dir = DEFAULT_CORPUS_DIRS[source_name]

    total = 0
    genre_counts: Counter[str] = Counter()
    band_counts: Counter[str] = Counter()
    rights_counts: Counter[str] = Counter()
    split_counts: Counter[str] = Counter()

    if not corpus_dir.exists():
        print(f"=== {source_name} ===")
        print(f"  corpus_dir not found: {corpus_dir}")
        print()
        return

    for pair in module.iter_pairs(corpus_dir):
        total += 1
        genre_counts[pair["genre"] or "(none)"] += 1
        rights_counts[pair["rights_status"] or "(none)"] += 1
        split_counts[pair["source_split"] or "(none)"] += 1
        band = length_band(arabic_word_count(pair["arabic"]))
        band_counts[band or "(outside bands)"] += 1

    print(f"=== {source_name} ===")
    print(f"  corpus_dir: {corpus_dir}")
    print(f"  total pairs: {total}")
    print(f"  by genre: {dict(genre_counts)}")
    print(f"  by source_split: {dict(split_counts)}")
    print(f"  by rights_status: {dict(rights_counts)}")
    print("  by Arabic-word length band:")
    for label, _lo, _hi in LENGTH_BANDS:
        print(f"    {label}: {band_counts.get(label, 0)}")
    print(f"    (outside bands): {band_counts.get('(outside bands)', 0)}")
    print()


def main() -> int:
    for source_name in SOURCE_MODULES:
        summarize(source_name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
