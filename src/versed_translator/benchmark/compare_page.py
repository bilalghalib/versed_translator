"""Build a side-by-side HTML compare page from reassembled runs.

Writes only to the caller-chosen path (off-repo). Includes source Arabic and
PD English from the eval file plus model outputs — do not commit the HTML
into this public repo.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

SAMPLE_14 = (
    "baladhuri_hitti:s42-a028_030-e048_052",
    "baladhuri_hitti:s60-a034_036-e074_080",
    "baladhuri_hitti:s66-a001_008-e001_006",
    "blunt_odes:zuhayr-v016_044",
    "hariri_assemblies:m46-a048_059",
    "ibn_khallikan_deslane:v2-bio-0362-i0365",
    "miskawayh_eclipse:ah325-a000_005",
    "blunt_odes:harith-v018_048",
    "blunt_odes:labid-v052_083",
    "baladhuri_hitti:s45-a002_004-e001_004",
    "ibn_khallikan_deslane:v2-bio-0442-i0445",
    "blunt_odes:antara-v033_048",
    "miskawayh_eclipse:ah318-a037_040",
    "hariri_assemblies:m20-a000_006",
)


def _load_jsonl(path: Path) -> dict[str, dict]:
    by_id: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        by_id[row["id"] if "id" in row else row["item_id"]] = row
    return by_id


def render_compare_html(
    *,
    items_path: Path,
    systems: list[tuple[str, Path]],
    item_ids: tuple[str, ...] = SAMPLE_14,
    title: str,
    blurb: str,
) -> str:
    items = _load_jsonl(items_path)
    loaded = [(label, _load_jsonl(path)) for label, path in systems]
    cards = []
    for item_id in item_ids:
        item = items.get(item_id, {})
        arabic = html.escape(item.get("arabic") or "")
        ref = html.escape(item.get("reference_english") or "")
        source = html.escape(item.get("source") or item_id.split(":")[0])
        cols = []
        for label, rows in loaded:
            row = rows.get(item_id, {})
            text = row.get("translation") or row.get("english") or ""
            err = row.get("error")
            body = html.escape(text) if text else f"<em>{html.escape(err or 'missing')}</em>"
            cols.append(
                f'<div class="col"><h4>{html.escape(label)}</h4>'
                f'<div class="txt" dir="auto">{body}</div></div>'
            )
        cards.append(
            f'<article class="pair" data-src="{source}">'
            f'<header><span class="where">{source.replace("_", " ")}</span>'
            f'<span class="id">{html.escape(item_id)}</span></header>'
            f'<div class="grid">'
            f'<div class="col ar"><h4>Arabic (source of truth)</h4>'
            f'<div class="txt" dir="rtl" lang="ar">{arabic}</div></div>'
            f'<div class="col"><h4>Public-domain English (abridges; not gold)</h4>'
            f'<div class="txt">{ref}</div></div>'
            f'{"".join(cols)}</div></article>'
        )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root {{
  --bg: #faf9f7; --bg-elevated: #fff; --text: #1f1d1a; --text-muted: #6b665f;
  --border: #e4e0da; --accent: #3d5a80;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; background: var(--bg); color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  line-height: 1.5;
}}
.wrap {{ max-width: 1680px; margin: 0 auto; padding: 2rem 1.25rem 4rem; }}
h1 {{ margin: 0 0 .35rem; font-size: 1.45rem; }}
.sub {{ color: var(--text-muted); font-size: .92rem; margin: 0 0 1.25rem; }}
.pair {{
  background: var(--bg-elevated); border: 1px solid var(--border);
  border-radius: 8px; padding: 1rem; margin: 1.25rem 0;
}}
.pair header {{ display: flex; gap: .75rem; flex-wrap: wrap; margin-bottom: .6rem; }}
.id {{ font-family: ui-monospace, monospace; font-size: .8rem; color: var(--text-muted); }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: .75rem; }}
.col h4 {{ margin: 0 0 .35rem; font-size: .8rem; color: var(--text-muted); font-weight: 600; }}
.txt {{ white-space: pre-wrap; font-size: .92rem; max-height: 28rem; overflow: auto; }}
.ar .txt {{ font-size: 1.05rem; }}
</style>
</head>
<body>
<div class="wrap">
<h1>{html.escape(title)}</h1>
<p class="sub">{html.escape(blurb)}</p>
<p class="sub">Arabic is the source of truth. PD English abridges. {len(item_ids)} passages.</p>
{"".join(cards)}
</div>
</body>
</html>
"""


def write_compare_html(
    out_path: Path,
    *,
    items_path: Path,
    systems: list[tuple[str, Path]],
    item_ids: tuple[str, ...] = SAMPLE_14,
    title: str,
    blurb: str,
) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        render_compare_html(
            items_path=items_path,
            systems=systems,
            item_ids=item_ids,
            title=title,
            blurb=blurb,
        ),
        encoding="utf-8",
    )
    return out_path
