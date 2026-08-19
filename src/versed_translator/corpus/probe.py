"""Sequential IA probe: find public-GET English translations we do not already have.

Walks Archive.org queries plus leftover catalog identifiers, skips nights/Quran/
Persian/reprints/login walls, and optionally fetches djvu.txt into pd-english.
A probe hit is not a rights stamp until the title-page year is read.
"""

from __future__ import annotations

import json
import re
import sqlite3
import urllib.parse
from pathlib import Path
from typing import Any, Callable

from versed_translator.corpus import fetch_pd, join as join_mod, translations
from versed_translator.corpus.inventory import REPO_ROOT

DEFAULT_OUT = REPO_ROOT / "corpus" / "cache" / "probe_hits.json"
DEFAULT_DB = translations.DEFAULT_DB_PATH

# Book-length PD English that is not already a known work, or later volumes of one.
# Title-only "translated from the arabic" is mostly Nights/Hariri/Quran (already skipped).
# Phrase-in-record + named translators/series find the leftovers.
DEEP_QUERIES = (
    '"translated from the arabic" AND mediatype:texts AND date:[1700 TO 1930] AND language:(eng OR english)',
    '"from the arabic of" AND mediatype:texts AND date:[1700 TO 1930]',
    '"rendered from the arabic" AND mediatype:texts AND date:[1700 TO 1930]',
    'publisher:"Oriental Translation Fund" AND language:eng AND mediatype:texts',
    'publisher:"Royal Asiatic" AND arabic AND language:eng AND date:[1800 TO 1930] AND mediatype:texts',
    'publisher:Luzac AND (arabic OR islam) AND language:eng AND date:[1890 TO 1930] AND mediatype:texts',
    'creator:Finkel AND (jahiz OR djahiz OR arabic) AND mediatype:texts',
    'creator:"Le Strange" AND language:eng AND mediatype:texts AND date:[1870 TO 1930]',
    'creator:Evetts AND mediatype:texts',
    'creator:Lyall AND (arabic OR mufaddal OR ancient) AND mediatype:texts',
    'creator:Amedroz AND mediatype:texts',
    'creator:Hitti AND mediatype:texts AND date:[1910 TO 1935]',
    'creator:Rosen AND (algebra OR khwarizmi OR khowarizmi) AND mediatype:texts',
    'creator:Reynolds AND (jerusalem OR temple) AND mediatype:texts',
    'creator:Malan AND (copt OR maqrizi OR makrizi) AND mediatype:texts',
    'creator:Friedlaender AND (hazm OR shiite OR heterodox) AND mediatype:texts',
    'creator:Guillaume AND mediatype:texts AND date:[1900 TO 1930]',
    'creator:Macdonald AND (ghazzali OR ghazali) AND mediatype:texts AND date:[1890 TO 1930]',
    'creator:Gairdner AND mediatype:texts',
    'creator:Nicholson AND (tarjuman OR diwan) AND mediatype:texts AND date:[1890 TO 1930]',
    'creator:Margoliouth AND language:eng AND mediatype:texts AND date:[1890 TO 1930]',
    'creator:Sachau AND mediatype:texts',
    'creator:Ockley AND mediatype:texts',
    'title:"Palestine under the Moslems"',
    'title:"three essays" AND (jahiz OR gahiz)',
    'title:"history of the patriarchs"',
    'title:"algebra of" AND (mohammed OR musa OR khowarizmi)',
    'title:"temple of jerusalem" AND reynolds',
    'title:"mufaddaliyat" OR title:"mufaddaliyyat"',
    'title:"eclipse of the abbasid"',
    'title:"table-talk of a mesopotamian"',
    'title:"hayy ibn" OR title:"hai ebn" OR title:"improvement of human reason"',
    'title:"secret of secrets" OR title:"secretum secretorum" AND date:[1800 TO 1930]',
    'title:"ibn jubair" OR title:"ibn jubayr"',
    'title:"marvels of india" AND date:[1800 TO 1930]',
    'publisher:"Gibb Memorial" AND language:eng AND date:[1900 TO 1930] AND mediatype:texts',
    'series:"Bibliotheca Indica" AND (arabic OR islam) AND language:eng AND date:[1800 TO 1930]',
    'creator:Gayangos AND mediatype:texts',
)

