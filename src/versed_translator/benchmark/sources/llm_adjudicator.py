"""LLM adjudication of alignment candidates the structural anchors cannot settle.

The structural aligner in `baladhuri.py` is high precision by construction:
every passage it emits is bracketed at both ends by matched transmitter
names. What it cannot do is judge the *inside* of a bracketed span -- whether
Hitti abridged a khabar away, whether the Shamela edition carries material
Hitti's manuscript did not, whether the span is parallel in content and not
merely in its endpoints. Word ratio catches the gross cases; it says nothing
about the rest.

So: every passage whose structural confidence is below a threshold, or which
carries a flag, is shown to Claude and asked one question -- is this English
a translation of this Arabic? The verdict is recorded as its own method
(``llm_proposed``) and its own confidence, and it NEVER overwrites the
structural evidence, it is stored beside it. A reviewer must be able to see
which of the two put a passage in the set.

Deliberate limits:

- The model is asked to JUDGE an existing candidate, not to propose a new
  split. Asking a model where to cut a text it cannot see in full invites
  exactly the confident fabrication this project has been burned by.
- ``misaligned`` verdicts do not delete the passage. They demote it, and it
  sorts to the top of the review HTML where a human sees it.
- No network call is ever made implicitly: `adjudicate` must be called, and
  the CLI requires an explicit flag.

Auth: ANTHROPIC_API_KEY from the environment, failing loudly if absent, per
the convention in harness/adapters/anthropic_adapter.py.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

DEFAULT_MODEL = "claude-sonnet-5"
# Sonnet 5 runs adaptive thinking by default and max_tokens caps thinking plus
# text together -- see the harness adapter's docstring for the incident this
# number exists to prevent.
DEFAULT_MAX_TOKENS = 8000

VERDICTS = ("aligned", "partial", "misaligned")

PROMPT = """\
You are auditing a candidate alignment for a Classical Arabic <-> English \
translation benchmark. The Arabic is from al-Baladhuri's Futuh al-Buldan. The \
English is from Philip Hitti's 1916 translation, which is literal but does \
abridge isnads and occasionally omits a report.

Judge ONLY whether the English passage is a translation of the Arabic passage.

Answer with a single JSON object and nothing else:
{{"verdict": "aligned" | "partial" | "misaligned", "confidence": <0.0-1.0>, \
"note": "<one sentence, max 25 words>"}}

- "aligned": the English renders substantially all of the Arabic, in the same \
order, with no unrelated material on either side.
- "partial": they overlap but one side carries material the other does not \
(an extra report at the start or end, an omitted khabar in the middle).
- "misaligned": they are about different events, or the correspondence is \
only incidental.

Report what you actually see. A confident "misaligned" is more useful than a \
hedged "aligned".

--- ARABIC ---
{arabic}

--- ENGLISH ---
{english}
"""


@dataclass(frozen=True)
class Verdict:
    verdict: str
    confidence: float
    note: str
    model: str
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.verdict in VERDICTS


def _get_client():
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - env-dependent
        raise RuntimeError("the 'anthropic' package is not installed") from exc
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set in the environment -- refusing to "
            "guess a credential source for this lab script"
        )
    return anthropic.Anthropic(api_key=api_key)


def parse_verdict(text: str, model: str) -> Verdict:
    """Parse the model's JSON reply, tolerantly but without inventing values.

    An unparseable reply becomes a Verdict carrying `error`, never a default
    "aligned" -- a silent default here would be indistinguishable from a real
    judgement in the output file.
    """
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return Verdict("", 0.0, "", model, error=f"no JSON object in reply: {text[:120]!r}")
    try:
        payload = json.loads(match.group())
    except json.JSONDecodeError as exc:
        return Verdict("", 0.0, "", model, error=f"bad JSON: {exc}")
    verdict = str(payload.get("verdict", "")).strip().lower()
    if verdict not in VERDICTS:
        return Verdict("", 0.0, "", model, error=f"unknown verdict {verdict!r}")
    try:
        confidence = float(payload.get("confidence", 0.0))
    except (TypeError, ValueError):
        return Verdict("", 0.0, "", model, error="confidence is not a number")
    confidence = max(0.0, min(1.0, confidence))
    note = str(payload.get("note", ""))[:200]
    return Verdict(verdict, confidence, note, model)


def adjudicate(
    arabic: str,
    english: str,
    *,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    client=None,
) -> Verdict:
    """Ask the model whether `english` translates `arabic`."""
    client = client or _get_client()
    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[
                {
                    "role": "user",
                    "content": PROMPT.format(arabic=arabic, english=english),
                }
            ],
        )
    except Exception as exc:  # noqa: BLE001 - surfaced, never swallowed
        return Verdict("", 0.0, "", model, error=f"{type(exc).__name__}: {exc}")
    text = "".join(
        block.text for block in response.content if getattr(block, "type", "") == "text"
    )
    if not text.strip():
        return Verdict(
            "", 0.0, "", model, error=f"empty reply (stop_reason={response.stop_reason})"
        )
    return parse_verdict(text, model)


#: How an LLM verdict maps onto a passage's confidence. `aligned` is capped
#: below 1.0 on purpose: a model agreeing with a structural anchor is weaker
#: evidence than two matched transmitter names, and the numbers should say so.
VERDICT_CEILING = {"aligned": 0.85, "partial": 0.5, "misaligned": 0.15}


def combined_confidence(structural: float, verdict: Verdict) -> float:
    """Blend a structural confidence with an LLM verdict.

    The result is capped by the verdict, so an LLM "misaligned" always pulls a
    passage down no matter how strong its brackets looked.
    """
    if not verdict.ok:
        return structural
    ceiling = VERDICT_CEILING[verdict.verdict]
    blended = 0.5 * structural + 0.5 * verdict.confidence
    return round(min(blended, ceiling), 3)
