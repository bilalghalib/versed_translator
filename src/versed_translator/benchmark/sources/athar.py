"""Loader for the ATHAR Classical-Arabic<->English parallel corpus.

Source: mohamed-khalil/ATHAR on HuggingFace, scraped from rasaif.com.
~66k Arabic/English sentence pairs across 18 Classical Arabic works. The
parquet files carry only two columns (arabic, english) -- no per-row work,
author, genre, or date metadata is present in the data itself, so those
fields are emitted as None here (see schema.py docstring: loaders compute
nothing fancy).

LICENSE NOTE (see corpus/rights_ledger.json for the full evidence trail):
the dataset card's YAML front matter declares ``license: cc-by-sa-4.0``,
but the card's own prose "## License" section states the dataset is
"licensed under CC BY NC 4.0" (NonCommercial). These two statements
conflict. Until resolved with the dataset author, this loader treats ATHAR
conservatively as non-commercial / internal-eval-only, per the roadmap's
C1 checkpoint-1 guidance ("ATHAR: internal-eval OK / NC redistribution").

The native ATHAR train/test split is preserved verbatim in source_split so
downstream benchmark assembly can keep ATHAR's own test rows out of any
training mix (contamination bookkeeping) independent of Versed's own
held-out split.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pandas as pd

from versed_translator.benchmark.sources.schema import make_pair

RIGHTS_STATUS = "CC_BY_NC_4.0_LICENSE_CONFLICT_SEE_LEDGER"


def _iter_split(path: Path, split: str) -> Iterator[dict]:
    df = pd.read_parquet(path, columns=["arabic", "english"])
    for row_idx, row in enumerate(df.itertuples(index=False)):
        yield make_pair(
            source="athar",
            source_native_id=f"{split}-{row_idx}",
            work_id=None,
            author=None,
            genre=None,
            date_or_century=None,
            arabic=row.arabic,
            reference_english=row.english,
            translator=None,
            english_source="rasaif.com (via ATHAR HF dataset)",
            rights_status=RIGHTS_STATUS,
            source_split=split,
            notes=None,
        )


def iter_pairs(corpus_dir: Path) -> Iterator[dict]:
    """Yield candidate pairs from the ATHAR train and test parquet files.

    corpus_dir is the ATHAR checkout root, e.g.
    .../corpus-cache/athar, containing data/train-*.parquet and
    data/test-*.parquet.
    """
    data_dir = Path(corpus_dir) / "data"
    train_files = sorted(data_dir.glob("train-*.parquet"))
    test_files = sorted(data_dir.glob("test-*.parquet"))
    for f in train_files:
        yield from _iter_split(f, "train")
    for f in test_files:
        yield from _iter_split(f, "test")
