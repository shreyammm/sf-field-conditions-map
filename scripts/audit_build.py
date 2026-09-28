#!/usr/bin/env python3
"""Fail deployment if the finished map drifts from documented layer semantics.

The individual builders validate their inputs. This second, independent pass
reads the final HTML and manifest after every UI patch and verifies the artifact
that a user will actually receive.
"""
from __future__ import annotations

import collections
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
match = re.search(r"window\.SF_FIELD_DATA=(\{.*?\});\s*</script>", html, re.S)
if not match:
    raise SystemExit("AUDIT FAIL: embedded data payload missing")
data = json.loads(match.group(1))
meta = data.get("meta", {})
issues: list[str] = []


def check(ok, message):
    if not ok:
        issues.append(message)


def props(feature):
    return feature.get("properties") or {}


def sf_point(coords):
    if not isinstance(coords, list) or len(coords) < 2:
        return False
    try:
        lon, lat = float(coords[0]), float(coords[1])
    except (TypeError, ValueError):
        return False
    return math.isfinite(lon) and math.isfinite(lat) and -122.60 <= lon <= -122.25 and 37.65 <= lat <= 37.90


# ---------- final-page architecture / UI ----------
ids = re.findall(r"\bid=[\"']([^\"']+)", html)
dup_ids = [k for k, n in collections.Counter(ids).items() if n > 1]
check(not dup_ids, f"duplicate HTML ids: {dup_ids[:10]}")
check(not re.search(r"<script[^>]+src=", html, re.I), "external script dependency present")
check(not re.search(r"<link[^>]+rel=[\"']?stylesheet", html, re.I), "external stylesheet dependency present")
check(not re.search(r"\bfetch\s*\(", html), "runtime fetch() present")
check('<input id="wToggle" type="checkbox">' in html, "ROW-permit layer is not off by default")
check('aria-label="Field date and time in San Francisco"' in html, "shared field-time control has stale accessibility label")
check("if(S.swk)addMarker" in html, "ROW-permit layer creates hidden markers while switched off")
check("$('wToggle').onchange=e=>{S.swk=e.target.checked;renderW()}" in html, "ROW-permit toggle does not rebuild/clear markers")
check("const workLocations=p=>" in html, "permit UI does not understand aggregated source locations")
check("distinct location text is preserved above" in html, "permit aggregation explanation missing from click details")

# ---------- layer presence / broad count guardrails ----------
ranges = {
    "precincts": (400, 800),
    "streets": (9_000, 25_000),
    "multifamily": (100, 10_000),
    "closures": (1, 20_000),
    "surface_permits": (500, 20_000),
}
for key, (lo, hi) in ranges.items():
    fs = (data.get(key) or {}).get("features") or []
    check(lo <= len(fs) <= hi, f"{key} count {len(fs)} outside guardrail {lo}-{hi}")

# ---------- precinct reference layer ----------
precinct_ids = []
for f in data["precincts"]["features"]:
    check((f.get("geometry") or {}).get("type") in {"Polygon", "MultiPolygon"}, "precinct non-polygon geometry")
    p = props(f)
    precinct_ids.append(str(p.get("prec_2022") or p.get("precinct") or p.get("id") or ""))
check(all(precinct_ids), "precinct missing ID")
check(len(precinct_ids) == len(set(precinct_ids)), "duplicate precinct IDs")

