#!/usr/bin/env python3
"""Build a self-contained static SF Field Conditions Map.

Core public datasets are retrieved during the build, validated, trimmed to the
fields used by the UI, and embedded directly into the generated HTML. The
browser therefore makes no DataSF requests when somebody opens the map.
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import math
import pathlib
import time
import urllib.request

from shapely.geometry import GeometryCollection, LineString, MultiLineString, MultiPoint, Point, shape
from shapely.ops import linemerge
from shapely.strtree import STRtree

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "src" / "index.template.html"
OUT = ROOT / "_site"

PRECINCT_DATASET_ID = "d6x4-hefw"
LAND_USE_DATASET_ID = "c5ge-t6pj"
STREET_DATASET_ID = "3psu-pn9h"
CONTOUR_DATASET_ID = "rnbg-2qxw"

# Official City and County of San Francisco downloadable distributions.
PRECINCT_URL = "https://data.sf.gov/api/v3/views/d6x4-hefw/query.geojson?accessType=DOWNLOAD"
LAND_USE_URL = "https://data.sf.gov/api/v3/views/c5ge-t6pj/query.geojson?accessType=DOWNLOAD"
STREET_URL = "https://data.sf.gov/api/v3/views/3psu-pn9h/query.geojson?accessType=DOWNLOAD"
CONTOUR_URL = "https://data.sf.gov/api/v3/views/rnbg-2qxw/query.geojson?accessType=DOWNLOAD"

PRECINCT_FIELDS = {"prec_2022", "precinct", "id", "neigh22", "nhood", "neighborhood"}
LAND_USE_FIELDS = {
    "ludb_id", "mapblklot", "resunits", "resunits_s", "geography_type", "data_as_of",
    "address", "street", "streetname", "from_st", "to_st", "restype", "landuse",
}
STREET_FIELDS = {
    "cnn", "street", "st_type", "streetname", "f_st", "t_st", "f_node_cnn", "t_node_cnn",
    "active", "accepted", "oneway", "classcode", "jurisdiction", "layer",
    "analysis_neighborhood", "data_as_of",
}

# These can be active in the source while not representing a physical street
# that should be used as route/grade geometry. Public Works explicitly describes
# PAPER* as mapped-but-not-real streets; PSEUDO is for addressing; PRIVATE_PARKING
# is a parking-lot centerline rather than a street.
STREET_EXCLUDED_LAYERS = {
    "PAPER", "PAPER_FWYS", "PAPER_WATER", "PSEUDO", "PRIVATE_PARKING",
}

HEADERS = {
    "User-Agent": "sf-field-conditions-map/1.0 (+https://github.com/shreyammm/sf-field-conditions-map)",
    "Accept": "application/json, application/geo+json;q=0.9, */*;q=0.1",
}


def get_json(url: str, *, attempts: int = 3, timeout: int = 120):
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


def get_geojson(url: str):
    obj = get_json(url)
    if obj.get("type") != "FeatureCollection" or not isinstance(obj.get("features"), list):
        raise ValueError(f"Expected GeoJSON FeatureCollection from {url}")
    return obj


def unit_count(feature: dict):
    p = feature.get("properties") or {}
    for key in ("resunits", "resunits_s"):
        try:
            if p.get(key) not in (None, ""):
                return float(p[key])
        except (TypeError, ValueError):
            pass
    return None


def geography_type(feature: dict) -> str:
    return str((feature.get("properties") or {}).get("geography_type") or "").strip().lower()


def parcel_key(feature: dict) -> str:
    p = feature.get("properties") or {}
    return str(p.get("mapblklot") or p.get("ludb_id") or "").strip()


def precinct_key(feature: dict) -> str:
    p = feature.get("properties") or {}
    return str(p.get("prec_2022") or p.get("precinct") or p.get("id") or "").strip()


def street_active(feature: dict) -> bool:
    value = (feature.get("properties") or {}).get("active")
    if value is True:
        return True
    return str(value or "").strip().lower() in {"true", "t", "1", "yes", "y"}


def street_cnn(feature: dict) -> str:
    return str((feature.get("properties") or {}).get("cnn") or "").strip()


def street_class(feature: dict) -> int:
    value = (feature.get("properties") or {}).get("classcode")
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def street_layer(feature: dict) -> str:
    return str((feature.get("properties") or {}).get("layer") or "").strip().upper()


def street_displayable(feature: dict) -> bool:
    return street_active(feature) and street_layer(feature) not in STREET_EXCLUDED_LAYERS


def trim_feature_collection(fc: dict, allowed_fields: set[str], predicate=None) -> dict:
    features = []
    for f in fc.get("features", []):
        geom = f.get("geometry")
        if not geom:
            continue
        if predicate is not None and not predicate(f):
            continue
        props = f.get("properties") or {}
        features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": {k: props.get(k) for k in allowed_fields if k in props},
        })
    return {"type": "FeatureCollection", "features": features}


def iter_coordinates(geometry: dict):
    coords = (geometry or {}).get("coordinates")

    def walk(value):
        if (
            isinstance(value, list)
            and len(value) >= 2
            and isinstance(value[0], (int, float))
            and isinstance(value[1], (int, float))
        ):
            yield float(value[0]), float(value[1])
        elif isinstance(value, list):
            for child in value:
                yield from walk(child)

    if coords is not None:
        yield from walk(coords)


def validate_sf_coordinates(fc: dict, label: str):
    # Broad guardrail around San Francisco, including Treasure/Yerba Buena Islands.
    # This is intentionally loose; it only catches corrupt CRS/outlier data.
    min_lon, max_lon = -122.60, -122.25
    min_lat, max_lat = 37.65, 37.90
    n = 0
    for feature in fc.get("features", []):
        for lon, lat in iter_coordinates(feature.get("geometry") or {}):
            n += 1
            if not (math.isfinite(lon) and math.isfinite(lat)):
                raise ValueError(f"{label} validation failed: non-finite coordinate")
            if not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat):
                raise ValueError(f"{label} validation failed: coordinate outside SF guardrail: {lon}, {lat}")
    if n == 0:
        raise ValueError(f"{label} validation failed: no coordinates found")


def threshold_bucket(value: float) -> int:
    if value >= 200:
        return 200
    if value >= 100:
        return 100
    if value >= 50:
        return 50
    return 20


def dedupe_exact_parcels(fc: dict):
    """Resolve exact duplicate parcel records without hiding meaningful conflicts.

    Duplicate rows are auto-resolved only when the parcel ID and geometry match.
    If unit counts conflict but remain in the same map threshold bucket, retain
    one record and annotate the displayed feature with the observed range. If a
    conflict would change the displayed threshold category, fail the build for
    manual review instead of choosing a category arbitrarily.
    """
    kept = {}
    resolved = []
    for feature in fc.get("features", []):
        key = parcel_key(feature)
        if not key:
            raise ValueError("Displayed parcel record is missing both mapblklot and ludb_id")
        if key not in kept:
            kept[key] = feature
            continue

        previous = kept[key]
        if previous.get("geometry") != feature.get("geometry"):
            raise ValueError(f"Parcel {key} appears more than once with different geometries")

        prev_units = unit_count(previous)
        new_units = unit_count(feature)
        counts = [x for x in (prev_units, new_units) if x is not None]
        if not counts:
            raise ValueError(f"Parcel {key} duplicate has no usable unit count")
        lo, hi = min(counts), max(counts)
        if threshold_bucket(lo) != threshold_bucket(hi):
            raise ValueError(
                f"Parcel {key} duplicate unit-count conflict crosses a display threshold: {lo} vs {hi}"
            )

        # Keep the higher-count source row for deterministic rendering, but make
        # the source conflict explicit on the retained feature so the UI does not
        # present false precision.
        if new_units is not None and (prev_units is None or new_units > prev_units):
            kept[key] = feature
        retained = kept[key]
        rp = retained.setdefault("properties", {})
        rp["source_unit_count_min"] = int(lo)
        rp["source_unit_count_max"] = int(hi)
        rp["source_unit_count_conflict"] = lo != hi

        resolved.append({
            "parcel_id": key,
            "unit_counts_seen": sorted({int(x) for x in counts}),
            "display_bucket": f"{threshold_bucket(hi)}+",
        })

    return {"type": "FeatureCollection", "features": list(kept.values())}, resolved


def validate_precincts(fc: dict):
    features = fc["features"]
    n = len(features)
    if not (400 <= n <= 800):
        raise ValueError(f"Precinct sanity check failed: received {n} features")
    keys = [precinct_key(f) for f in features]
    if any(not key for key in keys):
        raise ValueError("Precinct validation failed: one or more precinct IDs are missing")
    if len(keys) != len(set(keys)):
        raise ValueError("Precinct validation failed: duplicate precinct IDs found")
    validate_sf_coordinates(fc, "Precinct")


def validate_multifamily(fc: dict):
    features = fc["features"]
    if len(features) < 100:
        raise ValueError(f"Multifamily sanity check failed: received only {len(features)} features")
    bad_units = [f for f in features if unit_count(f) is None or unit_count(f) < 20]
    if bad_units:
        raise ValueError(f"Multifamily validation failed: {len(bad_units)} records lack a valid 20+ unit count")
    non_parcels = [f for f in features if geography_type(f) != "parcel"]
    if non_parcels:
        raise ValueError(f"Multifamily validation failed: {len(non_parcels)} retained records are not parcel geography")
    keys = [parcel_key(f) for f in features]
    if len(keys) != len(set(keys)):
        raise ValueError("Multifamily validation failed: duplicate parcel IDs remain after deduplication")
    validate_sf_coordinates(fc, "Multifamily")


def validate_streets(fc: dict):
    features = fc["features"]
    if not (9000 <= len(features) <= 25000):
        raise ValueError(f"Street sanity check failed: received {len(features)} displayable active features")
    bad_geom = [f for f in features if (f.get("geometry") or {}).get("type") not in {"LineString", "MultiLineString"}]
    if bad_geom:
        raise ValueError(f"Street validation failed: {len(bad_geom)} non-line geometries retained")
    missing_cnn = [f for f in features if not street_cnn(f)]
    if missing_cnn:
        raise ValueError(f"Street validation failed: {len(missing_cnn)} displayed records lack CNN")
    cnns = [street_cnn(f) for f in features]
    if len(cnns) != len(set(cnns)):
        dupes = [cnn for cnn, n in collections.Counter(cnns).items() if n > 1][:10]
        raise ValueError(f"Street validation failed: duplicate displayed CNNs found, examples: {dupes}")
    leaked = [f for f in features if street_layer(f) in STREET_EXCLUDED_LAYERS]
    if leaked:
        raise ValueError(f"Street validation failed: {len(leaked)} non-physical/pseudo layers leaked into display")
    validate_sf_coordinates(fc, "Street")



def contour_elevation(feature: dict):
    value = (feature.get("properties") or {}).get("elevation")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def validate_contours(fc: dict):
    features = fc.get("features", [])
    if not (10000 <= len(features) <= 20000):
        raise ValueError(f"Contour sanity check failed: received {len(features)} features")
    bad_geom = [f for f in features if (f.get("geometry") or {}).get("type") not in {"LineString", "MultiLineString"}]
    if bad_geom:
        raise ValueError(f"Contour validation failed: {len(bad_geom)} non-line geometries")
    elevations = [contour_elevation(f) for f in features]
    if any(v is None or not math.isfinite(v) for v in elevations):
        raise ValueError("Contour validation failed: missing/non-numeric elevation values")
    non_five = [v for v in elevations if abs(v / 5 - round(v / 5)) > 1e-6]
    if non_five:
        raise ValueError(f"Contour validation failed: {len(non_five)} elevations are not on five-foot intervals")
    if min(elevations) < -100 or max(elevations) > 2000:
        raise ValueError(f"Contour validation failed: implausible elevation range {min(elevations)}..{max(elevations)} ft")
    validate_sf_coordinates(fc, "Contour")


def line_length_ft(geometry: dict) -> float:
    """Approximate horizontal polyline length in feet using local WGS84 scale."""
    gtype = (geometry or {}).get("type")
    parts = [geometry.get("coordinates", [])] if gtype == "LineString" else geometry.get("coordinates", []) if gtype == "MultiLineString" else []
    total_m = 0.0
    for part in parts:
        for a, b in zip(part, part[1:]):
            lon1, lat1 = float(a[0]), float(a[1])
            lon2, lat2 = float(b[0]), float(b[1])
            mid_lat = math.radians((lat1 + lat2) / 2)
            dx = (lon2 - lon1) * 111320.0 * math.cos(mid_lat)
            dy = (lat2 - lat1) * 111320.0
            total_m += math.hypot(dx, dy)
    return total_m * 3.28084


def _intersection_points(geom):
    if geom.is_empty:
        return []
    if isinstance(geom, Point):
        return [geom]
    if isinstance(geom, MultiPoint):
        return list(geom.geoms)
    if isinstance(geom, GeometryCollection):
        out = []
        for child in geom.geoms:
            out.extend(_intersection_points(child))
        return out
    if isinstance(geom, LineString):
        coords = list(geom.coords)
        return [Point(coords[0]), Point(coords[-1])] if coords else []
    if isinstance(geom, MultiLineString):
        out = []
        for child in geom.geoms:
            out.extend(_intersection_points(child))
        return out
    return []


def _single_line_geometry(geometry: dict):
    geom = shape(geometry)
    if isinstance(geom, LineString):
        return geom
    if isinstance(geom, MultiLineString):
        merged = linemerge(geom)
        if isinstance(merged, LineString):
            return merged
        if isinstance(merged, MultiLineString) and merged.geoms:
            return max(merged.geoms, key=lambda g: g.length)
    return None


def _contour_crossings(street_feature: dict, contour_geoms, contour_elevations, contour_tree):
    line = _single_line_geometry(street_feature.get("geometry") or {})
    total_ft = line_length_ft(street_feature.get("geometry") or {})
    if line is None or total_ft <= 0:
        return total_ft, []

    crossings = []
    for idx in contour_tree.query(line, predicate="intersects"):
        inter = line.intersection(contour_geoms[int(idx)])
        elevation = float(contour_elevations[int(idx)])
        for point in _intersection_points(inter):
            position_ft = line.project(point, normalized=True) * total_ft
            crossings.append((position_ft, elevation))
    crossings.sort()

    # Remove exact/tiny duplicate intersection artifacts from coincident vertices.
    cleaned = []
    for position_ft, elevation in crossings:
        if cleaned and abs(position_ft - cleaned[-1][0]) < 0.5 and abs(elevation - cleaned[-1][1]) < 0.01:
            continue
        cleaned.append((position_ft, elevation))
    return total_ft, cleaned


def _monotonic_contour_runs(crossings):
    if not crossings:
        return []
    cleaned = [crossings[0]]
    for crossing in crossings[1:]:
        if crossing[1] == cleaned[-1][1] and crossing[0] - cleaned[-1][0] < 5:
            cleaned[-1] = crossing
        else:
            cleaned.append(crossing)

    runs = []
    current = [cleaned[0]]
    direction = 0
    for crossing in cleaned[1:]:
        delta = crossing[1] - current[-1][1]
        sign = 1 if delta > 0 else -1 if delta < 0 else 0
        if sign == 0 or direction == 0 or sign == direction:
            current.append(crossing)
            if sign:
                direction = sign
        else:
            if len(current) >= 2:
                runs.append(current)
            current = [current[-1], crossing]
            direction = sign
    if len(current) >= 2:
        runs.append(current)
    return runs


def _hill_metrics_for_street(street_feature: dict, contour_geoms, contour_elevations, contour_tree):
    """Estimate terrain grade from crossings of official five-foot contours.

    The segment-average fallback conservatively uses only the observed contour
    elevation range across the whole street segment; it does not invent endpoint
    elevations. The peak
    estimate searches monotonic contour runs for the steepest window spanning at
    least 80 horizontal feet. That window length suppresses single-contour noise
    while closely reproducing published steep-block examples used for validation.
    """
    total_ft, crossings = _contour_crossings(street_feature, contour_geoms, contour_elevations, contour_tree)
    if total_ft <= 0:
        return {"avg": None, "peak": None, "display": None, "crossings": 0, "basis": "unavailable"}

    if crossings:
        elevations = [z for _, z in crossings]
        average = (max(elevations) - min(elevations)) / total_ft * 100.0
    else:
        average = 0.0

    peak = 0.0
    for run in _monotonic_contour_runs(crossings):
        for i in range(len(run)):
            for j in range(i + 1, len(run)):
                horizontal = run[j][0] - run[i][0]
                vertical = abs(run[j][1] - run[i][1])
                if horizontal >= 80.0 and vertical >= 5.0:
                    peak = max(peak, vertical / horizontal * 100.0)

    if peak > 0:
        display = peak
        basis = "peak_80ft_window"
    else:
        display = average
        basis = "segment_average_fallback"

    return {
        "avg": round(average, 1),
        "peak": round(peak, 1) if peak > 0 else None,
        "display": round(display, 1),
        "crossings": len(crossings),
        "basis": basis,
    }


def _find_street_segment(streets: dict, street_name: str, endpoint_a: str, endpoint_b: str):
    target = street_name.strip().upper()
    endpoints = {endpoint_a.strip().upper(), endpoint_b.strip().upper()}
    for feature in streets.get("features", []):
        p = feature.get("properties") or {}
        name = " ".join(str(v).strip() for v in (p.get("street"), p.get("st_type")) if v).upper()
        source_endpoints = {str(p.get("f_st") or "").strip().upper(), str(p.get("t_st") or "").strip().upper()}
        if name == target and source_endpoints == endpoints:
            return feature
    return None


def derive_hills(streets: dict, contours: dict):
    validate_contours(contours)
    contour_geoms = [shape(f["geometry"]) for f in contours["features"]]
    contour_elevations = [contour_elevation(f) for f in contours["features"]]
    contour_tree = STRtree(contour_geoms)

    grade_bins = collections.Counter()
    route_grade_bins = collections.Counter()
    unavailable = 0
    freeway_context = 0
    for feature in streets.get("features", []):
        p = feature.setdefault("properties", {})
        metric = _hill_metrics_for_street(feature, contour_geoms, contour_elevations, contour_tree)
        p["hill_avg_grade_pct"] = metric["avg"]
        p["hill_peak_grade_pct"] = metric["peak"]
        p["hill_grade_pct"] = metric["display"]
        p["hill_grade_basis"] = metric["basis"]
        p["hill_contour_crossings"] = metric["crossings"]
        p["hill_route_context"] = not (street_class(feature) in {1, 6} or street_layer(feature) == "FREEWAYS")
        if not p["hill_route_context"]:
            freeway_context += 1
        grade = metric["display"]
        if grade is None:
            unavailable += 1
            grade_bins["unavailable"] += 1
            if p["hill_route_context"]:
                route_grade_bins["unavailable"] += 1
        else:
            if grade < 5:
                label = "0-4.9"
            elif grade < 10:
                label = "5-9.9"
            elif grade < 15:
                label = "10-14.9"
            elif grade < 20:
                label = "15-19.9"
            else:
                label = "20+"
            grade_bins[label] += 1
            if p["hill_route_context"]:
                route_grade_bins[label] += 1

    # Broad regression checks against well-documented steep blocks. The contour
    # method estimates terrain pitch, not a legal/engineering survey, so these are
    # intentionally wide guardrails rather than exact assertions.
    benchmark_specs = [
        ("FILBERT ST", "HYDE ST", "LEAVENWORTH ST", 31.5, 20, 45),
        ("22ND ST", "CHURCH ST", "VICKSBURG ST", 31.5, 20, 45),
        ("JONES ST", "UNION ST", "FILBERT ST", 29.0, 18, 45),
        ("DUBOCE AVE", "ALPINE TER", "BUENA VISTA AVE EAST", 27.9, 15, 45),
    ]
    benchmarks = []
    for street_name, a, b, reference, low, high in benchmark_specs:
        feature = _find_street_segment(streets, street_name, a, b)
        if feature is None:
            raise ValueError(f"Hill validation segment missing: {street_name} between {a} and {b}")
        estimate = (feature.get("properties") or {}).get("hill_grade_pct")
        if estimate is None or not (low <= estimate <= high):
            raise ValueError(
                f"Hill validation out of range for {street_name} between {a} and {b}: {estimate}%"
            )
        benchmarks.append({
            "street": street_name,
            "between": [a, b],
            "reference_peak_grade_pct": reference,
            "derived_grade_pct": estimate,
        })

    return {
        "feature_count": len(streets.get("features", [])),
        "grade_bin_counts": dict(grade_bins),
        "route_grade_bin_counts": dict(route_grade_bins),
        "unavailable_count": unavailable,
        "freeway_context_count": freeway_context,
        "validation_benchmarks": benchmarks,
        "method": "five-foot contour crossings; peak monotonic grade over >=80 horizontal ft, segment-average fallback",
    }

def metadata(dataset_id: str) -> dict:
    try:
        return get_json(f"https://data.sf.gov/api/views/{dataset_id}", attempts=2, timeout=30)
    except Exception as exc:
        print(f"warning: metadata unavailable for {dataset_id}: {exc}")
        return {}


def iso_from_unix(value):
    try:
        return dt.datetime.fromtimestamp(int(value), tz=dt.timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        return None


def newest_data_as_of(fc: dict):
    vals = []
    for f in fc["features"]:
        v = (f.get("properties") or {}).get("data_as_of")
        if v:
            vals.append(str(v))
    return max(vals) if vals else None


def threshold_counts(fc: dict):
    return {str(t): sum((unit_count(f) or 0) >= t for f in fc["features"]) for t in (20, 50, 100, 200)}


def fetch_precincts():
    fc = get_geojson(PRECINCT_URL)
    source = {
        "mode": "official",
        "label": "SF Department of Elections / DataSF",
        "url": PRECINCT_URL,
        "dataset_id": PRECINCT_DATASET_ID,
    }
    fc = trim_feature_collection(fc, PRECINCT_FIELDS)
    validate_precincts(fc)
    return fc, source


def fetch_multifamily():
    raw = get_geojson(LAND_USE_URL)
    source_20plus = [f for f in raw.get("features", []) if f.get("geometry") and (unit_count(f) or 0) >= 20]
    geography_counts = collections.Counter(geography_type(f) or "unknown" for f in source_20plus)
    fc = trim_feature_collection(
        raw,
        LAND_USE_FIELDS,
        predicate=lambda f: (unit_count(f) or 0) >= 20 and geography_type(f) == "parcel",
    )
    del raw
    fc, duplicate_parcels_resolved = dedupe_exact_parcels(fc)
    validate_multifamily(fc)
    excluded = {
        "analytical": int(geography_counts.get("analytical", 0)),
        "multiple_parcels": int(geography_counts.get("multiple_parcels", 0)),
        "unknown": int(geography_counts.get("unknown", 0)),
    }
    return (
        fc,
        {"mode": "official", "label": "SF Planning / DataSF", "url": LAND_USE_URL, "dataset_id": LAND_USE_DATASET_ID},
        dict(geography_counts),
        excluded,
        duplicate_parcels_resolved,
    )


def fetch_streets():
    raw = get_geojson(STREET_URL)
    source_count = len(raw.get("features", []))
    active = [f for f in raw.get("features", []) if f.get("geometry") and street_active(f)]
    active_count = len(active)
    excluded_layer_counts = collections.Counter(
        street_layer(f) or "UNKNOWN" for f in active if street_layer(f) in STREET_EXCLUDED_LAYERS
    )
    fc = trim_feature_collection(raw, STREET_FIELDS, predicate=street_displayable)
    del raw
    validate_streets(fc)
    classes = collections.Counter(str(street_class(f)) for f in fc["features"])
    return (
        fc,
        {"mode": "official", "label": "SF Public Works / DataSF", "url": STREET_URL, "dataset_id": STREET_DATASET_ID},
        source_count,
        active_count,
        dict(classes),
        dict(excluded_layer_counts),
    )


def main():
    if not TEMPLATE.exists():
        raise SystemExit(f"Missing template: {TEMPLATE}")

    retrieved = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    precincts, precinct_source = fetch_precincts()
    multifamily, multifamily_source, geography_counts, excluded, duplicate_parcels_resolved = fetch_multifamily()
    (
        streets,
        street_source,
        street_source_count,
        street_active_count,
        street_class_counts,
        street_excluded_layer_counts,
    ) = fetch_streets()

    contours = get_geojson(CONTOUR_URL)
    hill_stats = derive_hills(streets, contours)
    contour_feature_count = len(contours.get("features", []))
    del contours

    p_meta = metadata(PRECINCT_DATASET_ID)
    m_meta = metadata(LAND_USE_DATASET_ID)
    s_meta = metadata(STREET_DATASET_ID)
    c_meta = metadata(CONTOUR_DATASET_ID)
    bins = threshold_counts(multifamily)

    manifest = {
        "retrieved_at": retrieved,
        "precincts": {
            **precinct_source,
            "feature_count": len(precincts["features"]),
            "source_rows_updated_at": iso_from_unix(p_meta.get("rowsUpdatedAt")),
        },
        "streets": {
            **street_source,
            "feature_count": len(streets["features"]),
            "source_feature_count_including_retired": street_source_count,
            "source_active_feature_count": street_active_count,
            "display_filter": "active = true; exclude PAPER, PAPER_FWYS, PAPER_WATER, PSEUDO, PRIVATE_PARKING layers",
            "excluded_layer_counts": street_excluded_layer_counts,
            "classcode_counts": street_class_counts,
            "data_as_of": newest_data_as_of(streets),
            "source_rows_updated_at": iso_from_unix(s_meta.get("rowsUpdatedAt")),
        },
        "hills": {
            "mode": "derived from official public data",
            "label": "Derived from SF Public Works street centerlines + DataSF Elevation Contours",
            "street_dataset_id": STREET_DATASET_ID,
            "contour_dataset_id": CONTOUR_DATASET_ID,
            "contour_url": CONTOUR_URL,
            "contour_feature_count": contour_feature_count,
            "contour_interval_ft": 5,
            "grade_metric": "estimated terrain grade magnitude; peak monotonic window over >=80 horizontal ft when available, otherwise segment-average fallback",
            "grade_bin_counts": hill_stats["grade_bin_counts"],
            "route_grade_bin_counts": hill_stats["route_grade_bin_counts"],
            "unavailable_count": hill_stats["unavailable_count"],
            "freeway_context_count": hill_stats["freeway_context_count"],
            "validation_benchmarks": hill_stats["validation_benchmarks"],
            "source_rows_updated_at": iso_from_unix(c_meta.get("rowsUpdatedAt")),
        },
        "multifamily": {
            **multifamily_source,
            "feature_count": len(multifamily["features"]),
            "display_filter": "resunits >= 20 AND geography_type = parcel",
            "deduplication_rule": "same parcel ID + identical geometry => one record; conflicting unit counts in same display bucket => show observed range; threshold-crossing conflict => fail build",
            "duplicate_parcels_resolved": duplicate_parcels_resolved,
            "threshold_counts": bins,
            "source_20plus_counts_by_geography_type": geography_counts,
            "excluded_geographies": excluded,
            "data_as_of": newest_data_as_of(multifamily),
            "source_rows_updated_at": iso_from_unix(m_meta.get("rowsUpdatedAt")),
        },
    }

    payload = {
        "meta": {
            "retrieved_at": retrieved,
            "precinct_source_mode": precinct_source["mode"],
            "precinct_source_url": precinct_source["url"],
            "street_source_url": street_source["url"],
            "street_class_counts": street_class_counts,
            "street_source_active_count": street_active_count,
            "street_excluded_layer_counts": street_excluded_layer_counts,
            "street_data_as_of": manifest["streets"]["data_as_of"],
            "street_source_rows_updated_at": manifest["streets"]["source_rows_updated_at"],
            "hill_contour_source_url": CONTOUR_URL,
            "hill_contour_source_rows_updated_at": manifest["hills"]["source_rows_updated_at"],
            "hill_grade_bin_counts": hill_stats["grade_bin_counts"],
            "hill_route_grade_bin_counts": hill_stats["route_grade_bin_counts"],
            "hill_validation_benchmarks": hill_stats["validation_benchmarks"],
            "multifamily_source_url": multifamily_source["url"],
            "multifamily_data_as_of": manifest["multifamily"]["data_as_of"],
            "multifamily_display_filter": manifest["multifamily"]["display_filter"],
            "excluded_geographies": excluded,
            "duplicate_parcels_resolved": duplicate_parcels_resolved,
            "threshold_counts": bins,
        },
        "precincts": precincts,
        "streets": streets,
        "multifamily": multifamily,
    }

    packed = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    packed = packed.replace("</", "<\\/")
    injection = "window.SF_FIELD_DATA=" + packed + ";"

    template = TEMPLATE.read_text(encoding="utf-8")
    marker = "/*__SF_FIELD_DATA__*/"
    if template.count(marker) != 1:
        raise ValueError("Template must contain the data marker exactly once")
    html = template.replace(marker, injection)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "index.html").write_text(html, encoding="utf-8")
    (OUT / "data-manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (OUT / ".nojekyll").write_text("", encoding="utf-8")

    print(
        f"built {OUT / 'index.html'} with {len(precincts['features'])} precincts, "
        f"{len(streets['features'])} displayed street segments ({street_active_count} active in source), "
        f"and {len(multifamily['features'])} unique parcel-level 20+ unit records"
    )
    print(f"street excluded layers: {street_excluded_layer_counts}")
    print(f"street class counts: {street_class_counts}")
    print(f"hill grade bins: {hill_stats['grade_bin_counts']}")
    print(f"hill route-context grade bins: {hill_stats['route_grade_bin_counts']}")
    print(f"hill validation benchmarks: {hill_stats['validation_benchmarks']}")
    print(f"threshold counts: {bins}")
    print(f"source 20+ geography counts: {dict(geography_counts)}")
    print(f"excluded from apartment layer: {excluded}")
    print(f"duplicate parcels resolved: {duplicate_parcels_resolved}")
    print(f"manifest: {OUT / 'data-manifest.json'}")


if __name__ == "__main__":
    main()
