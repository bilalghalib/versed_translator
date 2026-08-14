"""Side-by-side alignment review page (C1 checkpoint 3, a [HUMAN] gate).

Renders aligned Arabic/English passages for spot-checking: Arabic RTL and
right-aligned beside the English, each pair carrying its confidence, its
method, the transmitter names that anchored it, and any flags.

Sort order is the point of the page. **Lowest confidence first**, so the
pairs most likely to be wrong are the ones a reviewer actually reaches. A
review page sorted by id gets read from the top until attention runs out,
which is the same as not reviewing the tail at all.

⚠️ THIS PAGE CONTAINS CORPUS TEXT. It must never be written into the repo,
and specifically never into `docs/`, which GitHub Pages serves publicly.
`render_page` returns a string; the caller decides where it lands, and
`pd_alignment.main` refuses to write it inside the repo tree.

Visual language matches tools/build_dashboard.py: warm off-white / dark,
accent #3d5a80, system font stack, theme-aware via prefers-color-scheme.
"""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from typing import Any

CSS = """
:root {
  --bg: #faf9f7;
  --bg-elevated: #ffffff;
  --text: #1f1d1a;
  --text-muted: #6b665f;
  --border: #e4e0da;
  --accent: #3d5a80;
  --chip-blue-bg: #e3edf7;
  --chip-blue-text: #29527a;
  --chip-gray-bg: #eceae6;
  --chip-gray-text: #66625c;
  --chip-green-bg: #e4f0e6;
  --chip-green-text: #2c6b3f;
  --chip-amber-bg: #f7efdd;
  --chip-amber-text: #8a6520;
  --chip-red-bg: #f6e6e5;
  --chip-red-text: #a13d36;
  --link: #3d5a80;
  --code-bg: #f1efeb;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #17181a;
    --bg-elevated: #1f2023;
    --text: #e8e6e1;
    --text-muted: #a3a099;
    --border: #34363a;
    --accent: #8fb4d9;
    --chip-blue-bg: #223244;
    --chip-blue-text: #9cc4ea;
    --chip-gray-bg: #2b2c2f;
    --chip-gray-text: #b3afa7;
    --chip-green-bg: #1f3625;
    --chip-green-text: #8fd39f;
    --chip-amber-bg: #3a3018;
    --chip-amber-text: #dcb663;
    --chip-red-bg: #3a2422;
    --chip-red-text: #e2938c;
    --link: #8fb4d9;
    --code-bg: #232427;
  }
}
:root[data-theme="dark"] {
  --bg: #17181a;
  --bg-elevated: #1f2023;
  --text: #e8e6e1;
  --text-muted: #a3a099;
  --border: #34363a;
  --accent: #8fb4d9;
  --chip-blue-bg: #223244;
  --chip-blue-text: #9cc4ea;
  --chip-gray-bg: #2b2c2f;
  --chip-gray-text: #b3afa7;
  --chip-green-bg: #1f3625;
  --chip-green-text: #8fd39f;
  --chip-amber-bg: #3a3018;
  --chip-amber-text: #dcb663;
  --chip-red-bg: #3a2422;
  --chip-red-text: #e2938c;
  --link: #8fb4d9;
  --code-bg: #232427;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  line-height: 1.5;
}
.wrap { max-width: 1180px; margin: 0 auto; padding: 2rem 1.25rem 4rem; }

header.site-header { border-bottom: 1px solid var(--border); padding-bottom: 1.25rem; margin-bottom: 1.5rem; }
header.site-header h1 { margin: 0 0 .35rem; font-size: 1.5rem; letter-spacing: -0.01em; }
header.site-header .sub { color: var(--text-muted); font-size: .9rem; margin: 0; }

.notice {
  background: var(--chip-red-bg); color: var(--chip-red-text);
  border: 1px solid var(--border); border-left: 4px solid var(--chip-red-text);
  border-radius: 6px; padding: .7rem .9rem; margin: 1rem 0 1.25rem; font-size: .87rem;
}
.notice code { background: transparent; }

.summary {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: .75rem; margin-bottom: 1.5rem;
}
.stat { background: var(--bg-elevated); border: 1px solid var(--border); border-radius: 8px; padding: .7rem .85rem; }
.stat .n { font-size: 1.35rem; font-weight: 600; }
.stat .k { color: var(--text-muted); font-size: .78rem; text-transform: uppercase; letter-spacing: .04em; }

.howto { background: var(--bg-elevated); border: 1px solid var(--border); border-left: 4px solid var(--accent);
  border-radius: 6px; padding: .8rem 1rem; margin-bottom: 1.5rem; font-size: .9rem; }
.howto p { margin: .3rem 0; }

.controls {
  position: sticky; top: 0; z-index: 5; background: var(--bg);
  border-bottom: 1px solid var(--border); padding: .6rem 0; margin-bottom: 1.25rem;
  display: flex; flex-wrap: wrap; gap: .5rem; align-items: center;
}
.controls label { font-size: .85rem; color: var(--text-muted); }
.controls select, .controls button {
  font: inherit; font-size: .85rem; padding: .3rem .55rem;
  background: var(--bg-elevated); color: var(--text);
  border: 1px solid var(--border); border-radius: 6px; cursor: pointer;
}
.controls button.primary { background: var(--accent); color: var(--bg-elevated); border-color: var(--accent); }
.controls .spacer { flex: 1; }
#tally { font-size: .85rem; color: var(--text-muted); }

.pair {
  background: var(--bg-elevated); border: 1px solid var(--border);
  border-radius: 8px; margin-bottom: 1.1rem; overflow: hidden;
}
.pair.lowconf { border-left: 4px solid var(--chip-red-text); }
.pair.midconf { border-left: 4px solid var(--chip-amber-text); }
.pair.hiconf  { border-left: 4px solid var(--chip-green-text); }

.pair-head {
  display: flex; flex-wrap: wrap; gap: .4rem .55rem; align-items: center;
  padding: .6rem .85rem; border-bottom: 1px solid var(--border);
}
.pair-head .id { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .78rem; color: var(--text-muted); }
.pair-head .where { font-size: .85rem; font-weight: 600; }
.chip { font-size: .72rem; padding: .12rem .45rem; border-radius: 999px; white-space: nowrap; }
.chip.blue { background: var(--chip-blue-bg); color: var(--chip-blue-text); }
.chip.gray { background: var(--chip-gray-bg); color: var(--chip-gray-text); }
.chip.green { background: var(--chip-green-bg); color: var(--chip-green-text); }
.chip.amber { background: var(--chip-amber-bg); color: var(--chip-amber-text); }
.chip.red { background: var(--chip-red-bg); color: var(--chip-red-text); }

.meta { padding: .45rem .85rem; font-size: .78rem; color: var(--text-muted); border-bottom: 1px solid var(--border); }
.meta code { background: var(--code-bg); padding: 0 .25rem; border-radius: 3px; }

.cols { display: grid; grid-template-columns: 1fr 1fr; }
.col { padding: .85rem 1rem; }
.col + .col { border-left: 1px solid var(--border); }
.col h4 { margin: 0 0 .4rem; font-size: .72rem; text-transform: uppercase;
  letter-spacing: .05em; color: var(--text-muted); font-weight: 600; }
.col p { margin: 0 0 .6rem; }
.col.ar { direction: rtl; text-align: right; font-size: 1.06rem; line-height: 1.95; }
.col.ar h4 { direction: ltr; text-align: right; }
@media (max-width: 820px) {
  .cols { grid-template-columns: 1fr; }
  .col + .col { border-left: none; border-top: 1px solid var(--border); }
}

.verdict { padding: .5rem .85rem; border-top: 1px solid var(--border); display: flex;
  gap: .8rem; align-items: center; flex-wrap: wrap; font-size: .82rem; }
.verdict label { display: inline-flex; gap: .25rem; align-items: center; cursor: pointer; }

footer { margin-top: 2.5rem; border-top: 1px solid var(--border); padding-top: 1rem;
  color: var(--text-muted); font-size: .8rem; }
"""