# ---------- street backbone + hills ----------
excluded_street_layers = {"PAPER", "PAPER_FWYS", "PAPER_WATER", "PSEUDO", "PRIVATE_PARKING"}
cnns = []
hill_categories = collections.Counter()
hill_confidence = collections.Counter()
grades = []
streets = data["streets"]["features"]
for f in streets:
    p = props(f)
    geom_type = (f.get("geometry") or {}).get("type")
    check(geom_type in {"LineString", "MultiLineString"}, "street non-line geometry")
    cnn = str(p.get("cnn") or "")
    cnns.append(cnn)
    layer = str(p.get("layer") or "").upper()
    check(layer not in excluded_street_layers, f"excluded street layer leaked: {layer}")
    try:
        classcode = int(p.get("classcode") or 0)
    except (TypeError, ValueError):
        classcode = 0
    grade = p.get("estimated_grade_pct")
    confidence = p.get("grade_confidence")
    if classcode in {1, 6}:
        check(grade is None and confidence == "not_applicable", f"freeway/ramp has canvassing grade: CNN {cnn}")
        hill_categories["not_applicable"] += 1
    elif grade is None:
        check(confidence == "unavailable", f"missing hill grade has bad confidence: CNN {cnn} / {confidence}")
        hill_categories["unavailable"] += 1
    else:
        check(isinstance(grade, (int, float)) and 0 <= grade <= 45, f"implausible hill grade: CNN {cnn} / {grade}")
        check(confidence in {"low", "medium", "high"}, f"bad hill confidence: CNN {cnn} / {confidence}")
        support = p.get("grade_support_fraction")
        check(isinstance(support, (int, float)) and 0 < support <= 1, f"bad hill support fraction: CNN {cnn} / {support}")
        check(p.get("grade_method") == "direct_5ft_contour_crossings_v2", f"bad hill method: CNN {cnn}")
        grades.append(float(grade))
        hill_confidence[confidence] += 1
        category = (
            "20+" if grade >= 20 else
            "15-19.9" if grade >= 15 else
            "10-14.9" if grade >= 10 else
            "5-9.9" if grade >= 5 else
            "<5"
        )
        hill_categories[category] += 1
check(all(cnns), "street missing CNN")
check(len(cnns) == len(set(cnns)), "duplicate street CNNs")
check(len(grades) == int(meta.get("graded_street_count", -1)), "graded street count/meta mismatch")
check(dict(hill_categories) == meta.get("grade_category_counts"), "hill category counts/meta mismatch")
check(dict(hill_confidence) == meta.get("grade_confidence_counts"), "hill confidence counts/meta mismatch")
check(hill_categories["20+"] <= 0.12 * max(1, len(grades)), "20%+ hill share unexpectedly high")

# ---------- high-unit residential parcels ----------
parcel_ids = []
thresholds = {20: 0, 50: 0, 100: 0, 200: 0}
for f in data["multifamily"]["features"]:
    p = props(f)
    check((f.get("geometry") or {}).get("type") in {"Polygon", "MultiPolygon"}, "housing non-polygon geometry")
    check(str(p.get("geography_type") or "").lower() == "parcel", "non-parcel geography in housing layer")
    parcel_id = str(p.get("mapblklot") or p.get("ludb_id") or "")
    parcel_ids.append(parcel_id)
    raw = p.get("resunits") if p.get("resunits") not in (None, "") else p.get("resunits_s")
    try:
        units = float(raw)
    except (TypeError, ValueError):
        units = -1
    check(units >= 20, f"housing record below 20 units: {parcel_id} / {raw}")
    for t in thresholds:
        thresholds[t] += units >= t
check(all(parcel_ids), "housing record missing parcel ID")
check(len(parcel_ids) == len(set(parcel_ids)), "duplicate parcel IDs remain")
check({str(k): v for k, v in thresholds.items()} == meta.get("threshold_counts"), "housing threshold counts/meta mismatch")

# ---------- temporary closures ----------
street_cnns = set(cnns)
objectids = []
cnn_with = 0
cnn_match = 0
for f in data["closures"]["features"]:
    p = props(f)
    check(str(p.get("status") or "").strip().upper() == "PERMITTED", f"non-permitted closure embedded: {p.get('status')}")
    check((f.get("geometry") or {}).get("type") in {"LineString", "MultiLineString"}, "closure non-line geometry")
    start = str(p.get("start_local") or "")
    end = str(p.get("end_local") or "")
    check(bool(start and end and start <= end), f"invalid closure time window: {start} / {end}")
    oid = str(p.get("objectid") or "")
    check(bool(oid), "closure missing objectid")
    objectids.append(oid)
    cnn = str(p.get("cnn") or "")
    if cnn:
        cnn_with += 1
        cnn_match += cnn in street_cnns
