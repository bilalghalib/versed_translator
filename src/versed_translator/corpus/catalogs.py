"""Catalog ingestors: HathiTrust Hathifiles, Wikisource, Oriental Translation Fund.

These emit the same hit shape as Gutenberg/IA joins. A join is not a rights
stamp. Token matches stay quarantined; aliases stay unknown until a title page.
"""

from __future__ import annotations

import gzip
import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Iterable, TextIO

from versed_translator.corpus import join as join_mod
from versed_translator.corpus import translations
from versed_translator.corpus.inventory import REPO_ROOT

USER_AGENT = "VersedTranslator/0.1 (https://github.com/bilalghalib/versed_translator)"
HATHI_FILE_LIST = "https://www.hathitrust.org/files/hathifiles/hathi_file_list.json"
HATHI_PD_RIGHTS = {"pd", "pdus"}
WIKISOURCE_API = "https://en.wikisource.org/w/api.php"
WIKISOURCE_CATEGORY = "Category:Works originally in Arabic"
OTF_QUERIES = (
    'creator:"Oriental Translation Fund"',
    'publisher:"Oriental Translation Fund"',
)

HATHI_FIELDS = (
    "htid",
    "access",
    "rights",
    "ht_bib_key",
    "description",
    "source",
    "source_bib_num",
    "oclc_num",
    "isbn",
    "issn",
    "lccn",
    "title",
    "imprint",
    "rights_reason_code",
    "rights_timestamp",
    "us_gov_doc_flag",
    "rights_date_used",
    "pub_place",
    "lang",
    "bib_fmt",
    "collection_code",
    "content_provider_code",
    "responsible_entity_code",
    "digitization_agent_code",
    "access_profile_code",
    "author",
)

DEFAULT_HATHI_DIR = REPO_ROOT / "corpus" / "cache" / "hathi"
DEFAULT_WIKISOURCE_CACHE = REPO_ROOT / "corpus" / "cache" / "wikisource" / "hits.json"

_EXTRA_KEYWORDS = (
    "kalbi",
    "tanukhi",
    "biruni",
    "alberuni",
    "khallikan",
    "battuta",
    "jahiz",
    "shafii",
    "zahrawi",
    "albucasis",
    "haytham",
    "munqidh",
    "tabari",
    "khaldun",
    "muqaddimah",
    "baghdadi",
    "seelye",
    "sachau",
    "margoliouth",
    "oriental translation",
    "avicenna",
    "canon of medicine",
    "moslem schisms",
    "book of idols",
    "ring of the dove",
    "miskawayh",
    "hariri",
    "tufayl",
)


def catalog_keywords() -> tuple[str, ...]:
    seen: list[str] = []
    for keyword in translations.GUTENBERG_KEYWORDS + _EXTRA_KEYWORDS:
        if keyword not in seen:
            seen.append(keyword)
    return tuple(seen)


def _open_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_hathi_line(line: str) -> dict[str, str] | None:
    parts = line.rstrip("\n").split("\t")
    if len(parts) < 12:
        return None
    row = {field: parts[i] if i < len(parts) else "" for i, field in enumerate(HATHI_FIELDS)}
    return row


def hathi_row_is_candidate(row: dict[str, str], keywords: tuple[str, ...] | None = None) -> bool:
    """English + Hathi PD/PDUS + keyword. Not a title-page determination."""
    rights = (row.get("rights") or "").lower()
    if rights not in HATHI_PD_RIGHTS:
        return False
    lang = (row.get("lang") or "").lower()
    if lang and "eng" not in lang.split(","):
        return False
    blob = " ".join(
        [
            row.get("title") or "",
            row.get("author") or "",
            row.get("imprint") or "",
        ]
    ).lower()
    needles = keywords or catalog_keywords()
    return any(keyword in blob for keyword in needles)


def hathi_row_to_hit(row: dict[str, str]) -> dict[str, str]:
    return {
        "source_id": row.get("htid") or "",
        "title": row.get("title") or "",
        "authors": row.get("author") or "",
        "subjects": row.get("imprint") or "",
        "year": row.get("rights_date_used") or "",
        "language": row.get("lang") or "",
        "rights": row.get("rights") or "",
    }


