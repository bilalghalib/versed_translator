"""C6 translations table — one row per known English edition.

Works (Arabic OpenITI identity) live in `works`. English editions live here.
A work may have zero, one, or many translation rows. ATHAR is recorded at
work level only (the parquet has no per-row work column) and is always
`eval_internal` / `private_eval` as gold (verbatim in-copyright English).

Two usage buckets (2026-08-16):

- ``train_ok`` / ``private_train`` — English we can public-GET without login
  and train on. Year of publication is irrelevant here (Watt 1953, Ivry 1974,
  Ithra 2020 are in). Not a license to ship the English in a dataset.
- ``redistribute_ok`` / ``public_wuquf`` — published-dataset English only:
  US PD (title-page 1930 or earlier, or the 95-year term) or CC0/BY/BY-SA.
  CC-BY-NC and all-rights-reserved free PDFs stay ``train_ok``.
"""

from __future__ import annotations

import csv
import io
import json
import sqlite3
from pathlib import Path
from typing import Any

from versed_translator.corpus import inventory

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH = inventory.DEFAULT_DB_PATH
DEFAULT_PD_SEED = REPO_ROOT / "corpus" / "pd_translations_seed.json"
DEFAULT_ATHAR_SEED = REPO_ROOT / "corpus" / "athar_works_seed.json"
DEFAULT_RASAIF_SEED = REPO_ROOT / "corpus" / "rasaif_works_seed.json"
DEFAULT_OPEN_ACCESS_SEED = REPO_ROOT / "corpus" / "open_access_editions.json"

# Rights that may stamp redistribute_ok on an open-access catalog row.
# Free-to-read + all-rights-reserved is not in this set.
_REDISTRIBUTE_RIGHTS = frozenset(
    {
        "PD_US_PRE_1930_PUBLICATION",
        "PD_US_95_YEAR_TERM",
        "CC0",
        "CC_BY",
        "CC_BY_SA",
    }
)

# Title-page verification (PD_TRANSLATIONS.md, 2026-08-14) dropped these as
# public English. They stay in the table so we do not rediscover them.
_DROPPED_TITLE_MARKERS = (
    "Mishkat-ul-Masabih",
    "The Life of Muhammad",
    "Arabian Society in the Middle Ages",
)

GUTENBERG_KEYWORDS = (
    "islam",
    "islamic",
    "arab",
    "arabic",
    "quran",
    "koran",
    "muhammad",
    "mohammed",
    "orient",
    "caliph",
    "hariri",
    "ghazali",
    "avicenna",
    "averroes",
    "hayy",
    "arabian nights",
    "thousand and one",
    "ibn ",
    "muslim",
    "sufi",
    "hadith",
    "maqama",
    "maqamat",
    "1001 nights",
    "suyuti",
    "tanukhi",
    "biruni",
    "alberuni",
    "usama",
)

TRANSLATIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS translations (
    id INTEGER PRIMARY KEY,
    openiti_uri TEXT,
    work_arabic_title TEXT,
    work_english_title TEXT,
    author TEXT,
    translator TEXT,
    translator_death_year TEXT,
    publication_year TEXT,
    source TEXT NOT NULL,
    source_url TEXT,
    source_id TEXT,
    digital_form TEXT,
    usage_policy TEXT NOT NULL,
    visibility TEXT NOT NULL,
    rights_status TEXT NOT NULL,
    rights_evidence TEXT,
    confidence TEXT,
    genre TEXT,
    alignment_status TEXT NOT NULL DEFAULT 'none',
    notes TEXT
);
CREATE INDEX IF NOT EXISTS translations_uri ON translations(openiti_uri);
CREATE INDEX IF NOT EXISTS translations_source ON translations(source);
CREATE INDEX IF NOT EXISTS translations_policy ON translations(usage_policy);
"""

FILES_SCHEMA = """
CREATE TABLE IF NOT EXISTS translation_files (
    edition_key TEXT PRIMARY KEY,
    translation_id INTEGER,
    openiti_uri TEXT,
    local_name TEXT NOT NULL,
    kind TEXT NOT NULL,
    source_id TEXT,
    bytes INTEGER,
    title_page_ok INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS translation_files_uri ON translation_files(openiti_uri);
CREATE INDEX IF NOT EXISTS translation_files_tid ON translation_files(translation_id);
"""


def ensure_schema(db_path: Path = DEFAULT_DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(inventory.SCHEMA)
        conn.executescript(TRANSLATIONS_SCHEMA)
        conn.executescript(FILES_SCHEMA)
        conn.commit()
    finally:
        conn.close()


def classify_pd_seed_entry(entry: dict[str, Any]) -> tuple[str, str, str]:
    """Return (usage_policy, visibility, rights_status) for a pd_seed row."""
    title = entry.get("work_english_title") or ""
    if any(marker in title for marker in _DROPPED_TITLE_MARKERS):
        return "dropped", "none", "NOT_PD_OR_NOT_A_TRANSLATION"
    if entry.get("confidence") == "high":
        rights = entry.get("rights_status") or "PD_US_PRE_1930_PUBLICATION"
        return "redistribute_ok", "public_wuquf", rights
    return "unknown", "private_eval", "PD_PLAUSIBLE_UNVERIFIED"


def classify_open_access_entry(entry: dict[str, Any]) -> tuple[str, str, str]:
    """Return (usage_policy, visibility, rights_status) for an open-access row.

    ``reuse_class=redistribute`` only becomes public when rights_status is PD
    or a permissive CC *and* confidence is high (title page or license page
    read). A free PDF with all rights reserved cannot be stamped
    ``redistribute_ok`` even if the cataloguer asks. Unverified PD stays
    ``train_ok`` until that check.
    """
    rights = str(entry.get("rights_status") or "UNKNOWN")
    reuse = entry.get("reuse_class")
    if (
        reuse == "redistribute"
        and rights in _REDISTRIBUTE_RIGHTS
        and entry.get("confidence") == "high"
    ):
        return "redistribute_ok", "public_wuquf", rights
    if reuse in {"train", "redistribute"}:
        return "train_ok", "private_train", rights
    return "unknown", "none", rights


def _insert_translation(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO translations (
            openiti_uri, work_arabic_title, work_english_title, author,
            translator, translator_death_year, publication_year, source,
            source_url, source_id, digital_form, usage_policy, visibility,
            rights_status, rights_evidence, confidence, genre,
            alignment_status, notes
        ) VALUES (
            :openiti_uri, :work_arabic_title, :work_english_title, :author,
            :translator, :translator_death_year, :publication_year, :source,
            :source_url, :source_id, :digital_form, :usage_policy, :visibility,
            :rights_status, :rights_evidence, :confidence, :genre,
            :alignment_status, :notes
        )
        """,
        row,
    )


def _blank_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "openiti_uri": None,
        "work_arabic_title": None,
        "work_english_title": None,
        "author": None,
        "translator": None,
        "translator_death_year": None,
        "publication_year": None,
        "source": None,
        "source_url": None,
        "source_id": None,
        "digital_form": None,
        "usage_policy": "unknown",
        "visibility": "private_eval",
        "rights_status": "UNKNOWN",
        "rights_evidence": None,
        "confidence": None,
        "genre": None,
        "alignment_status": "none",
        "notes": None,
    }
    row.update(overrides)
    return row


def load_pd_seed(
    db_path: Path = DEFAULT_DB_PATH, seed_path: Path = DEFAULT_PD_SEED
) -> int:
    ensure_schema(db_path)
    payload = json.loads(seed_path.read_text(encoding="utf-8"))
    entries = payload["entries"]
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DELETE FROM translations WHERE source = 'pd_seed'")
        for entry in entries:
            policy, visibility, rights = classify_pd_seed_entry(entry)
            year = entry.get("publication_year")
            death = entry.get("translator_death_year")
            _insert_translation(
                conn,
                _blank_row(
                    openiti_uri=entry.get("openiti_uri_guess"),
                    work_arabic_title=entry.get("work_arabic_title"),
                    work_english_title=entry.get("work_english_title"),
                    author=entry.get("author"),
                    translator=entry.get("translator"),
                    translator_death_year=None if death is None else str(death),
                    publication_year=None if year is None else str(year),
                    source="pd_seed",
                    source_url=entry.get("source_url"),
                    digital_form=entry.get("digital_form"),
                    usage_policy=policy,
                    visibility=visibility,
                    rights_status=rights,
                    rights_evidence=entry.get("pd_rationale"),
                    confidence=entry.get("confidence"),
                    genre=entry.get("genre"),
                    notes=entry.get("notes"),
                ),
            )
        conn.commit()
    finally:
        conn.close()
    return len(entries)


