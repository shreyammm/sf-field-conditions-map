#!/usr/bin/env python3
"""Attach conservative Public Works permit context to SFMTA closure records.

This is intentionally *context*, not a causal join. A Public Works permit is
attached only to SFMTA Special Traffic Permit closures when all three conditions
hold:
  1) the normalized street name matches,
  2) the permit authorization window overlaps the closure window by date, and
  3) the official permit point is within MATCH_DISTANCE_M of the official SFMTA
     closure line.

The UI labels these records as "related" permits and explains that a match does
not prove that the Public Works permit caused the SFMTA closure.
"""
from __future__ import annotations

import collections
import json
import math
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = ROOT / "_site" / "index.html"
MANIFEST = ROOT / "_site" / "data-manifest.json"

MATCH_DISTANCE_M = 120.0
MAX_RELATED_PERMITS = 5
MATCHABLE_CLOSURE_TYPES = {"SPECIAL TRAFFIC PERMIT"}

SUFFIXES = {
    "STREET": "ST",
    "AVENUE": "AVE",
    "BOULEVARD": "BLVD",
    "ROAD": "RD",
    "DRIVE": "DR",
    "LANE": "LN",
    "COURT": "CT",
    "PLACE": "PL",
    "TERRACE": "TER",
    "HIGHWAY": "HWY",
    "PARKWAY": "PKWY",
    "PLAZA": "PLZ",
    "CIRCLE": "CIR",
}


def parse_payload(html: str):
    m = re.search(r"window\.SF_FIELD_DATA=(\{.*?\});\s*</script>", html, flags=re.S)
    if not m:
        raise ValueError("Embedded payload not found")
    return m, json.loads(m.group(1))


def norm_street(value) -> str:
    s = re.sub(r"[^A-Z0-9 ]+", " ", str(value or "").upper())
    parts = [SUFFIXES.get(x, x) for x in s.split()]
    return " ".join(parts)


