#!/usr/bin/env python3
"""Derive street steepness from direct intersections with official 5-ft contours.

The layer intentionally avoids a synthetic terrain surface. A street receives a
grade only where its centerline has enough direct evidence from the City's
five-foot elevation contours. The result is a route-planning estimate, not an
official engineering street-grade survey.
"""
from __future__ import annotations

import collections
import json
import math
import pathlib
import re
import time
import urllib.request

from shapely.geometry import LineString
from shapely.strtree import STRtree

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = ROOT / "_site" / "index.html"
MANIFEST = ROOT / "_site" / "data-manifest.json"

CONTOUR_DATASET_ID = "rnbg-2qxw"
CONTOUR_URL = "https://data.sf.gov/api/v3/views/rnbg-2qxw/query.geojson?accessType=DOWNLOAD"

HEADERS = {
    "User-Agent": "sf-field-conditions-map/1.0 (+https://github.com/shreyammm/sf-field-conditions-map)",
    "Accept": "application/json, application/geo+json;q=0.9, */*;q=0.1",
}

FT_PER_M = 3.280839895
LAT0 = math.radians(37.77)
M_PER_DEG_LON = 111_320.0 * math.cos(LAT0)
M_PER_DEG_LAT = 110_540.0

# Freeway mainline and freeway ramps remain useful geographic context, but the
# canvassing hill layer should not classify them as walking-route streets.
NON_CANVASS_GRADE_CLASSES = {1, 6}


def get_json(url: str, attempts: int = 3, timeout: int = 180):
    last = None
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except Exception as exc:
            last = exc
            if attempt < attempts:
                time.sleep(2 * attempt)
    raise RuntimeError(f"Failed after {attempts} attempts: {url}\n{last}") from last


def contour_elevation(feature):
    p = feature.get("properties") or {}
    for k in ("ELEVATION", "elevation"):
        try:
            if p.get(k) not in (None, ""):
                return float(p[k])
        except (TypeError, ValueError):
            pass
    return None


def to_local(coord):
    """Small-area equirectangular projection to metres; sufficient within SF."""
    lon, lat = float(coord[0]), float(coord[1])
    return (lon + 122.45) * M_PER_DEG_LON, (lat - 37.75) * M_PER_DEG_LAT


def local_line(coords):
    return LineString([to_local(c) for c in coords])


def parts(geometry):
    if not geometry:
        return []
    if geometry.get("type") == "LineString":
        return [geometry.get("coordinates") or []]
    if geometry.get("type") == "MultiLineString":
        return geometry.get("coordinates") or []
    return []


def extract_points(g):
    if g.is_empty:
        return []
    t = g.geom_type
    if t == "Point":
        return [g]
    if t == "MultiPoint":
        return list(g.geoms)
    if t == "GeometryCollection":
        out = []
        for x in g.geoms:
            out.extend(extract_points(x))
        return out
    return []


def build_contours(fc):
    geoms, elevations = [], []
    for f in fc.get("features", []):
        z = contour_elevation(f)
        if z is None:
            continue
        if abs((z / 5.0) - round(z / 5.0)) > 0.02:
            raise ValueError(f"Contour elevation {z} is not on the documented 5-ft grid")
        for p in parts(f.get("geometry")):
            if len(p) < 2:
                continue
            try:
                g = local_line(p)
            except Exception:
                continue
            if not g.is_empty and g.length > 0:
                geoms.append(g)
                elevations.append(z)
    if len(geoms) < 10_000:
        raise ValueError(f"Too few usable contour lines: {len(geoms)}")
    return geoms, elevations, STRtree(geoms)


def collapse_crossings(raw):
    if not raw:
        return [], 0
    raw = sorted(raw)
    clusters = []
    cur = [raw[0]]
    for item in raw[1:]:
        if abs(item[0] - cur[-1][0]) < 0.75:
            cur.append(item)
        else:
            clusters.append(cur)
            cur = [item]
    clusters.append(cur)

    clean = []
    ambiguous = 0
    for cluster in clusters:
        zs = sorted({round(z, 3) for _s, z in cluster})
        if max(zs) - min(zs) > 0.25:
            ambiguous += 1
            continue
        clean.append((sum(s for s, _z in cluster) / len(cluster), sum(z for _s, z in cluster) / len(cluster)))
    return clean, ambiguous