# Always look at these leftover volumes even if scrape misses them.
SEED_IDENTIFIERS = (
    "TheTable-talkOfAMesopotamianJudgePart2",
    "TheTable-talkOfAMesopotamianJudgePart8",
    "eclipseofabbasid06ameduoft",
    "eclipseofabbasid07ameduoft",
)


def identifier_is_seed_volume(source_id: str) -> bool:
    return source_id in SEED_IDENTIFIERS

SKIP_TITLE = (
    "nights",
    "thousand and one",
    "arabian nights",
    "koran",
    "qur'an",
    "quran",
    "burton",
    "mardrus",
    "persian",
    "chinese",
    "sanskrit",
    "turkish empire",
    "grammar",
    "dictionary of",
    "lexicon",
    "lectures delivered",
    "coins",
    "missionary",
    "wikiquote",
    "thingiverse",
    "women of persia",
    "hafiz ool",
    "sheikh mohammed ali hazin",
    "hydur naik",
    "harivansa",
    "gospel of st peter",
    "marocco",
    "alberta",
    "greek and roman",
    "druze people",
    "catalogue of",
    "catalog of",
    "reading lessons",
    "student edition of the arabic",
    "johnson reprint",
    "ams press",
    "classics of medicine",
    "assemblies of al",
    "khallikan",
    "bedoueen romance",
    "diatessaron",
    "earliest life of christ",
    "ottoman literature",
    "hindustani",
    "aboulfeda",
    "beasts at law",
    "ilm al-nikah",
    "kitab al-izah",
    "book of exposition",
)

SKIP_SOURCE_PREFIX = (
    "344",  # Burton Gutenberg 3435-3450
)

MIN_YEAR = 1700
MAX_PD_YEAR = 1930
MIN_DJVU_BYTES = 80_000

Opener = Callable[[str], bytes]
JsonOpener = Callable[[str], dict[str, Any]]


def _fold(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower())


def already_have_ids(
    pd_map: Path = fetch_pd.DEFAULT_MAP,
    train_map: Path = fetch_pd.DEFAULT_TRAIN_MAP,
) -> set[str]:
    have: set[str] = set()
    for path in (pd_map, train_map):
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for row in (payload.get("files") or []) + (payload.get("not_fetched") or []):
            sid = str(row.get("source_id") or "").strip()
            if sid:
                have.add(sid)
            have.add(str(row.get("id") or ""))
    have.discard("")
    return have


def skip_reason(title: str, source_id: str = "") -> str | None:
    blob = _fold(title)
    sid = (source_id or "").lower()
    for marker in SKIP_TITLE:
        if marker in blob:
            return f"skip_title:{marker}"
    if sid.startswith(SKIP_SOURCE_PREFIX) or sid in {str(n) for n in range(3435, 3451)}:
        return "skip_burton"
    if "16955" in sid or "2800" in sid:
        return "skip_quran_bundle"
    return None


def year_int(value: str) -> int | None:
    match = re.search(r"(17|18|19|20)\d{2}", value or "")
    if not match:
        return None
    return int(match.group(0))


