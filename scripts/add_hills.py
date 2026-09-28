#!/usr/bin/env python3
"""Derive street steepness from official 5-ft SF elevation contours.

This script runs after scripts/build_site.py. It reads the already bundled street
GeoJSON from _site/index.html, downloads the official DataSF elevation-contour
source, estimates an average absolute grade for each displayed street segment,
annotates the street properties, updates the embedded payload and manifest, and
leaves all geometry self-contained for GitHub Pages.

The result is an analytical estimate for route planning, not an official survey
or engineering street-grade record.
"""
from __future__ import annotations

import collections
import json
import math
import pathlib
import re
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = ROOT / "_site" / "index.html"
MANIFEST = ROOT / "_site" / "data-manifest.json"

CONTOUR_DATASET_ID = "rnbg-2qxw"
CONTOUR_URL = "https://data.sf.gov/api/v3/views/rnbg-2qxw/query.geojson?accessType=DOWNLOAD"
HEADERS = {
    "User-Agent": "sf-field-conditions-map/1.0 (+https://github.com/shreyammm/sf-field-conditions-map)",
    "Accept": "application/json, application/geo+json;q=0.9, */*;q=0.1",
}

LAT0 = math.radians(37.77)
M_PER_DEG_LON = 111_320.0 * math.cos(LAT0)
M_PER_DEG_LAT = 110_540.0
LON0 = -122.45
LAT_REF = 37.75
FT_PER_M = 3.280839895

GRID_M = 80.0
CONTOUR_SAMPLE_M = 18.0
SEARCH_RADIUS_M = 220.0
MAX_LEVELS = 10
STREET_SAMPLES = 5


def get_json(url: str, attempts: int = 3, timeout: int = 180):
    last = None
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.load(response)
        except Exception as exc:
            last = exc
            if attempt < attempts:
                time.sleep(attempt * 2)
    raise RuntimeError(f"Failed after {attempts} attempts: {url}\n{last}") from last


def xy(coord):
    lon, lat = float(coord[0]), float(coord[1])
    return (lon - LON0) * M_PER_DEG_LON, (lat - LAT_REF) * M_PER_DEG_LAT


def elevation(feature):
    p = feature.get("properties") or {}
    for key in ("elevation", "ELEVATION"):
        if p.get(key) not in (None, ""):
            try:
                return float(p[key])
            except (TypeError, ValueError):
                pass
    return None


def line_parts(geometry):
    if not geometry:
        return []
    t = geometry.get("type")
    c = geometry.get("coordinates") or []
    if t == "LineString":
        return [c]
    if t == "MultiLineString":
        return c
    return []


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def sample_polyline(coords, spacing_m):
    if len(coords) < 2:
        return [xy(coords[0])] if coords else []
    pts = [xy(c) for c in coords]
    out = [pts[0]]
    carry = 0.0
    prev = pts[0]
    for cur in pts[1:]:
        seg = dist(prev, cur)
        if seg <= 0:
            prev = cur
            continue
        ux, uy = (cur[0] - prev[0]) / seg, (cur[1] - prev[1]) / seg
        remaining = seg
        start = prev
        need = spacing_m - carry
        while remaining >= need:
            q = (start[0] + ux * need, start[1] + uy * need)
            out.append(q)
            start = q
            remaining -= need
            carry = 0.0
            need = spacing_m
        carry += remaining
        prev = cur
    if dist(out[-1], pts[-1]) > 1.0:
        out.append(pts[-1])
    return out


def build_contour_index(fc):
    grid = collections.defaultdict(list)
    elevations = set()
    n_samples = 0
    for f in fc.get("features", []):
        z = elevation(f)
        if z is None:
            continue
        elevations.add(z)
        for part in line_parts(f.get("geometry")):
            for x, y in sample_polyline(part, CONTOUR_SAMPLE_M):
                cell = (math.floor(x / GRID_M), math.floor(y / GRID_M))
                grid[cell].append((x, y, z))
                n_samples += 1
    if n_samples < 10_000 or len(elevations) < 20:
        raise ValueError(f"Contour index looks incomplete: {n_samples} samples, {len(elevations)} levels")
    return grid, n_samples, len(elevations)


