#!/usr/bin/env python3
"""Audit final SFPD reported-incident aggregate data and UI semantics."""
from __future__ import annotations

import collections
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
issues: list[str] = []


def check(ok, message):
    if not ok:
        issues.append(message)


match = re.search(r"window\.SF_FIELD_DATA=(\{.*?\});\s*</script>", html, re.S)
check(bool(match), "embedded payload missing")
data = json.loads(match.group(1)) if match else {}
meta = data.get("meta") or {}
features = ((data.get("incidents") or {}).get("features") or [])
windows = meta.get("incident_windows") or {}
expected_days = {30, 90, 180, 365}

check(meta.get("incident_dataset_id") == "wg3w-h783", "wrong incident dataset ID")
check(1_000 <= len(features) <= 250_000, f"incident aggregate feature count implausible: {len(features)}")
check(len(features) == int(meta.get("incident_aggregate_feature_count", -1)), "incident aggregate count/meta mismatch")
check(set(map(int, meta.get("incident_lookback_options") or [])) == expected_days, "incident lookback metadata is not 30/90/180/365")
check(set(map(int, windows.keys())) == expected_days, "incident window metadata missing a lookback")
check((manifest.get("incidents") or {}).get("dataset_id") == "wg3w-h783", "incident manifest missing/wrong dataset")
check("nearby intersections" in str(meta.get("incident_location_note") or "").lower(), "privacy-mapped intersection note missing")
check("risk score" in str(meta.get("incident_interpretation") or "").lower(), "non-risk-score interpretation missing")

categories_meta = set(map(str, meta.get("incident_categories") or []))
check(bool(categories_meta), "incident category metadata is empty")

by_window_all_memberships = collections.Counter()
by_window_category_groups = collections.Counter()
seen_categories = set()
for feature in features:
    props = feature.get("properties") or {}
    geom = feature.get("geometry") or {}
    check(geom.get("type") == "Point", "incident aggregate has non-point geometry")
    coords = geom.get("coordinates") or []
    point_ok = False
    if isinstance(coords, list) and len(coords) >= 2:
        try:
            lon, lat = float(coords[0]), float(coords[1])
            point_ok = (
                math.isfinite(lon)
                and math.isfinite(lat)
                and -122.60 <= lon <= -122.25
                and 37.65 <= lat <= 37.90
            )
        except (TypeError, ValueError):
            pass
    check(point_ok, f"incident aggregate point outside SF guardrail: {coords}")

    try:
        days = int(props.get("lookback_days"))
    except (TypeError, ValueError):
        days = -1
    check(days in expected_days, f"bad incident lookback: {props.get('lookback_days')}")
    category = str(props.get("category") or "")
    check(bool(category), "incident aggregate missing category")
    try:
        count = int(props.get("report_count"))
    except (TypeError, ValueError):
        count = -1
    check(count >= 1, f"bad incident report_count: {count}")

    check("incident_id" not in props, "aggregate layer unexpectedly embeds individual Incident IDs")
    check("latitude" not in props and "longitude" not in props, "aggregate properties duplicate raw coordinates")

    if days in expected_days and count >= 1:
        if category == "ALL":
            by_window_all_memberships[days] += count
        else:
            by_window_category_groups[(days, category)] += 1
            seen_categories.add(category)

check(seen_categories == categories_meta, "embedded category set differs from metadata")

for days in sorted(expected_days):
    w = windows.get(str(days)) or {}
    exact = int(w.get("exact_distinct_report_count") or 0)
    memberships = by_window_all_memberships[days]
    check(exact > 0, f"{days}d exact distinct report count missing")
    check(memberships >= exact, f"{days}d point memberships below exact report count")
    check(memberships <= exact * 1.05, f"{days}d point memberships inflate exact report count by >5%")
    check(int(w.get("all_point_report_memberships") or -1) == memberships, f"{days}d all-point membership/meta mismatch")
    check(int(w.get("all_point_group_count") or -1) > 0, f"{days}d ALL point-group count missing")
    cat_meta = w.get("category_report_memberships") or {}
    check(bool(cat_meta), f"{days}d category membership metadata missing")
    for category in categories_meta:
        # Categories may genuinely have no reports in the shortest window, so
        # require metadata/group agreement only when either side is present.
        has_group = (days, category) in by_window_category_groups
        has_meta = int(cat_meta.get(category) or 0) > 0
        check(has_group == has_meta, f"{days}d category group/meta presence mismatch: {category}")

