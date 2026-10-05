#!/usr/bin/env python3
"""Ensure all production/context sources have final provenance in manifest/UI."""
from __future__ import annotations

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = ROOT / "_site" / "index.html"
MANIFEST = ROOT / "_site" / "data-manifest.json"
html = SITE.read_text(encoding="utf-8")
manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
issues = []


def check(ok, msg):
    if not ok:
        issues.append(msg)


expected = {
    "streets": "3psu-pn9h",
    "precincts": "d6x4-hefw",
    "multifamily": "c5ge-t6pj",
    "hills": "rnbg-2qxw",
    "closures": "8x25-yybr",
    "surface_permits": "bpc9-7sus",
    "live_calls": "gnap-fj3t",
    "historical_incidents": "wg3w-h783",
    "precinct_incident_index": "wg3w-h783",
    "supervisor_districts": "hcgx-vtsb",
}
for key, did in expected.items():
    section = manifest.get(key) or {}
    check(section.get("dataset_id") == did, f"{key} manifest dataset id drift: {section.get('dataset_id')} != {did}")
    check(f"https://data.sf.gov/d/{did}" in html, f"{key} official DataSF source link missing from final UI")

for did in sorted(set(expected.values())):
    check(html.count(f"https://data.sf.gov/d/{did}") >= 1, f"official source {did} absent from final artifact")

check("Official data sources" in html, "source directory missing")
check(len(re.findall(r"\bfetch\s*\(", html)) == 1, "unexpected runtime data dependency introduced")

if issues:
    print(f"SOURCE REGISTRY V2 AUDIT FAIL: {len(issues)} issue(s)")
    for x in issues:
        print(" -", x)
    raise SystemExit(1)
print("SOURCE REGISTRY V2 AUDIT PASS")
print("registered source sections:", ", ".join(sorted(expected)))
