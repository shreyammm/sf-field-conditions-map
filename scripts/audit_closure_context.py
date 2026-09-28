#!/usr/bin/env python3
"""Audit location-first closure details and conservative permit-context joins."""
from __future__ import annotations

import json
import math
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = ROOT / "_site" / "index.html"
MANIFEST = ROOT / "_site" / "data-manifest.json"

html = SITE.read_text(encoding="utf-8")
manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
m = re.search(r"window\.SF_FIELD_DATA=(\{.*?\});\s*</script>", html, re.S)
if not m:
    raise SystemExit("CLOSURE CONTEXT AUDIT FAIL: embedded payload missing")
data = json.loads(m.group(1))
meta = data.get("meta") or {}
issues: list[str] = []

SUFFIXES = {
    "STREET": "ST", "AVENUE": "AVE", "BOULEVARD": "BLVD", "ROAD": "RD",
    "DRIVE": "DR", "LANE": "LN", "COURT": "CT", "PLACE": "PL",
    "TERRACE": "TER", "HIGHWAY": "HWY", "PARKWAY": "PKWY",
    "PLAZA": "PLZ", "CIRCLE": "CIR",
}


def check(ok, message):
    if not ok:
        issues.append(message)


def norm_street(value):
    s = re.sub(r"[^A-Z0-9 ]+", " ", str(value or "").upper())
    return " ".join(SUFFIXES.get(x, x) for x in s.split())


