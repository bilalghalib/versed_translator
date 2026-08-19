"""Probe: can Fable r1a labels train a publishable detector?

This is not a production router. It answers three questions before we
label more rows:

1. Do the existing deterministic checks catch Fable's N rows? (Exp 0 preview)
2. Does a linear model on those checks beat "always N"?
3. Does a bag-of-words model on (arabic+english) beat (2) only by
   recognizing which *system* wrote the English? (style leak)

Splits never put the same passage in train and test. System identity is
not a feature. Leave-one-system-out is the leak test: if performance
collapses when the test system was unseen, we learned voice, not errors.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from versed_translator.qe.checks import run_checks


def prf(y_true: np.ndarray, y_pred: np.ndarray, positive: int = 1) -> dict[str, float]:
    tp = int(((y_true == positive) & (y_pred == positive)).sum())
    fp = int(((y_true != positive) & (y_pred == positive)).sum())
    fn = int(((y_true == positive) & (y_pred != positive)).sum())
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    acc = float((y_true == y_pred).mean()) if len(y_true) else 0.0
    return {
        "n": int(len(y_true)),
        "positive": int((y_true == positive).sum()),
        "accuracy": round(acc, 3),
        "precision": round(prec, 3),
        "recall": round(rec, 3),
        "f1": round(f1, 3),
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def check_features(arabic: str, english: str) -> dict[str, float]:
    report = run_checks(arabic, english)
    feats: dict[str, float] = {}
    n_fail = 0
    n_app = 0
    for finding in report.findings:
        if finding.check in {"entity_coverage", "terminology_violations"}:
            continue
        key = finding.check
        feats[f"{key}_failed"] = (
            1.0 if finding.applicable and not finding.passed else 0.0
        )
        feats[f"{key}_value"] = (
            float(finding.value) if finding.value is not None else 0.0
        )
        if finding.applicable:
            n_app += 1
            if not finding.passed:
                n_fail += 1
    feats["n_core_failed"] = float(n_fail)
    feats["empty_output"] = 1.0 if not (english or "").strip() else 0.0
    return feats


def matrix(rows: list[dict], keys: list[str] | None = None) -> tuple[np.ndarray, list[str]]:
    dicts = [check_features(r["arabic"], r["translation"]) for r in rows]
    if keys is None:
        keys = sorted(dicts[0].keys())
    x = np.array([[d[k] for k in keys] for d in dicts], dtype=float)
    return x, keys


def labels_blocking(rows: list[dict]) -> np.ndarray:
    """1 = has a publication-blocking flag (publishable N)."""
    return np.array(
        [0 if (r.get("publishable") or "").strip().upper() == "Y" else 1 for r in rows],
        dtype=int,
    )


def flag_label(rows: list[dict], flag: str) -> np.ndarray:
    return np.array(
        [
            1
            if flag in {
                p.strip()
                for p in (r.get("blocking_flags") or "").replace(",", "|").split("|")
            }
            else 0
            for r in rows
        ],
        dtype=int,
    )


def grouped_indices(rows: list[dict], key: str) -> dict[str, list[int]]:
    g: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        g[r[key]].append(i)
    return dict(g)


def _standardize(train: np.ndarray, test: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mu = train.mean(axis=0)
    sd = train.std(axis=0) + 1e-6
    return (train - mu) / sd, (test - mu) / sd


def fit_predict_logreg(x_train, y_train, x_test, steps: int = 400, lr: float = 0.4):
    """Numpy logistic regression. No sklearn — that import hung in this env."""
    if len(set(y_train.tolist())) < 2:
        return np.full(len(x_test), int(y_train[0]), dtype=int)
    xt, xv = _standardize(x_train.astype(float), x_test.astype(float))
    xt = np.hstack([xt, np.ones((len(xt), 1))])
    xv = np.hstack([xv, np.ones((len(xv), 1))])
    y = y_train.astype(float)
    n1 = y.sum()
    n0 = len(y) - n1
    sample_w = np.where(y == 1, len(y) / (2 * n1 + 1e-6), len(y) / (2 * n0 + 1e-6))
    w = np.zeros(xt.shape[1])
    for _ in range(steps):
        p = 1.0 / (1.0 + np.exp(-np.clip(xt @ w, -20, 20)))
        grad = xt.T @ ((p - y) * sample_w) / len(y)
        w -= lr * grad
    p_te = 1.0 / (1.0 + np.exp(-np.clip(xv @ w, -20, 20)))
    return (p_te >= 0.5).astype(int)


def leave_one_group_out(rows, x, y, group_key: str) -> dict:
    groups = grouped_indices(rows, group_key)
    y_true_all = []
    y_pred_all = []
    per = {}
    for g, idx in sorted(groups.items()):
        test = np.array(idx)
        train = np.array([i for i in range(len(rows)) if i not in set(idx)])
        pred = fit_predict_logreg(x[train], y[train], x[test])
        per[g] = prf(y[test], pred, positive=1)
        y_true_all.extend(y[test].tolist())
        y_pred_all.extend(pred.tolist())
    pooled = prf(np.array(y_true_all), np.array(y_pred_all), positive=1)
    return {"pooled": pooled, "per_group": per}


def style_features(english: str) -> np.ndarray:
    """Cheap English-side style vector — the leak we are trying to detect."""
    words = (english or "").split()
    n = max(len(words), 1)
    chars = len(english or "")
    allah = sum(1 for w in words if w.lower().strip(".,;:") in {"allah", "god"})
    avg_len = chars / n
    return np.array(
        [
            float(n),
            avg_len,
            float(allah) / n,
            float((english or "").count("'")),
            float(sum(1 for w in words if w[:1].isupper())) / n,
        ],
        dtype=float,
    )


def style_matrix(rows: list[dict]) -> np.ndarray:
    return np.stack([style_features(r.get("translation") or "") for r in rows])


def rule_any_check_failed(rows: list[dict]) -> np.ndarray:
    pred = []
    for r in rows:
        feats = check_features(r["arabic"], r["translation"])
        pred.append(1 if feats["n_core_failed"] > 0 or feats["empty_output"] else 0)
    return np.array(pred, dtype=int)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)

    rows = load_rows(args.csv)
    y = labels_blocking(rows)
    print("loaded", len(rows), "blocking", int(y.sum()), flush=True)
    x, keys = matrix(rows)
    print("features", keys, flush=True)

    always_n = np.ones(len(y), dtype=int)
    always_y = np.zeros(len(y), dtype=int)
    rule = rule_any_check_failed(rows)

    report: dict = {
        "n_rows": len(rows),
        "n_blocking": int(y.sum()),
        "n_publishable": int((y == 0).sum()),
        "by_system": {
            sid: {
                "n": sum(1 for r in rows if r["system_id"] == sid),
                "blocking": int(
                    sum(
                        1
                        for r, yi in zip(rows, y)
                        if r["system_id"] == sid and yi == 1
                    )
                ),
            }
            for sid in sorted({r["system_id"] for r in rows})
        },
        "feature_names": keys,
        "baselines": {
            "always_blocking": prf(y, always_n, 1),
            "always_publishable": prf(y, always_y, 1),
            "any_core_check_failed": prf(y, rule, 1),
        },
        "note": (
            "positive class = blocking (publishable N). "
            "Splits are grouped so a passage never appears in both train and test. "
            "System id is not a feature."
        ),
    }

    report["logreg_check_features"] = {
        "leave_one_source_out": leave_one_group_out(rows, x, y, "source"),
        "leave_one_system_out": leave_one_group_out(rows, x, y, "system_id"),
    }
    print("check-feature logreg done", flush=True)
    style = style_matrix(rows)
    report["english_style_features"] = {
        "leave_one_source_out": leave_one_group_out(rows, style, y, "source"),
        "leave_one_system_out": leave_one_group_out(rows, style, y, "system_id"),
    }
    print("style logreg done", flush=True)

    # Per-flag: can checks see NUMBER at least?
    report["per_flag_rule_recall"] = {}
    for flag in ("NUMBER", "ENTITY", "TERM", "ROLE", "OMISSION", "ADDITION"):
        yf = flag_label(rows, flag)
        if yf.sum() == 0:
            continue
        report["per_flag_rule_recall"][flag] = {
            "n_positive": int(yf.sum()),
            "rule_any_check": prf(yf, rule, 1),
        }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_json = args.out_dir / "probe_r1a.json"
    out_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    md = [
        "# r1a classifier probe",
        "",
        f"n={report['n_rows']} rows, {report['n_blocking']} blocking / "
        f"{report['n_publishable']} publishable. Positive class = blocking.",
        "",
        "## Baselines",
        "",
        f"- always blocking: {report['baselines']['always_blocking']}",
        f"- any existing core check failed: {report['baselines']['any_core_check_failed']}",
        "",
        "## Logistic on check features (no system id)",
        "",
        f"- leave-one-source-out: {report['logreg_check_features']['leave_one_source_out']['pooled']}",
        f"- leave-one-system-out: {report['logreg_check_features']['leave_one_system_out']['pooled']}",
        "",
        "## English style features only (word count, caps, Allah/God) — leak test",
        "",
        f"- leave-one-source-out: {report['english_style_features']['leave_one_source_out']['pooled']}",
        f"- leave-one-system-out: {report['english_style_features']['leave_one_system_out']['pooled']}",
        "",
        "If style features beat check features on source-out, the labels are "
        "entangled with which model wrote the English. That is still useful "
        "for a checker trained *within* a system, not for a router.",
        "",
        f"Per-system (check features): "
        f"{report['logreg_check_features']['leave_one_system_out']['per_group']}",
        "",
        f"Per-system (style): "
        f"{report['english_style_features']['leave_one_system_out']['per_group']}",
        "",
    ]
    (args.out_dir / "probe_r1a.md").write_text("\n".join(md), encoding="utf-8")
    print((args.out_dir / "probe_r1a.md").read_text(encoding="utf-8"))
    print(f"wrote {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