def _text_handle(path: Path) -> TextIO:
    if path.suffix == ".gz" or path.name.endswith(".txt.gz"):
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return path.open("r", encoding="utf-8", errors="replace")


def iter_hathi_hits(path: Path, keywords: tuple[str, ...] | None = None) -> Iterable[dict[str, str]]:
    with _text_handle(path) as handle:
        for line in handle:
            if not line.strip() or line.startswith("htid"):
                continue
            row = parse_hathi_line(line)
            if row is None:
                continue
            if hathi_row_is_candidate(row, keywords=keywords):
                yield hathi_row_to_hit(row)


def latest_hathi_full(file_list: list[dict[str, Any]]) -> dict[str, Any]:
    full = [item for item in file_list if item.get("full")]
    if not full:
        raise ValueError("no hathi_full entry in file list")
    return max(full, key=lambda item: str(item.get("created") or item.get("filename") or ""))


def parse_wikisource_category(payload: dict[str, Any]) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    for member in (payload.get("query") or {}).get("categorymembers") or []:
        ns = member.get("ns")
        title = str(member.get("title") or "")
        if ns != 0 or not title:
            continue
        hits.append(
            {
                "source_id": title,
                "title": title,
                "authors": "",
                "subjects": "Works originally in Arabic",
                "year": "",
                "language": "en",
            }
        )
    return hits


def fetch_wikisource_category(
    *,
    opener: Callable[[str], dict[str, Any]] | None = None,
    category: str = WIKISOURCE_CATEGORY,
) -> list[dict[str, str]]:
    fetch = opener or _open_json
    hits: list[dict[str, str]] = []
    continue_token: str | None = None
    for _ in range(20):
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": category,
            "cmlimit": "500",
            "format": "json",
        }
        if continue_token:
            params["cmcontinue"] = continue_token
        url = WIKISOURCE_API + "?" + urllib.parse.urlencode(params)
        payload = fetch(url)
        hits.extend(parse_wikisource_category(payload))
        continue_token = ((payload.get("continue") or {}).get("cmcontinue")) or None
        if not continue_token:
            break
    return hits


def harvest_wikisource(
    db_path: Path,
    *,
    opener: Callable[[str], dict[str, Any]] | None = None,
    hits: list[dict[str, str]] | None = None,
    replace_source: bool = True,
) -> dict[str, int]:
    catalog = hits if hits is not None else fetch_wikisource_category(opener=opener)
    return join_mod.load_catalog_hits(
        db_path,
        catalog,
        source="wikisource",
        url_for=lambda h: "https://en.wikisource.org/wiki/"
        + urllib.parse.quote(h["source_id"].replace(" ", "_")),
        replace_source=replace_source,
    )


def harvest_otf(
    db_path: Path,
    *,
    opener: Callable[[str], dict[str, Any]] | None = None,
    replace_source: bool = True,
) -> dict[str, int]:
    return join_mod.harvest_archive_org(
        db_path,
        queries=OTF_QUERIES,
        opener=opener,
        replace_source=replace_source,
        source="otf",
    )


def harvest_hathi(
    db_path: Path,
    tsv_path: Path,
    *,
    replace_source: bool = True,
) -> dict[str, int]:
    hits = list(iter_hathi_hits(tsv_path))
    return join_mod.load_catalog_hits(
        db_path,
        hits,
        source="hathitrust",
        url_for=lambda h: f"https://hdl.handle.net/2027/{h['source_id']}",
        replace_source=replace_source,
    )


def download_hathi_full(
    dest: Path,
    *,
    opener: Callable[[str], Any] | None = None,
    file_list: list[dict[str, Any]] | None = None,
) -> Path:
    """Download the latest monthly Hathifile to dest. ~1.2 GB gzipped."""
    listing = file_list if file_list is not None else (opener or _open_json)(HATHI_FILE_LIST)
    latest = latest_hathi_full(listing)
    url = str(latest["url"])
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as response, tmp.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
    tmp.replace(dest)
    return dest
