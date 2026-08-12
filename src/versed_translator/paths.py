"""Env-overridable data locations for the versed-translator lab.

Defaults assume local development on machines with the `hikma` network
share mounted at /Volumes/hikma (visible to the wayway server at
/mnt/hikma) and a fast local scratch disk at /Volumes/Nodes. Override any
of them via environment variables. Nothing here touches the filesystem at
import time -- call ensure_dirs() to create the writable dirs on demand.
"""

from __future__ import annotations

import os
from pathlib import Path

SCRATCH_DIR = Path(os.environ.get("VERSED_SCRATCH", "/Volumes/Nodes/versed-translator"))
SHARED_DIR = Path(os.environ.get("VERSED_SHARED", "/Volumes/hikma/versed-translator"))
OPENITI_DIR = Path(os.environ.get("VERSED_OPENITI", "/Volumes/hikma/OpenITI"))


def ensure_dirs() -> None:
    """Create SCRATCH_DIR and SHARED_DIR if they do not already exist.

    Does not create OPENITI_DIR: that corpus is expected to already be
    present at its configured location.
    """
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    SHARED_DIR.mkdir(parents=True, exist_ok=True)
