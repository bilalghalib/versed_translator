"""Export long-format CSVs for human flag grading (Claude Fable).

One row = one (passage, system) translation. Arabic is the source of truth.
Do not grade against the public-domain English; that column is omitted on
purpose so the reviewer does not chrF-match 19th-century abridgments.
"""

from __future__ import annotations

import csv
import json
import random
from collections import defaultdict
from pathlib import Path

from versed_translator.benchmark.compare_page import SAMPLE_14

REGISTER_BY_SOURCE = {
    "blunt_odes": "verse",
    "hariri_assemblies": "saj_maqama",
    "ockley_hayy": "philosophy",
    "ibn_khallikan_deslane": "biography",
    "baladhuri_hitti": "history",
    "miskawayh_eclipse": "history",
}

# Failure-curriculum systems (not the production panel). Qwen stays here
# because it is error-rich; it is out of the factory mix.
DEFAULT_SYSTEMS = (
    ("tg27b", "TranslateGemma 27B official"),
    ("flash_lite", "Gemini Flash-Lite"),
    ("flash", "Gemini Flash"),
    ("qwen", "Qwen-MT turbo"),
)

# ~corpus-shaped prose plus deliberate verse/maqama oversample. Totals 50.
STRATA_N = {
    "baladhuri_hitti": 18,
    "ibn_khallikan_deslane": 10,
    "hariri_assemblies": 8,
    "blunt_odes": 6,
    "miskawayh_eclipse": 4,
    "ockley_hayy": 4,
}

FABLE_COLUMNS = [
    "row_id",
    "batch_id",
    "item_id",
    "source",
    "genre",
    "band",
    "register_hint",
    "system_id",
    "system_label",
    "arabic",
    "translation",
    "error",
    "arabic_word_count",
    "translation_word_count",
    "length_ratio",
    "publishable",
    "blocking_flags",
    "cosmetic_flags",
    "arabic_error_span",
    "english_error_span",
    "term_ar",
    "term_en_wrong",
    "term_en_should",
    "entity_ar",
    "entity_en_wrong",
    "entity_en_should",
    "role_speaker_ar",
    "role_assigned_wrong",
    "notes",
    "confidence",
]


def load_jsonl(path: Path) -> dict[str, dict]:
    by_id: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        key = row.get("id") or row.get("item_id")
        by_id[key] = row
    return by_id


def word_count(text: str) -> int:
    return len((text or "").split())


def stratified_sample(
    items: list[dict],
    *,
    exclude_ids: set[str],
    strata_n: dict[str, int] = STRATA_N,
    seed: int = 20260816,
) -> list[str]:
    """Return item ids, stable under the seed. Raises if a stratum is short."""
    pool: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        if item["id"] in exclude_ids:
            continue
        pool[item["source"]].append(item)
    rng = random.Random(seed)
    chosen: list[str] = []
    for source, n in strata_n.items():
        available = pool.get(source, [])
        if len(available) < n:
            raise ValueError(
                f"stratum {source} has {len(available)} after excludes, need {n}"
            )
        available = sorted(available, key=lambda r: r["id"])
        rng.shuffle(available)
        chosen.extend(row["id"] for row in available[:n])
    return chosen


def length_ratio(arabic: str, english: str) -> str:
    a, e = word_count(arabic), word_count(english)
    if a == 0:
        return ""
    return f"{e / a:.3f}"


def build_rows(
    *,
    items: dict[str, dict],
    systems: dict[str, dict[str, dict]],
    item_ids: list[str],
    system_order: tuple[tuple[str, str], ...] = DEFAULT_SYSTEMS,
    batch_id: str,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    n = 0
    for item_id in item_ids:
        item = items[item_id]
        arabic = item.get("arabic") or ""
        for system_id, system_label in system_order:
            hit = systems[system_id].get(item_id, {})
            translation = hit.get("translation") or hit.get("english") or ""
            err = hit.get("error") or ""
            n += 1
            rows.append(
                {
                    "row_id": f"{batch_id}-{n:04d}",
                    "batch_id": batch_id,
                    "item_id": item_id,
                    "source": item.get("source") or "",
                    "genre": item.get("genre") or "",
                    "band": item.get("band") or "",
                    "register_hint": REGISTER_BY_SOURCE.get(
                        item.get("source") or "", "prose"
                    ),
                    "system_id": system_id,
                    "system_label": system_label,
                    "arabic": arabic,
                    "translation": translation,
                    "error": err,
                    "arabic_word_count": str(word_count(arabic)),
                    "translation_word_count": str(word_count(translation)),
                    "length_ratio": length_ratio(arabic, translation),
                    "publishable": "",
                    "blocking_flags": "",
                    "cosmetic_flags": "",
                    "arabic_error_span": "",
                    "english_error_span": "",
                    "term_ar": "",
                    "term_en_wrong": "",
                    "term_en_should": "",
                    "entity_ar": "",
                    "entity_en_wrong": "",
                    "entity_en_should": "",
                    "role_speaker_ar": "",
                    "role_assigned_wrong": "",
                    "notes": "",
                    "confidence": "",
                }
            )
    return rows


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FABLE_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def split_batches(rows: list[dict[str, str]], chunk_rows: int) -> list[list[dict[str, str]]]:
    return [rows[i : i + chunk_rows] for i in range(0, len(rows), chunk_rows)]


def default_system_paths(runs_dir: Path) -> dict[str, Path]:
    return {
        "tg27b": runs_dir / "20260816T044600Z-modal-translategemma_27b-reassembled" / "results.jsonl",
        "flash_lite": runs_dir / "20260816T100202Z-openai_compat-gemini-flash-lite-latest-feccfd39-reassembled" / "results.jsonl",
        "flash": runs_dir / "20260816T101414Z-openai_compat-gemini-flash-latest-d9e1b3e6-reassembled" / "results.jsonl",
        "qwen": runs_dir / "20260816T094828Z-openai_compat-qwen-mt-turbo-e8b198f4-reassembled" / "results.jsonl",
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="versed_translator.benchmark.fable_export")
    parser.add_argument("--items", type=Path, required=True)
    parser.add_argument("--runs-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260816)
    parser.add_argument("--chunk-rows", type=int, default=100)
    args = parser.parse_args(argv)

    items = load_jsonl(args.items)
    item_list = list(items.values())
    item_ids = stratified_sample(
        item_list, exclude_ids=set(SAMPLE_14), seed=args.seed
    )
    systems = {
        sid: load_jsonl(path) for sid, path in default_system_paths(args.runs_dir).items()
    }
    rows = build_rows(items=items, systems=systems, item_ids=item_ids, batch_id="fable_r1")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    chunks = split_batches(rows, args.chunk_rows)
    written = []
    for i, chunk in enumerate(chunks, start=1):
        suffix = chr(ord("a") + i - 1)
        path = args.out_dir / f"fable_r1{suffix}.csv"
        write_csv(path, chunk)
        written.append(str(path))
    manifest = {
        "batch_id": "fable_r1",
        "seed": args.seed,
        "n_passages": len(item_ids),
        "n_rows": len(rows),
        "systems": [sid for sid, _ in DEFAULT_SYSTEMS],
        "item_ids": item_ids,
        "chunks": written,
        "excluded_sample14": list(SAMPLE_14),
        "note": "Flags-only grading. Arabic is truth. PD English omitted on purpose.",
    }
    (args.out_dir / "fable_r1_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(rows)} rows in {len(chunks)} chunks to {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

