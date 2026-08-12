#!/usr/bin/env python3
"""
build_dashboard.py — Status dashboard generator for the versed_translator lab repo.

Reads VERSED_TRANSLATION_ROADMAP.md and TRANSLATION_EXPERIMENTS.md (plus git log
and doc mtimes) and emits dashboard/status.json + dashboard/index.html.

Python 3.10 stdlib only. No pip dependencies.

Parsing is deliberately tolerant: if a section is missing or malformed we
render whatever we have and record a note in the "gaps" list rather than
raising. The only hard failure mode is "the two source docs don't exist at
all", which is reported clearly rather than crashing with a traceback.
"""

from __future__ import annotations

import html
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ROADMAP_PATH = REPO_ROOT / "VERSED_TRANSLATION_ROADMAP.md"
EXPERIMENTS_PATH = REPO_ROOT / "TRANSLATION_EXPERIMENTS.md"
DASHBOARD_DIR = REPO_ROOT / "docs"  # served by GitHub Pages (main:/docs)

ROOT_DOCS = [
    "VERSED_TRANSLATION_ROADMAP.md",
    "TRANSLATION_EXPERIMENTS.md",
    "VERSED_TRANSLATE_MASTER_PLAN.md",
    "VERSED_TRANSLATION_ARCHITECTURE.md",
]

REPO_URL = "https://github.com/bilalghalib/versed_translator"

STATUS_COLORS = {
    "ACTIVE": "blue",
    "NOT STARTED": "gray",
    "COMPLETE": "green",
    "BLOCKED": "red",
}


# ---------------------------------------------------------------------------
# Small parsing helpers
# ---------------------------------------------------------------------------