def load_athar_works(
    db_path: Path = DEFAULT_DB_PATH, seed_path: Path = DEFAULT_ATHAR_SEED
) -> int:
    ensure_schema(db_path)
    payload = json.loads(seed_path.read_text(encoding="utf-8"))
    entries = payload["entries"]
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DELETE FROM translations WHERE source = 'athar'")
        for entry in entries:
            _insert_translation(
                conn,
                _blank_row(
                    openiti_uri=entry.get("openiti_uri_guess"),
                    work_arabic_title=entry.get("work_arabic_title"),
                    work_english_title=entry.get("work_english_title"),
                    author=entry.get("author"),
                    source="athar",
                    source_url="https://huggingface.co/datasets/mohamed-khalil/ATHAR",
                    usage_policy="eval_internal",
                    visibility="private_eval",
                    rights_status="EVAL_INTERNAL_IN_COPYRIGHT_ENGLISH",
                    rights_evidence=entry.get("known_english"),
                    notes=(
                        "ATHAR work-level index only. English never ships. "
                        f"pd_english_known={entry.get('pd_english_known')}"
                    ),
                ),
            )
        conn.commit()
    finally:
        conn.close()
    return len(entries)


def load_rasaif_biblio(
    db_path: Path = DEFAULT_DB_PATH, seed_path: Path = DEFAULT_RASAIF_SEED
) -> int:
    """Load Al-Ghamdi's work list as bibliography only. No English text."""
    ensure_schema(db_path)
    payload = json.loads(seed_path.read_text(encoding="utf-8"))
    entries = payload["entries"]
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DELETE FROM translations WHERE source = 'rasaif_biblio'")
        for entry in entries:
            _insert_translation(
                conn,
                _blank_row(
                    openiti_uri=entry.get("openiti_uri_guess"),
                    work_arabic_title=entry.get("work_arabic_title"),
                    work_english_title=entry.get("work_english_title"),
                    author=entry.get("author"),
                    source="rasaif_biblio",
                    source_url="https://ahmedhsalghamdi.github.io/arabic-english-rasaif-corpus/",
                    source_id=entry.get("rasaif_key"),
                    digital_form="bibliography",
                    usage_policy="unknown",
                    visibility="none",
                    rights_status="BIBLIOGRAPHY_ONLY_NO_TEXT",
                    rights_evidence=entry.get("rasaif_english"),
                    alignment_status="bibliography_only",
                    notes=(
                        "Rasaif bibliography only. Do not ingest the parallel CSV. "
                        f"pd_english_known={entry.get('pd_english_known')}"
                    ),
                ),
            )
        conn.commit()
    finally:
        conn.close()
    return len(entries)


def load_open_access(
    db_path: Path = DEFAULT_DB_PATH, seed_path: Path = DEFAULT_OPEN_ACCESS_SEED
) -> int:
    """Load modern free-to-read editions. Does not download files.

    ``train_ok`` rows are catalog only: do not fetch them into pd-english.
    """
    ensure_schema(db_path)
    payload = json.loads(seed_path.read_text(encoding="utf-8"))
    entries = payload["entries"]
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DELETE FROM translations WHERE source = 'open_access'")
        for entry in entries:
            policy, visibility, rights = classify_open_access_entry(entry)
            year = entry.get("publication_year")
            death = entry.get("translator_death_year")
            _insert_translation(
                conn,
                _blank_row(
                    openiti_uri=entry.get("openiti_uri_guess"),
                    work_arabic_title=entry.get("work_arabic_title"),
                    work_english_title=entry.get("work_english_title"),
                    author=entry.get("author"),
                    translator=entry.get("translator"),
                    translator_death_year=None if death is None else str(death),
                    publication_year=None if year is None else str(year),
                    source="open_access",
                    source_url=entry.get("source_url"),
                    source_id=entry.get("edition_key"),
                    digital_form=entry.get("digital_form"),
                    usage_policy=policy,
                    visibility=visibility,
                    rights_status=rights,
                    rights_evidence=entry.get("rights_evidence"),
                    confidence=entry.get("confidence"),
                    genre=entry.get("genre"),
                    alignment_status="bibliography_only",
                    notes=entry.get("notes"),
                ),
            )
        conn.commit()
    finally:
        conn.close()
    return len(entries)