SCRIPT = """
(function () {
  var pairs = Array.prototype.slice.call(document.querySelectorAll('.pair'));
  var fMethod = document.getElementById('f-method');
  var fBand = document.getElementById('f-band');
  var fConf = document.getElementById('f-conf');
  var tally = document.getElementById('tally');

  function apply() {
    var m = fMethod.value, b = fBand.value, c = parseFloat(fConf.value);
    var shown = 0;
    pairs.forEach(function (el) {
      var ok = (m === '*' || el.dataset.method === m)
        && (b === '*' || el.dataset.band === b)
        && (isNaN(c) || parseFloat(el.dataset.confidence) <= c);
      el.style.display = ok ? '' : 'none';
      if (ok) shown++;
    });
    tally.textContent = shown + ' of ' + pairs.length + ' shown';
  }
  [fMethod, fBand, fConf].forEach(function (el) { el.addEventListener('change', apply); });
  apply();

  document.getElementById('copy').addEventListener('click', function () {
    var out = [];
    pairs.forEach(function (el) {
      var checked = el.querySelector('input[type=radio]:checked');
      if (checked) {
        out.push({ id: el.dataset.id, reviewer_verdict: checked.value,
                   confidence: parseFloat(el.dataset.confidence),
                   method: el.dataset.method });
      }
    });
    var text = JSON.stringify(out, null, 2);
    navigator.clipboard.writeText(text).then(function () {
      var b = document.getElementById('copy');
      var old = b.textContent;
      b.textContent = 'Copied ' + out.length + ' verdicts';
      setTimeout(function () { b.textContent = old; }, 1800);
    });
  });
})();
"""


