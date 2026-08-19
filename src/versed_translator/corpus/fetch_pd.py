"""Download public pd_seed English texts off-repo and record them in the DB.

A successful fetch is not a rights stamp. Burton / Mathers / reprints that
failed title-page checks are not in the file map. Texts never go in git.
"""

from __future__ import annotations

import json
import re
import sqlite3
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from versed_translator.corpus import translations
from versed_translator.corpus.catalogs import USER_AGENT
from versed_translator.corpus.inventory import REPO_ROOT

DEFAULT_MAP = REPO_ROOT / "corpus" / "pd_english_files.json"
DEFAULT_TRAIN_MAP = REPO_ROOT / "corpus" / "train_english_files.json"
DEFAULT_DEST = Path.home() / "versed-translator-data" / "pd-english"
DEFAULT_TRAIN_DEST = Path.home() / "versed-translator-data" / "train-english"
TITLE_WINDOW = 80_000

Opener = Callable[[str], bytes]


class TitlePageError(ValueError):
    """Downloaded bytes failed the edition needles / reject list."""


def load_file_map(path: Path = DEFAULT_MAP) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    files = payload["files"]
    if not isinstance(files, list) or not files:
        raise ValueError(f"no files in {path}")
    return files


def remote_url(entry: dict[str, Any]) -> str | None:
    kind = entry["kind"]
    if kind == "local":
        return None
    if kind == "http":
        url = str(entry.get("url") or "")
        return url or None
    source_id = str(entry.get("source_id") or "")
    if kind == "gutenberg":
        return f"https://www.gutenberg.org/cache/epub/{source_id}/pg{source_id}.txt"
    if kind == "ia_djvu":
        name = str(entry.get("remote_name") or f"{source_id}_djvu.txt")
        quoted = urllib.parse.quote(name, safe="()_-.")
        return f"https://archive.org/download/{source_id}/{quoted}"
    raise ValueError(f"unknown kind {kind!r} for {entry.get('id')}")


def _fold(text: str) -> str:
    """OCR title pages split words across newlines and double-space letters."""
    return re.sub(r"\s+", " ", text.lower())


def _is_pdf(entry: dict[str, Any]) -> bool:
    name = str(entry.get("local_name") or "")
    url = str(entry.get("url") or "")
    return name.lower().endswith(".pdf") or url.lower().endswith(".pdf")


def _title_text(raw: bytes, entry: dict[str, Any]) -> str:
    if _is_pdf(entry):
        body = raw.lstrip()
        if not body.startswith(b"%PDF"):
            raise TitlePageError(f"{entry['id']}: body is not a PDF")
        return body[:TITLE_WINDOW].decode("latin-1", errors="replace")
    return raw.decode("utf-8", errors="replace")


def check_title_page(text: str, entry: dict[str, Any], *, window: int | None = None) -> None:
    if window is None:
        window = int(entry.get("title_window") or TITLE_WINDOW)
    blob = _fold(text[:window])
    for needle in entry.get("reject") or []:
        if needle.lower() in blob:
            raise TitlePageError(
                f"{entry['id']}: reject needle {needle!r} in title-page window"
            )
    missing = [
        needle for needle in entry.get("needles") or [] if needle.lower() not in blob
    ]
    if missing:
        raise TitlePageError(f"{entry['id']}: missing title-page needles {missing}")


def title_page_ok(path: Path, entry: dict[str, Any]) -> bool:
    raw = path.read_bytes()
    try:
        check_title_page(_title_text(raw, entry), entry)
        return True
    except TitlePageError:
        return False


def _download(url: str, opener: Opener | None = None) -> bytes:
    if opener is not None:
        return opener(url)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=300) as response:
        return response.read()


def _ia_cors_url(source_id: str, remote_name: str) -> str:
    """IA /cors/ often serves djvu.txt when /download/ 500s. No metadata call."""
    quoted = urllib.parse.quote(remote_name, safe="()_-.")
    return f"https://archive.org/cors/{source_id}/{quoted}"


def _ia_storage_url(source_id: str, remote_name: str, opener: Opener | None = None) -> str | None:
    """Direct item URL from IA metadata. /download/ often 500s; the storage node does not."""
    meta = json.loads(
        _download(f"https://archive.org/metadata/{source_id}", opener=opener).decode(
            "utf-8", errors="replace"
        )
    )
    host = meta.get("d1") or meta.get("d2")
    directory = meta.get("dir")
    if not host or not directory:
        return None
    quoted = urllib.parse.quote(remote_name, safe="()_-.")
    return f"https://{host}{directory}/{quoted}"