def classify_item(
    *,
    title: str,
    source_id: str,
    year: str,
    restricted: str | None,
    djvu_name: str | None,
    djvu_size: int,
    have: set[str],
) -> dict[str, Any]:
    if source_id in have:
        return {"decision": "have", "reason": "already_on_disk"}
    skipped = skip_reason(title, source_id)
    if skipped:
        return {"decision": "skip", "reason": skipped}
    if str(restricted).lower() in {"true", "1"}:
        return {"decision": "skip", "reason": "access_restricted"}
    if not djvu_name:
        return {"decision": "skip", "reason": "no_djvu_txt"}
    if djvu_size and djvu_size < MIN_DJVU_BYTES:
        return {"decision": "skip", "reason": f"too_small:{djvu_size}"}
    yr = year_int(year)
    if identifier_is_seed_volume(source_id):
        if source_id.endswith("07ameduoft"):
            return {"decision": "skip", "reason": "eclipse_index"}
        return {"decision": "fetch", "reason": "seed_volume"}
    if yr is None:
        return {"decision": "review", "reason": "no_year"}
    if yr < MIN_YEAR:
        return {"decision": "skip", "reason": f"year:{yr}"}
    if yr > MAX_PD_YEAR:
        return {"decision": "train_or_skip", "reason": f"after_1930:{yr}"}
    blob = _fold(title)
    if "translated" in blob or "translation" in blob or "gayangos" in blob:
        return {"decision": "fetch", "reason": f"pd_year:{yr}"}
    return {"decision": "review", "reason": f"pd_year_no_trans_marker:{yr}"}


def _ia_meta(identifier: str, opener: JsonOpener | None = None) -> dict[str, Any]:
    url = f"https://archive.org/metadata/{identifier}"
    if opener is not None:
        return opener(url)
    raw = fetch_pd._download(url)
    return json.loads(raw.decode("utf-8", errors="replace"))


def probe_identifier(
    identifier: str,
    *,
    have: set[str] | None = None,
    opener: JsonOpener | None = None,
    title_hint: str = "",
) -> dict[str, Any]:
    have = have if have is not None else already_have_ids()
    try:
        payload = _ia_meta(identifier, opener=opener)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "source_id": identifier,
            "decision": "error",
            "reason": str(exc),
            "title": title_hint,
        }
    meta = payload.get("metadata") or {}
    files = payload.get("files") or []
    djvu = next(
        (f for f in files if str(f.get("name") or "").endswith("_djvu.txt")),
        None,
    )
    title = str(meta.get("title") or title_hint or identifier)
    year, status = join_mod.year_from_ia_metadata(payload)
    size = int(djvu.get("size") or 0) if djvu else 0
    decision = classify_item(
        title=title,
        source_id=identifier,
        year=year,
        restricted=meta.get("access-restricted-item"),
        djvu_name=str(djvu["name"]) if djvu else None,
        djvu_size=size,
        have=have,
    )
    return {
        "source_id": identifier,
        "title": title,
        "year": year,
        "copyright_status": status,
        "djvu": djvu["name"] if djvu else None,
        "djvu_size": size,
        "creator": meta.get("creator"),
        "language": meta.get("language"),
        **decision,
    }


def search_archive(
    query: str,
    *,
    opener: JsonOpener | None = None,
    rows: int = 40,
) -> list[dict[str, str]]:
    """Small IA advancedsearch page. Avoids the 10k-row harvest scrape."""
    params = urllib.parse.urlencode(
        {"q": query, "rows": rows, "page": 1, "output": "json"}
    )
    url = (
        "https://archive.org/advancedsearch.php?"
        + params
        + "&fl[]=identifier&fl[]=title&fl[]=year&fl[]=date&fl[]=creator"
    )
    if opener is not None:
        payload = opener(url)
    else:
        payload = json.loads(
            fetch_pd._download(url).decode("utf-8", errors="replace")
        )
    docs = (payload.get("response") or {}).get("docs") or payload.get("items") or []
    hits: list[dict[str, str]] = []
    for doc in docs:
        sid = str(doc.get("identifier") or doc.get("source_id") or "")
        if not sid:
            continue
        hits.append(
            {
                "source_id": sid,
                "title": str(doc.get("title") or ""),
                "year": str(doc.get("year") or doc.get("date") or ""),
                "authors": str(doc.get("creator") or doc.get("authors") or ""),
            }
        )
    return hits


