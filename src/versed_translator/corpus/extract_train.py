"""Pull English verse out of train-only OCR dumps.

Ithra 2020 is bilingual; the OCR mixes Arabic commentary with numbered
English lines. This keeps the numbered English runs. Output is train-only
JSONL, never pd-english, never redistribute_ok.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from versed_translator.corpus.fetch_pd import DEFAULT_TRAIN_DEST

ITHRA_NAME = "ithra_muallaqat_for_millennials_2020_djvu.txt"
JOHNSON_NAME = "johnson_seven_poems_ams1973_djvu.txt"

VERSE_LINE = re.compile(r"^(\d+)\.\s+(.*\S)\s*$")
JOHNSON_HEADER = re.compile(
    r"THE\s+(FIRST|SECOND|THIRD|FOURTH|FIFTH|SIXTH|SEVENTH)\s+POEM",
    re.IGNORECASE,
)
ORDINALS = {
    "FIRST": 1,
    "SECOND": 2,
    "THIRD": 3,
    "FOURTH": 4,
    "FIFTH": 5,
    "SIXTH": 6,
    "SEVENTH": 7,
}

# First-line fingerprints for the five numbered English odes in the Ithra OCR.
ITHRA_OPENINGS = (
    ("imru_al_qays", "stop, my friends"),
    ("tarafah", "traces of khawlah"),
    ("labid", "effacedare the abodes"),
    ("asha", "the caravan is departing"),
    ("abid_ibn_al_abras", "malhüb is empty"),
)


def _fold(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract_ithra_odes(text: str) -> list[dict[str, Any]]:
    """Return numbered English odes from the Ithra millennials OCR."""
    odes: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    pending: list[str] = []

    def flush_pending() -> None:
        if current is None or not pending:
            return
        extra = _fold(" ".join(pending))
        pending.clear()
        if extra and current["verses"]:
            current["verses"][-1]["text"] = _fold(
                current["verses"][-1]["text"] + " " + extra
            )

    for raw in text.splitlines():
        line = raw.strip()
        match = VERSE_LINE.match(line)
        if match:
            flush_pending()
            number = int(match.group(1))
            body = match.group(2)
            if number == 1 or current is None:
                current = {"verses": []}
                odes.append(current)
            current["verses"].append({"n": number, "text": body})
            continue
        if current is not None and line and not line.startswith("©"):
            # Continuation of the previous English verse; stop if we hit
            # a long Arabic-majority line.
            letters = [c for c in line if c.isalpha()]
            latin = sum(c.isascii() for c in letters) if letters else 0
            if letters and latin / len(letters) < 0.6:
                continue
            if current["verses"]:
                pending.append(line)

    flush_pending()

    labelled: list[dict[str, Any]] = []
    for ode in odes:
        if not ode["verses"]:
            continue
        first = _fold(ode["verses"][0]["text"]).lower().replace(" ", "")
        poet = "unknown"
        for name, needle in ITHRA_OPENINGS:
            compact = needle.replace(" ", "")
            if compact in first.replace(" ", "") or needle in _fold(
                ode["verses"][0]["text"]
            ).lower():
                poet = name
                break
        labelled.append(
            {
                "source": "ithra_2020",
                "poet": poet,
                "n_verses": len(ode["verses"]),
                "verses": ode["verses"],
                "usage_policy": "train_ok",
            }
        )
    return labelled


def extract_johnson_quotes(text: str) -> list[dict[str, Any]]:
    """Best-effort English lines from Johnson's quoted translations.

    The OCR buries Arabic footnotes in the same stream. Keep quoted spans
    that are almost entirely Latin and look like verse, not apparatus.
    """
    poems: list[dict[str, Any]] = []
    seen: set[int] = set()
    parts = JOHNSON_HEADER.split(text)
    # preamble, ORDINAL, body, ORDINAL, body, ...
    i = 1
    while i + 1 < len(parts):
        ordinal = parts[i].upper()
        body = parts[i + 1]
        index = ORDINALS.get(ordinal)
        i += 2
        if index is None or index in seen:
            continue
        seen.add(index)
        lines: list[str] = []
        for raw in re.findall(r'"([^"]{40,900})"', body):
            folded = _fold(raw)
            letters = [c for c in folded if c.isalpha()]
            if not letters:
                continue
            latin = sum(c.isascii() for c in letters) / len(letters)
            if latin < 0.97:
                continue
            low = folded.lower()
            if any(
                bad in low
                for bad in (
                    "preface",
                    "bombay",
                    "the metre",
                    "aorist",
                    "obj. of",
                    "1st per",
                    "university of california",
                )
            ):
                continue
            if not re.match(r"^[A-Za-z]", folded):
                continue
            lines.append(folded)
        if lines:
            poems.append(
                {
                    "source": "johnson_1893",
                    "poem_index": index,
                    "n_lines": len(lines),
                    "lines": lines,
                    "usage_policy": "train_ok",
                }
            )
    return poems


def write_jsonl(rows: list[dict[str, Any]], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def extract_all(dest_dir: Path = DEFAULT_TRAIN_DEST) -> dict[str, Any]:
    report: dict[str, Any] = {"ithra_odes": 0, "johnson_poems": 0, "paths": []}
    ithra_path = dest_dir / ITHRA_NAME
    if ithra_path.exists():
        odes = extract_ithra_odes(
            ithra_path.read_text(encoding="utf-8", errors="replace")
        )
        out = write_jsonl(odes, dest_dir / "ithra_english_odes.jsonl")
        report["ithra_odes"] = len(odes)
        report["ithra_verses"] = sum(row["n_verses"] for row in odes)
        report["paths"].append(str(out))
    johnson_path = dest_dir / JOHNSON_NAME
    if johnson_path.exists():
        poems = extract_johnson_quotes(
            johnson_path.read_text(encoding="utf-8", errors="replace")
        )
        out = write_jsonl(poems, dest_dir / "johnson_english_quotes.jsonl")
        report["johnson_poems"] = len(poems)
        report["johnson_lines"] = sum(row["n_lines"] for row in poems)
        report["paths"].append(str(out))
    return report


def main() -> int:
    report = extract_all()
    print(
        f"ithra odes: {report.get('ithra_odes', 0)} "
        f"({report.get('ithra_verses', 0)} verses); "
        f"johnson poems: {report.get('johnson_poems', 0)} "
        f"({report.get('johnson_lines', 0)} quoted lines)"
    )
    for path in report.get("paths") or []:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