def fetch_one(
    entry: dict[str, Any],
    dest_dir: Path,
    *,
    opener: Opener | None = None,
) -> dict[str, Any]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    local_name = str(entry["local_name"])
    path = dest_dir / local_name
    url = remote_url(entry)
    if path.exists() and path.stat().st_size > 0:
        ok = title_page_ok(path, entry)
        return {
            "id": entry["id"],
            "status": "skipped",
            "path": str(path),
            "bytes": path.stat().st_size,
            "url": url,
            "title_page_ok": ok,
        }
    if not url:
        return {
            "id": entry["id"],
            "status": "missing",
            "path": str(path),
            "bytes": 0,
            "url": None,
            "title_page_ok": False,
        }
    urls = [url]
    for extra in entry.get("url_fallbacks") or []:
        extra = str(extra)
        if extra and extra not in urls:
            urls.append(extra)
    raw = b""
    last_exc: Exception | None = None
    used = url
    for candidate in urls:
        try:
            raw = _download(candidate, opener=opener)
            used = candidate
            last_exc = None
            break
        except OSError as exc:
            last_exc = exc
    if last_exc is not None and not raw and entry.get("kind") == "ia_djvu":
        source_id = str(entry.get("source_id") or "")
        remote_name = str(entry.get("remote_name") or f"{source_id}_djvu.txt")
        cors = _ia_cors_url(source_id, remote_name)
        try:
            raw = _download(cors, opener=opener)
            used = cors
            last_exc = None
        except OSError as exc:
            last_exc = exc
        if last_exc is not None and not raw:
            storage = _ia_storage_url(source_id, remote_name, opener=opener)
            if storage:
                try:
                    raw = _download(storage, opener=opener)
                    used = storage
                    last_exc = None
                except OSError as exc:
                    last_exc = exc
    if last_exc is not None and not raw:
        raise last_exc
    check_title_page(_title_text(raw, entry), entry)
    tmp = path.with_name(path.name + ".part")
    tmp.write_bytes(raw)
    tmp.replace(path)
    return {
        "id": entry["id"],
        "status": "fetched",
        "path": str(path),
        "bytes": path.stat().st_size,
        "url": used,
        "title_page_ok": True,
    }


def write_manifest(dest_dir: Path, results: list[dict[str, Any]]) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / "manifest.json"
    path.write_text(
        json.dumps({"files": results}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def fetch_all(
    dest_dir: Path = DEFAULT_DEST,
    *,
    map_path: Path = DEFAULT_MAP,
    opener: Opener | None = None,
) -> dict[str, Any]:
    entries = load_file_map(map_path)
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    for entry in entries:
        try:
            results.append(fetch_one(entry, dest_dir, opener=opener))
        except (TitlePageError, OSError, ValueError) as exc:
            errors.append(str(exc))
            results.append(
                {
                    "id": entry.get("id"),
                    "status": "error",
                    "error": str(exc),
                    "url": remote_url(entry) if entry.get("kind") else None,
                }
            )
    manifest = write_manifest(dest_dir, results)
    return {
        "fetched": sum(1 for row in results if row.get("status") == "fetched"),
        "skipped": sum(1 for row in results if row.get("status") == "skipped"),
        "missing": sum(1 for row in results if row.get("status") == "missing"),
        "errors": errors,
        "results": results,
        "manifest": str(manifest),
    }


def lookup_pd_seed_id(conn: sqlite3.Connection, entry: dict[str, Any]) -> int | None:
    uri = (entry.get("openiti_uri") or "").strip()
    match = (entry.get("match_title") or "").strip().lower()
    if uri:
        rows = conn.execute(
            """
            SELECT id, work_english_title FROM translations
            WHERE source = 'pd_seed' AND openiti_uri = ?
            """,
            (uri,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, work_english_title FROM translations WHERE source = 'pd_seed'"
        ).fetchall()
    if match:
        matched = [row for row in rows if match in (row[1] or "").lower()]
        if matched:
            rows = matched
    if not rows:
        return None
    return int(rows[0][0])


def lookup_translation_id(conn: sqlite3.Connection, entry: dict[str, Any]) -> int | None:
    source = str(entry.get("source") or "pd_seed")
    key = str(entry.get("lookup_id") or entry.get("id") or "")
    if source == "open_access" and key:
        row = conn.execute(
            """
            SELECT id FROM translations
            WHERE source = 'open_access' AND source_id = ?
            """,
            (key,),
        ).fetchone()
        return int(row[0]) if row else None
    return lookup_pd_seed_id(conn, entry)


def record_files(
    db_path: Path,
    dest_dir: Path,
    *,
    map_path: Path,
) -> dict[str, Any]:
    """Upsert translation_files for one map. Does not wipe other buckets or stamp rights."""
    translations.ensure_schema(db_path)
    entries = load_file_map(map_path)
    recorded = 0
    missing = 0
    unmatched = 0
    conn = sqlite3.connect(db_path)
    try:
        conn.executemany(
            "DELETE FROM translation_files WHERE edition_key = ?",
            [(str(entry["id"]),) for entry in entries],
        )
        for entry in entries:
            path = dest_dir / str(entry["local_name"])
            if not path.exists() or path.stat().st_size <= 0:
                missing += 1
                continue
            translation_id = lookup_translation_id(conn, entry)
            if translation_id is None:
                unmatched += 1
            conn.execute(
                """
                INSERT INTO translation_files (
                    edition_key, translation_id, openiti_uri, local_name,
                    kind, source_id, bytes, title_page_ok
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry["id"],
                    translation_id,
                    entry.get("openiti_uri"),
                    entry["local_name"],
                    entry["kind"],
                    entry.get("source_id") or None,
                    path.stat().st_size,
                    1 if title_page_ok(path, entry) else 0,
                ),
            )
            recorded += 1
        conn.commit()
    finally:
        conn.close()
    return {
        "recorded": recorded,
        "missing": missing,
        "unmatched": unmatched,
    }


def record_pd_files(
    db_path: Path,
    dest_dir: Path = DEFAULT_DEST,
    *,
    map_path: Path = DEFAULT_MAP,
) -> dict[str, Any]:
    """Write translation_files rows. Does not change usage_policy or visibility."""
    return record_files(db_path, dest_dir, map_path=map_path)


def record_train_files(
    db_path: Path,
    dest_dir: Path = DEFAULT_TRAIN_DEST,
    *,
    map_path: Path = DEFAULT_TRAIN_MAP,
) -> dict[str, Any]:
    """Record train-only files. Does not stamp redistribute_ok or wipe pd-english rows."""
    return record_files(db_path, dest_dir, map_path=map_path)