def nearby_samples(grid, point):
    x, y = point
    cx, cy = math.floor(x / GRID_M), math.floor(y / GRID_M)
    cells = math.ceil(SEARCH_RADIUS_M / GRID_M)
    best_by_level = {}
    for dx in range(-cells, cells + 1):
        for dy in range(-cells, cells + 1):
            for sx, sy, z in grid.get((cx + dx, cy + dy), ()):
                d = math.hypot(sx - x, sy - y)
                if d > SEARCH_RADIUS_M:
                    continue
                old = best_by_level.get(z)
                if old is None or d < old[0]:
                    best_by_level[z] = (d, sx, sy)
    nearest = sorted((d, z, sx, sy) for z, (d, sx, sy) in best_by_level.items())
    return nearest[:MAX_LEVELS]


def estimate_elevation(grid, point):
    candidates = nearby_samples(grid, point)
    if len(candidates) < 3:
        return None, None, len(candidates)
    num = den = 0.0
    for d, z, _sx, _sy in candidates:
        w = 1.0 / ((d + 6.0) ** 2)
        num += w * z
        den += w
    return num / den, candidates[0][0], len(candidates)


def polyline_length_xy(part):
    pts = [xy(c) for c in part]
    return sum(dist(a, b) for a, b in zip(pts, pts[1:]))


def point_along(part, fraction):
    pts = [xy(c) for c in part]
    if len(pts) == 1:
        return pts[0]
    lens = [dist(a, b) for a, b in zip(pts, pts[1:])]
    total = sum(lens)
    if total <= 0:
        return pts[0]
    target = max(0.0, min(1.0, fraction)) * total
    run = 0.0
    for a, b, seg in zip(pts, pts[1:], lens):
        if run + seg >= target:
            q = (target - run) / seg if seg else 0
            return a[0] + q * (b[0] - a[0]), a[1] + q * (b[1] - a[1])
        run += seg
    return pts[-1]


def estimate_part_grade(grid, part):
    length_m = polyline_length_xy(part)
    if length_m < 8:
        return None
    samples = []
    for i in range(STREET_SAMPLES):
        f = i / (STREET_SAMPLES - 1)
        pt = point_along(part, f)
        z, nearest_m, levels = estimate_elevation(grid, pt)
        if z is None:
            return None
        samples.append((f * length_m, z, nearest_m, levels))
    total_abs_ft = 0.0
    for a, b in zip(samples, samples[1:]):
        total_abs_ft += abs(b[1] - a[1])
    grade = 100.0 * total_abs_ft / (length_m * FT_PER_M)
    nearest = max(s[2] for s in samples)
    min_levels = min(s[3] for s in samples)
    return grade, length_m, nearest, min_levels


def estimate_street_grade(grid, feature):
    results = []
    for part in line_parts(feature.get("geometry")):
        r = estimate_part_grade(grid, part)
        if r:
            results.append(r)
    if not results:
        return None
    total_len = sum(r[1] for r in results)
    grade = sum(r[0] * r[1] for r in results) / total_len
    farthest = max(r[2] for r in results)
    min_levels = min(r[3] for r in results)
    if farthest <= 35 and min_levels >= 5:
        confidence = "high"
    elif farthest <= 75 and min_levels >= 4:
        confidence = "medium"
    else:
        confidence = "low"
    return round(grade, 1), confidence, round(farthest, 1), min_levels


def grade_bucket(g):
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
        raise ValueError("Could not locate embedded SF_FIELD_DATA payload")
    return m, json.loads(m.group(1))


