"""Join English catalog hits onto OpenITI works.

Matches are catalog candidates only: usage_policy stays ``unknown`` and
visibility stays ``private_eval``. A join is not a rights determination.
"""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from versed_translator.corpus import translations

# If every needle appears in the normalized hit, force this URI (when present
# in the works list). Order matters: first match wins.
ALIASES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("hayy", "yaqzan"), "0581IbnTufayl.HayyIbnYaqzan"),
    (("hayy", "yaqdan"), "0581IbnTufayl.HayyIbnYaqzan"),
    (("assemblies", "hariri"), "0516IbnCaliHariri.Maqamat"),
    (("maqamat", "hariri"), "0516IbnCaliHariri.Maqamat"),
    (("thousand", "nights"), "1300Anonymous.AlfLaylaWaLayla"),
    (("arabian", "nights", "entertainments"), "1300Anonymous.AlfLaylaWaLayla"),
    (("alf", "layla"), "1300Anonymous.AlfLaylaWaLayla"),
    (("origins", "islamic", "state"), "0279Baladhuri.FutuhBuldan"),
    (("baladhuri",), "0279Baladhuri.FutuhBuldan"),
    (("khallikan",), "0681IbnKhallikan.WafayatAcyan"),
    (("kalila",), "0139IbnMuqaffac.KalilaWaDimna"),
    (("antar", "bedoueen"), "0800Anonymous.SiratCantara"),
    (("ibn", "batuta"), "0779IbnBattuta.Rihla"),
    (("ibn", "battuta"), "0779IbnBattuta.Rihla"),
    (("miskawayh", "eclipse"), "0421Miskawayh.Tajarib"),
    (("suyuti", "khulafa"), "0911Suyuti.TarikhKhulafa"),
    (("jarrett", "caliphs"), "0911Suyuti.TarikhKhulafa"),
    (("tanukhi",), "0384MuhassinTanukhi.NishwarMuhadara"),
    (("nishwar",), "0384MuhassinTanukhi.NishwarMuhadara"),
    (("biruni", "india"), "0440AbuRayhanBiruni.TahqiqMaLilHind"),
    (("alberuni", "india"), "0440AbuRayhanBiruni.TahqiqMaLilHind"),
    (("biruni",), "0440AbuRayhanBiruni.AtharBaqiya"),
    (("albiruni",), "0440AbuRayhanBiruni.AtharBaqiya"),
    (("sachau", "chronology"), "0440AbuRayhanBiruni.AtharBaqiya"),
    (("usama", "munqidh"), "0584IbnMunqidhShayzari.Ictibar"),
    (("syrian", "gentleman"), "0584IbnMunqidhShayzari.Ictibar"),
    (("golden", "odes"), "0486IbnAhmadZuzani.SharhMucallaqat"),
    (("muallaqat",), "0486IbnAhmadZuzani.SharhMucallaqat"),
    (("koran",), "0001Quran.Mushaf"),
    (("qur an",), "0001Quran.Mushaf"),
    (("book", "idols"), "0204IbnKalbi.Asnam"),
    (("moslem", "schisms"), "0429IbnTahirBaghdadi.FarqBaynaFiraq"),
    (("muslim", "schisms"), "0429IbnTahirBaghdadi.FarqBaynaFiraq"),
    (("ring", "dove"), "0456IbnHazm.TawqHamama"),
    (("tawq", "hamama"), "0456IbnHazm.TawqHamama"),
    (("canon", "medicine"), "0428IbnSina.QanunFiTibb"),
    (("qanun", "tibb"), "0428IbnSina.QanunFiTibb"),
    (("book", "misers"), "0255Jahiz.Bukhala"),
    (("avarice", "avaricious"), "0255Jahiz.Bukhala"),
    (("peak", "eloquence"), "0406SharifRadi.NahjBalagha"),
    (("nahj", "balagha"), "0406SharifRadi.NahjBalagha"),
    (("muqaddimah",), "0808IbnKhaldun.Tarikh"),
    (("history", "tabari"), "0310Tabari.Tarikh"),
    (("unique", "necklace"), "0328IbnCabdRabbih.CiqdFarid"),
    (("iqd", "farid"), "0328IbnCabdRabbih.CiqdFarid"),
    (("epistle", "legal", "theory"), "0204Shafici.Risala"),
    (("optics", "haytham"), "0430IbnHaytham.Manazir"),
    (("albucasis",), "0400AbuQasimZahrawi.Tasrif"),
    (("book", "strangers"), "0362AbuFarajIsbahani.AdabGhuraba"),
    (("excellence", "arabs"), "0276IbnQutaybaDinawari.FadlCarab"),
    (("history", "saladin"), "0632BahaDinIbnShaddad.NawadirSultaniyya"),
    (("singing", "girls"), "0255Jahiz.Qiyan"),
    (("poem", "antarah"), "0001CantaraIbnShaddad.Mucallaqa"),
    (("stealing", "mare"), "0800Anonymous.SiratCantara"),
    (("hamadhani", "maqamat"), "0398BadicZamanHamadhani.Maqamat"),
    (("prendergast",), "0398BadicZamanHamadhani.Maqamat"),
    (("mufaddaliyat",), "0168MufaddalDabbi.Mufaddaliyyat"),
    (("mufaddaliyyat",), "0168MufaddalDabbi.Mufaddaliyyat"),
    (("baidawi",), "0685NasirDinBaydawi.AnwarTanzil"),
    (("baydawi",), "0685NasirDinBaydawi.AnwarTanzil"),
    (("chrestomathia",), "0685NasirDinBaydawi.AnwarTanzil"),
    (("confessions", "ghazzali"), "0505Ghazali.Munqidh"),
    (("confessions", "ghazali"), "0505Ghazali.Munqidh"),
    (("ihya", "nawab"), "0505Ghazali.IhyaCulumDin"),
    (("niche", "lights"), "0505Ghazali.MishkatAnwar"),
    (("gairdner", "mishkat"), "0505Ghazali.MishkatAnwar"),
    (("mishkat", "anwar"), "0505Ghazali.MishkatAnwar"),
    (("religious", "moral", "ghazzali"), "0505Ghazali.IhyaCulumDin"),
    (("meadows", "gold"), "0346Mascudi.MurujDhahab"),
    (("kindi", "metaphysics"), "0256IbnIshaqKindi.RasailFalsafiyya"),
    (("first", "philosophy", "kindi"), "0256IbnIshaqKindi.RasailFalsafiyya"),
    (("genequand",), "0595IbnRushdHafid.SharhMaBacdTabica"),
    (("ibn rushd", "metaphysics"), "0595IbnRushdHafid.SharhMaBacdTabica"),
    (("faith", "practice", "ghazali"), "0505Ghazali.Munqidh"),
    (("avicenna", "psychology"), "0428IbnSina.Najat"),
    (("najat",), "0428IbnSina.Najat"),
    (("harmony", "religion", "philosophy"), "0595IbnRushdHafid.FaslMaqal"),
    (("incoherence", "philosophers"), "0505Ghazali.Tahafut"),
    (("isharat",), "0428IbnSina.IsharatWaTanbihat"),
    (("fihrist",), "0385IbnNadim.Fihrist"),
    (("treatise", "love", "avicenna"), "0428IbnSina.MaHiyaCishq"),
    (("tarjuman",), "0638IbnCarabi.Diwan"),
    (("hikam", "ata"), "0709IbnCataAllahSikandari.HikamCataiyya"),
    (("wine", "farid"), "0632SharafDinIbnFarid.Diwan"),
    (("mysteries of worship",), "0505Ghazali.IhyaCulumDin"),
    (("book of knowledge", "ghazzali"), "0505Ghazali.IhyaCulumDin"),
    (("wonders of the heart",), "0505Ghazali.IhyaCulumDin"),
    (("secrets of pilgrimage",), "0505Ghazali.IhyaCulumDin"),
    (("muqaddimah",), "0808IbnKhaldun.Tarikh"),
    (("etiquette of marriage",), "0505Ghazali.IhyaCulumDin"),
    (("fazlul", "karim"), "0505Ghazali.IhyaCulumDin"),
    (("revival of religious learnings",), "0505Ghazali.IhyaCulumDin"),
    (("gayangos",), "1041Maqqari.NafhTib"),
    (("mohammedan", "dynasties", "spain"), "1041Maqqari.NafhTib"),
    (("nafh", "tib"), "1041Maqqari.NafhTib"),
    (("renaudot",), "0330AbuZaydSirafi.Rihla"),
    (("ancient accounts", "india", "china"), "0330AbuZaydSirafi.Rihla"),
    (("marvels", "india"), "0350BuzurgIbnShahriyarRamhurmuzi.CajaibHind"),
    (("buzurg",), "0350BuzurgIbnShahriyarRamhurmuzi.CajaibHind"),
)

