"""Per-work glossary candidates. Status is candidate until a human verifies.

Do not inject the whole table into every request. Retrieve only entries
whose Arabic surface form appears in the passage. `الحلقة` is mail-armor
in one Baladhuri sitting and must not become a global gloss.
"""

from __future__ import annotations

import csv
import re
from dataclasses import asdict, dataclass
from pathlib import Path


def _split_pipe(value: str) -> list[str]:
    if not value or not value.strip():
        return []
    return [p.strip() for p in re.split(r"\s*\|\s*", value) if p.strip()]


def _kind_from_row(kind: str, arabic: str, en_should: str) -> str:
    blob = f"{kind} {arabic} {en_should}".lower()
    if kind == "entity":
        if any(w in blob for w in ("toponym", "place", "fortress", "town", "city", "district")):
            return "place"
        if any(w in blob for w in ("tribe", "people", "group", "regiment")):
            return "group"
        return "person"
    return "term"


@dataclass(frozen=True)
class GlossaryEntry:
    arabic: str
    lemma: str
    en_should: str
    en_wrong: str
    kind: str  # term | person | place | group
    book: str
    item_ids: str
    status: str  # candidate | verified | rejected
    source_label: str
    reviewer: str = ""
    train_eligible: str = "false"

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def normalize_mined_rows(rows: list[dict[str, str]]) -> list[GlossaryEntry]:
    out: list[GlossaryEntry] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        ars = _split_pipe(row.get("arabic") or "")
        shoulds = _split_pipe(row.get("en_should") or "")
        wrongs = _split_pipe(row.get("en_wrong_examples") or row.get("en_wrong") or "")
        n = max(len(ars), len(shoulds), 1)
        raw_kind = (row.get("kind") or "term").strip()
        book = (row.get("sources") or row.get("book") or "").split(",")[0].strip()
        for i in range(n):
            ar = ars[i] if i < len(ars) else (ars[-1] if ars else "")
            should = shoulds[i] if i < len(shoulds) else (shoulds[-1] if shoulds else "")
            wrong = wrongs[i] if i < len(wrongs) else ""
            ar = re.sub(r"\s+", " ", ar).strip()
            if len(ar) < 2 or not should:
                continue
            key = (ar, should, book)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                GlossaryEntry(
                    arabic=ar,
                    lemma=(row.get("lemma") or "").strip(),
                    en_should=should,
                    en_wrong=wrong,
                    kind=_kind_from_row(raw_kind, ar, should),
                    book=book,
                    item_ids=row.get("item_ids") or "",
                    status=(row.get("status") or "candidate").strip() or "candidate",
                    source_label=(row.get("source_label") or "fable_r1a").strip(),
                    reviewer=(row.get("reviewer") or "").strip(),
                    train_eligible=(row.get("train_eligible") or "false").strip()
                    or "false",
                )
            )
    return out


def load_glossary(path: Path) -> list[GlossaryEntry]:
    """Load mined (pipe-joined) or already-normalized candidate CSVs."""
    with path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        return []
    sample = rows[0]
    if sample.get("status") and "en_wrong_examples" not in sample:
        return [
            GlossaryEntry(
                arabic=(r.get("arabic") or "").strip(),
                lemma=(r.get("lemma") or "").strip(),
                en_should=(r.get("en_should") or "").strip(),
                en_wrong=(r.get("en_wrong") or "").strip(),
                kind=(r.get("kind") or "term").strip() or "term",
                book=(r.get("book") or "").strip(),
                item_ids=(r.get("item_ids") or "").strip(),
                status=(r.get("status") or "candidate").strip() or "candidate",
                source_label=(r.get("source_label") or "").strip(),
                reviewer=(r.get("reviewer") or "").strip(),
                train_eligible=(r.get("train_eligible") or "false").strip() or "false",
            )
            for r in rows
            if (r.get("arabic") or "").strip()
        ]
    return normalize_mined_rows(rows)


def load_mined_csv(path: Path) -> list[GlossaryEntry]:
    return load_glossary(path)


def write_candidates_csv(path: Path, entries: list[GlossaryEntry]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(GlossaryEntry.__dataclass_fields__.keys())
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for entry in entries:
            writer.writerow(entry.as_dict())


def retrieve_for_passage(
    entries: list[GlossaryEntry],
    arabic: str,
    book: str | None = None,
) -> list[GlossaryEntry]:
    """Entries whose Arabic surface form occurs in this passage.

    Two-character tokens require a word-ish boundary so `جى` does not
    match inside longer words.
    """
    hits: list[GlossaryEntry] = []
    for entry in entries:
        if entry.status == "rejected":
            continue
        if book and entry.book and entry.book != book:
            continue
        token = entry.arabic
        if len(token) <= 2:
            if not re.search(rf"(?<![\u0600-\u06FF]){re.escape(token)}(?![\u0600-\u06FF])", arabic):
                continue
        elif token not in arabic:
            continue
        hits.append(entry)
    return hits


def _wrong_keys(wrong: str) -> list[str]:
    """Distinctive English spans that signal a bad glossary rendering."""
    keys: list[str] = []
    for part in re.split(r"\s*\|\s*", (wrong or "").lower()):
        part = re.sub(r"^\([^)]*\)\s*", "", part).strip()
        if not part:
            continue
        before = re.split(r"\s*[\(,;]", part, maxsplit=1)[0].strip()
        for cand in (before, part.strip("() ")):
            cand = cand.strip()
            if len(cand) >= 4 and cand not in keys:
                keys.append(cand)
    return keys


def glossary_contradictions(english: str, hits: list[GlossaryEntry]) -> list[GlossaryEntry]:
    """Wrong rendering present and preferred rendering absent — checker signal."""
    lowered = (english or "").lower()
    bad: list[GlossaryEntry] = []
    for entry in hits:
        should_key = (entry.en_should or "").lower().split("(")[0].strip()[:8]
        hit = False
        for key in _wrong_keys(entry.en_wrong):
            if key in lowered and (not should_key or should_key not in lowered):
                hit = True
                break
        if hit:
            bad.append(entry)
    return bad
    """Wrong rendering present and preferred rendering absent — checker signal."""
    lowered = (english or "").lower()
    bad: list[GlossaryEntry] = []
    for entry in hits:
        wrong = (entry.en_wrong or "").lower().strip()
        should = (entry.en_should or "").lower().strip()
        if not wrong or len(wrong) < 4:
            continue
        # Take a short distinctive wrong span (before | or parenthesis).
        wrong_key = re.split(r"[|;,(]", wrong)[0].strip()
        if len(wrong_key) < 4:
            continue
        if wrong_key in lowered and should.split("(")[0].strip()[:8] not in lowered:
            bad.append(entry)
    return bad