# Product semantics: independent opt-in layer; selectable windows/categories;
# zoom-dependent point visualization; explicit source/privacy/statistical caveats.
check('<input id="iToggle" type="checkbox">' in html, "incident layer is not off by default")
for days in sorted(expected_days):
    check(f'data-days="{days}"' in html, f"missing {days}-day incident preset")
check('id="iCategory"' in html and 'All SFPD categories' in html, "incident category filter missing")
check('privacy-mapped to nearby intersections' in html, "incident privacy wording missing from controls")
check('not a neighborhood risk score' in html.lower(), "incident non-risk-score caveat missing")
check('count(distinct incident_id)' in html, "methodology does not document Incident-ID deduplication")
check("S.z<2.4" in html and "low_zoom_aggregate" in html and "privacy_mapped_point" in html, "zoom-dependent incident display missing")
check("DATA?.incidents" in html and "renderI()" in html, "incident payload not wired to UI")
check("$('iToggle').onchange" in html and "$('iCategory').onchange" in html and "$('iPills').onclick" in html, "incident controls not wired")
check("incident_categories" in html and "incident_windows" in html, "incident metadata not used by UI")
check("reported-incident marker" in html, "selected-feature prompt does not mention incident markers")
check("sourceLink(incidentSourceUrl()" in html, "incident details lack official source link")

render_match = re.search(r"function renderI\(\).*?function renderW\(\)", html, re.S)
check(bool(render_match), "incident render function missing")
if render_match:
    render_text = render_match.group(0).lower()
    check("precinct" not in render_text and "risk" not in render_text, "incident rendering appears to create precinct/risk scoring")

# Packaging integrity after the last product mutation.
ids = re.findall(r"\bid=[\"']([^\"']+)", html)
dups = [key for key, n in collections.Counter(ids).items() if n > 1]
check(not dups, f"duplicate HTML ids after incident UI patch: {dups[:10]}")
check(not re.search(r"\bfetch\s*\(", html), "runtime fetch introduced by incident UI")
check(not re.search(r"<script[^>]+src=", html, re.I), "external JS dependency introduced")
check(not re.search(r"<link[^>]+rel=[\"']?stylesheet", html, re.I), "external stylesheet introduced")

scripts = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", html, re.S | re.I)
for i, script in enumerate(scripts):
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as tmp:
        tmp.write(script)
        filename = tmp.name
    result = subprocess.run(["node", "--check", filename], capture_output=True, text=True)
    pathlib.Path(filename).unlink(missing_ok=True)
    check(result.returncode == 0, f"inline JS block {i} syntax error: {result.stderr.strip()}")

if issues:
    print(f"INCIDENT AGGREGATE AUDIT FAIL: {len(issues)} issue(s)")
    for issue in issues:
        print(" -", issue)
    raise SystemExit(1)

print("INCIDENT AGGREGATE AUDIT PASS")
print(f"embedded aggregate features: {len(features):,}; categories: {len(categories_meta)}")
for days in sorted(expected_days):
    w = windows[str(days)]
    print(
        f"{days}d: exact distinct reports={int(w['exact_distinct_report_count']):,}; "
        f"ALL source point groups={int(w['all_point_group_count']):,}; "
        f"point memberships={int(w['all_point_report_memberships']):,}"
    )
print("UI: opt-in; 30/90/180/365; SFPD category filter; low-zoom display aggregation / high-zoom privacy-mapped point clusters")
print("interpretation: reported incidents only; no precinct/neighborhood risk score")