def _esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def _paragraphs(text: str) -> str:
    blocks = [b.strip() for b in str(text).split("\n\n") if b.strip()]
    return "".join(f"<p>{_esc(b)}</p>" for b in blocks) or "<p></p>"


def _conf_class(confidence: float) -> str:
    if confidence < 0.6:
        return "lowconf"
    return "midconf" if confidence < 0.8 else "hiconf"


def _conf_chip(confidence: float) -> str:
    colour = "red" if confidence < 0.6 else ("amber" if confidence < 0.8 else "green")
    return f'<span class="chip {colour}">confidence {confidence:.2f}</span>'


def _render_pair(record: dict) -> str:
    confidence = float(record.get("confidence", 0.0))
    method = record.get("method", "unknown")
    flags = record.get("flags") or []
    verdict = record.get("llm_verdict") or {}

    chips = [
        _conf_chip(confidence),
        f'<span class="chip {"blue" if method == "structural" else "amber"}">{_esc(method)}</span>',
        f'<span class="chip gray">{_esc(record.get("band"))}</span>',
        (
            f'<span class="chip gray">ar {record.get("arabic_word_count")}w '
            f'/ en {record.get("english_word_count")}w</span>'
        ),
    ]
    for flag in flags:
        chips.append(f'<span class="chip red">{_esc(flag)}</span>')
    if verdict.get("verdict"):
        chips.append(
            f'<span class="chip amber">LLM: {_esc(verdict["verdict"])} '
            f'{float(verdict.get("confidence", 0.0)):.2f}</span>'
        )

    meta_bits = [
        f'anchors open <code>{_esc("/".join(record.get("anchors_open") or []) or "-")}</code>',
        f'close <code>{_esc("/".join(record.get("anchors_close") or []) or "-")}</code>',
        f'ratio <code>{float(record.get("word_ratio", 0.0)):.2f}</code>',
        f'arabic paras <code>{_esc(record.get("arabic_range"))}</code>',
        f'english paras <code>{_esc(record.get("english_range"))}</code>',
    ]
    if verdict.get("note"):
        meta_bits.append(f'LLM note: {_esc(verdict["note"])}')
    if record.get("headings_stripped"):
        meta_bits.append(
            "run-in headings removed: "
            + _esc("; ".join(record["headings_stripped"]))
        )

    pid = _esc(record.get("id"))
    return f"""
<article class="pair {_conf_class(confidence)}" data-id="{pid}"
         data-method="{_esc(method)}" data-band="{_esc(record.get("band"))}"
         data-confidence="{confidence:.3f}">
  <div class="pair-head">
    <span class="where">{_esc(record.get("section_title"))} &nbsp;&middot;&nbsp;
      {_esc(record.get("chapter_label"))} {_esc(record.get("chapter_title"))}</span>
    {"".join(chips)}
    <span class="id">{pid}</span>
  </div>
  <div class="meta">{" &nbsp;&middot;&nbsp; ".join(meta_bits)}</div>
  <div class="cols">
    <div class="col en"><h4>English &mdash; Hitti 1916</h4>{_paragraphs(record.get("english", ""))}</div>
    <div class="col ar"><h4>العربية &mdash; OpenITI</h4>{_paragraphs(record.get("arabic", ""))}</div>
  </div>
  <div class="verdict">
    <span>Reviewer:</span>
    <label><input type="radio" name="v-{pid}" value="aligned"> aligned</label>
    <label><input type="radio" name="v-{pid}" value="partial"> partial</label>
    <label><input type="radio" name="v-{pid}" value="misaligned"> misaligned</label>
  </div>
</article>"""