_STOP = {
    "ibn",
    "bin",
    "bint",
    "abu",
    "abi",
    "al",
    "the",
    "of",
    "and",
    "a",
    "an",
    "or",
    "de",
    "la",
    "le",
    "book",
    "history",
    "volume",
    "vol",
    "part",
    "anonymous",
    "author",
    "translated",
    "translation",
    "trans",
    "diwan",
    "kitab",
    "sir",
    "selected",
}

_QURAN_SKIP = ("tafsir", "commentary", "commentar", "gharib", "ahkam")
_NIGHTS_SKIP = ("society", "studies", "essay", "essays")
# OpenITI death-year prefixes ≥ this are modern Arabic books (Locke, Shakespeare
# studies, etc.) and must not be join targets except via an explicit alias.
_MODERN_AH = 1350

ARCHIVE_SCRAPE = "https://archive.org/services/search/v1/scrape"
ARCHIVE_QUERIES = (
    'creator:"Oriental Translation Fund"',
    'publisher:"Oriental Translation Fund"',
    # Year window is the PD harvest, not a train filter.
    'collection:americana AND subject:arabic AND language:english AND date:[1800 TO 1929]',
    'creator:Margoliouth AND (arabic OR islam OR muhammad)',
    'creator:"de Slane" OR creator:Deslane OR creator:"McGuckin"',
    'creator:Ockley AND (hayy OR arabic)',
    'creator:Chenery AND hariri',
    'creator:Steingass AND hariri',
    'creator:Sachau AND (biruni OR arabic)',
    'creator:Jarrett AND (suyuti OR khulafa OR caliph)',
    'creator:Knatchbull AND kalila',
    'creator:Hitti AND (baladhuri OR usama OR origins)',
    'creator:Payne AND (nights OR arabic)',
)
EXTRA_ARCHIVE_QUERIES = (
    'creator:Tanukhi OR nishwar OR "table-talk of a mesopotamian"',
    'creator:Biruni OR Alberuni OR (Sachau AND (chronology OR vestiges))',
    'title:"Arab-Syrian Gentleman" OR title:"Kitab al-I\'tibar"',
)


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    stripped = stripped.lower().replace("ʿ", "").replace("ʾ", "").replace("'", " ")
    stripped = re.sub(r"[^a-z0-9]+", " ", stripped)
    return " ".join(stripped.split())


