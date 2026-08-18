"""Two-sitting Fable consensus for the r1a hard-24.

Labels are silver model-consensus, never human gold. Disputed rows are
parked as challenge cases; they are not training or benchmark truth.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

MAJOR_FLAGS = {
    "ENTITY",
    "NUMBER",
    "ROLE",
    "TERM",
    "OMISSION",
    "ADDITION",
    "MISSING",
}

CONSENSUS_FIELDS = [
    "row_id",
    "item_id",
    "source",
    "system_id",
    "arabic",
    "translation",
    "first_publishable",
    "first_blocking_flags",
    "first_confidence",
    "second_publishable",
    "second_blocking_flags",
    "second_confidence",
    "agreement",
    "consensus_publishable",
    "consensus_blocking_flags",
    "consensus_label_status",
    "future_human_priority",
    "why_sampled",
    "disagreement_reason",
    "arabic_error_span",
    "english_error_span",
    "notes",
]

DAD_FIELDS = [
    "row_id",
    "source",
    "system_label",
    "arabic",
    "translation",
    "fable_first_publishable",
    "fable_second_publishable",
    "consensus_flags",
    "arabic_error_span",
    "english_error_span",
    "why_sampled",
    "future_human_priority",
    "dad_publishable",
    "dad_blocking_flags",
    "dad_notes",
]


def flag_set(raw: str) -> set[str]:
    parts = re.split(r"[|;,]", raw or "")
    out: set[str] = set()
    for part in parts:
        token = part.strip().upper()
        if token in MAJOR_FLAGS:
            out.add(token)
    return out


def pipe_flags(raw: str) -> str:
    flags = flag_set(raw)
    if not flags:
        return "OK"
    order = [f for f in ("ENTITY", "NUMBER", "ROLE", "TERM", "OMISSION", "ADDITION", "MISSING") if f in flags]
    return "|".join(order)


def _notes_blob(*chunks: str) -> str:
    return " ".join(c or "" for c in chunks).lower()


def classify_row(
    *,
    first_publishable: str,
    first_flags: str,
    first_confidence: str,
    second_publishable: str,
    second_flags: str,
    second_confidence: str,
    first_notes: str = "",
    second_notes: str = "",
) -> dict[str, str]:
    """Assign consensus status and dad-queue priority. Never emits human_gold."""
    p1 = (first_publishable or "").strip().upper()
    p2 = (second_publishable or "").strip().upper()
    c1 = (first_confidence or "").strip().lower()
    c2 = (second_confidence or "").strip().lower()
    f1, f2 = flag_set(first_flags), flag_set(second_flags)
    notes = _notes_blob(first_notes, second_notes)

    yn_flip = p1 != p2
    disjoint_classes = p1 == p2 == "N" and bool(f1) and bool(f2) and f1.isdisjoint(f2)
    corrupt = "corrupt in the source" in notes or "lemma is corrupt" in notes
    specialist = "specialist" in notes
    agreement = "Y" if (not yn_flip and p1 in {"Y", "N"}) else "N"

    if yn_flip or disjoint_classes or corrupt or specialist:
        if yn_flip:
            reason = f"Y/N flip {p1}→{p2}; not resolved"
        elif disjoint_classes:
            reason = (
                "blocking class "
                + "|".join(sorted(f1))
                + " vs "
                + "|".join(sorted(f2))
            )
        elif corrupt:
            reason = "source Arabic/lemma marked corrupt"
        else:
            reason = "Fable asked for a specialist"
        return {
            "agreement": agreement,
            "consensus_publishable": "",
            "consensus_blocking_flags": "",
            "consensus_label_status": "disputed",
            "future_human_priority": "P1",
            "disagreement_reason": reason,
        }

    ambiguity = any(
        w in notes
        for w in (
            "obscure",
            "defensible",
            "genuinely available",
            "defensible reading",
        )
    )
    flag_refine = f1 != f2
    both_high = c1 == "high" and c2 == "high"

    if both_high and not ambiguity and not flag_refine:
        status, priority = "silver_consensus_high", "P3"
        reason = ""
    else:
        status, priority = "silver_consensus_med", "P2"
        if not both_high:
            reason = f"confidence {c1}/{c2}"
        elif ambiguity:
            reason = "notes mark linguistic ambiguity or a defensible alternative"
        else:
            reason = (
                "flag refinement "
                + pipe_flags(first_flags)
                + " vs "
                + pipe_flags(second_flags)
            )

    return {
        "agreement": agreement,
        "consensus_publishable": p2,
        "consensus_blocking_flags": pipe_flags(second_flags),
        "consensus_label_status": status,
        "future_human_priority": priority,
        "disagreement_reason": reason,
    }


def _load(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return {row["row_id"]: row for row in csv.DictReader(fh)}


def build_consensus(
    *,
    graded: dict[str, dict[str, str]],
    sent: dict[str, dict[str, str]],
    regrade: dict[str, dict[str, str]],
    dad: dict[str, dict[str, str]],
) -> tuple[list[dict[str, str]], dict]:
    report = {
        "n": 0,
        "agree_yn": 0,
        "bytes_changed": False,
        "missing": [],
        "status": {},
        "priority": {},
    }
    rows: list[dict[str, str]] = []
    for row_id, sent_row in sent.items():
        first = graded.get(row_id)
        second = regrade.get(row_id)
        meta = dad.get(row_id) or {}
        if first is None or second is None:
            report["missing"].append(row_id)
            continue
        if sent_row["arabic"] != first["arabic"] or sent_row["translation"] != first["translation"]:
            report["bytes_changed"] = True
        if sent_row["arabic"] != second["arabic"] or sent_row["translation"] != second["translation"]:
            report["bytes_changed"] = True

        decision = classify_row(
            first_publishable=first.get("publishable") or "",
            first_flags=first.get("blocking_flags") or "",
            first_confidence=first.get("confidence") or "",
            second_publishable=second.get("publishable") or "",
            second_flags=second.get("blocking_flags") or "",
            second_confidence=second.get("confidence") or "",
            first_notes=first.get("notes") or "",
            second_notes=second.get("notes") or "",
        )
        span_ar = (second.get("arabic_error_span") or first.get("arabic_error_span") or "")
        span_en = (second.get("english_error_span") or first.get("english_error_span") or "")
        notes = second.get("notes") or first.get("notes") or ""
        row = {
            "row_id": row_id,
            "item_id": sent_row["item_id"],
            "source": sent_row["source"],
            "system_id": sent_row["system_id"],
            "arabic": sent_row["arabic"],
            "translation": sent_row["translation"],
            "first_publishable": (first.get("publishable") or "").strip().upper(),
            "first_blocking_flags": first.get("blocking_flags") or "",
            "first_confidence": first.get("confidence") or "",
            "second_publishable": (second.get("publishable") or "").strip().upper(),
            "second_blocking_flags": second.get("blocking_flags") or "",
            "second_confidence": second.get("confidence") or "",
            "why_sampled": meta.get("why_sampled") or "",
            "arabic_error_span": span_ar,
            "english_error_span": span_en,
            "notes": notes,
            **decision,
        }
        rows.append(row)
        report["n"] += 1
        if decision["agreement"] == "Y":
            report["agree_yn"] += 1
        report["status"][decision["consensus_label_status"]] = (
            report["status"].get(decision["consensus_label_status"], 0) + 1
        )
        report["priority"][decision["future_human_priority"]] = (
            report["priority"].get(decision["future_human_priority"], 0) + 1
        )

    rank = {"P1": 0, "P2": 1, "P3": 2}
    rows.sort(key=lambda r: (rank.get(r["future_human_priority"], 9), r["row_id"]))
    return rows, report


def dad_rows(
    consensus: list[dict[str, str]],
    sent: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    out = []
    for row in consensus:
        sent_row = sent[row["row_id"]]
        out.append(
            {
                "row_id": row["row_id"],
                "source": row["source"],
                "system_label": sent_row.get("system_label") or "",
                "arabic": row["arabic"],
                "translation": row["translation"],
                "fable_first_publishable": row["first_publishable"],
                "fable_second_publishable": row["second_publishable"],
                "consensus_flags": row["consensus_blocking_flags"],
                "arabic_error_span": row["arabic_error_span"],
                "english_error_span": row["english_error_span"],
                "why_sampled": row["why_sampled"],
                "future_human_priority": row["future_human_priority"],
                "dad_publishable": "",
                "dad_blocking_flags": "",
                "dad_notes": "",
            }
        )
    return out


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    from versed_translator.paths import FABLE_R1_DIR

    graded = _load(FABLE_R1_DIR / "fable_r1a_graded.csv")
    sent = _load(FABLE_R1_DIR / "hard24_for_fable.csv")
    regrade = _load(FABLE_R1_DIR / "hard24_fable_regrade.csv")
    dad_in = _load(FABLE_R1_DIR / "hard24_for_dad.csv")
    consensus, report = build_consensus(
        graded=graded, sent=sent, regrade=regrade, dad=dad_in
    )
    write_csv(FABLE_R1_DIR / "hard24_consensus.csv", CONSENSUS_FIELDS, consensus)
    write_csv(FABLE_R1_DIR / "hard24_for_dad.csv", DAD_FIELDS, dad_rows(consensus, sent))

    # Round-trip byte check on arabic/translation strings.
    back = _load(FABLE_R1_DIR / "hard24_consensus.csv")
    changed = [
        rid
        for rid, row in sent.items()
        if back[rid]["arabic"] != row["arabic"]
        or back[rid]["translation"] != row["translation"]
    ]
    report["roundtrip_changed_ids"] = changed
    print(
        {
            "n": report["n"],
            "agree_yn": report["agree_yn"],
            "disagree_yn": report["n"] - report["agree_yn"],
            "status": report["status"],
            "priority": report["priority"],
            "source_bytes_changed": report["bytes_changed"],
            "roundtrip_changed": changed,
            "missing": report["missing"],
            "consensus": str(FABLE_R1_DIR / "hard24_consensus.csv"),
            "dad": str(FABLE_R1_DIR / "hard24_for_dad.csv"),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
