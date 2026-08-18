"""C1-checkpoint-1 source loaders: parallel-corpus ingestion for Versed Benchmark v0.1.

Each submodule (athar, lk_hadith, hadith_json) exposes ``iter_pairs(corpus_dir)
-> Iterator[dict]`` yielding dicts shaped per schema.PAIR_FIELDS. This
package does no normalization, sampling, or coverage-target logic -- that
is C1 checkpoint 2. It only loads what each source actually provides and
records rights_status per corpus/rights_ledger.json.

Also here, but deliberately NOT in SOURCE_MODULES, is the D1e option (d)
PD-alignment stack:

    openiti_markdown  read-only OpenITI mARkdown reader (no factory imports)
    translit          Arabic <-> transliteration consonant-skeleton anchors
    hitti_ocr         OCR cleanup for one specific 1916 archive.org scan
    baladhuri         per-work alignment: Futuh al-Buldan <-> Hitti vol. 1
    llm_adjudicator   second opinion on spans the anchors cannot settle

Those are excluded from SOURCE_MODULES because they do not fit the
``iter_pairs(corpus_dir)`` contract: alignment needs BOTH an Arabic and an
English path, so `baladhuri.iter_pairs` takes two. They are driven by
`versed_translator.benchmark.pd_alignment` instead. Registering them here
would break the per-source summary CLI, which assumes one directory.
"""

from __future__ import annotations

from pathlib import Path

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


def __getattr__(name: str):
    """Load pandas-backed corpus readers only when asked.

    Importing this package for PD alignment (translit, OpenITI, Hayy)
    must not pull numpy/pandas. Those readers segfault in some macOS
    test environments during numpy's self-check.
    """
    if name == "SOURCE_MODULES":
        from versed_translator.benchmark.sources import athar, hadith_json, lk_hadith

        modules = {
            "athar": athar,
            "lk_hadith": lk_hadith,
            "hadith_json": hadith_json,
        }
        globals()["SOURCE_MODULES"] = modules
        return modules
    if name in {"athar", "hadith_json", "lk_hadith"}:
        import importlib

        module = importlib.import_module(f"versed_translator.benchmark.sources.{name}")
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "DEFAULT_CORPUS_DIRS",
    "PAIR_FIELDS",
    "SOURCE_MODULES",
    "arabic_word_count",
    "length_band",
    "make_pair",
]