def tokens(text: str) -> set[str]:
    return {tok for tok in normalize(text).split() if len(tok) >= 3 and tok not in _STOP}


def camel_tokens(identifier: str) -> list[str]:
    return [p.lower() for p in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])", identifier)]


def uri_tokens(uri: str) -> set[str]:
    tail = uri.rsplit("/", 1)[-1]
    rest = re.sub(r"^\d+", "", tail)
    author, _, title = rest.partition(".")
    return tokens(" ".join(camel_tokens(author) + camel_tokens(title)))


def _blob(hit: dict[str, str]) -> str:
    return normalize(
        " ".join(
            [
                hit.get("title") or "",
                hit.get("authors") or "",
                hit.get("subjects") or "",
            ]
        )
    )


def _alias_uri(hit: dict[str, str], work_uris: set[str]) -> str | None:
    blob = f" {_blob(hit)} "
    title = f" {normalize(hit.get('title') or '')} "
    skip_quran = any(f" {marker} " in title for marker in _QURAN_SKIP)
    skip_nights = any(f" {marker} " in title for marker in _NIGHTS_SKIP)
    for needles, uri in ALIASES:
        if uri not in work_uris:
            continue
        if uri.endswith("Quran.Mushaf") and skip_quran:
            continue
        if uri.endswith("AlfLaylaWaLayla") and skip_nights:
            continue
        if all(f" {needle} " in blob for needle in needles):
            return uri
    return None


