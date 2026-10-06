#!/usr/bin/env python3
"""Deployment-blocking audit for the 365-day precinct incident-frequency overlay."""
from __future__ import annotations

import json
import math
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
check(bool(m), "embedded payload missing")
data = json.loads(m.group(1)) if m else {}
precincts = ((data.get("precincts") or {}).get("features") or [])
hist = ((data.get("historical_incidents") or {}).get("features") or [])
freq = data.get("precinct_incident_frequency") or {}
meta = manifest.get("precinct_incident_frequency") or {}

check(400 <= len(precincts) <= 800, f"precinct count implausible: {len(precincts)}")
check(freq.get("dataset_id") == "wg3w-h783", "embedded frequency source id drift")
check(meta.get("dataset_id") == "wg3w-h783", "manifest frequency source id drift")
check(int(freq.get("window_days") or 0) == 365 and int(meta.get("window_days") or 0) == 365, "frequency window is not fixed at 365 days")

counts = []
bands = {i: 0 for i in range(1, 6)}
ranks = []
for f in precincts:
    p = f.get("properties") or {}
    try:
        n = int(p.get("incident_frequency_365"))
        b = int(p.get("incident_frequency_band"))
        r = int(p.get("incident_frequency_rank"))
    except Exception:
        issues.append("precinct missing/malformed frequency properties")
        continue
    check(n >= 0, "negative precinct frequency count")
    check(1 <= b <= 5, f"frequency band outside 1-5: {b}")
    check(1 <= r <= len(precincts), f"frequency rank outside precinct count: {r}")
    counts.append(n); bands[b] += 1; ranks.append(r)

check(len(counts) == len(precincts), "not every precinct has frequency metadata")
check(sum(counts) == int(meta.get("assigned_report_count") or -1), "assigned frequency total disagrees with precinct properties")
check(sum(bands.values()) == len(precincts), "frequency band totals do not cover all precincts")
for b, n in bands.items():
    check(70 <= n <= 135, f"quintile band {b} is unexpectedly imbalanced: {n}")

cuts = list(meta.get("band_cutpoints") or [])
check(len(cuts) == 4 and all(isinstance(x, int) for x in cuts), f"invalid quintile cuts: {cuts}")
check(all(cuts[i] < cuts[i+1] for i in range(3)), f"quintile cuts not strictly increasing: {cuts}")
if counts and len(cuts) == 4:
    xs = sorted(counts)
    expected = [xs[max(0, min(len(xs)-1, math.ceil(q*len(xs))-1))] for q in (0.2,0.4,0.6,0.8)]
    check(cuts == expected, f"stored cuts {cuts} do not match nearest-rank quintiles {expected}")

source_total = sum(int((f.get("properties") or {}).get("c365") or 0) for f in hist)
check(source_total == int(meta.get("source_mapped_report_count") or -1), "source mapped 365d total disagrees with historical payload")
check(int(meta.get("assigned_report_count") or 0) + int(meta.get("unassigned_report_count") or 0) + int(meta.get("ambiguous_report_count") or 0) == source_total, "assigned/unassigned/ambiguous accounting does not reconcile")
check(int(meta.get("ambiguous_report_count") or 0) <= 100, "too many boundary-ambiguous reports for a stable precinct view")

for token in (
    'id="dToggle" type="checkbox" checked',
    'id="freqFilter"',
    'id="ifl"',
    'Past-year incident report filter',
    'rolling 365 days',
    'highest 20%',
    'not a safety score',
    'Supervisor district boundaries',
    'thick colored boundary outline',
    'Recent law-enforcement dispatch activity',
    'id="iToggle" type="checkbox"',
):
    check(token in html, f"frequency/dispatch/district UI missing: {token}")
check('<g id="view"><g id="dl"></g><g id="ifl"></g><g id="tl"></g>' in html, "frequency highlight layer is not directly above district boundaries")
check('class="row legacyHistoryHidden"' in html, "legacy historical control row is not hidden")
check('class="histControls legacyHistoryHidden"' in html, "legacy historical window controls are not hidden")
check('legacyHistoryHidden{display:none!important}' in html, "legacy historical hiding CSS missing")
check('<div class="methoditem"><strong>Reported incident history</strong><br>' not in html, "obsolete historical-point methodology remains visible")
check('<div class="methoditem"><strong>Precinct reported-incident context index</strong><br>' not in html, "obsolete weighted-index methodology remains visible")
check('Reported incident frequency ↗' in html, "source directory was not relabeled for frequency view")
check('id="freqToggle"' not in html, "obsolete frequency overlay toggle remains visible")
check("S.freqBand=0" in html, "incident-frequency filter does not default to All/no highlight")
check("freqBand(p)!==b" in html, "incident-frequency filter does not highlight only the selected band")
check(".freqfill" in html and "pointer-events:none" in html, "frequency highlight may intercept map interactions")
check(".distfill{fill-opacity:0!important" in html, "district fill is not suppressed in final presentation")
check("e.style.stroke=DISTRICT_COLORS[n]" in html, "district outlines do not preserve categorical district colors")
check(len(re.findall(r"\bfetch\s*\(", html)) == 1, "frequency filter introduced a new runtime fetch")

scripts = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", html, re.S | re.I)
for i, script in enumerate(scripts):
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write(script)
        p = fh.name
    r = subprocess.run(["node", "--check", p], capture_output=True, text=True)
    pathlib.Path(p).unlink(missing_ok=True)
    check(r.returncode == 0, f"inline JS block {i} syntax failed: {r.stderr.strip()[:500]}")

if issues:
    print(f"PRECINCT FREQUENCY OVERLAY AUDIT FAIL: {len(issues)} issue(s)")
    for x in issues:
        print(" -", x)
    raise SystemExit(1)

print("PRECINCT FREQUENCY OVERLAY AUDIT PASS")
print(f"precincts={len(precincts)}; cuts={cuts}; bands={bands}")
print(f"365d reports: assigned={meta.get('assigned_report_count')}; unassigned={meta.get('unassigned_report_count')}; ambiguous={meta.get('ambiguous_report_count')}; source={source_total}")
print("presentation: incident frequency is an explicit single-band precinct highlight filter; Supervisor Districts are thick colored outlines; legacy historical circles/windows retired; recent dispatch retained")