def crossing_grade(line, tree, contour_geoms, elevations):
    raw = []
    for idx in tree.query(line):
        cg = contour_geoms[int(idx)]
        if not line.intersects(cg):
            continue
        inter = line.intersection(cg)
        for pt in extract_points(inter):
            raw.append((float(line.project(pt)), float(elevations[int(idx)])))

    clean, ambiguous_clusters = collapse_crossings(raw)
    if len(clean) < 2:
        return None

    intervals = []
    rejected_jumps = 0
    rejected_steep = 0
    rise_intervals = 0
    zero_intervals = 0

    for (s1, z1), (s2, z2) in zip(clean, clean[1:]):
        ds = s2 - s1
        if ds < 4.0:
            continue
        dz = abs(z2 - z1)

        if dz <= 0.25:
            g = 0.0
            zero_intervals += 1
        elif 4.5 <= dz <= 5.5:
            g = 100.0 * (dz / FT_PER_M) / ds
            rise_intervals += 1
        else:
            rejected_jumps += 1
            continue

        if g > 45.0:
            rejected_steep += 1
            continue
        intervals.append((ds, g))

    if not intervals:
        return None

    total_span = sum(ds for ds, _g in intervals)
    if total_span < 8.0:
        return None

    weighted = sum(ds * g for ds, g in intervals) / total_span
    support_fraction = min(1.0, total_span / max(line.length, 1e-9))
    distinct_levels = len({round(z, 2) for _s, z in clean})

    if (
        len(intervals) >= 3
        and rise_intervals >= 2
        and distinct_levels >= 3
        and total_span >= 40
        and support_fraction >= 0.50
    ):
        conf = "high"
    elif (
        len(intervals) >= 2
        and rise_intervals >= 1
        and distinct_levels >= 2
        and total_span >= 20
        and support_fraction >= 0.25
    ):
        conf = "medium"
    else:
        conf = "low"

    return {
        "grade": weighted,
        "confidence": conf,
        "intervals": len(intervals),
        "rise_intervals": rise_intervals,
        "zero_intervals": zero_intervals,
        "distinct_levels": distinct_levels,
        "supported_span_m": total_span,
        "support_fraction": support_fraction,
        "ambiguous_clusters": ambiguous_clusters,
        "rejected_jumps": rejected_jumps,
        "rejected_steep": rejected_steep,
        "line_length_m": line.length,
    }


def street_class(feature):
    try:
        return int((feature.get("properties") or {}).get("classcode") or 0)
    except (TypeError, ValueError):
        return 0


def street_grade(feature, tree, contour_geoms, elevations):
    results = []
    total_length = 0.0
    for p in parts(feature.get("geometry")):
        if len(p) < 2:
            continue
        line = local_line(p)
        total_length += line.length
        r = crossing_grade(line, tree, contour_geoms, elevations)
        if r:
            results.append(r)
    if not results:
        return None

    span = sum(r["supported_span_m"] for r in results)
    g = sum(r["grade"] * r["supported_span_m"] for r in results) / span
    conf_rank = {"low": 1, "medium": 2, "high": 3}
    conf = min((r["confidence"] for r in results), key=lambda x: conf_rank[x])
    support_fraction = min(1.0, span / max(total_length, 1e-9))

    if conf == "high" and support_fraction < 0.50:
        conf = "medium"
    if conf == "medium" and support_fraction < 0.25:
        conf = "low"

    return {
        "grade": round(g, 1),
        "confidence": conf,
        "intervals": sum(r["intervals"] for r in results),
        "rise_intervals": sum(r["rise_intervals"] for r in results),
        "zero_intervals": sum(r["zero_intervals"] for r in results),
        "distinct_levels": max(r["distinct_levels"] for r in results),
        "supported_span_m": round(span, 1),
        "support_fraction": round(support_fraction, 3),
        "ambiguous_clusters": sum(r["ambiguous_clusters"] for r in results),
        "rejected_jumps": sum(r["rejected_jumps"] for r in results),
        "rejected_steep": sum(r["rejected_steep"] for r in results),
    }


def bucket(g):
    if g is None:
        return "unavailable"
    if g >= 20:
        return "20+"
    if g >= 15:
        return "15-19.9"
    if g >= 10:
        return "10-14.9"
    if g >= 5:
        return "5-9.9"
    return "<5"


def parse_payload(html):
    m = re.search(r"window\.SF_FIELD_DATA=(\{.*?\});\s*</script>", html, flags=re.S)
    if not m:
        raise ValueError("Embedded payload not found")
    return m, json.loads(m.group(1))