def _death_ah(uri: str) -> int | None:
    match = re.match(r"^(\d+)", uri.rsplit("/", 1)[-1])
    if not match:
        return None
    return int(match.group(1))


def _joinable_works(works: list[dict[str, str]]) -> list[dict[str, str]]:
    alias_uris = {uri for _needles, uri in ALIASES}
    joinable = []
    for work in works:
        death = _death_ah(work["uri"])
        if work["uri"] in alias_uris:
            joinable.append(work)
            continue
        if death is not None and death >= _MODERN_AH:
            continue
        joinable.append(work)
    return joinable


def _work_index(
    works: list[dict[str, str]],
) -> tuple[dict[str, dict[str, str]], dict[str, list[str]]]:
    by_uri = {work["uri"]: work for work in works}
    index: dict[str, list[str]] = defaultdict(list)
    for work in works:
        for tok in uri_tokens(work["uri"]) | tokens(work.get("author") or "") | tokens(
            work.get("title") or ""
        ):
            index[tok].append(work["uri"])
    return by_uri, index


def join_hit(
    hit: dict[str, str],
    works: list[dict[str, str]],
    *,
    by_uri: dict[str, dict[str, str]] | None = None,
    index: dict[str, list[str]] | None = None,
) -> dict[str, str] | None:
    """Return the best matching work, or None if the hit is not a translation of one."""
    if by_uri is None or index is None:
        joinable = _joinable_works(works)
        by_uri, index = _work_index(joinable)
        alias_pool = {work["uri"] for work in works}
    else:
        alias_pool = set(by_uri)
    alias = _alias_uri(hit, alias_pool)
    if alias and alias in by_uri:
        matched = dict(by_uri[alias])
        matched["join_reason"] = "alias"
        return matched
    if alias and alias not in by_uri:
        # Alias target was filtered out of the token index; still honour it
        # if it exists in the original works list.
        for work in works:
            if work["uri"] == alias:
                matched = dict(work)
                matched["join_reason"] = "alias"
                return matched

    hit_tokens = tokens(hit.get("title") or "") | tokens(hit.get("authors") or "")
    scores: dict[str, float] = defaultdict(float)
    rare_hits: dict[str, int] = defaultdict(int)
    for tok in hit_tokens:
        uris = index.get(tok) or []
        if not uris:
            continue
        weight = 1.0 / len(uris)
        for uri in uris:
            scores[uri] += weight
            if len(uris) <= 2:
                rare_hits[uri] += 1

    if not scores:
        return None
    best_uri, best_score = max(scores.items(), key=lambda item: item[1])
    if rare_hits[best_uri] < 1 or best_score < 0.5:
        return None
    matched = dict(by_uri[best_uri])
    matched["join_reason"] = "tokens"
    return matched


def join_hits(
    hits: list[dict[str, str]], works: list[dict[str, str]]
) -> tuple[list[tuple[dict[str, str], dict[str, str]]], list[dict[str, str]]]:
    joinable = _joinable_works(works)
    by_uri, index = _work_index(joinable)
    joined: list[tuple[dict[str, str], dict[str, str]]] = []
    unmatched: list[dict[str, str]] = []
    for hit in hits:
        match = join_hit(hit, works, by_uri=by_uri, index=index)
        if match is None:
            unmatched.append(hit)
        else:
            joined.append((hit, match))
    return joined, unmatched