def leftover_catalog_ids(db_path: Path = DEFAULT_DB) -> list[tuple[str, str]]:
    """Alias duplicates whose IA id is not already on disk (later volumes, extra scans)."""
    have = already_have_ids()
    if not db_path.exists():
        return []
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT source_id, work_english_title
            FROM translations
            WHERE source IN ('archive_org', 'otf')
              AND source_id IS NOT NULL AND source_id != ''
              AND confidence = 'alias'
            """
        ).fetchall()
    finally:
        conn.close()
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for source_id, title in rows:
        if source_id in have or source_id in seen:
            continue
        seen.add(source_id)
        if skip_reason(title or "", source_id):
            continue
        out.append((source_id, title or ""))
    return out


def collect_candidates(
    *,
    queries: tuple[str, ...] = DEEP_QUERIES,
    extra_ids: list[tuple[str, str]] | None = None,
    scrape_opener: JsonOpener | None = None,
    rows: int = 40,
) -> dict[str, str]:
    """Map IA identifier -> title hint."""
    found: dict[str, str] = {}
    for ident in SEED_IDENTIFIERS:
        found[ident] = ident
    for ident, title in extra_ids or []:
        found.setdefault(ident, title)
    for query in queries:
        for hit in search_archive(query, opener=scrape_opener, rows=rows):
            sid = hit.get("source_id") or ""
            if sid:
                found.setdefault(sid, hit.get("title") or sid)
    return found


def run_probe(
    *,
    dest: Path = DEFAULT_OUT,
    db_path: Path = DEFAULT_DB,
    fetch: bool = False,
    pd_dir: Path | None = None,
    limit: int = 80,
    include_leftovers: bool = False,
    opener: JsonOpener | None = None,
    scrape_opener: JsonOpener | None = None,
) -> dict[str, Any]:
    have = already_have_ids()
    leftovers = leftover_catalog_ids(db_path) if include_leftovers else []
    candidates = collect_candidates(
        extra_ids=leftovers, scrape_opener=scrape_opener
    )
    hits: list[dict[str, Any]] = []
    fetched: list[dict[str, Any]] = []
    n = 0
    for source_id, title in candidates.items():
        if n >= limit:
            break
        n += 1
        row = probe_identifier(
            source_id, have=have, opener=opener, title_hint=title
        )
        hits.append(row)
        if fetch and row.get("decision") == "fetch" and row.get("djvu"):
            entry = {
                "id": f"probe_{source_id}"[:80],
                "kind": "ia_djvu",
                "source_id": source_id,
                "remote_name": row["djvu"],
                "local_name": f"probe_{re.sub(r'[^a-zA-Z0-9._-]+', '_', source_id)[:60]}_djvu.txt",
                "needles": [],
                "reject": ["johnson reprint", "ams press", "1964", "1984", "1987"],
            }
            try:
                result = fetch_pd.fetch_one(entry, pd_dir or fetch_pd.DEFAULT_DEST)
                fetched.append(result)
                have.add(source_id)
            except (fetch_pd.TitlePageError, OSError, ValueError) as exc:
                fetched.append({"id": source_id, "status": "error", "error": str(exc)})
    summary = {
        "probed": len(hits),
        "fetch": sum(1 for h in hits if h.get("decision") == "fetch"),
        "skip": sum(1 for h in hits if h.get("decision") == "skip"),
        "have": sum(1 for h in hits if h.get("decision") == "have"),
        "review": sum(1 for h in hits if h.get("decision") == "review"),
        "train_or_skip": sum(1 for h in hits if h.get("decision") == "train_or_skip"),
        "error": sum(1 for h in hits if h.get("decision") == "error"),
        "fetched_ok": sum(1 for r in fetched if r.get("status") in {"fetched", "skipped"}),
    }
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps({"summary": summary, "hits": hits, "fetched": fetched}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    return {"summary": summary, "hits": hits, "fetched": fetched, "path": str(dest)}
