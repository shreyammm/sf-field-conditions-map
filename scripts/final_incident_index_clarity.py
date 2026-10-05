#!/usr/bin/env python3
"""Make incident-index coverage/exclusions explicit in the final turf UI."""
from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = ROOT / "_site" / "index.html"
MANIFEST = ROOT / "_site" / "data-manifest.json"
html = SITE.read_text(encoding="utf-8")
manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
meta = manifest.get("precinct_incident_index") or {}
coverage = meta.get("weighted_category_coverage_365d_pct")
if coverage is None:
    raise SystemExit("incident index coverage metadata missing")

old = '<th>Reports /30d</th>'
if old not in html:
    raise SystemExit("incident ranking report-column anchor missing")
html = html.replace(old, '<th>Scored reports /30d</th>', 1)

old = 'Ambiguous, administrative and non-criminal categories are excluded rather than guessed.</div><input id="incidentRankFilter"'
if old not in html:
    raise SystemExit("incident ranking explanation anchor missing")
new = (
    'Ambiguous, administrative and non-criminal categories are excluded rather than guessed. '
    f'<strong>Current one-year coverage:</strong> {float(coverage):.1f}% of mapped initial reports '
    'inside precinct geography fall into explicitly weighted categories; the rest do not contribute to the index.'
    '</div><input id="incidentRankFilter"'
)
html = html.replace(old, new, 1)
SITE.write_text(html, encoding="utf-8")
manifest["incident_index_clarity"] = {
    "scored_report_column_explicit": True,
    "weighted_category_coverage_365d_pct_visible": float(coverage),
}
MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"incident index clarity applied: weighted-category one-year coverage={float(coverage):.1f}%")
