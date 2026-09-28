#!/usr/bin/env python3
"""Audit the final reported-incident artifact and UI semantics."""
from __future__ import annotations

import collections
import datetime as dt
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
issues: list[str] = []


def check(ok, message):
    if not ok:
        issues.append(message)


m = re.search(r"window\.SF_FIELD_DATA=(\{.*?\});\s*</script>", html, re.S)
check(bool(m), "embedded payload missing")
data = json.loads(m.group(1)) if m else {}
meta = data.get("meta") or {}
features = ((data.get("incidents") or {}).get("features") or [])

check(meta.get("incident_dataset_id") == "wg3w-h783", "wrong incident dataset ID")
check(3_000 <= len(features) <= 200_000, f"incident display count implausible: {len(features)}")
check(len(features) == int(meta.get("incident_display_report_count", -1)), "incident count/meta mismatch")
check((manifest.get("incidents") or {}).get("dataset_id") == "wg3w-h783", "incident manifest missing/wrong")
check("nearby intersections" in str(meta.get("incident_location_note") or "").lower(), "privacy-mapped intersection note missing from meta")
check("risk score" in str(meta.get("incident_interpretation") or "").lower(), "non-risk-score interpretation missing from meta")

try:
    a = dt.date.fromisoformat(str(meta.get("incident_window_start")))
    b = dt.date.fromisoformat(str(meta.get("incident_window_end")))
    check((b - a).days + 1 >= 365, "embedded incident buffer is shorter than one year")
except ValueError:
    issues.append("invalid incident embedded window dates")

ids = []
category_counts = collections.Counter()
source_rows_represented = 0
point_variant_reports = 0
multi_category_reports = 0
for f in features:
    p = f.get("properties") or {}
    g = f.get("geometry") or {}
    check(g.get("type") == "Point", "incident feature is not a point")
    c = g.get("coordinates") or []
    ok_point = False
    if isinstance(c, list) and len(c) >= 2:
        try:
            lon, lat = float(c[0]), float(c[1])
            ok_point = -122.60 <= lon <= -122.25 and 37.65 <= lat <= 37.90
        except (TypeError, ValueError):
            pass
    check(ok_point, f"incident point outside SF guardrail: {c}")

    incident_id = str(p.get("incident_id") or "")
    check(bool(incident_id), "incident feature missing incident_id")
    ids.append(incident_id)
    when = str(p.get("incident_datetime") or "")
    check(bool(re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$", when)), f"bad incident datetime: {when}")

    cats = p.get("categories")
    check(isinstance(cats, list) and bool(cats), f"incident categories missing: {incident_id}")
    if isinstance(cats, list):
        check(len(cats) == len(set(cats)), f"duplicate category on incident: {incident_id}")
        for cat in cats:
            category_counts[str(cat)] += 1
        if len(cats) > 1:
            multi_category_reports += 1

    rows = p.get("source_row_count")
    check(isinstance(rows, int) and rows >= 1, f"bad source_row_count: {incident_id} / {rows}")
    if isinstance(rows, int) and rows >= 1:
        source_rows_represented += rows
    variants = p.get("source_point_variant_count")
    check(isinstance(variants, int) and variants >= 1, f"bad source_point_variant_count: {incident_id} / {variants}")
    if isinstance(variants, int) and variants > 1:
        point_variant_reports += 1

    # Geometry is sufficient; avoid duplicating coordinates or case numbers in
    # properties when the operational UI does not need them.
    check("latitude" not in p and "longitude" not in p, f"redundant raw coordinates embedded in props: {incident_id}")
    check("incident_number" not in p and "cad_number" not in p, f"unneeded case identifier embedded: {incident_id}")

check(len(ids) == len(set(ids)), "incident IDs are not unique after deduplication")
check(source_rows_represented == int(meta.get("incident_source_rows_represented", -1)), "represented source-row count/meta mismatch")
check(dict(category_counts) == meta.get("incident_category_report_memberships"), "incident category membership counts/meta mismatch")
check(multi_category_reports == int(meta.get("incident_multi_category_report_count", -1)), "multi-category count/meta mismatch")
check(point_variant_reports == int(meta.get("incident_point_variant_report_count", -1)), "point-variant count/meta mismatch")

# Product semantics: opt-in, user-selectable lookback, no precinct risk shading,
# explicit privacy caveat, and low/high zoom rendering behavior.
check('<input id="iToggle" type="checkbox">' in html, "incident layer is not off by default")
for days in (30, 90, 180, 365):
    check(f'data-days="{days}"' in html, f"missing {days}-day incident preset")
check('id="iCategory"' in html and 'All SFPD categories' in html, "incident category filter missing")
check('privacy-mapped to nearby intersections' in html, "incident privacy wording missing from controls")
check('not a neighborhood risk score' in html.lower(), "incident non-risk-score caveat missing")
check("S.z<2.4" in html and "low_zoom_aggregate" in html and "privacy_mapped_point" in html, "zoom-dependent incident rendering missing")
check("DATA?.incidents" in html and "renderI()" in html, "incident payload not wired to UI")
check("$('iToggle').onchange" in html and "$('iCategory').onchange" in html and "$('iPills').onclick" in html, "incident controls not wired")
check("incident_category_report_memberships" in html, "category options are not sourced from embedded metadata")
check("reported-incident marker" in html, "selected-feature prompt does not mention incident markers")
check("precinct" not in re.search(r"function renderI\(\).*?function renderW\(\)", html, re.S).group(0).lower() if re.search(r"function renderI\(\).*?function renderW\(\)", html, re.S) else False, "incident rendering appears to aggregate to precincts")

# Final inline-JS syntax check catches patching errors before deployment.
scripts = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", html, re.S | re.I)
for i, script in enumerate(scripts):
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as tmp:
        tmp.write(script)
        name = tmp.name
    result = subprocess.run(["node", "--check", name], capture_output=True, text=True)
    pathlib.Path(name).unlink(missing_ok=True)
    check(result.returncode == 0, f"inline JS block {i} syntax error: {result.stderr.strip()}")

if issues:
    print(f"INCIDENT AUDIT FAIL: {len(issues)} issue(s)")
    for issue in issues:
        print(" -", issue)
    raise SystemExit(1)

print("INCIDENT AUDIT PASS")
print(f"displayed reports: {len(features):,}; source rows represented: {source_rows_represented:,}")
print(f"incident dates: {meta.get('incident_min_date')} through {meta.get('incident_max_date')}")
print(f"categories: {len(category_counts)}; multi-category reports: {multi_category_reports:,}")
print("UI: opt-in; 30/90/180/365-day windows; category filter; low-zoom aggregation / high-zoom privacy-mapped points")
print("interpretation: reported incidents only; no precinct/neighborhood risk score")