def render_page(records: list[dict], summary: dict) -> str:
    """Render the review page. Records are sorted lowest-confidence first."""
    ordered = sorted(
        records,
        key=lambda r: (float(r.get("confidence", 0.0)), str(r.get("id"))),
    )
    bands = sorted({str(r.get("band")) for r in records})
    methods = sorted({str(r.get("method")) for r in records})

    stats = "".join(
        f'<div class="stat"><div class="n">{_esc(v)}</div><div class="k">{_esc(k)}</div></div>'
        for k, v in summary.get("stats", {}).items()
    )
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    band_options = "".join(f'<option value="{_esc(b)}">{_esc(b)}</option>' for b in bands)
    method_options = "".join(f'<option value="{_esc(m)}">{_esc(m)}</option>' for m in methods)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Alignment review &mdash; {_esc(summary.get("work_title", ""))}</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header class="site-header">
  <h1>Alignment review &mdash; {_esc(summary.get("work_title", ""))}</h1>
  <p class="sub">{_esc(summary.get("subtitle", ""))} &middot; generated {generated}</p>
</header>

<div class="notice">
  <strong>Contains corpus text.</strong> This file must stay outside the repository
  &mdash; and specifically out of <code>docs/</code>, which GitHub Pages serves publicly.
  Rights: {_esc(summary.get("rights", ""))}
</div>

<div class="summary">{stats}</div>

<div class="howto">
  <p><strong>What to check.</strong> Not "is the English good" &mdash; is it a translation of
  <em>this</em> Arabic. The failure that matters is a systematic shift: every pair looks
  plausible on its own while the whole set sits one report off.</p>
  <p><strong>Read the ends, not the middle.</strong> Each passage is bracketed by matched
  transmitter names. If the first Arabic report has no counterpart at the top of the English,
  or the last English paragraph runs past the end of the Arabic, the bracket failed.</p>
  <p><strong>Lowest confidence sorts first.</strong> Mark verdicts below each pair, then
  <em>Copy verdicts</em> to get JSON for the record.</p>
</div>

<div class="controls">
  <label for="f-method">method</label>
  <select id="f-method"><option value="*">all</option>{method_options}</select>
  <label for="f-band">band</label>
  <select id="f-band"><option value="*">all</option>{band_options}</select>
  <label for="f-conf">confidence at most</label>
  <select id="f-conf">
    <option value="">any</option>
    <option value="0.6">0.60</option>
    <option value="0.8">0.80</option>
    <option value="0.9">0.90</option>
  </select>
  <span class="spacer"></span>
  <span id="tally"></span>
  <button id="copy" class="primary">Copy verdicts</button>
</div>

{"".join(_render_pair(r) for r in ordered)}

<footer>
  <p>Arabic: OpenITI <code>{_esc(summary.get("work_id", ""))}</code>.
     English: {_esc(summary.get("english_source", ""))}.</p>
  <p>Alignment method and thresholds:
     <code>src/versed_translator/benchmark/sources/baladhuri.py</code>.
     Provenance for every pair is carried in the sibling JSONL.</p>
</footer>
</div>
<script>{SCRIPT}</script>
</body>
</html>
"""


def render_from_jsonl(path: str, summary: dict) -> str:
    """Convenience: read a passages JSONL and render the page."""
    with open(path, encoding="utf-8") as handle:
        records = [json.loads(line) for line in handle if line.strip()]
    return render_page(records, summary)
