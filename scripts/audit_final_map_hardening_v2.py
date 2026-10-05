#!/usr/bin/env python3
"""Deployment-blocking audit for precinct labels and final performance hardening."""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import tempfile

from shapely.geometry import Point, shape

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = ROOT / "_site" / "index.html"
MANIFEST = ROOT / "_site" / "data-manifest.json"
html = SITE.read_text(encoding="utf-8")
manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
issues: list[str] = []


def check(ok, msg):
    if not ok:
        issues.append(msg)


m = re.search(r"window\.SF_FIELD_DATA=(\{.*?\});\s*</script>", html, re.S)
check(bool(m), "embedded payload missing")
data = json.loads(m.group(1)) if m else {}
precincts = ((data.get("precincts") or {}).get("features") or [])
label_points = data.get("precinct_label_points") or {}
check(len(label_points) == len(precincts), "precinct label-point count does not equal precinct feature count")
for f in precincts:
    p = f.get("properties") or {}
    pid = str(p.get("prec_2022") or p.get("precinct") or p.get("id") or "")
    c = label_points.get(pid)
    check(isinstance(c, list) and len(c) >= 2, f"precinct {pid} missing label point")
    if isinstance(c, list) and len(c) >= 2:
        try:
            check(shape(f.get("geometry")).covers(Point(float(c[0]), float(c[1]))), f"precinct {pid} label point is outside official polygon")
        except Exception:
            issues.append(f"precinct {pid} label point malformed")

for token in (
    'id="precLabelToggle" type="checkbox"',
    'id="pnl"',
    '.preclabel{',
    "representative point inside each official polygon",
    "Labels are automatically de-cluttered",
):
    check(token in html, f"precinct label UI/runtime missing: {token}")
check('id="precLabelToggle" type="checkbox" checked' not in html, "precinct labels should remain optional/off by default")
check(".preclabel" in html and "pointer-events:none" in html, "precinct labels may intercept map interactions")

palette = ['#4E79A7','#F28E2B','#E15759','#76B7B2','#59A14F','#EDC948','#B07AA1','#FF9DA7','#9C755F','#7F8C8D','#17BECF']
for c in palette:
    check(c in html, f"strong Supervisor District palette missing {c}")
check("fill-opacity:.19" in html and "fill-opacity:.27" in html, "district opacity strengthening missing")
check("#8dd3c7" not in html and "#ffffb3" not in html, "old low-contrast district palette remains in final artifact")

check("document.querySelectorAll('.pill')" not in html, "global .pill selector bug remains")
check("document.querySelectorAll('#pills .pill')" in html, "parcel threshold selector is not scoped")

for token in (
    "const PARCEL_DETAIL_ZOOM=1.75",
    "zoom/select to draw",
    "HIST_RENDER_SIG",
    "wheelTimer",
    "},85);",
    "renderFocusAware=function(){renderS();renderP();renderM();renderW();renderC();renderI()}",
):
    check(token in html, f"performance hardening missing: {token}")
check("At whole-city zoom, individual parcel shapes are deferred for speed" in html, "parcel defer behavior not explained to user")
check('id="incidentRankDetails" class="incidentRank"' in html, "incident ranking is not lazy/collapsed")

hard = manifest.get("final_map_hardening_v2") or {}
check(hard.get("version") == 2, "final hardening manifest version missing")
check("85 ms" in str(hard.get("wheel_rendering") or ""), "wheel debounce not recorded in manifest")
check("#pills" in str(hard.get("pill_scope_bugfix") or ""), "pill bugfix not recorded in manifest")
check("zoom 1.75" in str(hard.get("parcel_initial_rendering") or ""), "parcel detail zoom not recorded in manifest")

check(len(re.findall(r"\bfetch\s*\(", html)) == 1, "final hardening introduced extra runtime fetches")
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
    print(f"FINAL MAP HARDENING V2 AUDIT FAIL: {len(issues)} issue(s)")
    for x in issues:
        print(" -", x)
    raise SystemExit(1)
print("FINAL MAP HARDENING V2 AUDIT PASS")
print(f"precinct labels={len(label_points)}; final HTML={len(html.encode('utf-8')):,} bytes")
print("performance: whole-city parcels deferred; wheel rendering debounced; duplicate history/focus work reduced")
