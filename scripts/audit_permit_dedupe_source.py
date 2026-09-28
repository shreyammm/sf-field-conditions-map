#!/usr/bin/env python3
"""Audit whether rows collapsed by the surface-permit key are truly redundant.

This is a source-audit helper, not part of map rendering. It uses the same key as
add_surface_permits.py and fails if rows sharing that key disagree on core
operational fields. Differences limited to neighborhood/district/data timestamp
are reported but do not change the physical permit interpretation.
"""
from __future__ import annotations
import collections
import datetime as dt
import json
import urllib.request

URL = "https://data.sf.gov/api/v3/views/bpc9-7sus/query.geojson?accessType=DOWNLOAD"
HEADERS = {"User-Agent": "sf-field-conditions-map/1.0", "Accept": "application/geo+json,application/json"}
KEEP_TYPES = {"Excavation", "TempOccup", "StrtImprov", "ExcStreet", "AddlStSpac", "StorCont", "MinorEnc", "StreetSpace"}
CORE_FIELDS = ("permit_description", "status", "street_name", "cross_street")
DIAGNOSTIC_FIELDS = ("analysis_neighborhood", "supervisor_district", "data_as_of")


def local_iso(value):
    if value in (None, ""):
        return None
    s = str(value).strip().replace(" ", "T")
    if len(s) < 10:
        return None
    candidate = s[:19] if len(s) >= 19 else s[:10] + "T00:00:00"
    try:
        dt.datetime.fromisoformat(candidate)
    except ValueError:
        return None
    return candidate


def point(geometry):
    if not geometry or geometry.get("type") != "Point":
        return None
    c = geometry.get("coordinates") or []
    if len(c) < 2:
        return None
    try:
        return round(float(c[0]), 7), round(float(c[1]), 7)
    except (TypeError, ValueError):
        return None


req = urllib.request.Request(URL, headers=HEADERS)
with urllib.request.urlopen(req, timeout=180) as r:
    fc = json.load(r)

groups = collections.defaultdict(list)
for f in fc.get("features", []):
    p = f.get("properties") or {}
    typ = str(p.get("permit_type") or "").strip()
    status = str(p.get("status") or "").strip().upper()
    pt = point(f.get("geometry"))
    start = local_iso(p.get("permit_start_date"))
    end = local_iso(p.get("permit_end_date"))
    if typ not in KEEP_TYPES or status not in {"ACTIVE", "APPROVED"} or not pt or not start or not end or end < start:
        continue
    key = (str(p.get("permit_number") or "").strip(), typ, pt[0], pt[1], start, end)
    groups[key].append(p)

multi = {k: rows for k, rows in groups.items() if len(rows) > 1}
core_conflicts = []
diagnostic_differences = collections.Counter()
for key, rows in multi.items():
    diffs = {}
    for field in CORE_FIELDS + DIAGNOSTIC_FIELDS:
        values = {str(r.get(field) or "").strip() for r in rows}
        if len(values) > 1:
            diffs[field] = sorted(values)
    if any(field in diffs for field in CORE_FIELDS):
        core_conflicts.append((key, diffs))
    for field in DIAGNOSTIC_FIELDS:
        if field in diffs:
            diagnostic_differences[field] += 1

print("PERMIT_DEDUPE_AUDIT eligible_groups", len(groups))
print("PERMIT_DEDUPE_AUDIT repeated_key_groups", len(multi))
print("PERMIT_DEDUPE_AUDIT rows_collapsible", sum(len(v) - 1 for v in multi.values()))
print("PERMIT_DEDUPE_AUDIT diagnostic_difference_groups", dict(diagnostic_differences))
print("PERMIT_DEDUPE_AUDIT core_conflicts", len(core_conflicts))
for key, diffs in core_conflicts[:10]:
    print("PERMIT_DEDUPE_CONFLICT", key, diffs)
if core_conflicts:
    raise SystemExit("Permit dedupe key collapses rows with different core operational fields")
