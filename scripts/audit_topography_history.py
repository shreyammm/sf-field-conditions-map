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

# Actual topography: the browser receives two compact SVG paths projected from
# a lightly simplified subset of the official contour-line geometry. This keeps
# actual terrain contours without embedding tens of MB of redundant GeoJSON.
topo = data.get("topography_paths") or {}
minor = str(topo.get("minor") or "")
major = str(topo.get("major") or "")
check(bool(minor) and bool(major), "compact topography paths missing")
check(minor.startswith("M") and major.startswith("M"), "topography SVG paths malformed")
path_vertices = minor.count("M") + minor.count("L") + major.count("M") + major.count("L")
mt = manifest.get("topography_display") or {}
check(mt.get("dataset_id") == "rnbg-2qxw", "topography source id drift")
check(10_000 <= int(mt.get("source_feature_count") or 0) <= 20_000, "topography source feature count implausible")
check(1_500 <= int(mt.get("display_source_feature_count") or 0) <= 5_000, "25-ft contour source-subset count implausible")
check(mt.get("source_interval_ft") == 5 and mt.get("display_interval_ft") == 25 and mt.get("major_interval_ft") == 100, "topography interval metadata wrong")
check(0 < float(mt.get("display_simplification_degrees") or 0) <= 0.0001, "topography display simplification missing/too coarse")
check(int(mt.get("display_vertex_count") or 0) == path_vertices, "topography path vertex count disagrees with manifest")
check(0 < path_vertices < int(mt.get("source_vertex_count_selected") or 0), "topography simplification did not reduce selected source vertices")
actual_path_bytes = len(minor.encode()) + len(major.encode())
check(actual_path_bytes == int(mt.get("path_bytes") or -1), "topography path byte count disagrees with manifest")
check(actual_path_bytes < 7_000_000, f"topography paths exceed 7 MB: {actual_path_bytes:,}")
check("No synthetic elevation surface is interpolated" in html, "topography interpolation caveat missing")
check("lightly simplifies the line geometry only for rendering performance" in html, "topography display-simplification disclosure missing")
check('id="topoToggle" type="checkbox" checked' in html, "topography is not available/on by default")
check('id="hToggle" type="checkbox"' in html and 'id="hToggle" type="checkbox" checked' not in html, "derived street steepness should be optional/off by default")
check("Topographic contour · 25 ft" in html and "Index contour · 100 ft" in html, "topography legend missing")
check("DATA.topography_paths" in html, "runtime is not rendering compact topography paths")

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
check('id="histToggle" type="checkbox"' in html and 'id="histToggle" type="checkbox" checked' not in html, "historical layer should remain opt-in")
check('data-hdays="90">3 months</button>' in html and 'data-hdays="90">3 months</button>' in html, "3-month historical option missing")

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

# Preserve app packaging contract: this feature adds no browser requests and the
# final static page stays reasonably sized for mobile field use.
check(len(re.findall(r"\bfetch\s*\(", html)) == 1, "topography/history introduced an extra runtime fetch")
final_bytes = len(html.encode("utf-8"))
check(final_bytes < 32_000_000, f"final HTML exceeds 32 MB: {final_bytes:,}")

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
print(f"topography: {mt.get('display_source_feature_count')} official 25-ft source contours -> {path_vertices:,} compact display vertices / {actual_path_bytes:,} bytes")
print(f"historical points: {len(hist)}; rolling totals: {sums}")
print(f"final HTML: {final_bytes:,} bytes")
for x in warnings:
    print("warning:", x)