check(len(objectids) == len(set(objectids)), "duplicate closure objectids")
if cnn_with:
    check(cnn_match / cnn_with >= 0.80, f"closure CNN match rate unexpectedly low: {cnn_match}/{cnn_with}")
check(len(data["closures"]["features"]) == int(meta.get("closure_display_count", -1)), "closure count/meta mismatch")

# ---------- current/upcoming Public Works permits ----------
allowed_permit_types = {"Excavation", "TempOccup", "StrtImprov", "ExcStreet", "AddlStSpac", "StorCont", "MinorEnc", "StreetSpace"}
forbidden_permit_fields = {"dba_name", "name", "applicant", "phone", "email", "contact", "latitude", "longitude"}
marker_keys = []
total_source_rows_represented = 0
aggregate_groups = 0
aggregate_extra_rows = 0
multi_location_groups = 0
multi_description_groups = 0
multi_status_groups = 0
for f in data["surface_permits"]["features"]:
    p = props(f)
    geom = f.get("geometry") or {}
    check(geom.get("type") == "Point", "surface permit non-point geometry")
    coordinates = geom.get("coordinates") or []
    check(sf_point(coordinates), f"surface permit point outside SF guardrail: {coordinates}")
    check(p.get("permit_type") in allowed_permit_types, f"disallowed surface-permit type: {p.get('permit_type')}")

    statuses = p.get("source_statuses")
    check(isinstance(statuses, list) and bool(statuses), f"permit missing source_statuses: {p.get('permit_number')}")
    if isinstance(statuses, list):
        check(all(str(x).upper() in {"ACTIVE", "APPROVED"} for x in statuses), f"disallowed source permit status: {statuses}")
        if len(statuses) == 1:
            check(p.get("status") == statuses[0], f"permit scalar status disagrees with source status: {p.get('permit_number')}")
        else:
            check("status" not in p, f"ambiguous multi-status permit exposes arbitrary scalar status: {p.get('permit_number')}")

    start = str(p.get("start_local") or "")
    end = str(p.get("end_local") or "")
    check(bool(start and end and start <= end), f"invalid surface-permit window: {start} / {end}")
    leaked = forbidden_permit_fields.intersection(p)
    check(not leaked, f"unnecessary permit fields embedded: {sorted(leaked)}")

    locations = p.get("source_locations")
    descriptions = p.get("source_descriptions")
    check(isinstance(locations, list), f"permit source_locations not a list: {p.get('permit_number')}")
    check(isinstance(descriptions, list), f"permit source_descriptions not a list: {p.get('permit_number')}")
    if isinstance(locations, list):
        check(p.get("source_location_count") == len(locations), f"permit location count mismatch: {p.get('permit_number')}")
        for loc in locations:
            check(isinstance(loc, dict) and set(loc).issubset({"street", "cross_street"}), f"malformed permit source location: {loc}")
        if len(locations) > 1:
            multi_location_groups += 1
            check("street_name" not in p and "cross_street" not in p, f"multi-location marker exposes arbitrary scalar location: {p.get('permit_number')}")
        elif len(locations) == 1:
            check(p.get("street_name", "") == locations[0].get("street", ""), f"single-location street mismatch: {p.get('permit_number')}")
            check(p.get("cross_street", "") == locations[0].get("cross_street", ""), f"single-location cross-street mismatch: {p.get('permit_number')}")
    if isinstance(descriptions, list) and len(descriptions) > 1:
        multi_description_groups += 1
        check("permit_description" not in p, f"multi-description marker exposes arbitrary scalar description: {p.get('permit_number')}")

    rows = p.get("source_row_count")
    check(isinstance(rows, int) and rows >= 1, f"bad source_row_count: {p.get('permit_number')} / {rows}")
    if isinstance(rows, int) and rows >= 1:
        total_source_rows_represented += rows
        if rows > 1:
            aggregate_groups += 1
            aggregate_extra_rows += rows - 1
    if isinstance(statuses, list) and len(statuses) > 1:
        multi_status_groups += 1

    if len(coordinates) >= 2:
        marker_keys.append((
            str(p.get("permit_number") or ""),
            p.get("permit_type"),
            float(coordinates[0]),
            float(coordinates[1]),
            start,
            end,
        ))

