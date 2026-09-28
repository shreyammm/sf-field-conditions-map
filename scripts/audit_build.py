#!/usr/bin/env python3
"""Fail the build if a deployed layer drifts from its documented semantics.

This is intentionally independent of the individual layer builders. It reads the
finished HTML/manifest after every patch has run and re-checks the invariants a
user actually receives in the deployed artifact.
"""
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


# ---------- final-page architecture / UI ----------
ids = re.findall(r"\bid=[\"']([^\"']+)", html)
dup_ids = [k for k, n in collections.Counter(ids).items() if n > 1]
check(not dup_ids, f"duplicate HTML ids: {dup_ids[:10]}")
check(not re.search(r"<script[^>]+src=", html, re.I), "external script dependency present")
check(not re.search(r"<link[^>]+rel=[\"']?stylesheet", html, re.I), "external stylesheet dependency present")
check(not re.search(r"\bfetch\s*\(", html), "runtime fetch() present")
check('<input id="wToggle" type="checkbox">' in html, "ROW-permit layer is not off by default")
check(
    'aria-label="Field date and time in San Francisco"' in html,
    "shared field-time control has a stale/incorrect accessibility label",
)
check("if(S.swk)addMarker" in html, "ROW-permit layer creates markers while switched off")
check(
    "$('wToggle').onchange=e=>{S.swk=e.target.checked;renderW()}" in html,
    "ROW-permit toggle does not rebuild/clear its markers",
)

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
dedupe_keys = []
for f in data["surface_permits"]["features"]:
    p = props(f)
    check((f.get("geometry") or {}).get("type") == "Point", "surface permit non-point geometry")
    check(p.get("permit_type") in allowed_permit_types, f"disallowed surface-permit type: {p.get('permit_type')}")
    check(str(p.get("status") or "").upper() in {"ACTIVE", "APPROVED"}, f"disallowed surface-permit status: {p.get('status')}")
    start = str(p.get("start_local") or "")
    end = str(p.get("end_local") or "")
    check(bool(start and end and start <= end), f"invalid surface-permit window: {start} / {end}")
    leaked = forbidden_permit_fields.intersection(p)
    check(not leaked, f"unnecessary permit fields embedded: {sorted(leaked)}")
    coordinates = (f.get("geometry") or {}).get("coordinates") or []
    if len(coordinates) >= 2:
        dedupe_keys.append((
            str(p.get("permit_number") or ""),
            p.get("permit_type"),
            round(float(coordinates[0]), 7),
            round(float(coordinates[1]), 7),
            start,
            end,
        ))
check(len(dedupe_keys) == len(set(dedupe_keys)), "surface-permit dedupe keys remain duplicated")

retrieved_sf = str(meta.get("surface_permit_retrieved_sf") or "")
supported_from = str(meta.get("surface_permit_supported_from") or "")
supported_through = str(meta.get("surface_permit_supported_through") or "")
check(retrieved_sf.startswith(supported_from), "permit support start is not the SF retrieval date")
try:
    check(
        (dt.date.fromisoformat(supported_through) - dt.date.fromisoformat(supported_from)).days == 14,
        "permit support window is not 14 days",
    )
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
print(f"permit support: {supported_from} through {supported_through}")
