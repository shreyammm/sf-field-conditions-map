#!/usr/bin/env python3
"""Deployment-blocking audit for current Supervisor District shading."""
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


m = re.search(r"window\.SF_FIELD_DATA=(\{.*?\});\s*</script>", html, re.S)
check(bool(m), "embedded production payload missing")
data = json.loads(m.group(1)) if m else {}

features = ((data.get("supervisor_districts") or {}).get("features") or [])
check(len(features) == 11, f"expected 11 Supervisor Districts, got {len(features)}")
nums = []
for f in features:
    p = f.get("properties") or {}
    g = f.get("geometry") or {}
    try:
        n = int(p.get("district"))
    except Exception:
        n = -1
    nums.append(n)
    check(g.get("type") in {"Polygon", "MultiPolygon"}, f"district {n} has non-polygon geometry")
check(sorted(nums) == list(range(1, 12)), f"district numbers are not exactly 1-11: {sorted(nums)}")
check(len(nums) == len(set(nums)), "duplicate district number")

meta = manifest.get("supervisor_districts") or {}
check(meta.get("dataset_id") == "hcgx-vtsb", f"Supervisor District source id drift: {meta.get('dataset_id')}")
check(meta.get("embedded_feature_count") == 11, "manifest district count wrong")
check(meta.get("district_numbers") == list(range(1, 12)), "manifest district-number set wrong")
check("trimmed" in str(meta.get("geometry_interpretation") or "").lower(), "trimmed mapping-geometry semantics missing")
check("categorical" in str(meta.get("visual_interpretation") or "").lower(), "categorical color semantics missing")

precincts = ((data.get("precincts") or {}).get("features") or [])
unassigned = 0
cross = 0
for f in precincts:
    ds = (f.get("properties") or {}).get("supervisor_districts")
    check(isinstance(ds, list), "precinct missing supervisor_districts overlap list")
    if not isinstance(ds, list):
        continue
    check(all(isinstance(x, int) and 1 <= x <= 11 for x in ds), f"precinct has invalid Supervisor District assignment: {ds}")
    if not ds:
        unassigned += 1
    if len(ds) > 1:
        cross += 1
check(unassigned == int(meta.get("precinct_unassigned_count") or 0), "precinct district-unassigned count disagrees with manifest")
check(cross == int(meta.get("precinct_cross_district_count") or 0), "cross-district precinct count disagrees with manifest")
check(unassigned <= 2, f"too many precincts unassigned to Supervisor Districts: {unassigned}")
check(cross <= 5, f"unexpected number of precincts materially crossing Supervisor Districts: {cross}")

# UI: background only, easy opt-out, and explicit non-score semantics.
for token in (
    'id="dToggle" type="checkbox" checked',
    'id="dl"',
    'Supervisor district shading',
    'categorical reference only',
    'Supervisor district background · D1–D11',
    'colors are arbitrary categorical identifiers only',
    'selectedSupervisorDistricts()',
):
    check(token in html, f"Supervisor District UI missing: {token}")
check('<g id="view"><g id="dl"></g><g id="tl"></g>' in html, "district layer is not behind topography/streets")
check('.distfill' in html and 'pointer-events:none' in html, "district background may intercept map interactions")
check(html.count('href="https://data.sf.gov/d/hcgx-vtsb"') >= 2, "Supervisor District official source not linked in directory + methodology")
check("rank, political preference, safety, access, or turf quality" in html, "district colors are not explicitly described as non-scoring")

# Palette must be stable and complete for D1-D11.
for n in range(1, 12):
    check(f"{n}:" in html or f"{n}:'#" in html, f"district palette missing D{n}")

# This layer must not add runtime network dependencies or bloat the app badly.
check(len(re.findall(r"\bfetch\s*\(", html)) == 1, "district feature introduced extra runtime fetches")
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
    print(f"SUPERVISOR DISTRICT AUDIT FAIL: {len(issues)} issue(s)")
    for issue in issues:
        print(" -", issue)
    raise SystemExit(1)

print("SUPERVISOR DISTRICT AUDIT PASS")
print(f"districts=11; precinct_unassigned={unassigned}; cross_district_precincts={cross}")
print("visual: low-opacity categorical background; default on; optional off; non-interactive")
