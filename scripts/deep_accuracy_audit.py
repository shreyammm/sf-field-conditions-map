#!/usr/bin/env python3
"""End-to-end audit of the final production artifact.

Unlike layer builders, this reads the exact HTML/manifest that will be deployed.
It fails on semantic drift, provenance drift, impossible geometry, duplicate
identifiers, unsafe inference, stale live data, or UI text that overstates what
the official sources establish.
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
issues: list[str] = []
warnings: list[str] = []


def check(ok, message):
    if not ok:
        issues.append(message)


def props(f):
    return f.get("properties") or {}


def local_naive(value):
    text = str(value or "").strip().replace(" ", "T")
    if not text:
        return None
    try:
        return dt.datetime.fromisoformat(text[:19])
    except ValueError:
        return None


def sf_point(coords):
    if not isinstance(coords, list) or len(coords) < 2:
        return False
    try:
        lon, lat = float(coords[0]), float(coords[1])
    except (TypeError, ValueError):
        return False
    return (
        math.isfinite(lon)
        and math.isfinite(lat)
        and -122.60 <= lon <= -122.25
        and 37.65 <= lat <= 37.90
    )


def threshold_bucket(x):
    x = float(x)
    if x >= 200:
        return 200
    if x >= 100:
        return 100
    if x >= 50:
        return 50
    return 20


m = re.search(r"window\.SF_FIELD_DATA=(\{.*?\});\s*</script>", html, re.S)
check(bool(m), "embedded production payload is missing")
data = json.loads(m.group(1)) if m else {}
meta = data.get("meta") or {}

# ---------------------------------------------------------------------------
# Provenance: every deployed source must resolve to the intended official ID.
# ---------------------------------------------------------------------------
expected = {
    "streets": "3psu-pn9h",
    "precincts": "d6x4-hefw",
    "multifamily": "c5ge-t6pj",
    "hills": "rnbg-2qxw",
    "closures": "8x25-yybr",
    "surface_permits": "bpc9-7sus",
    "live_calls": "gnap-fj3t",
}
for key, dataset_id in expected.items():
    section = manifest.get(key) or {}
    check(section.get("dataset_id") == dataset_id, f"{key} dataset id drift: {section.get('dataset_id')} != {dataset_id}")
    check(html.count(f'href="https://data.sf.gov/d/{dataset_id}"') >= 2, f"{key} official source is not linked both in directory and methodology")

check("Official data sources" in html, "official source directory missing")
check("data.sf.gov/resource/gnap-fj3t.json" in html, "live runtime endpoint is not official DataSF")

# ---------------------------------------------------------------------------
# No known stale/overstated copy may survive into the deployed artifact.
# ---------------------------------------------------------------------------
for stale in (
    "No hill or routing score is calculated yet",
    "future street conditions",
    "This orange circle",
    "Solid orange means",
    "hollow orange marker",
    "Recent public-safety activity",
):
    check(stale not in html, f"stale or imprecise UI text remains: {stale!r}")
check("Recent law-enforcement dispatch activity" in html, "precise live-layer title missing")
check("Calls received within" in html, "live lookback is not explicitly tied to received time")
check("not confirmed crimes" in html.lower() or "not a crime count" in html.lower(), "dispatch-vs-crime caveat missing")
check("privacy-mapped" in html.lower() or "privacy-masked" in html.lower(), "public-location privacy caveat missing")
check("not an official engineering street-grade survey" in html, "hill non-engineering caveat missing")
check("not a confirmed closure" in html.lower() or "does not establish a street closure" in html.lower(), "permit-vs-closure caveat missing")
check("not proof that pedestrians cannot pass" in html.lower() or "does not necessarily mean pedestrian access is blocked" in html.lower(), "closure pedestrian caveat missing")

# ---------------------------------------------------------------------------
# Precincts: geometry/reference only, never scored.
# ---------------------------------------------------------------------------
precincts = ((data.get("precincts") or {}).get("features") or [])
check(400 <= len(precincts) <= 800, f"precinct count implausible: {len(precincts)}")
pids = []
for f in precincts:
    check((f.get("geometry") or {}).get("type") in {"Polygon", "MultiPolygon"}, "precinct has non-polygon geometry")
    p = props(f)
    pid = str(p.get("prec_2022") or p.get("precinct") or p.get("id") or "")
    pids.append(pid)
    check(not any("score" in str(k).lower() or "risk" in str(k).lower() for k in p), f"precinct {pid} contains a derived score/risk field")
check(all(pids), "precinct record missing id")
check(len(pids) == len(set(pids)), "duplicate precinct ids")
check("precinct score" not in html.lower() or "not averaged into precinct scores" in html.lower(), "UI appears to create a precinct score")

# ---------------------------------------------------------------------------
# Streets: official active centerlines filtered by explicit product policy.
# ---------------------------------------------------------------------------
streets = ((data.get("streets") or {}).get("features") or [])
check(9_000 <= len(streets) <= 25_000, f"street count implausible: {len(streets)}")
excluded_layers = {"PAPER", "PAPER_FWYS", "PAPER_WATER", "PSEUDO", "PRIVATE_PARKING"}
cnns = []
for f in streets:
    p = props(f)
    check((f.get("geometry") or {}).get("type") in {"LineString", "MultiLineString"}, "street has non-line geometry")
    check(str(p.get("active") or "").lower() in {"true", "t", "1", "yes", "y"} or p.get("active") is True, f"retired/inactive street leaked: {p.get('cnn')}")
    check(str(p.get("layer") or "").upper() not in excluded_layers, f"excluded street layer leaked: {p.get('layer')}")
    cnn = str(p.get("cnn") or "")
    cnns.append(cnn)
check(all(cnns), "street missing CNN")
check(len(cnns) == len(set(cnns)), "duplicate displayed street CNN")

# ---------------------------------------------------------------------------
# Hill estimates: derived values must carry method/support/confidence.
# ---------------------------------------------------------------------------
hill_counts = collections.Counter()
conf_counts = collections.Counter()
grades = []
for f in streets:
    p = props(f)
    try:
        cls = int(p.get("classcode") or 0)
    except (TypeError, ValueError):
        cls = 0
    grade = p.get("estimated_grade_pct")
    conf = str(p.get("grade_confidence") or "")
    if cls in {1, 6}:
        check(grade is None and conf == "not_applicable", f"freeway/ramp has canvassing hill estimate: {p.get('cnn')}")
        hill_counts["not_applicable"] += 1
    elif grade is None:
        check(conf == "unavailable", f"missing hill estimate has non-unavailable confidence: {p.get('cnn')} / {conf}")
        hill_counts["unavailable"] += 1
    else:
        check(isinstance(grade, (int, float)) and 0 <= float(grade) <= 45, f"hill estimate outside guardrail: {p.get('cnn')} / {grade}")
        check(conf in {"low", "medium", "high"}, f"hill confidence invalid: {p.get('cnn')} / {conf}")
        check(p.get("grade_method") == "direct_5ft_contour_crossings_v2", f"hill method drift: {p.get('cnn')}")
        support = p.get("grade_support_fraction")
        check(isinstance(support, (int, float)) and 0 < float(support) <= 1, f"hill support fraction invalid: {p.get('cnn')} / {support}")
        check(int(p.get("grade_crossing_intervals") or 0) >= 1, f"classified hill lacks accepted intervals: {p.get('cnn')}")
        g = float(grade)
        grades.append(g)
        conf_counts[conf] += 1
        hill_counts["20+" if g >= 20 else "15-19.9" if g >= 15 else "10-14.9" if g >= 10 else "5-9.9" if g >= 5 else "<5"] += 1
check(len(grades) == int(meta.get("graded_street_count", -1)), "graded-street count disagrees with embedded metadata")
check(dict(hill_counts) == meta.get("grade_category_counts"), "hill category totals disagree with embedded metadata")
check(dict(conf_counts) == meta.get("grade_confidence_counts"), "hill confidence totals disagree with embedded metadata")
check(grades and max(grades) <= 45, "hill maximum failed physical guardrail")
check(hill_counts["20+"] <= 0.12 * max(1, len(grades)), "20%+ hill share unexpectedly high")
check("Consecutive same-elevation crossings contribute zero net rise" in html, "deployed hill methodology does not match v2 code")
check("Dashed/faded color = low-confidence estimate" in html and ".hlow" in html, "low-confidence hill estimates are not visually distinguished")

# ---------------------------------------------------------------------------
# High-unit parcel layer: parcel geometry only, no building-footprint claim.
# ---------------------------------------------------------------------------
parcels = ((data.get("multifamily") or {}).get("features") or [])
check(100 <= len(parcels) <= 10_000, f"high-unit parcel count implausible: {len(parcels)}")
parcel_ids = []
thresholds = {20: 0, 50: 0, 100: 0, 200: 0}
for f in parcels:
    p = props(f)
    check((f.get("geometry") or {}).get("type") in {"Polygon", "MultiPolygon"}, "parcel has non-polygon geometry")
    check(str(p.get("geography_type") or "").lower() == "parcel", "non-parcel geography leaked into housing layer")
    pid = str(p.get("mapblklot") or p.get("ludb_id") or "")
    parcel_ids.append(pid)
    raw = p.get("resunits") if p.get("resunits") not in (None, "") else p.get("resunits_s")
    try:
        units = float(raw)
    except (TypeError, ValueError):
        units = -1
    check(20 <= units <= 20_000, f"parcel unit count invalid: {pid} / {raw}")
    for t in thresholds:
        thresholds[t] += units >= t
    if p.get("source_unit_count_conflict"):
        lo = p.get("source_unit_count_min")
        hi = p.get("source_unit_count_max")
        check(isinstance(lo, (int, float)) and isinstance(hi, (int, float)) and lo <= hi, f"parcel conflict range malformed: {pid}")
        if isinstance(lo, (int, float)) and isinstance(hi, (int, float)):
            check(threshold_bucket(lo) == threshold_bucket(hi), f"parcel conflict crosses display bucket: {pid} / {lo}-{hi}")
check(all(parcel_ids), "parcel missing stable id")
check(len(parcel_ids) == len(set(parcel_ids)), "duplicate parcel ids remain")
check({str(k): v for k, v in thresholds.items()} == meta.get("threshold_counts"), "parcel threshold totals disagree with metadata")
check("not necessarily a building footprint" in html.lower(), "parcel-vs-building caveat missing")

# ---------------------------------------------------------------------------
# Closures: permitted-only source lines, calendar-day overlap, no access claim.
# ---------------------------------------------------------------------------
closures = ((data.get("closures") or {}).get("features") or [])
check(1 <= len(closures) <= 20_000, f"closure count implausible: {len(closures)}")
oids = []
for f in closures:
    p = props(f)
    check(str(p.get("status") or "").strip().upper() == "PERMITTED", f"non-permitted closure embedded: {p.get('status')}")
    check((f.get("geometry") or {}).get("type") in {"LineString", "MultiLineString"}, "closure has non-line geometry")
    a, b = str(p.get("start_local") or ""), str(p.get("end_local") or "")
    check(bool(a and b and a <= b), f"closure invalid time window: {p.get('objectid')} / {a} / {b}")
    oid = str(p.get("objectid") or "")
    oids.append(oid)
    for rel in p.get("related_work_permits") or []:
        check(str(p.get("type") or "").upper() == "SPECIAL TRAFFIC PERMIT", f"related permit context attached to non-STP closure: {oid}")
        check(float(rel.get("distance_m", 999999)) <= 120.0, f"closure-context distance exceeds 120m: {oid}")
        check("match_basis" in rel, f"closure-context match basis omitted: {oid}")
check(all(oids), "closure missing objectid")
check(len(oids) == len(set(oids)), "duplicate closure objectids")
check("a<nextStart&&b>=dayStart" in html, "closure UI is not using day-overlap semantics")
check("calendar date" in str((manifest.get("closures") or {}).get("filter_rule") or "").lower(), "manifest still claims exact-time closure filtering")
closure_asof = local_naive((manifest.get("closures") or {}).get("data_as_of"))
build_time = dt.datetime.fromisoformat(str(manifest.get("retrieved_at") or "").replace("Z", "+00:00")).replace(tzinfo=None) if manifest.get("retrieved_at") else None
if closure_asof and build_time:
    closure_age_days = (build_time.date() - closure_asof.date()).days
    if closure_age_days > 14:
        issues.append(f"official closure source appears >14 days stale: {closure_age_days}d")
    elif closure_age_days > 2:
        warnings.append(f"official closure source data_as_of is {closure_age_days} days before build; UI must show this freshness warning")
        check("verify source if planning is time-sensitive" in html, "closure source is >2d old but UI freshness warning is missing")

# ---------------------------------------------------------------------------
# Public Works permit points: authorization context, not guessed footprints.
# ---------------------------------------------------------------------------
permits = ((data.get("surface_permits") or {}).get("features") or [])
allowed_types = {"Excavation", "TempOccup", "StrtImprov", "ExcStreet", "AddlStSpac", "StorCont", "MinorEnc", "StreetSpace"}
marker_keys = []
for f in permits:
    p = props(f)
    g = f.get("geometry") or {}
    check(g.get("type") == "Point" and sf_point(g.get("coordinates")), f"permit point invalid: {p.get('permit_number')}")
    check(p.get("permit_type") in allowed_types, f"permit type outside product scope: {p.get('permit_type')}")
    statuses = p.get("source_statuses") or []
    check(statuses and all(str(x).upper() in {"ACTIVE", "APPROVED"} for x in statuses), f"permit has disallowed/missing status: {p.get('permit_number')}")
    a, b = str(p.get("start_local") or ""), str(p.get("end_local") or "")
    check(bool(a and b and a <= b), f"permit invalid date window: {p.get('permit_number')}")
    coords = g.get("coordinates") or []
    if len(coords) >= 2:
        marker_keys.append((str(p.get("permit_number") or ""), p.get("permit_type"), float(coords[0]), float(coords[1]), a, b))
    check(isinstance(p.get("source_locations"), list), f"permit source locations not preserved: {p.get('permit_number')}")
    check(isinstance(p.get("source_descriptions"), list), f"permit source descriptions not preserved: {p.get('permit_number')}")
check(500 <= len(permits) <= 20_000, f"permit marker count implausible: {len(permits)}")
check(len(marker_keys) == len(set(marker_keys)), "duplicate permit aggregation keys remain")
pman = manifest.get("surface_permits") or {}
try:
    a = dt.date.fromisoformat(str(pman.get("supported_from")))
    b = dt.date.fromisoformat(str(pman.get("supported_through")))
    check((b - a).days == 14, "permit UI support window is not exactly current date + 14 days")
except ValueError:
    issues.append("permit support dates malformed")
check("point is not an exact work footprint" in html.lower(), "permit point/footprint caveat missing")

# ---------------------------------------------------------------------------
# Real-time law-enforcement dispatch layer: strict recency/uniqueness semantics.
# ---------------------------------------------------------------------------
live_features = ((data.get("live_calls") or {}).get("features") or [])
lman = manifest.get("live_calls") or {}
check(lman.get("dataset_id") == "gnap-fj3t", "live source id incorrect")
check(int(lman.get("display_max_hours") or -1) == 48, "live display max lookback is not 48h")
check(int(lman.get("query_window_hours") or -1) == 49, "live fallback query buffer is not 49h")
check(int(lman.get("query_limit") or -1) == 10_000, "live fallback safety limit is not 10,000")
check(int(lman.get("source_row_count") or 0) < int(lman.get("query_limit") or 0), "live fallback query hit its limit and may be truncated")
check(int(lman.get("cad_unique_count") or -1) == int(lman.get("source_row_count") or -2), "live fallback source is not one unique CAD number per row")
check(float(lman.get("source_age_minutes") or 999999) <= 180, "live fallback data_as_of is too stale")
check(float(lman.get("newest_call_age_minutes") or 999999) <= 180, "newest live fallback call is too old")
check(50 <= len(live_features) < 10_000, f"mapped live fallback count implausible: {len(live_features)}")
retrieved = dt.datetime.fromisoformat(str(lman.get("retrieved_sf") or "")).replace(tzinfo=None) if lman.get("retrieved_sf") else None
live_ids = []
for f in live_features:
    p = props(f)
    g = f.get("geometry") or {}
    check(g.get("type") == "Point" and sf_point(g.get("coordinates")), f"live mapped point invalid: {p.get('id')}")
    check(isinstance(p.get("open"), bool), f"live open flag not boolean: {p.get('id')}")
    if p.get("open") is True:
        check(not p.get("close_datetime"), f"live call marked open but has close time: {p.get('id')}")
    if p.get("close_datetime"):
        check(p.get("open") is False, f"live closed call not marked closed: {p.get('id')}")
    check("cad_number" not in p, "CAD number unnecessarily embedded in UI payload")
    iid = str(p.get("id") or "")
    if iid:
        live_ids.append(iid)
    if retrieved:
        received = local_naive(p.get("received_datetime"))
        check(received is not None, f"live mapped row missing received time: {iid}")
        if received:
            age_h = (retrieved - received).total_seconds() / 3600
            check(-0.25 <= age_h <= 49.1, f"live fallback row outside 49h query buffer: {iid} / {age_h:.2f}h")
check(len(live_ids) == len(set(live_ids)), "duplicate public row ids in mapped live fallback")
check("LIVE_CALLS_LIMIT=10000" in html and "LIVE_CALLS_QUERY_HOURS=49" in html, "runtime live query guardrails missing")
check("row.cad_number" in html and "Duplicate CAD number" in html, "runtime CAD uniqueness validation missing")
check("dataAge>180" in html, "runtime live freshness rejection missing")
check("rows.length>=LIVE_CALLS_LIMIT" in html, "runtime truncation guard missing")
check("fetch(liveCallsUrl()" in html, "runtime live query is not using bounded official URL builder")
check("setInterval(()=>{if(S.si)refreshLiveCalls()},600000)" in html, "runtime live refresh is not conditional on layer being enabled")
check("renderI();refreshLiveCalls();" not in html, "live API is still fetched automatically on page open")
check("if(cls==='lcp'||cls==='lcg')" in html and ".lcg.closed" in html and ".lcg.mixed" in html, "low-zoom live aggregates do not preserve open/closed/mixed visual semantics")
for h in (1, 3, 6, 12, 24, 48):
    check(f'data-hours="{h}"' in html, f"live {h}h filter missing")
check("iagency:'Police'" in html, "Police-only live default missing")
check("id=\"iOpenOnly\"" in html, "open-only live filter missing")
check("Dark forest-green" in html or "forest-green" in html, "live forest-green methodology missing")

# ---------------------------------------------------------------------------
# Final web-package integrity: exactly one whitelisted optional runtime fetch.
# ---------------------------------------------------------------------------
fetch_calls = re.findall(r"\bfetch\s*\(", html)
check(len(fetch_calls) == 1, f"unexpected runtime fetch count: {len(fetch_calls)}")
ids = re.findall(r"\bid=[\"']([^\"']+)", html)
dups = [x for x, n in collections.Counter(ids).items() if n > 1]
check(not dups, f"duplicate HTML ids: {dups[:10]}")
check(not re.search(r"<script[^>]+src=", html, re.I), "external script dependency introduced")
check(not re.search(r"<link[^>]+rel=[\"']?stylesheet", html, re.I), "external stylesheet introduced")

scripts = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", html, re.S | re.I)
for i, script in enumerate(scripts):
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as tmp:
        tmp.write(script)
        filename = tmp.name
    result = subprocess.run(["node", "--check", filename], capture_output=True, text=True)
    pathlib.Path(filename).unlink(missing_ok=True)
    check(result.returncode == 0, f"inline JavaScript block {i} has syntax error: {result.stderr.strip()}")

if issues:
    print(f"DEEP ACCURACY AUDIT FAIL: {len(issues)} issue(s)")
    for issue in issues:
        print(" -", issue)
    if warnings:
        print("WARNINGS:")
        for warning in warnings:
            print(" -", warning)
    raise SystemExit(1)

print("DEEP ACCURACY AUDIT PASS")
print("production dataset ids:", expected)
print(f"counts: precincts={len(precincts):,}, streets={len(streets):,}, parcels={len(parcels):,}, closures={len(closures):,}, permits={len(permits):,}, mapped_live_fallback={len(live_features):,}")
print(f"hills: classified={len(grades):,}; confidence={dict(conf_counts)}; categories={dict(hill_counts)}")
print(f"live: source_age={lman.get('source_age_minutes')}m; newest_call_age={lman.get('newest_call_age_minutes')}m; query_rows={lman.get('source_row_count')}; mapped={len(live_features)}")
print("runtime network: one official DataSF fetch, only for optional live layer while enabled")
print("interpretation: precinct reference only; no risk/targeting score; permits/closures/dispatches retain source limitations")
if warnings:
    print("NON-FATAL SOURCE FRESHNESS WARNINGS:")
    for warning in warnings:
        print(" -", warning)