check(len(marker_keys) == len(set(marker_keys)), "surface-permit aggregation keys remain duplicated")
check(len(data["surface_permits"]["features"]) == int(meta.get("surface_permit_display_count", -1)), "surface-permit marker count/meta mismatch")
check(total_source_rows_represented == int(meta.get("surface_permit_eligible_source_row_count", -1)), "surface-permit represented source row count/meta mismatch")
agg_meta = meta.get("surface_permit_aggregation") or {}
check(aggregate_groups == agg_meta.get("marker_groups_with_multiple_source_rows"), "permit aggregation-group count/meta mismatch")
check(aggregate_extra_rows == agg_meta.get("additional_source_rows_aggregated"), "permit aggregated-extra-row count/meta mismatch")
check(multi_location_groups == agg_meta.get("marker_groups_with_multiple_source_locations"), "permit multi-location count/meta mismatch")
check(multi_description_groups == agg_meta.get("marker_groups_with_multiple_descriptions"), "permit multi-description count/meta mismatch")
check(multi_status_groups == agg_meta.get("marker_groups_with_multiple_statuses"), "permit multi-status count/meta mismatch")

retrieved_sf = str(meta.get("surface_permit_retrieved_sf") or "")
supported_from = str(meta.get("surface_permit_supported_from") or "")
supported_through = str(meta.get("surface_permit_supported_through") or "")
check(retrieved_sf.startswith(supported_from), "permit support start is not the SF retrieval date")
try:
    check((dt.date.fromisoformat(supported_through) - dt.date.fromisoformat(supported_from)).days == 14, "permit support window is not 14 days")
except ValueError:
    issues.append("invalid permit support dates")

# ---------- provenance ----------
expected_ids = {
    "precincts": "d6x4-hefw",
    "streets": "3psu-pn9h",
    "multifamily": "c5ge-t6pj",
    "hills": "rnbg-2qxw",
    "closures": "8x25-yybr",
    "surface_permits": "bpc9-7sus",
}
for key, dataset_id in expected_ids.items():
    check((manifest.get(key) or {}).get("dataset_id") == dataset_id, f"{key} manifest dataset ID mismatch")

# ---------- inline JavaScript syntax ----------
scripts = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", html, re.S | re.I)
for i, script in enumerate(scripts):
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as tmp:
        tmp.write(script)
        name = tmp.name
    result = subprocess.run(["node", "--check", name], capture_output=True, text=True)
    pathlib.Path(name).unlink(missing_ok=True)
    check(result.returncode == 0, f"inline JS block {i} syntax error: {result.stderr.strip()}")

if issues:
    print(f"AUDIT FAIL: {len(issues)} issue(s)")
    for issue in issues:
        print(f" - {issue}")
    raise SystemExit(1)

print("AUDIT PASS")
print("layer counts:", {key: len(data[key]["features"]) for key in ranges})
print("hill categories:", dict(hill_categories))
print("hill confidence:", dict(hill_confidence))
print(f"closure CNN match: {cnn_match}/{cnn_with}")
print("permit aggregation:", {
    "markers": len(data["surface_permits"]["features"]),
    "source_rows_represented": total_source_rows_represented,
    "multi_row_markers": aggregate_groups,
    "extra_rows_aggregated": aggregate_extra_rows,
    "multi_location_markers": multi_location_groups,
    "multi_description_markers": multi_description_groups,
    "multi_status_markers": multi_status_groups,
})
print(f"permit support: {supported_from} through {supported_through}")
