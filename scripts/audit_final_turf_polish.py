#!/usr/bin/env python3
"""Deployment-blocking audit for final turf-cutting clarity/performance polish."""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = ROOT / "_site" / "index.html"
MANIFEST = ROOT / "_site" / "data-manifest.json"
html = SITE.read_text(encoding="utf-8")
manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
issues = []


def check(ok, msg):
    if not ok:
        issues.append(msg)


check('id="pSearch"' in html and 'aria-label="Precinct IDs"' in html, "precinct search lacks accessible name")
check("closer lines = steeper terrain" in html, "plain-language topography interpretation missing")

parcel_meta = manifest.get("multifamily") or {}
parcel_date = str(parcel_meta.get("data_as_of") or "")[:10]
check(bool(parcel_date), "parcel source date missing from manifest")
if parcel_date:
    y, m, d = parcel_date.split('-')
    months = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    expected = f"snapshot {months[int(m)]} {int(d)}, {int(y)}"
    check(expected in html, f"parcel snapshot date is not visible in access-screen control: {expected}")
check("access is not confirmed" in html, "parcel access caveat was lost")

# Historical citywide rendering guard: preserve exact intersection semantics by
# deferring points instead of aggregating or resizing them.
for token in (
    "HIST_DETAIL_ZOOM=2.2",
    "!PFOCUS.size&&S.z<HIST_DETAIL_ZOOM",
    "Zoom in or select precincts to draw individual reported-incident intersections.",
    "hil.replaceChildren()",
    "updateHistorySummary()",
):
    check(token in html, f"historical low-zoom guard missing: {token}")
check("heatmap" not in html.lower(), "historical UI unexpectedly introduces heatmap semantics")

polish = manifest.get("final_turf_polish") or {}
check(int(polish.get("version") or 0) == 1, "final turf polish manifest missing/wrong version")
check(polish.get("parcel_snapshot_visible_in_controls") is True, "manifest does not record parcel snapshot visibility")
check(polish.get("precinct_search_accessible_name") is True, "manifest does not record precinct search accessibility")
check("zoom < 2.2" in str(polish.get("historical_point_rendering") or ""), "manifest does not document historical draw threshold")

# Preserve packaging/performance/security guarantees.
check(len(re.findall(r"\bfetch\s*\(", html)) == 1, "final polish introduced an unexpected runtime fetch")
check(len(html.encode("utf-8")) < 32_000_000, f"final HTML exceeds 32 MB: {len(html.encode('utf-8')):,}")
scripts = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", html, re.S | re.I)
for i, script in enumerate(scripts):
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write(script)
        path = fh.name
    r = subprocess.run(["node", "--check", path], capture_output=True, text=True)
    pathlib.Path(path).unlink(missing_ok=True)
    check(r.returncode == 0, f"inline JS block {i} syntax failed: {r.stderr.strip()[:500]}")

if issues:
    print(f"FINAL TURF POLISH AUDIT FAIL: {len(issues)} issue(s)")
    for issue in issues:
        print(" -", issue)
    raise SystemExit(1)

print("FINAL TURF POLISH AUDIT PASS")
print("clarity: parcel snapshot visible; topography explained; precinct search named")
print("performance: historical point SVGs deferred at citywide low zoom without aggregating source meaning")