def date_only(value):
    s = str(value or "").strip()
    return s[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", s) else ""


def overlap(a0, a1, b0, b1):
    return bool(a0 and a1 and b0 and b1 and a0 <= b1 and b0 <= a1)


def permit_streets(p):
    out = set()
    for loc in p.get("source_locations") or []:
        if isinstance(loc, dict):
            n = norm_street(loc.get("street"))
            if n:
                out.add(n)
    n = norm_street(p.get("street_name"))
    if n:
        out.add(n)
    return out


def xy(coord):
    lon, lat = float(coord[0]), float(coord[1])
    return lon * 111_320.0 * math.cos(math.radians(37.77)), lat * 110_540.0


def segdist(point, a, b):
    px, py = xy(point); ax, ay = xy(a); bx, by = xy(b)
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    qx, qy = ax + t * dx, ay + t * dy
    return math.hypot(px - qx, py - qy)


def line_parts(g):
    if (g or {}).get("type") == "LineString":
        return [(g or {}).get("coordinates") or []]
    if (g or {}).get("type") == "MultiLineString":
        return (g or {}).get("coordinates") or []
    return []


def point_line_distance(point, g):
    best = float("inf")
    for part in line_parts(g):
        if len(part) == 1:
            best = min(best, math.dist(xy(point), xy(part[0])))
        for a, b in zip(part, part[1:]):
            best = min(best, segdist(point, a, b))
    return best


def marker_key(f):
    p = f.get("properties") or {}
    c = (f.get("geometry") or {}).get("coordinates") or []
    if len(c) < 2:
        return ""
    return "|".join([
        str(p.get("permit_number") or ""), str(p.get("permit_type") or ""),
        f"{float(c[0]):.7f}", f"{float(c[1]):.7f}",
        str(p.get("start_local") or p.get("permit_start_date") or ""),
        str(p.get("end_local") or p.get("permit_end_date") or ""),
    ])


check("const closureTitle=p=>" in html, "location-first closure title helper missing")
check("const closureName=p=>" not in html, "legacy case_name-first closure title helper remains")
check("SFMTA case:" in html, "case_name is not labeled as SFMTA case context")
check("Open SFMTA source record" in html, "SFMTA source link missing")
check("Open Public Works/DataSF permit record" in html, "Public Works permit source link missing")
check("Related Public Works permit context" in html, "related permit context section missing")
check("A match does not prove" in html, "causality caveat missing")
check("same normalized street" in html and "within 120 m" in html, "match rule is not explained in the UI")

threshold = float(meta.get("closure_context_match_distance_m") or 0)
cap = int(meta.get("closure_context_max_related_per_closure") or 0)
check(100 <= threshold <= 150, f"unexpected closure-context distance threshold: {threshold}")
check(1 <= cap <= 10, f"unexpected related-permit display cap: {cap}")
check(meta.get("closure_context_method") == "conservative Public Works context match; not a causal join", "closure-context method metadata missing/stale")

permit_by_key = {}
for f in (data.get("surface_permits") or {}).get("features") or []:
    k = marker_key(f)
    check(bool(k), "surface permit missing audit marker key")
    if k:
        check(k not in permit_by_key, f"duplicate surface permit marker key: {k}")
        permit_by_key[k] = f

matched_closures = 0
stored_links = 0
candidate_total = 0
for f in (data.get("closures") or {}).get("features") or []:
    p = f.get("properties") or {}
    related = p.get("related_work_permits") or []
    total = int(p.get("related_work_permit_count") or 0)
    if not related:
        check(total == 0, f"closure has related count but no stored records: {p.get('objectid')}")
        continue

    matched_closures += 1
    stored_links += len(related)
    candidate_total += total
    check(str(p.get("type") or "").strip().upper() == "SPECIAL TRAFFIC PERMIT", f"non-Special-Traffic closure has related permit context: {p.get('objectid')}")
    check(total >= len(related), f"related permit total below stored count: {p.get('objectid')}")
    check(len(related) <= cap, f"related permit storage exceeds cap: {p.get('objectid')}")

    street = norm_street(p.get("street"))
    c0 = date_only(p.get("start_local") or p.get("start_dt"))
    c1 = date_only(p.get("end_local") or p.get("end_dt"))
    seen = set()
    for r in related:
        allowed = {
            "permit_number", "permit_type", "permit_type_label", "start_local", "end_local",
            "source_descriptions", "source_locations", "distance_m", "permit_marker_key", "match_basis",
        }
        check(set(r).issubset(allowed), f"unexpected fields in compact related permit: {set(r)-allowed}")
        k = str(r.get("permit_marker_key") or "")
        check(k and k in permit_by_key, f"related permit marker does not exist: {k}")
        check(k not in seen, f"duplicate related permit on closure {p.get('objectid')}: {k}")
        seen.add(k)
        if k not in permit_by_key:
            continue
        source = permit_by_key[k]
        sp = source.get("properties") or {}
        point = (source.get("geometry") or {}).get("coordinates") or []
        check(street and street in permit_streets(sp), f"related permit street mismatch: closure {p.get('objectid')} / permit {sp.get('permit_number')}")
        p0 = date_only(sp.get("start_local") or sp.get("permit_start_date"))
        p1 = date_only(sp.get("end_local") or sp.get("permit_end_date"))
        check(overlap(c0, c1, p0, p1), f"related permit date-window mismatch: closure {p.get('objectid')} / permit {sp.get('permit_number')}")
        distance = point_line_distance(point, f.get("geometry") or {}) if len(point) >= 2 else float("inf")
        check(math.isfinite(distance) and distance <= threshold + 0.2, f"related permit exceeds distance threshold: {distance:.1f}m / closure {p.get('objectid')}")
        try:
            stored_distance = float(r.get("distance_m"))
            check(abs(stored_distance - distance) <= 0.2, f"stored/recomputed related-permit distance mismatch: {stored_distance} vs {distance:.1f}")
        except (TypeError, ValueError):
            issues.append(f"bad stored related-permit distance on closure {p.get('objectid')}")
        check("same normalized street" in str(r.get("match_basis") or ""), f"related permit match basis missing: {p.get('objectid')}")

check(matched_closures == int(meta.get("closure_context_closures_with_related_permit") or 0), "matched closure count/meta mismatch")
check(stored_links == int(meta.get("closure_context_related_permit_links_stored") or 0), "stored related permit link count/meta mismatch")
check(candidate_total == int(meta.get("closure_context_related_permit_candidates") or 0), "candidate related permit count/meta mismatch")

manifest_ctx = manifest.get("closure_context") or {}
check(manifest_ctx.get("closures_with_related_permit") == matched_closures, "manifest matched-closure count mismatch")
check(manifest_ctx.get("related_permit_links_stored") == stored_links, "manifest stored-link count mismatch")
check(manifest_ctx.get("related_permit_candidates") == candidate_total, "manifest candidate-link count mismatch")
check("not proof" in str(manifest_ctx.get("interpretation") or "").lower(), "manifest causality limitation missing")

if issues:
    print(f"CLOSURE CONTEXT AUDIT FAIL: {len(issues)} issue(s)")
    for issue in issues:
        print(" -", issue)
    raise SystemExit(1)

print("CLOSURE CONTEXT AUDIT PASS")
print(f"matched closures: {matched_closures}; candidate permit links: {candidate_total}; stored links: {stored_links}; threshold: {threshold:.0f}m")
print("case_name is contextual; location is primary; related permit links are non-causal context")
