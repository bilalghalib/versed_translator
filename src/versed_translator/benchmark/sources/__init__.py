"""C1-checkpoint-1 source loaders: parallel-corpus ingestion for Versed Benchmark v0.1.

Each submodule (athar, lk_hadith, hadith_json) exposes ``iter_pairs(corpus_dir)
-> Iterator[dict]`` yielding dicts shaped per schema.PAIR_FIELDS. This
package does no normalization, sampling, or coverage-target logic -- that
is C1 checkpoint 2. It only loads what each source actually provides and
records rights_status per corpus/rights_ledger.json.
"""

from __future__ import annotations

from pathlib import Path

from versed_translator.benchmark.sources import athar, hadith_json, lk_hadith
from versed_translator.benchmark.sources.schema import (
    PAIR_FIELDS,
    arabic_word_count,
    length_band,
    make_pair,
)
from versed_translator.paths import SCRATCH_DIR

# corpus_dir default locations, matching the paths already downloaded per
# the task brief. Overridable by callers (e.g. tests) by passing a
# different corpus_dir straight to each module's iter_pairs.
DEFAULT_CORPUS_DIRS: dict[str, Path] = {
    "athar": SCRATCH_DIR / "corpus-cache" / "athar",
    "lk_hadith": SCRATCH_DIR / "corpus-cache" / "lk-hadith",
    "hadith_json": SCRATCH_DIR / "corpus-cache" / "hadith-json",
}

SOURCE_MODULES = {
    "athar": athar,
    "lk_hadith": lk_hadith,
    "hadith_json": hadith_json,
}

__all__ = [
    "DEFAULT_CORPUS_DIRS",
    "PAIR_FIELDS",
    "SOURCE_MODULES",
    "arabic_word_count",
    "length_band",
    "make_pair",
]
