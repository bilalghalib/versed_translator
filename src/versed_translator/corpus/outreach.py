"""Rights-holder outreach tracker.

Hosting a scan (muslimphilosophy, ghazali.org, Traditional Hikma, sacred-texts)
is not a sublicense. This table is who to ask for CC-BY/BY-SA so a train_ok
edition could move to redistribute_ok. It is not a legal opinion.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path
from typing import Any

from versed_translator.corpus import inventory
from versed_translator.corpus import translations

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTREACH = REPO_ROOT / "corpus" / "rights_outreach.json"
DEFAULT_CSV = REPO_ROOT / "corpus" / "rights_outreach.csv"

STATUSES = frozenset(
    {
        "not_started",
        "drafted",
        "sent",
        "followed_up",
        "waiting",
        "granted_cc_by",
        "granted_cc_by_sa",
        "granted_nc_only",
        "refused",
        "no_response",
        "n_a_already_pd",
    }
)
PRIORITIES = frozenset({"high", "medium", "low"})

CSV_COLUMNS = (
    "edition_key",
    "work_english_title",
    "translator",
    "publication_year",
    "ask_who",
    "ask_contact",
    "host_site",
    "host_permission_claim",
    "ask_for",
    "priority",
    "status",
    "first_contact_date",
    "last_followup_date",
    "next_followup_date",
    "followup_count",
    "response_summary",
    "grant_license",
    "usage_now",
    "source_url",
    "notes",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS rights_outreach (
    edition_key TEXT PRIMARY KEY,
    work_english_title TEXT,
    translator TEXT,
    publication_year TEXT,
    ask_who TEXT,
    ask_contact TEXT,
    host_site TEXT,
    host_permission_claim TEXT,
    ask_for TEXT,
    priority TEXT NOT NULL,
    status TEXT NOT NULL,
    first_contact_date TEXT,
    last_followup_date TEXT,
    next_followup_date TEXT,
    followup_count INTEGER NOT NULL DEFAULT 0,
    response_summary TEXT,
    grant_license TEXT,
    usage_now TEXT,
    source_url TEXT,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS rights_outreach_status ON rights_outreach(status);
CREATE INDEX IF NOT EXISTS rights_outreach_priority ON rights_outreach(priority);
"""


def ensure_schema(db_path: Path = translations.DEFAULT_DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(inventory.SCHEMA)
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def load_payload(path: Path = DEFAULT_OUTREACH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload.get("hosts"), list):
        raise ValueError(f"no hosts list in {path}")
    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"no entries in {path}")
    return payload


def validate_entry(entry: dict[str, Any]) -> None:
    key = entry.get("edition_key")
    if not key:
        raise ValueError("outreach row missing edition_key")
    status = entry.get("status")
    if status not in STATUSES:
        raise ValueError(f"{key}: bad status {status!r}")
    priority = entry.get("priority")
    if priority not in PRIORITIES:
        raise ValueError(f"{key}: bad priority {priority!r}")
    if entry.get("status") in {"granted_cc_by", "granted_cc_by_sa"} and not entry.get(
        "grant_license"
    ):
        raise ValueError(f"{key}: grant status needs grant_license")


def load_outreach(
    db_path: Path = translations.DEFAULT_DB_PATH,
    seed_path: Path = DEFAULT_OUTREACH,
) -> int:
    """Replace rights_outreach rows from the JSON seed. Does not stamp translations."""
    ensure_schema(db_path)
    payload = load_payload(seed_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DELETE FROM rights_outreach")
        for entry in payload["entries"]:
            validate_entry(entry)
            conn.execute(
                """
                INSERT INTO rights_outreach (
                    edition_key, work_english_title, translator, publication_year,
                    ask_who, ask_contact, host_site, host_permission_claim,
                    ask_for, priority, status, first_contact_date,
                    last_followup_date, next_followup_date, followup_count,
                    response_summary, grant_license, usage_now, source_url, notes
                ) VALUES (
                    :edition_key, :work_english_title, :translator, :publication_year,
                    :ask_who, :ask_contact, :host_site, :host_permission_claim,
                    :ask_for, :priority, :status, :first_contact_date,
                    :last_followup_date, :next_followup_date, :followup_count,
                    :response_summary, :grant_license, :usage_now, :source_url, :notes
                )
                """,
                {
                    "edition_key": entry["edition_key"],
                    "work_english_title": entry.get("work_english_title"),
                    "translator": entry.get("translator"),
                    "publication_year": None
                    if entry.get("publication_year") is None
                    else str(entry.get("publication_year")),
                    "ask_who": entry.get("ask_who"),
                    "ask_contact": entry.get("ask_contact"),
                    "host_site": entry.get("host_site"),
                    "host_permission_claim": entry.get("host_permission_claim"),
                    "ask_for": entry.get("ask_for"),
                    "priority": entry["priority"],
                    "status": entry["status"],
                    "first_contact_date": entry.get("first_contact_date"),
                    "last_followup_date": entry.get("last_followup_date"),
                    "next_followup_date": entry.get("next_followup_date"),
                    "followup_count": int(entry.get("followup_count") or 0),
                    "response_summary": entry.get("response_summary") or "",
                    "grant_license": entry.get("grant_license"),
                    "usage_now": entry.get("usage_now"),
                    "source_url": entry.get("source_url"),
                    "notes": entry.get("notes") or "",
                },
            )
        conn.commit()
    finally:
        conn.close()
    return len(payload["entries"])


def write_csv(
    dest: Path = DEFAULT_CSV,
    seed_path: Path = DEFAULT_OUTREACH,
) -> Path:
    """Write a spreadsheet-friendly copy. JSON remains the source of truth."""
    payload = load_payload(seed_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for entry in payload["entries"]:
            validate_entry(entry)
            row = {col: entry.get(col) if entry.get(col) is not None else "" for col in CSV_COLUMNS}
            row["followup_count"] = int(entry.get("followup_count") or 0)
            writer.writerow(row)
    return dest