def date_only(value) -> str:
    s = str(value or "").strip()
    return s[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", s) else ""


def date_overlap(a0: str, a1: str, b0: str, b1: str) -> bool:
    return bool(a0 and a1 and b0 and b1 and a0 <= b1 and b0 <= a1)


def permit_streets(p: dict) -> set[str]:
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


def line_parts(geometry: dict):
    typ = (geometry or {}).get("type")
    coords = (geometry or {}).get("coordinates") or []
    if typ == "LineString":
        return [coords]
    if typ == "MultiLineString":
        return coords
    return []


def xy(coord):
    lon, lat = float(coord[0]), float(coord[1])
    # Accurate enough for sub-km SF matching and avoids treating longitude and
    # latitude degrees as equal distances.
    x = lon * 111_320.0 * math.cos(math.radians(37.77))
    y = lat * 110_540.0
    return x, y


def point_segment_distance_m(point, a, b) -> float:
    px, py = xy(point)
    ax, ay = xy(a)
    bx, by = xy(b)
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    qx, qy = ax + t * dx, ay + t * dy
    return math.hypot(px - qx, py - qy)


def point_line_distance_m(point, geometry: dict) -> float:
    best = float("inf")
    for part in line_parts(geometry):
        if len(part) == 1:
            best = min(best, math.dist(xy(point), xy(part[0])))
        for a, b in zip(part, part[1:]):
            try:
                best = min(best, point_segment_distance_m(point, a, b))
            except (TypeError, ValueError, IndexError):
                continue
    return best


def marker_key(feature: dict) -> str:
    p = feature.get("properties") or {}
    c = (feature.get("geometry") or {}).get("coordinates") or []
    if len(c) < 2:
        return ""
    return "|".join(
        [
            str(p.get("permit_number") or ""),
            str(p.get("permit_type") or ""),
            f"{float(c[0]):.7f}",
            f"{float(c[1]):.7f}",
            str(p.get("start_local") or p.get("permit_start_date") or ""),
            str(p.get("end_local") or p.get("permit_end_date") or ""),
        ]
    )


def compact_permit(feature: dict, distance_m: float) -> dict:
    p = feature.get("properties") or {}
    return {
        "permit_number": p.get("permit_number"),
        "permit_type": p.get("permit_type"),
        "permit_type_label": p.get("permit_type_label"),
        "start_local": p.get("start_local") or p.get("permit_start_date"),
        "end_local": p.get("end_local") or p.get("permit_end_date"),
        "source_descriptions": list(p.get("source_descriptions") or [])[:5],
        "source_locations": list(p.get("source_locations") or [])[:5],
        "distance_m": round(distance_m, 1),
        "permit_marker_key": marker_key(feature),
        "match_basis": "same normalized street + overlapping date windows + official permit point within 120 m of official closure line",
    }


def main():
    html = SITE.read_text(encoding="utf-8")
    match, payload = parse_payload(html)
    closures = (payload.get("closures") or {}).get("features") or []
    permits = (payload.get("surface_permits") or {}).get("features") or []
    if not closures or not permits:
        raise ValueError("Closure-context enrichment requires both closure and surface-permit layers")

    by_street: dict[str, list[dict]] = collections.defaultdict(list)
    for f in permits:
        for street in permit_streets(f.get("properties") or {}):
            by_street[street].append(f)

    matched_closures = 0
    stored_links = 0
    total_candidate_links = 0
    type_counts = collections.Counter()
    distances = []

    for closure in closures:
        p = closure.get("properties") or {}
        p.pop("related_work_permits", None)
        p.pop("related_work_permit_count", None)
        ctype = str(p.get("type") or "").strip().upper()
        if ctype not in MATCHABLE_CLOSURE_TYPES:
            continue
        type_counts[ctype] += 1

        street = norm_street(p.get("street"))
        c0 = date_only(p.get("start_local") or p.get("start_dt"))
        c1 = date_only(p.get("end_local") or p.get("end_dt"))
        if not street or not c0 or not c1:
            continue

        candidates = []
        seen_keys = set()
        for permit in by_street.get(street, []):
            pp = permit.get("properties") or {}
            p0 = date_only(pp.get("start_local") or pp.get("permit_start_date"))
            p1 = date_only(pp.get("end_local") or pp.get("permit_end_date"))
            if not date_overlap(c0, c1, p0, p1):
                continue
            point = (permit.get("geometry") or {}).get("coordinates") or []
            if len(point) < 2:
                continue
            distance = point_line_distance_m(point, closure.get("geometry") or {})
            if not math.isfinite(distance) or distance > MATCH_DISTANCE_M:
                continue
            key = marker_key(permit)
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)
            candidates.append((distance, permit))

        candidates.sort(key=lambda x: (x[0], marker_key(x[1])))
        total_candidate_links += len(candidates)
        if candidates:
            matched_closures += 1
            p["related_work_permit_count"] = len(candidates)
            p["related_work_permits"] = [
                compact_permit(f, distance)
                for distance, f in candidates[:MAX_RELATED_PERMITS]
            ]
            stored_links += len(p["related_work_permits"])
            distances.extend(x[0] for x in candidates[:MAX_RELATED_PERMITS])

    meta = payload.setdefault("meta", {})
    meta.update(
        {
            "closure_context_method": "conservative Public Works context match; not a causal join",
            "closure_context_matchable_types": sorted(MATCHABLE_CLOSURE_TYPES),
            "closure_context_match_distance_m": MATCH_DISTANCE_M,
            "closure_context_max_related_per_closure": MAX_RELATED_PERMITS,
            "closure_context_match_rule": "same normalized street; date windows overlap; Public Works source point <= 120 m from SFMTA source closure line",
            "closure_context_closures_considered": sum(type_counts.values()),
            "closure_context_closures_with_related_permit": matched_closures,
            "closure_context_related_permit_candidates": total_candidate_links,
            "closure_context_related_permit_links_stored": stored_links,
            "closure_context_max_stored_distance_m": round(max(distances), 1) if distances else None,
        }
    )

    packed = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    SITE.write_text(html[: match.start(1)] + packed + html[match.end(1) :], encoding="utf-8")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["closure_context"] = {
        "method": "conservative Public Works context match; not a causal join",
        "closure_types_considered": sorted(MATCHABLE_CLOSURE_TYPES),
        "distance_threshold_m": MATCH_DISTANCE_M,
        "max_related_per_closure": MAX_RELATED_PERMITS,
        "rule": "same normalized street + overlapping date windows + official Public Works permit point within 120 m of official SFMTA closure line",
        "closures_considered": sum(type_counts.values()),
        "closures_with_related_permit": matched_closures,
        "related_permit_candidates": total_candidate_links,
        "related_permit_links_stored": stored_links,
        "interpretation": "context only; a matched Public Works permit is not proof that it caused the SFMTA closure",
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if matched_closures > sum(type_counts.values()):
        raise ValueError("closure-context match count exceeds considered closure count")
    if stored_links > matched_closures * MAX_RELATED_PERMITS:
        raise ValueError("closure-context stored link count exceeds configured cap")

    print(
        "closure context: "
        f"considered={sum(type_counts.values())} special-traffic closures; "
        f"matched={matched_closures}; candidates={total_candidate_links}; stored={stored_links}; "
        f"threshold={MATCH_DISTANCE_M:.0f}m"
    )


if __name__ == "__main__":
    main()