def read_text(path: Path, gaps: list[str]) -> str:
    """Read a file's text, tolerantly. Returns '' and notes a gap on failure."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        gaps.append(f"Missing source file: {path.name} (expected at {path})")
        return ""
    except OSError as exc:
        gaps.append(f"Could not read {path.name}: {exc}")
        return ""


def normalize_status(raw: str) -> str:
    """Map a free-text status cell to one of our four canonical labels."""
    raw_up = raw.strip().upper()
    for canonical in STATUS_COLORS:
        if raw_up == canonical or raw_up.startswith(canonical):
            return canonical
    if "ACTIVE" in raw_up:
        return "ACTIVE"
    if "BLOCK" in raw_up:
        return "BLOCKED"
    if "COMPLETE" in raw_up or "DONE" in raw_up:
        return "COMPLETE"
    if "NOT STARTED" in raw_up or "NOT-STARTED" in raw_up:
        return "NOT STARTED"
    return raw.strip() or "UNKNOWN"


def split_md_table_row(line: str) -> list[str]:
    """Split a markdown table row '| a | b | c |' into ['a','b','c']."""
    line = line.strip()
    line = line.removeprefix("|")
    line = line.removesuffix("|")
    return [cell.strip() for cell in line.split("|")]


def is_table_separator(cells: list[str]) -> bool:
    """True if every cell looks like '---' / ':---:' etc."""
    return all(re.fullmatch(r":?-{2,}:?", c.strip()) is not None for c in cells if c.strip() != "") and len(cells) > 0


def find_table_after_heading(text: str, heading_pattern: str) -> list[list[str]]:
    """
    Find a markdown table located after a line matching heading_pattern
    (a regex applied with re.search per line). Returns rows of cells,
    header row included as rows[0]. Returns [] if not found.
    """
    lines = text.splitlines()
    heading_re = re.compile(heading_pattern)
    start_idx = None
    for i, line in enumerate(lines):
        if heading_re.search(line):
            start_idx = i
            break
    if start_idx is None:
        return []

    # Scan forward for the first '|' table line after the heading.
    table_lines: list[str] = []
    i = start_idx + 1
    n = len(lines)
    # Skip blank lines before the table starts.
    while i < n and not lines[i].strip():
        i += 1
    while i < n and lines[i].strip().startswith("|"):
        table_lines.append(lines[i])
        i += 1

    if not table_lines:
        return []

    rows = [split_md_table_row(l) for l in table_lines]
    # Drop the separator row (usually rows[1]).
    rows = [r for r in rows if not is_table_separator(r)]
    return rows


# ---------------------------------------------------------------------------
# Roadmap parsing
# ---------------------------------------------------------------------------

def parse_status_ledger(text: str, gaps: list[str]) -> dict[str, str]:
    """Returns {component_id: normalized_status} from the '# STATUS ledger' table."""
    rows = find_table_after_heading(text, r"^#{1,6}\s*STATUS ledger")
    if not rows:
        gaps.append("STATUS ledger table not found in roadmap doc.")
        return {}

    header = [c.lower() for c in rows[0]]
    data_rows = rows[1:] if header and "component" in header[0] else rows

    result: dict[str, str] = {}
    for row in data_rows:
        if len(row) < 2:
            continue
        comp_cell, status_cell = row[0], row[1]
        m = re.match(r"\s*(C\d{1,2})\b", comp_cell)
        if not m:
            continue
        cid = m.group(1)
        result[cid] = normalize_status(status_cell)
    if not result:
        gaps.append("STATUS ledger table found but no component rows parsed.")
    return result


def parse_decision_queue(text: str, gaps: list[str]) -> list[dict[str, str]]:
    """Returns list of {id, decision, when} from '# Decision queue' table."""
    rows = find_table_after_heading(text, r"^#{1,6}\s*Decision queue")
    if not rows:
        gaps.append("Decision queue table not found in roadmap doc.")
        return []

    header = [c.lower() for c in rows[0]]
    data_rows = rows[1:] if header and header[0].strip() in ("id",) else rows

    decisions = []
    for row in data_rows:
        if len(row) < 3:
            # tolerate short rows by padding
            row = row + [""] * (3 - len(row))
        did, decision, when = row[0], row[1], row[2]
        did = did.strip()
        decision = decision.strip()
        when = when.strip()
        if not did and not decision:
            continue
        decisions.append({"id": did or "—", "decision": decision, "when": when})
    if not decisions:
        gaps.append("Decision queue table found but no rows parsed.")
    return decisions


def parse_components(text: str, gaps: list[str]) -> list[dict[str, str]]:
    """
    Parse each '## C<N> — <name>' section for its END STATE first sentence,
    STATUS line, and NEXT DEPENDENCY line. Section-level STATUS here is a
    fallback; the STATUS ledger table is the primary source and wins when
    both exist (they're expected to agree).
    """
    heading_re = re.compile(r"^##\s+(C\d{1,2})\s*[—–-]\s*(.+?)\s*$", re.MULTILINE)
    matches = list(heading_re.finditer(text))
    if not matches:
        gaps.append("No component sections ('## C<N> — <name>') found in roadmap doc.")
        return []

    components = []
    for idx, m in enumerate(matches):
        cid, name = m.group(1), m.group(2).strip()
        section_start = m.end()
        section_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        section = text[section_start:section_end]

        end_state_sentence = ""
        es_match = re.search(r"\*\*END STATE[^:]*:\*\*\s*(.+)", section)
        if es_match:
            rest_of_section = section[es_match.start():]
            # Grab everything up to a blank line or next bold-heading, then
            # take the first sentence out of that.
            block_match = re.match(r"\*\*END STATE[^:]*:\*\*\s*(.*?)(?:\n\n|\Z)", rest_of_section, re.DOTALL)
            block_text = block_match.group(1) if block_match else es_match.group(1)
            block_text = " ".join(block_text.split())  # collapse whitespace/newlines
            sent_match = re.search(r"(.+?[.:;])(?:\s|$)", block_text)
            end_state_sentence = sent_match.group(1).strip() if sent_match else block_text.strip()
        else:
            gaps.append(f"{cid}: no END STATE line found.")

        status_match = re.search(r"\*\*STATUS:\*\*\s*(.+)", section)
        section_status = normalize_status(status_match.group(1).split(".")[0]) if status_match else ""
        if not status_match:
            gaps.append(f"{cid}: no STATUS line found in section body.")

        dep_match = re.search(r"\*\*NEXT DEPENDENCY:\*\*\s*(.+)", section)
        next_dependency = dep_match.group(1).strip() if dep_match else ""

        components.append({
            "id": cid,
            "name": name,
            "end_state": end_state_sentence,
            "section_status": section_status,
            "next_dependency": next_dependency,
        })
    return components


# ---------------------------------------------------------------------------
# Experiments parsing
# ---------------------------------------------------------------------------

def parse_experiments(text: str, gaps: list[str]) -> list[dict[str, str]]:
    """
    Two shapes are collected:
      1. '## EXP-YYYYMMDD-NN — <one-line name>' headings.
      2. Imported-findings bullets: '- **EXP-... — <name>:**' or similar.
    """
    if not text:
        return []

    experiments: list[dict[str, str]] = []
    seen_ids: set[str] = set()

    heading_re = re.compile(r"^##\s+(EXP-[\w-]+)\s*[—–-]\s*(.+?)\s*$", re.MULTILINE)
    for m in heading_re.finditer(text):
        eid, name = m.group(1), m.group(2).strip()
        if eid not in seen_ids:
            experiments.append({"id": eid, "name": name})
            seen_ids.add(eid)

    bullet_re = re.compile(
        r"^\s*-\s*\*\*(EXP-[\w-]+)\s*[—–-]\s*(.+?)\s*(?::)?\*\*",
        re.MULTILINE,
    )
    for m in bullet_re.finditer(text):
        eid, name = m.group(1), m.group(2).strip()
        if eid not in seen_ids:
            experiments.append({"id": eid, "name": name})
            seen_ids.add(eid)

    if not experiments:
        gaps.append("No experiment entries (## EXP- headings or imported-findings bullets) found.")

    return experiments


# ---------------------------------------------------------------------------
# Git + filesystem metadata
# ---------------------------------------------------------------------------

def get_recent_commits(n: int, gaps: list[str]) -> list[dict[str, str]]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "log", f"-{n}", "--pretty=format:%s\t%ar"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        gaps.append(f"Could not run git log: {exc}")
        return []

    if proc.returncode != 0:
        gaps.append(f"git log exited non-zero: {proc.stderr.strip()[:200]}")
        return []

    commits = []
    for line in proc.stdout.splitlines():
        if "\t" in line:
            subject, rel_date = line.split("\t", 1)
        else:
            subject, rel_date = line, ""
        commits.append({"subject": subject, "relative_date": rel_date})
    if not commits:
        gaps.append("git log returned no commits.")
    return commits


def get_doc_mtimes(gaps: list[str]) -> list[dict[str, str]]:
    out = []
    for name in ROOT_DOCS:
        path = REPO_ROOT / name
        try:
            ts = path.stat().st_mtime
            iso = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
            out.append({"name": name, "mtime": iso})
        except OSError:
            gaps.append(f"Doc not found for mtime: {name}")
            out.append({"name": name, "mtime": None})
    return out


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def build_status_data() -> dict:
    gaps: list[str] = []

    roadmap_text = read_text(ROADMAP_PATH, gaps)
    experiments_text = read_text(EXPERIMENTS_PATH, gaps)

    ledger_status = parse_status_ledger(roadmap_text, gaps)
    decisions = parse_decision_queue(roadmap_text, gaps)
    components = parse_components(roadmap_text, gaps)
    experiments = parse_experiments(experiments_text, gaps)
    commits = get_recent_commits(12, gaps)
    doc_mtimes = get_doc_mtimes(gaps)

    # Merge status ledger (primary) with per-section parsing (fallback).
    for comp in components:
        cid = comp["id"]
        ledger_val = ledger_status.get(cid)
        if ledger_val:
            comp["status"] = ledger_val
        elif comp.get("section_status"):
            comp["status"] = comp["section_status"]
            gaps.append(f"{cid}: status taken from section body; missing from STATUS ledger table.")
        else:
            comp["status"] = "UNKNOWN"
            gaps.append(f"{cid}: no status found anywhere.")
        comp.pop("section_status", None)

    # Components present in the ledger but with no matching section.
    section_ids = {c["id"] for c in components}
    for cid, status in ledger_status.items():
        if cid not in section_ids:
            gaps.append(f"{cid}: present in STATUS ledger but no '## {cid} — ...' section found.")
            components.append({
                "id": cid, "name": "(name unavailable — section not found)",
                "end_state": "", "status": status, "next_dependency": "",
            })

    def comp_sort_key(c):
        m = re.match(r"C(\d+)", c["id"])
        return int(m.group(1)) if m else 999

    components.sort(key=comp_sort_key)

    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo_url": REPO_URL,
        "components": components,
        "decisions": decisions,
        "experiments": experiments,
        "recent_commits": commits,
        "doc_mtimes": doc_mtimes,
        "gaps": gaps,
    }
    return data


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

def esc(s) -> str:
    return html.escape(str(s) if s is not None else "", quote=True)


def status_chip_html(status: str) -> str:
    color = STATUS_COLORS.get(status, "gray")
    return f'<span class="chip chip-{color}">{esc(status)}</span>'


def render_component_cards(components: list[dict]) -> str:
    if not components:
        return '<p class="empty-note">No component data parsed from the roadmap.</p>'
    cards = []
    for c in components:
        end_state = esc(c.get("end_state") or "(no END STATE sentence found)")
        next_dep = c.get("next_dependency") or ""
        next_dep_html = f'<div class="card-dep">Next dependency: {esc(next_dep)}</div>' if next_dep else ""
        cards.append(f"""
        <div class="card">
          <div class="card-head">
            <span class="card-id">{esc(c['id'])}</span>
            {status_chip_html(c.get('status', 'UNKNOWN'))}
          </div>
          <div class="card-name">{esc(c.get('name', ''))}</div>
          <div class="card-end-state">{end_state}</div>
          {next_dep_html}
        </div>""")
    return f'<div class="component-grid">{"".join(cards)}</div>'


def render_decisions_table(decisions: list[dict]) -> str:
    if not decisions:
        return '<p class="empty-note">No decisions parsed from the decision queue.</p>'
    rows = "".join(
        f"<tr><td>{esc(d['id'])}</td><td>{esc(d['decision'])}</td><td>{esc(d['when'])}</td></tr>"
        for d in decisions
    )
    return f"""
    <div class="table-wrap">
      <table>
        <thead><tr><th>ID</th><th>Decision</th><th>When</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>"""


def render_experiments_list(experiments: list[dict]) -> str:
    if not experiments:
        return '<p class="empty-note">No experiment entries found in TRANSLATION_EXPERIMENTS.md.</p>'
    items = "".join(
        f'<li><span class="exp-id">{esc(e["id"])}</span> — {esc(e["name"])}</li>'
        for e in experiments
    )
    return f'<ul class="experiment-list">{items}</ul>'


def render_commits_list(commits: list[dict]) -> str:
    if not commits:
        return '<p class="empty-note">No recent commits found.</p>'
    items = "".join(
        f'<li><span class="commit-subject">{esc(c["subject"])}</span> '
        f'<span class="commit-date">{esc(c["relative_date"])}</span></li>'
        for c in commits
    )
    return f'<ul class="commit-list">{items}</ul>'


def render_gaps(gaps: list[str]) -> str:
    if not gaps:
        return ""
    items = "".join(f"<li>{esc(g)}</li>" for g in gaps)
    return f"""
    <section class="gaps">
      <h2>Parsing gaps</h2>
      <p class="section-note">The generator noted the following while reading the source docs. Nothing here blocked the build; it's a record of what to double-check.</p>
      <ul>{items}</ul>
    </section>"""


def render_html(data: dict) -> str:
    generated_at = data["generated_at"]
    doc_mtimes_html = "".join(
        f'<li>{esc(d["name"])}: {esc(d["mtime"] or "unknown")}</li>' for d in data["doc_mtimes"]
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Versed Translate Lab</title>
<style>
:root {{
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
  --chip-red-bg: #f6e6e5;
  --chip-red-text: #a13d36;
  --link: #3d5a80;
  --code-bg: #f1efeb;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
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
    --chip-red-bg: #3a2422;
    --chip-red-text: #e2938c;
    --link: #8fb4d9;
    --code-bg: #232427;
  }}
}}
:root[data-theme="dark"] {{
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
  --chip-red-bg: #3a2422;
  --chip-red-text: #e2938c;
  --link: #8fb4d9;
  --code-bg: #232427;
}}

* {{ box-sizing: border-box; }}

body {{
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  line-height: 1.5;
}}

.wrap {{
  max-width: 980px;
  margin: 0 auto;
  padding: 2rem 1.25rem 4rem;
}}

header.site-header {{
  border-bottom: 1px solid var(--border);
  padding-bottom: 1.25rem;
  margin-bottom: 2rem;
}}
header.site-header h1 {{
  margin: 0 0 0.35rem;
  font-size: 1.5rem;
  font-weight: 600;
}}
header.site-header .meta {{
  color: var(--text-muted);
  font-size: 0.9rem;
}}
header.site-header .meta a {{
  color: var(--link);
  text-decoration: none;
}}
header.site-header .meta a:hover {{
  text-decoration: underline;
}}

section {{
  margin-bottom: 2.5rem;
}}
section h2 {{
  font-size: 1.15rem;
  font-weight: 600;
  margin: 0 0 0.25rem;
}}
.section-note {{
  color: var(--text-muted);
  font-size: 0.88rem;
  margin: 0 0 1rem;
}}

.component-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
  gap: 0.9rem;
}}
.card {{
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.9rem 1rem;
}}
.card-head {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.4rem;
}}
.card-id {{
  font-weight: 700;
  font-size: 0.95rem;
  letter-spacing: 0.02em;
}}
.card-name {{
  font-weight: 600;
  font-size: 0.92rem;
  margin-bottom: 0.4rem;
}}
.card-end-state {{
  color: var(--text-muted);
  font-size: 0.85rem;
}}
.card-dep {{
  margin-top: 0.5rem;
  font-size: 0.78rem;
  color: var(--text-muted);
  border-top: 1px solid var(--border);
  padding-top: 0.4rem;
}}

.chip {{
  display: inline-block;
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.03em;
  padding: 0.18rem 0.55rem;
  border-radius: 999px;
  white-space: nowrap;
}}
.chip-blue {{ background: var(--chip-blue-bg); color: var(--chip-blue-text); }}
.chip-gray {{ background: var(--chip-gray-bg); color: var(--chip-gray-text); }}
.chip-green {{ background: var(--chip-green-bg); color: var(--chip-green-text); }}
.chip-red {{ background: var(--chip-red-bg); color: var(--chip-red-text); }}

.table-wrap {{
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: 8px;
}}
table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 0.88rem;
  background: var(--bg-elevated);
}}
th, td {{
  text-align: left;
  padding: 0.55rem 0.75rem;
  border-bottom: 1px solid var(--border);
  vertical-align: top;
}}
th {{
  color: var(--text-muted);
  font-weight: 600;
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}}
tbody tr:last-child td {{
  border-bottom: none;
}}

ul.experiment-list, ul.commit-list {{
  list-style: none;
  margin: 0;
  padding: 0;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-elevated);
  overflow: hidden;
}}
ul.experiment-list li, ul.commit-list li {{
  padding: 0.6rem 0.85rem;
  border-bottom: 1px solid var(--border);
  font-size: 0.88rem;
}}
ul.experiment-list li:last-child, ul.commit-list li:last-child {{
  border-bottom: none;
}}
.exp-id {{
  font-weight: 600;
  color: var(--accent);
}}
.commit-subject {{
  display: inline-block;
}}
.commit-date {{
  float: right;
  color: var(--text-muted);
  font-size: 0.8rem;
}}

.gaps ul {{
  font-size: 0.85rem;
  color: var(--text-muted);
  padding-left: 1.2rem;
}}
.gaps li {{
  margin-bottom: 0.3rem;
}}

.empty-note {{
  color: var(--text-muted);
  font-style: italic;
  font-size: 0.9rem;
}}

footer.site-footer {{
  border-top: 1px solid var(--border);
  padding-top: 1.25rem;
  color: var(--text-muted);
  font-size: 0.82rem;
}}
footer.site-footer ul {{
  margin: 0.5rem 0 0;
  padding-left: 1.2rem;
}}

@media (max-width: 700px) {{
  .wrap {{ padding: 1.25rem 1rem 3rem; }}
  .component-grid {{ grid-template-columns: 1fr; }}
  .commit-date {{ float: none; display: block; }}
}}
</style>
</head>
<body>
<div class="wrap">

<header class="site-header">
  <h1>Versed Translate Lab</h1>
  <div class="meta">
    Generated {esc(generated_at)} &middot;
    <a href="{esc(data['repo_url'])}">{esc(data['repo_url'])}</a>
  </div>
</header>

<section id="components">
  <h2>Components</h2>
  <p class="section-note">C0 through C12, status and end state per the roadmap's STATUS ledger and component sections.</p>
  {render_component_cards(data['components'])}
</section>

<section id="decisions">
  <h2>Decisions waiting on Bilal</h2>
  <p class="section-note">From the roadmap's Decision queue.</p>
  {render_decisions_table(data['decisions'])}
</section>

<section id="experiments">
  <h2>Experiments</h2>
  <p class="section-note">From TRANSLATION_EXPERIMENTS.md.</p>
  {render_experiments_list(data['experiments'])}
</section>

<section id="commits">
  <h2>Recent commits</h2>
  <p class="section-note">Last {len(data['recent_commits'])} entries from git log.</p>
  {render_commits_list(data['recent_commits'])}
</section>

{render_gaps(data['gaps'])}

<footer class="site-footer">
  The roadmap and experiment docs are the source of truth, not this page. This dashboard is a
  generated snapshot — rebuild with <code>python3 tools/build_dashboard.py</code> (or
  <code>make -f tools/dashboard.mk dashboard</code>) whenever the docs change.
  <ul>
    Doc modification times:
    {doc_mtimes_html}
  </ul>
</footer>

</div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)

    data = build_status_data()

    json_path = DASHBOARD_DIR / "status.json"
    json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    html_path = DASHBOARD_DIR / "index.html"
    html_path.write_text(render_html(data), encoding="utf-8")

    print(f"Wrote {json_path}")
    print(f"Wrote {html_path}")
    print(f"Components parsed: {len(data['components'])}")
    print(f"Decisions parsed: {len(data['decisions'])}")
    print(f"Experiments parsed: {len(data['experiments'])}")
    print(f"Commits captured: {len(data['recent_commits'])}")
    if data["gaps"]:
        print(f"Parsing gaps noted: {len(data['gaps'])}")
        for g in data["gaps"]:
            print(f"  - {g}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
