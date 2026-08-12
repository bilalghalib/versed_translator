"""C6 checkpoint 2 — provenance resolver v0.

Given an OpenITI catalog URI (and optionally its already-loaded metadata
dict), extract whatever provenance claims can be read straight off the URI
string and/or the metadata's `url` field: the author's death year (AH) and
the upstream digital-library source claim (e.g. "Shamela", "JK", "GRAR").

No re-OCR, no network calls, no guessing beyond documented string patterns.
Every returned value is paired with an `evidence` entry naming the exact
field/pattern that produced it, so callers (and the stats report) can
measure real coverage instead of assuming it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# Leading 4-digit death-year prefix on every OpenITI author-work URI, e.g.
# "0505Ghazali.Tahafut" -> 505. Anonymous/undated authors use "0000" or "0001"
# by OpenITI convention; we surface whatever digits are there and let
# downstream consumers decide how to treat the placeholder values.
_URI_DEATH_AH_RE = re.compile(r"^(\d{4})")

# The upstream-source tail that OpenITI appends to a work's version
# filename, e.g. ".../0179MalikIbnAnas.Muwatta.Shamela0028107-ara1.completed"
# or ".../0001AwsIbnHajar.Diwan.JK007502-ara1". Captures the alphabetic
# source-library tag (non-greedy, so digits are not swallowed) immediately
# followed by its numeric id and a "-<lang><version>" suffix. Matches
# against either the metadata `url` field or (as a fallback) the URI string
# itself, in case a caller passes an already-versioned URI.
_SOURCE_TAIL_RE = re.compile(r"\.([A-Za-z]+?)(\d{2,})-([a-zA-Z0-9]+)(?:\.[A-Za-z0-9]+)?$")


def _load_meta(uri: str, openiti_dir: Path) -> dict[str, Any] | None:
    meta_path = openiti_dir / "meta" / f"{uri}.json"
    try:
        with meta_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None


def _resolve_death_ah(uri: str, meta: dict[str, Any] | None) -> tuple[int | None, str | None]:
    m = _URI_DEATH_AH_RE.match(uri)
    if m:
        return int(m.group(1)), "uri_prefix"
    if meta and isinstance(meta.get("death_ah"), int):
        return meta["death_ah"], "meta.death_ah"
    return None, None


def _resolve_source_lib(uri: str, meta: dict[str, Any] | None) -> tuple[str | None, str | None]:
    url = meta.get("url") if meta else None
    if url:
        m = _SOURCE_TAIL_RE.search(url)
        if m:
            return m.group(1), "meta.url_tail"
    m = _SOURCE_TAIL_RE.search(uri)
    if m:
        return m.group(1), "uri_tail"
    return None, None


def resolve(
    uri: str,
    meta: dict[str, Any] | None = None,
    openiti_dir: Path | None = None,
) -> dict[str, Any]:
    """Resolve provenance claims for a single OpenITI work URI.

    `meta` may be passed in (already-loaded JSON dict) to avoid re-reading
    the metadata file. If `meta` is omitted (left `None`) and `openiti_dir`
    is explicitly given, the resolver loads `meta/<uri>.json` itself from
    that directory. If both are omitted, resolution proceeds from the URI
    string alone — the resolver never silently reaches for the default
    `OPENITI_DIR` share, so callers who want live metadata must ask for it
    explicitly (keeps tests and offline use fast and deterministic).
    """
    if meta is None and openiti_dir is not None:
        meta = _load_meta(uri, openiti_dir)

    death_ah, death_evidence = _resolve_death_ah(uri, meta)
    source_lib, source_evidence = _resolve_source_lib(uri, meta)

    return {
        "work_uri": uri,
        "author_death_ah": death_ah,
        "source_lib_claim": source_lib,
        "evidence": {
            "author_death_ah": death_evidence,
            "source_lib_claim": source_evidence,
        },
    }
