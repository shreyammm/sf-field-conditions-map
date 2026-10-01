#!/usr/bin/env python3
"""Deployment-blocking audit for actual topography and historical incidents."""
from __future__ import annotations

import datetime as dt
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
warnings = []


def check(ok, msg):
    if not ok:
        issues.append(msg)


def sf_point(c):
    try:
        lon, lat = float(c[0]), float(c[1])
    except Exception:
        return False
    return math.isfinite(lon) and math.isfinite(lat) and -122.60 <= lon <= -122.25 and 37.65 <= lat <= 37.90


m = re.search(r"window\.SF_FIELD_DATA=(\{.*?\});\s*</script>", html, re.S)
check(bool(m), "embedded payload missing")
data = json.loads(m.group(1)) if m else {}

# Actual topography: official contour geometry, not another street-color proxy.
topo = ((data.get("topography") or {}).get("features") or [])
check(1_500 <= len(topo) <= 5_000, f"topography feature count implausible: {len(topo)}")
for f in topo:
    p = f.get("properties") or {}
    g = f.get("geometry") or {}
    check(g.get("type") in {"LineString", "MultiLineString"}, "topography includes non-line geometry")
    z = p.get("elevation_ft")
    check(isinstance(z, (int, float)) and abs(float(z) / 25 - round(float(z) / 25)) < 1e-6, f"display contour is not 25-ft interval: {z}")
    check(bool(p.get("major")) == (int(z) % 100 == 0), f"100-ft index-contour flag mismatch: {z}")
mt = manifest.get("topography_display") or {}
check(mt.get("dataset_id") == "rnbg-2qxw", "topography source id drift")
check(mt.get("source_interval_ft") == 5 and mt.get("display_interval_ft") == 25 and mt.get("major_interval_ft") == 100, "topography interval metadata wrong")
check("No synthetic elevation surface is interpolated" in html, "topography interpolation caveat missing")
check('id="topoToggle" type="checkbox" checked' in html, "topography is not available/on by default")
check('id="hToggle" type="checkbox"' in html and 'id="hToggle" type="checkbox" checked' not in html, "derived street steepness should be optional/off by default")
check("Topographic contour · 25 ft" in html and "Index contour · 100 ft" in html, "topography legend missing")

# Historical incident context: one unique incident report per incident_id, then
# aggregated only at DataSF's privacy-mapped public intersection points.
hist = ((data.get("historical_incidents") or {}).get("features") or [])
check(500 <= len(hist) <= 10_000, f"historical incident point count implausible: {len(hist)}")
precinct_ids = {str((f.get("properties") or {}).get("prec_2022") or (f.get("properties") or {}).get("precinct") or (f.get("properties") or {}).get("id") or "") for f in ((data.get("precincts") or {}).get("features") or [])}
coord_keys = set()
sums = {30: 0, 90: 0, 180: 0, 365: 0}
for f in hist:
    p = f.get("properties") or {}
    g = f.get("geometry") or {}
    c = g.get("coordinates") or []
    check(g.get("type") == "Point" and sf_point(c), "historical incident has invalid public mapped point")
    if len(c) >= 2:
        key = (round(float(c[0]), 5), round(float(c[1]), 5))
        check(key not in coord_keys, f"duplicate historical mapped coordinate: {key}")
        coord_keys.add(key)
    counts = [int(p.get(f"c{d}") or 0) for d in (30, 90, 180, 365)]
    check(0 <= counts[0] <= counts[1] <= counts[2] <= counts[3], f"non-monotonic historical counts at point: {counts}")
    for d, n in zip((30, 90, 180, 365), counts):
        sums[d] += n
    fps = p.get("focus_precincts") or []
    check(isinstance(fps, list) and all(str(x) in precinct_ids for x in fps), "historical point has invalid precinct assignment")

mh = manifest.get("historical_incidents") or {}
check(mh.get("dataset_id") == "wg3w-h783", "historical incident source id drift")
check("one count per incident_id" in str(mh.get("dedupe_rule") or ""), "historical dedupe rule missing")
check(mh.get("report_filter") == "Initial, Vehicle Initial, Coplogic Initial", "historical report-type filter drift")
check({str(k): v for k, v in sums.items()} == (mh.get("window_unique_incident_counts") or {}), "historical window totals disagree with manifest")
check(int(mh.get("unique_incident_ids") or 0) >= sums[365], "unique incident total smaller than mapped 365d count")
check("privacy-mapped" in str(mh.get("location_interpretation") or "").lower(), "historical location privacy semantics missing")
check("not convictions" in str(mh.get("count_interpretation") or "").lower(), "historical count caveat missing")

# UI must expose the four requested windows but avoid converting report volume
# into a made-up crime-severity or safety score.
for token in ('data-hdays="30"', 'data-hdays="90"', 'data-hdays="180"', 'data-hdays="365"', "Reported incident history", "Fixed-size circles", "report volume, not severity"):
    check(token in html, f"historical incident UI missing: {token}")
check("c30" in html and "c90" in html and "c180" in html and "c365" in html, "historical runtime does not use all four windows")
check("color encodes average unique reports per 30 days" in html, "historical color semantics missing from methodology")
check("not every report establishes a crime" in html.lower(), "historical report-vs-crime caveat missing")
check(html.count('href="https://data.sf.gov/d/wg3w-h783"') >= 2, "historical source is not linked in both directory/methodology")

# Daily source is allowed modest lag, but a very stale historical snapshot should
# block deployment rather than silently look current.
updated = mh.get("source_rows_updated_at")
if updated:
    try:
        u = dt.datetime.fromisoformat(str(updated).replace("Z", "+00:00"))
        now = dt.datetime.now(dt.timezone.utc)
        age = (now - u).total_seconds() / 86400
        if age > 7:
            issues.append(f"historical incident source metadata is >7 days stale: {age:.1f}d")
        elif age > 2:
            warnings.append(f"historical incident source metadata is {age:.1f}d old")
    except Exception:
        issues.append("historical incident source_rows_updated_at is malformed")
else:
    warnings.append("historical incident source metadata did not provide rowsUpdatedAt")

# Preserve app packaging contract: this feature adds no browser requests.
check(len(re.findall(r"\bfetch\s*\(", html)) == 1, "topography/history introduced an extra runtime fetch")
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
    print(f"TOPOGRAPHY/HISTORY AUDIT FAIL: {len(issues)} issue(s)")
    for x in issues:
        print(" -", x)
    for x in warnings:
        print(" warning:", x)
    raise SystemExit(1)

print("TOPOGRAPHY/HISTORY AUDIT PASS")
print(f"topography: {len(topo)} official 25-ft display contours; 100-ft index contours emphasized")
print(f"historical points: {len(hist)}; rolling totals: {sums}")
for x in warnings:
    print("warning:", x)