def _catalog_rows(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;")
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    return list(reader)


def _field(row: dict[str, str | None], *names: str) -> str:
    lower: dict[str, str] = {}
    for key, value in row.items():
        if key is None:
            continue
        lower[key.lower()] = value or ""
    for name in names:
        value = row.get(name) or lower.get(name.lower())
        if value:
            return value
    return ""


def gutenberg_keyword_hits(csv_path: Path) -> list[dict[str, str]]:
    """Return Gutenberg catalog rows whose title/subjects/authors look relevant.

    This is a harvest candidate list, not a rights determination.
    """
    hits: list[dict[str, str]] = []
    for raw in _catalog_rows(csv_path):
        language = _field(raw, "Language", "language").lower()
        if language and language != "en" and "en" not in language.split(";"):
            continue
        blob = " ".join(
            [
                _field(raw, "Title", "title"),
                _field(raw, "Subjects", "subjects"),
                _field(raw, "Authors", "authors"),
                _field(raw, "Bookshelves", "bookshelves"),
            ]
        ).lower()
        if not any(keyword in blob for keyword in GUTENBERG_KEYWORDS):
            continue
        hits.append(
            {
                "source_id": _field(raw, "Text#", "text#", "id"),
                "title": _field(raw, "Title", "title"),
                "language": _field(raw, "Language", "language"),
                "authors": _field(raw, "Authors", "authors"),
                "subjects": _field(raw, "Subjects", "subjects"),
            }
        )
    return hits


def translation_stats(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    conn = sqlite3.connect(db_path)
    try:
        total = conn.execute("SELECT COUNT(*) FROM translations").fetchone()[0]
        by_policy = dict(
            conn.execute(
                "SELECT usage_policy, COUNT(*) FROM translations GROUP BY usage_policy"
            ).fetchall()
        )
        by_source = dict(
            conn.execute(
                "SELECT source, COUNT(*) FROM translations GROUP BY source"
            ).fetchall()
        )
        public = conn.execute(
            "SELECT COUNT(*) FROM translations WHERE visibility = 'public_wuquf'"
        ).fetchone()[0]
        train_ok = conn.execute(
            "SELECT COUNT(*) FROM translations WHERE usage_policy = 'train_ok'"
        ).fetchone()[0]
        with_uri = conn.execute(
            "SELECT COUNT(*) FROM translations WHERE openiti_uri IS NOT NULL AND openiti_uri != ''"
        ).fetchone()[0]
        unique_works = conn.execute(
            "SELECT COUNT(DISTINCT openiti_uri) FROM translations "
            "WHERE openiti_uri IS NOT NULL AND openiti_uri != '' "
            "AND usage_policy != 'quarantine' "
            "AND IFNULL(alignment_status, 'none') != 'bibliography_only'"
        ).fetchone()[0]
        unique_including_quarantine = conn.execute(
            "SELECT COUNT(DISTINCT openiti_uri) FROM translations "
            "WHERE openiti_uri IS NOT NULL AND openiti_uri != ''"
        ).fetchone()[0]
        alias_candidates = conn.execute(
            "SELECT COUNT(*) FROM translations WHERE confidence = 'alias' "
            "AND usage_policy = 'unknown'"
        ).fetchone()[0]
        duplicates = conn.execute(
            "SELECT COUNT(*) FROM translations WHERE alignment_status = 'duplicate_pd_seed'"
        ).fetchone()[0]
        works_total = conn.execute("SELECT COUNT(*) FROM works").fetchone()[0]
        try:
            files_on_disk = conn.execute("SELECT COUNT(*) FROM translation_files").fetchone()[0]
            public_with_files = conn.execute(
                """
                SELECT COUNT(DISTINCT t.id) FROM translations t
                JOIN translation_files f ON f.translation_id = t.id
                WHERE t.visibility = 'public_wuquf'
                """
            ).fetchone()[0]
            files_title_ok = conn.execute(
                "SELECT COUNT(*) FROM translation_files WHERE title_page_ok = 1"
            ).fetchone()[0]
        except sqlite3.OperationalError:
            files_on_disk = 0
            public_with_files = 0
            files_title_ok = 0
    finally:
        conn.close()
    return {
        "translations": total,
        "public_wuquf": public,
        "train_ok": train_ok,
        "joined_to_openiti": with_uri,
        "unique_openiti_works": unique_works,
        "unique_including_quarantine": unique_including_quarantine,
        "alias_candidates": alias_candidates,
        "duplicate_pd_seed": duplicates,
        "works_total": works_total,
        "files_on_disk": files_on_disk,
        "public_with_files": public_with_files,
        "files_title_ok": files_title_ok,
        "by_policy": by_policy,
        "by_source": by_source,
    }