def load_works(db_path: Path) -> list[dict[str, str]]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT uri, author, title FROM works").fetchall()
    finally:
        conn.close()
    return [{"uri": uri, "author": author or "", "title": title or ""} for uri, author, title in rows]


def load_catalog_hits(
    db_path: Path,
    hits: list[dict[str, str]],
    *,
    source: str,
    url_for: Callable[[dict[str, str]], str],
    works: list[dict[str, str]] | None = None,
    replace_source: bool = True,
) -> dict[str, int]:
    """Insert joined hits as unverified candidates. Does not insert unmatched rows."""
    translations.ensure_schema(db_path)
    if works is None:
        works = load_works(db_path)
    joined, unmatched = join_hits(hits, works)
    conn = sqlite3.connect(db_path)
    try:
        existing_ids: set[str] = set()
        if replace_source:
            conn.execute("DELETE FROM translations WHERE source = ?", (source,))
        else:
            existing_ids = {
                row[0]
                for row in conn.execute(
                    "SELECT source_id FROM translations WHERE source = ? AND source_id IS NOT NULL",
                    (source,),
                )
            }
        inserted = 0
        skipped = 0
        for hit, work in joined:
            source_id = hit.get("source_id") or ""
            if source_id and source_id in existing_ids:
                skipped += 1
                continue
            token_join = work.get("join_reason") == "tokens"
            translations._insert_translation(
                conn,
                translations._blank_row(
                    openiti_uri=work["uri"],
                    work_arabic_title=work.get("title"),
                    work_english_title=hit.get("title"),
                    author=work.get("author") or hit.get("authors"),
                    translator=hit.get("authors"),
                    publication_year=hit.get("year"),
                    source=source,
                    source_url=url_for(hit),
                    source_id=source_id,
                    digital_form="catalog",
                    usage_policy="quarantine" if token_join else "unknown",
                    visibility="none" if token_join else "private_eval",
                    rights_status="CATALOG_CANDIDATE_UNVERIFIED",
                    rights_evidence=(
                        "Catalog join only; not a title-page rights determination. "
                        f"join_reason={work.get('join_reason')}"
                    ),
                    confidence=work.get("join_reason"),
                    notes=hit.get("subjects"),
                ),
            )
            inserted += 1
        conn.commit()
    finally:
        conn.close()
    return {
        "joined": len(joined),
        "inserted": inserted,
        "skipped_existing": skipped,
        "unmatched": len(unmatched),
        "hits": len(hits),
    }


def quarantine_token_joins(db_path: Path) -> int:
    """Mark existing token-join rows so they do not count as real coverage."""
    translations.ensure_schema(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            """
            UPDATE translations
            SET usage_policy = 'quarantine', visibility = 'none'
            WHERE confidence = 'tokens'
            """
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def mark_pd_seed_duplicates(db_path: Path) -> int:
    """Flag catalog rows that share an OpenITI URI with the verified PD seed."""
    translations.ensure_schema(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            """
            UPDATE translations
            SET alignment_status = 'duplicate_pd_seed'
            WHERE source IN ('gutenberg', 'archive_org', 'hathitrust', 'wikisource', 'otf')
              AND openiti_uri IS NOT NULL
              AND openiti_uri IN (
                  SELECT openiti_uri FROM translations
                  WHERE source = 'pd_seed'
                    AND openiti_uri IS NOT NULL
                    AND openiti_uri != ''
              )
            """
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def parse_archive_scrape(payload: dict[str, Any]) -> tuple[list[dict[str, str]], str | None]:
    hits: list[dict[str, str]] = []
    for item in payload.get("items") or []:
        creator = item.get("creator") or ""
        if isinstance(creator, list):
            creator = "; ".join(str(part) for part in creator)
        title = item.get("title") or ""
        if isinstance(title, list):
            title = title[0] if title else ""
        hits.append(
            {
                "source_id": str(item.get("identifier") or ""),
                "title": str(title),
                "authors": str(creator),
                "subjects": "",
                "year": str(item.get("date") or item.get("year") or ""),
                "language": "en",
            }
        )
    cursor = payload.get("cursor")
    return hits, cursor if cursor else None


def fetch_archive_scrape(
    query: str,
    *,
    opener: Callable[[str], dict[str, Any]] | None = None,
    max_pages: int = 5,
) -> list[dict[str, str]]:
    """Page the IA scrape API. ``opener`` is injectable for tests."""

    def _default_open(url: str) -> dict[str, Any]:
        req = urllib.request.Request(url, headers={"User-Agent": "VersedTranslator/0.1"})
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))

    fetch = opener or _default_open
    hits: list[dict[str, str]] = []
    cursor: str | None = None
    fields = "identifier,title,creator,date,year"
    for _ in range(max_pages):
        params = {"q": query, "fields": fields, "count": 10000}
        if cursor:
            params["cursor"] = cursor
        url = ARCHIVE_SCRAPE + "?" + urllib.parse.urlencode(params)
        payload = fetch(url)
        page, cursor = parse_archive_scrape(payload)
        hits.extend(page)
        if not cursor:
            break
    return hits


