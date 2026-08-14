"""Scoring for a finished harness run.

Produces a per-run report dict and a markdown summary. Per the repo's
rights-hygiene rule, nothing here ever writes item text (Arabic source or
English translation/reference) into the report -- only counts, rates, and
aggregate scores. Callers that want to inspect actual text do so by reading
results.jsonl directly under /Volumes/Nodes/versed-translator/runs/.
"""

from __future__ import annotations

import re
import statistics

import sacrebleu

from versed_translator.harness.structured import ID_CONTRACT_ERRORS, id_error_counts

# Arabic script + Arabic presentation forms + Arabic supplement blocks.
_ARABIC_RE = re.compile(
    r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]"
)


def has_untranslated_arabic(text: str | None) -> bool:
    """True if `text` contains any Arabic-script codepoint at all.

    A crude but useful smell test: a genuine English translation should
    contain none, so any Arabic surfacing in the output is worth flagging
    (untranslated fragment, verbatim quotation left in, or hallucinated
    Arabic in the response).
    """
    if not text:
        return False
    return bool(_ARABIC_RE.search(text))


def length_ratio(source_text: str | None, output_text: str | None) -> float | None:
    """Output-word-count / source-word-count. None if source is empty."""
    if not source_text or not output_text:
        return None
    src_words = len(source_text.split())
    if src_words == 0:
        return None
    out_words = len(output_text.split())
    return out_words / src_words


def flag_length_ratio(ratio: float | None, low: float = 0.4, high: float = 3.0) -> bool:
    """True if the ratio falls outside a sane band (too compressed / too expanded)."""
    if ratio is None:
        return False
    return ratio < low or ratio > high


def chrf_score(hypotheses: list[str], references: list[str]) -> float | None:
    """Corpus-level chrF via sacrebleu. None if no reference-bearing pairs exist."""
    pairs = [(h, r) for h, r in zip(hypotheses, references) if h and r]
    if not pairs:
        return None
    hyps, refs = zip(*pairs)
    result = sacrebleu.corpus_chrf(list(hyps), [list(refs)])
    return result.score


def id_preservation_report(rows: list[dict]) -> dict:
    """id-preservation rate for structured-template rows.

    A row counts as an id-preservation violation when its error is one of
    ``structured.ID_CONTRACT_ERRORS``: the id was dropped from the response,
    duplicated in it, or invented by it. All three mean the same thing for
    safety purposes -- the model did not honour the id contract, so the block
    it was supposed to translate is unaccounted for.

    Non-structured rows (error is anything else, or None) don't count against
    the denominator unless they came from a structured run -- callers should
    pass only the rows belonging to a structured-template run.
    """
    total = len(rows)
    violations = sum(1 for r in rows if r.get("error") in ID_CONTRACT_ERRORS)
    rate = (total - violations) / total if total else None
    report = {"total": total, "id_violations": violations, "id_preservation_rate": rate}
    report.update(id_error_counts(rows))
    return report


def score_run(rows: list[dict], source_texts: dict[str, str] | None = None, reference_texts: dict[str, str] | None = None) -> dict:
    """Build a per-run report dict from a list of result rows (schema.ROW_FIELDS shape).

    source_texts / reference_texts are optional {item_id: text} maps supplied
    by the caller from the (rights-restricted) item data -- never persisted
    back into the report, used only to compute aggregate numbers here.
    """
    total = len(rows)
    errors = [r for r in rows if r.get("error")]
    successes = [r for r in rows if not r.get("error")]

    untranslated_flags = 0
    length_flags = 0
    ratios: list[float] = []
    hyps: list[str] = []
    refs: list[str] = []

    for row in successes:
        translation = row.get("translation") or ""
        if has_untranslated_arabic(translation):
            untranslated_flags += 1
        source_text = (source_texts or {}).get(row["item_id"])
        ratio = length_ratio(source_text, translation)
        if ratio is not None:
            ratios.append(ratio)
            if flag_length_ratio(ratio):
                length_flags += 1
        ref_text = (reference_texts or {}).get(row["item_id"])
        if ref_text:
            hyps.append(translation)
            refs.append(ref_text)

    latencies = [r["latency_s"] for r in rows if r.get("latency_s") is not None]
    costs = [r["cost_estimate"] for r in rows if r.get("cost_estimate") is not None]

    report = {
        "total_items": total,
        "error_count": len(errors),
        "success_count": len(successes),
        "error_rate": len(errors) / total if total else None,
        "untranslated_arabic_count": untranslated_flags,
        "untranslated_arabic_rate": untranslated_flags / len(successes) if successes else None,
        "length_ratio_flag_count": length_flags,
        "length_ratio_mean": statistics.mean(ratios) if ratios else None,
        "chrf": chrf_score(hyps, refs) if refs else None,
        "chrf_pair_count": len(refs),
        "latency_s_mean": statistics.mean(latencies) if latencies else None,
        "latency_s_p95": (sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)] if latencies else None),
        "cost_estimate_total": sum(costs) if costs else None,
    }
    report.update({f"id_{k}": v for k, v in id_preservation_report(rows).items()})
    return report


def render_markdown(report: dict, title: str = "Harness Run Report") -> str:
    """Render a report dict as a markdown summary. No item text is quoted."""
    lines = [f"# {title}", ""]
    lines.append(f"- Items: {report.get('total_items')}")
    lines.append(f"- Success: {report.get('success_count')}  |  Errors: {report.get('error_count')}")
    err_rate = report.get("error_rate")
    lines.append(f"- Error rate: {err_rate:.2%}" if err_rate is not None else "- Error rate: n/a")
    lines.append("")
    lines.append("## Quality signals")
    ua_rate = report.get("untranslated_arabic_rate")
    lines.append(
        f"- Untranslated-Arabic rate: {ua_rate:.2%}" if ua_rate is not None else "- Untranslated-Arabic rate: n/a"
    )
    lines.append(f"- Length-ratio flags: {report.get('length_ratio_flag_count')}")
    lr_mean = report.get("length_ratio_mean")
    lines.append(f"- Mean length ratio (out/src words): {lr_mean:.2f}" if lr_mean is not None else "- Mean length ratio: n/a")
    chrf = report.get("chrf")
    lines.append(
        f"- chrF ({report.get('chrf_pair_count')} reference pairs): {chrf:.2f}"
        if chrf is not None
        else "- chrF: n/a (no reference pairs)"
    )
    id_rate = report.get("id_id_preservation_rate")
    if id_rate is not None:
        lines.append(f"- ID preservation rate: {id_rate:.2%} ({report.get('id_id_violations')} violations)")
        lines.append(
            f"  - missing: {report.get('id_id_missing_count')}"
            f"  |  unexpected: {report.get('id_id_unexpected_count')}"
            f"  |  duplicated: {report.get('id_id_duplicate_count')}"
            f"  |  empty: {report.get('id_structured_empty_count')}"
        )
    lines.append("")
    lines.append("## Cost & latency")
    lat_mean = report.get("latency_s_mean")
    lines.append(f"- Mean latency: {lat_mean:.2f}s" if lat_mean is not None else "- Mean latency: n/a")
    lat_p95 = report.get("latency_s_p95")
    lines.append(f"- p95 latency: {lat_p95:.2f}s" if lat_p95 is not None else "- p95 latency: n/a")
    cost = report.get("cost_estimate_total")
    lines.append(f"- Total cost estimate: ${cost:.4f}" if cost is not None else "- Total cost estimate: n/a")
    lines.append("")
    return "\n".join(lines)