def main():
    if not SITE.exists() or not MANIFEST.exists():
        raise SystemExit("Run scripts/build_site.py first")
    html = SITE.read_text(encoding="utf-8")
    match, payload = parse_payload(html)
    contours = get_json(CONTOUR_URL)
    if contours.get("type") != "FeatureCollection":
        raise ValueError("Elevation source was not a GeoJSON FeatureCollection")
    source_count = len(contours.get("features", []))
    if not (10_000 <= source_count <= 20_000):
        raise ValueError(f"Unexpected contour feature count: {source_count}")
    grid, contour_samples, contour_levels = build_contour_index(contours)

    categories = collections.Counter()
    confidence_counts = collections.Counter()
    graded = 0
    missing = 0
    grades = []
    for f in payload.get("streets", {}).get("features", []):
        p = f.setdefault("properties", {})
        result = estimate_street_grade(grid, f)
        if result is None:
            p["estimated_grade_pct"] = None
            p["grade_confidence"] = "unavailable"
            p["grade_method"] = "5ft_contours_idw_5point_abs"
            missing += 1
            categories["unavailable"] += 1
            continue
        g, conf, nearest, levels = result
        if not (0 <= g <= 45):
            raise ValueError(f"Implausible derived grade {g}% for CNN {p.get('cnn')}")
        p["estimated_grade_pct"] = g
        p["grade_confidence"] = conf
        p["grade_nearest_contour_m"] = nearest
        p["grade_min_distinct_levels"] = levels
        p["grade_method"] = "5ft_contours_idw_5point_abs"
        graded += 1
        grades.append(g)
        categories[grade_bucket(g)] += 1
        confidence_counts[conf] += 1

    if graded < 0.90 * len(payload["streets"]["features"]):
        raise ValueError(f"Too few street grades derived: {graded}/{len(payload['streets']['features'])}")

    sorted_grades = sorted(grades)
    def pct(q):
        if not sorted_grades:
            return None
        return sorted_grades[min(len(sorted_grades)-1, int(q * (len(sorted_grades)-1)))]

    grade_meta = {
        "dataset_id": CONTOUR_DATASET_ID,
        "source_url": CONTOUR_URL,
        "source_feature_count": source_count,
        "contour_interval_ft": 5,
        "contour_samples_used": contour_samples,
        "distinct_contour_levels": contour_levels,
        "method": "Five points are sampled along each displayed street part. Elevation at each point is estimated by inverse-distance weighting the nearest sample from up to 10 distinct 5-ft contour levels within 220 m. Estimated average grade is total absolute elevation change between successive street samples divided by horizontal street length.",
        "interpretation": "analytical estimate for route planning; not an official engineering street-grade survey",
        "graded_street_count": graded,
        "unavailable_count": missing,
        "confidence_counts": dict(confidence_counts),
        "category_counts": dict(categories),
        "distribution_pct": {"p50": pct(.50), "p75": pct(.75), "p90": pct(.90), "p95": pct(.95), "p99": pct(.99), "max": max(grades) if grades else None},
    }
    payload.setdefault("meta", {})["grade_source_url"] = CONTOUR_URL
    payload["meta"]["graded_street_count"] = graded
    payload["meta"]["grade_low_confidence_count"] = confidence_counts.get("low", 0) + missing
    payload["meta"]["grade_category_counts"] = dict(categories)
    payload["meta"]["grade_confidence_counts"] = dict(confidence_counts)
    payload["meta"]["grade_method"] = grade_meta["method"]

    packed = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    new_html = html[:match.start(1)] + packed + html[match.end(1):]
    SITE.write_text(new_html, encoding="utf-8")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["hills"] = grade_meta
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"derived grades for {graded}/{len(payload['streets']['features'])} displayed street segments; unavailable={missing}")
    print(f"grade confidence: {dict(confidence_counts)}")
    print(f"grade categories: {dict(categories)}")
    print(f"grade distribution: {grade_meta['distribution_pct']}")


if __name__ == "__main__":
    main()
