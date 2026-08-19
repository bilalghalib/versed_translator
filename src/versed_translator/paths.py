"""Env-overridable data locations for the versed-translator lab.

Three different trees, not duplicates:

* **Repo** (`REPO_DIR`): git checkout — code, tests, STATUS, ledger.
* **Package** (`PACKAGE_DIR`): `src/versed_translator/` — the importable
  library inside the repo (src layout).
* **Data** (`DATA_DIR`): `~/versed-translator-data` — CSVs, runs, PD
  texts, Fable sittings, reports. Not in git; too large / rights-mixed.

Hikma/OpenITI and scratch stay on the network/fast disks. Override any
path via environment variables. Nothing here touches the filesystem at
import time -- call ensure_dirs() to create the *writable scratch/share*
dirs on demand. DATA_DIR is expected to already exist.
"""

from __future__ import annotations

import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_DIR = PACKAGE_DIR.parents[1]

DATA_DIR = Path(os.environ.get("VERSED_DATA", str(Path.home() / "versed-translator-data")))
SCRATCH_DIR = Path(os.environ.get("VERSED_SCRATCH", "/Volumes/Nodes/versed-translator"))
SHARED_DIR = Path(os.environ.get("VERSED_SHARED", "/Volumes/hikma/versed-translator"))
OPENITI_DIR = Path(os.environ.get("VERSED_OPENITI", "/Volumes/hikma/OpenITI"))

FABLE_R1_DIR = DATA_DIR / "benchmark-alignment" / "fable_r1"


def ensure_dirs() -> None:
    """Create SCRATCH_DIR and SHARED_DIR if they do not already exist.

    Does not create OPENITI_DIR: that corpus is expected to already be
    present at its configured location.
    """
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    SHARED_DIR.mkdir(parents=True, exist_ok=True)
