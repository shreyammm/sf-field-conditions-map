#!/usr/bin/env python3
"""Deployment-blocking audit for closure/access-screen clarity improvements."""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import tempfile
from collections import Counter

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
check(bool(m), "embedded payload missing")
data = json.loads(m.group(1)) if m else {}

# Closure line must no longer visually collide with selected precinct blue.
check(".cl{fill:none;stroke:#c11574" in html, "magenta closure styling missing")
check("stroke-dasharray:8 4" in html, "temporary closure dash pattern missing")
check("border-top:4px dashed #c11574" in html, "closure legend does not match map styling")
check("Magenta dashed lines are closures; solid blue lines are selected precinct boundaries." in html, "closure/boundary distinction missing from summary")

# Human summary must distinguish source records from grouped physical corridors.
for token in ("closureGroupsForSelection", "source location description", "official source line record", "What are these closures?"):
    check(token in html, f"closure summary clarity missing: {token}")
check("cg.groups.length" in html and "cg.records.length" in html, "closure corridor/source-record counts not both represented")

# The source often has repeated records for a named corridor. Verify the payload
# still contains the source rows; the UI grouping must not mutate/delete them.
closures = (data.get("closures") or {}).get("features") or []
check(bool(closures), "closure payload empty")
labels = Counter()
for f in closures:
    p = f.get("properties") or {}
    label = str(p.get("loc_desc") or "").strip().upper()
    if label:
        labels[label] += 1
check(any(n > 1 for n in labels.values()), "expected at least one repeated source location to exercise grouping")

# Parcel layer must be interpretable as a screen for advance access verification,
# while remaining explicit that unit count is not observed access or a skip list.
for token in (
    "Shared-entry access screen",
    "SF Planning parcel unit count · access is not confirmed",
    "Flag parcels with at least",
    "verify access before assigning",
    "access-verification screen, not a no-canvass list",
    "not calibrated probabilities of access failure",
    "Access-verification screen",
    "Screening cue only: verify building entry before assignment",
    "not a confirmed no-canvass list",
    "accesscallout",
):
    check(token in html, f"access-screen interpretation missing: {token}")
check("selectedHousingSummary" in html and "densitybreak" in html, "selected parcel breakdown missing")
check("20–49" in html and "50–99" in html and "100–199" in html and "200+" in html, "housing unit buckets missing")
check("ge50" in html and "ge100" in html, "selected-area large-parcel counts missing")
check("not confirmed access" in html, "source limitation on access missing")

hard = manifest.get("closure_housing_clarity") or {}
check(int(hard.get("version") or 0) == 2, "closure/access clarity manifest missing or wrong version")
interp = str(hard.get("housing_interpretation") or "")
for phrase in ("access verification", "size signal only", "not confirmed access", "not units per acre", "not a no-canvass designation"):
    check(phrase in interp, f"manifest access-screen interpretation incomplete: {phrase}")
check("source location description" in str(hard.get("closure_summary") or ""), "manifest closure grouping rule incomplete")

# Preserve network/security contract and valid JS.
check(len(re.findall(r"\bfetch\s*\(", html)) == 1, "unexpected runtime fetch count")
scripts = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", html, re.S | re.I)
for i, script in enumerate(scripts):
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write(script); path = fh.name
    r = subprocess.run(["node", "--check", path], capture_output=True, text=True)
    pathlib.Path(path).unlink(missing_ok=True)
    check(r.returncode == 0, f"inline JS block {i} syntax failed: {r.stderr.strip()[:500]}")

if issues:
    print(f"CLOSURE/ACCESS CLARITY AUDIT FAIL: {len(issues)} issue(s)")
    for issue in issues:
        print(" -", issue)
    raise SystemExit(1)

print("CLOSURE/ACCESS CLARITY AUDIT PASS")
print("closures: magenta dashed source geometry; summary separates corridors from source line records")
print("parcels: explicit access-verification screen; 50+/100+ counts; no claim of confirmed access or automatic skip")