def year_from_ia_metadata(payload: dict[str, Any]) -> tuple[str, str]:
    """Return (year, possible_copyright_status) from an IA metadata API payload."""
    meta = payload.get("metadata") or {}
    year = str(meta.get("year") or meta.get("date") or "")
    status = str(meta.get("possible-copyright-status") or "")
    return year, status


def enrich_archive_metadata(
    db_path: Path,
    *,
    opener: Callable[[str], dict[str, Any]] | None = None,
    limit: int = 120,
) -> int:
    """Fill year + IA copyright hint on alias archive.org rows. Not a rights stamp."""

    def _default_open(url: str) -> dict[str, Any]:
        req = urllib.request.Request(url, headers={"User-Agent": "VersedTranslator/0.1"})
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    fetch = opener or _default_open
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT id, source_id FROM translations
            WHERE source = 'archive_org' AND confidence = 'alias'
              AND source_id IS NOT NULL AND source_id != ''
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        updated = 0
        for row_id, identifier in rows:
            payload = fetch(f"https://archive.org/metadata/{identifier}")
            year, status = year_from_ia_metadata(payload)
            evidence = (
                "IA metadata (not a title-page determination). "
                f"possible-copyright-status={status or 'missing'}"
            )
            conn.execute(
                """
                UPDATE translations
                SET publication_year = COALESCE(NULLIF(publication_year, ''), ?),
                    rights_evidence = ?
                WHERE id = ?
                """,
                (year, evidence, row_id),
            )
            updated += 1
        conn.commit()
        return updated
    finally:
        conn.close()


def harvest_archive_org(
    db_path: Path,
    *,
    queries: tuple[str, ...] = ARCHIVE_QUERIES,
    opener: Callable[[str], dict[str, Any]] | None = None,
    replace_source: bool = True,
    source: str = "archive_org",
) -> dict[str, int]:
    seen: dict[str, dict[str, str]] = {}
    for query in queries:
        for hit in fetch_archive_scrape(query, opener=opener):
            key = hit.get("source_id") or ""
            if key and key not in seen:
                seen[key] = hit
    return load_catalog_hits(
        db_path,
        list(seen.values()),
        source=source,
        url_for=lambda h: f"https://archive.org/details/{h['source_id']}",
        replace_source=replace_source,
    )


def write_review_queue(db_path: Path, out_path: Path) -> dict[str, int]:
    """Write alias candidates that still need a title-page read."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT openiti_uri, work_english_title, translator, publication_year,
                   source, source_url, source_id, alignment_status
            FROM translations
            WHERE confidence = 'alias'
              AND usage_policy = 'unknown'
              AND IFNULL(alignment_status, 'none') != 'duplicate_pd_seed'
            ORDER BY openiti_uri, source
            """
        ).fetchall()
    finally:
        conn.close()
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        uri = row["openiti_uri"] or ""
        grouped.setdefault(uri, []).append(dict(row))
    payload = {
        "schema_note": "Alias joins awaiting title-page review. Not public.",
        "works": grouped,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"works": len(grouped), "editions": len(rows)}