def main():
    html = SITE.read_text(encoding="utf-8")
    match, payload = parse_payload(html)

    contours = get_json(CONTOUR_URL)
    if contours.get("type") != "FeatureCollection":
        raise ValueError("Contour source is not GeoJSON")
    source_count = len(contours.get("features", []))
    if not 10_000 <= source_count <= 20_000:
        raise ValueError(f"Unexpected contour feature count {source_count}")
    contour_geoms, elevations, tree = build_contours(contours)

    cats = collections.Counter()
    confs = collections.Counter()
    grades = []
    top = []
    audit = collections.Counter()

    for f in payload["streets"]["features"]:
        p = f.setdefault("properties", {})
        c = street_class(f)

        if c in NON_CANVASS_GRADE_CLASSES:
            p["estimated_grade_pct"] = None
            p["grade_confidence"] = "not_applicable"
            p["grade_method"] = "direct_5ft_contour_crossings_v2"
            cats["not_applicable"] += 1
            continue

        r = street_grade(f, tree, contour_geoms, elevations)
        if r is None:
            p["estimated_grade_pct"] = None
            p["grade_confidence"] = "unavailable"
            p["grade_method"] = "direct_5ft_contour_crossings_v2"
            cats["unavailable"] += 1
            continue

        g = r["grade"]
        p["estimated_grade_pct"] = g
        p["grade_confidence"] = r["confidence"]
        p["grade_crossing_intervals"] = r["intervals"]
        p["grade_rise_intervals"] = r["rise_intervals"]
        p["grade_zero_intervals"] = r["zero_intervals"]
        p["grade_distinct_contours"] = r["distinct_levels"]
        p["grade_supported_span_m"] = r["supported_span_m"]
        p["grade_support_fraction"] = r["support_fraction"]
        p["grade_rejected_jumps"] = r["rejected_jumps"]
        p["grade_method"] = "direct_5ft_contour_crossings_v2"

        cats[bucket(g)] += 1
        confs[r["confidence"]] += 1
        grades.append(g)
        audit["ambiguous_clusters"] += r["ambiguous_clusters"]
        audit["rejected_non5ft_jumps"] += r["rejected_jumps"]
        audit["rejected_over45_intervals"] += r["rejected_steep"]
        top.append(
            (
                g,
                str(p.get("street") or ""),
                str(p.get("st_type") or ""),
                str(p.get("cnn") or ""),
                r["confidence"],
                r["intervals"],
                r["supported_span_m"],
                r["support_fraction"],
            )
        )

    graded = len(grades)
    total = len(payload["streets"]["features"])
    applicable = total - cats["not_applicable"]

    if graded < 1500:
        raise ValueError(f"Direct contour coverage unexpectedly low: {graded}/{applicable}")
    if not grades or max(grades) > 45:
        raise ValueError(f"Implausible max grade {max(grades) if grades else 'none'}")
    if cats["20+"] > 0.12 * graded:
        raise ValueError(f"Too many 20%+ segments: {cats['20+']}/{graded}")

    sg = sorted(grades)
    def pct(q):
        return sg[min(len(sg) - 1, int(q * (len(sg) - 1)))]

    top.sort(reverse=True)
    meta = {
        "dataset_id": CONTOUR_DATASET_ID,
        "source_url": CONTOUR_URL,
        "source_feature_count": source_count,
        "usable_contour_parts": len(contour_geoms),
        "contour_interval_ft": 5,
        "method_version": 2,
        "method": (
            "Directly intersect each non-freeway displayed street centerline with official "
            "5-ft contour lines. Consecutive same-elevation crossings contribute zero net "
            "rise over their span; non-zero consecutive crossings must differ by about 5 ft. "
            "Non-5-ft jumps and >45% short-span artifacts are rejected. Accepted intervals "
            "are combined by along-street distance, and coverage fraction contributes to confidence."
        ),
        "interpretation": (
            "contour-supported route-planning estimate over the directly supported portions "
            "of a segment; not an official engineering street-grade survey"
        ),
        "displayed_street_count": total,
        "applicable_street_count": applicable,
        "graded_street_count": graded,
        "unavailable_count": cats["unavailable"],
        "not_applicable_count": cats["not_applicable"],
        "confidence_counts": dict(confs),
        "category_counts": dict(cats),
        "audit_rejections": dict(audit),
        "distribution_pct": {
            "p50": pct(.5),
            "p75": pct(.75),
            "p90": pct(.9),
            "p95": pct(.95),
            "p99": pct(.99),
            "max": max(grades),
        },
        "top_20": top[:20],
    }

    pm = payload.setdefault("meta", {})
    pm["grade_source_url"] = CONTOUR_URL
    pm["grade_method_version"] = 2
    pm["graded_street_count"] = graded
    pm["grade_unavailable_count"] = cats["unavailable"]
    pm["grade_not_applicable_count"] = cats["not_applicable"]
    pm["grade_low_confidence_count"] = confs.get("low", 0) + cats["unavailable"]
    pm["grade_category_counts"] = dict(cats)
    pm["grade_confidence_counts"] = dict(confs)
    pm["grade_method"] = meta["method"]

    packed = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    SITE.write_text(html[:match.start(1)] + packed + html[match.end(1):], encoding="utf-8")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["hills"] = meta
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"hill v2 grades: {graded}/{applicable} applicable streets; unavailable={cats['unavailable']}; not_applicable={cats['not_applicable']}")
    print(f"confidence: {dict(confs)}")
    print(f"categories: {dict(cats)}")
    print(f"audit rejections: {dict(audit)}")
    print(f"distribution: {meta['distribution_pct']}")
    print("top grades:")
    for row in top[:20]:
        print(row)


if __name__ == "__main__":
    main()
