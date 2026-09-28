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
import pathlib
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "src" / "index.template.html"
OUT = ROOT / "_site"

PRECINCT_DATASET_ID = "d6x4-hefw"
LAND_USE_DATASET_ID = "c5ge-t6pj"

# Official downloadable distributions. These work better in CI than the
# browser-oriented Socrata /resource endpoint.
PRECINCT_URL = "https://data.sf.gov/api/v3/views/d6x4-hefw/query.geojson?accessType=DOWNLOAD"
LAND_USE_URL = "https://data.sf.gov/api/v3/views/c5ge-t6pj/query.geojson?accessType=DOWNLOAD"
PRECINCT_FALLBACK_URL = (
    "https://raw.githubusercontent.com/sfbay/datadiver/"
    "0eca631307a658be1e2b55ec3acde18f88ee11ec/"
    "public/data/elections/geo/prec-2022.geojson"
)

PRECINCT_FIELDS = {"prec_2022", "precinct", "id", "neigh22", "nhood", "neighborhood"}
LAND_USE_FIELDS = {
    "ludb_id",
    "mapblklot",
    "resunits",
    "resunits_s",
    "geography_type",
    "data_as_of",
    # Keep route-useful descriptive fields when present in the current source.
    "address",
    "street",
    "streetname",
    "from_st",
    "to_st",
    "restype",
    "landuse",
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


def trim_feature_collection(fc: dict, allowed_fields: set[str], predicate=None) -> dict:
    features = []
    for f in fc.get("features", []):
        geom = f.get("geometry")
        if not geom:
            continue
        if predicate is not None and not predicate(f):
            continue
        props = f.get("properties") or {}
        features.append(
            {
                "type": "Feature",
                "geometry": geom,
                "properties": {k: props.get(k) for k in allowed_fields if k in props},
            }
        )
    return {"type": "FeatureCollection", "features": features}


def validate_precincts(fc: dict):
    n = len(fc["features"])
    if not (400 <= n <= 800):
        raise ValueError(f"Precinct sanity check failed: received {n} features")


def validate_multifamily(fc: dict):
    features = fc["features"]
    if len(features) < 100:
        raise ValueError(f"Multifamily sanity check failed: received only {len(features)} features")
    bad_units = [f for f in features if unit_count(f) is None or unit_count(f) < 20]
    if bad_units:
        raise ValueError(
            f"Multifamily validation failed: {len(bad_units)} records lack a valid 20+ unit count"
        )
    non_parcels = [f for f in features if geography_type(f) != "parcel"]
    if non_parcels:
        raise ValueError(
            f"Multifamily validation failed: {len(non_parcels)} retained records are not parcel geography"
        )


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


def fetch_precincts():
    try:
        fc = get_geojson(PRECINCT_URL)
        source = {
            "mode": "official",
            "label": "SF Department of Elections / DataSF",
            "url": PRECINCT_URL,
            "dataset_id": PRECINCT_DATASET_ID,
        }
    except Exception as exc:
        print(f"warning: official precinct download failed; using documented public snapshot: {exc}")
        fc = get_geojson(PRECINCT_FALLBACK_URL)
        source = {
            "mode": "fallback_snapshot",
            "label": "Versioned public snapshot derived from SF Department of Elections data",
            "url": PRECINCT_FALLBACK_URL,
            "dataset_id": PRECINCT_DATASET_ID,
        }
    fc = trim_feature_collection(fc, PRECINCT_FIELDS)
    validate_precincts(fc)
    return fc, source


def fetch_multifamily():
    raw = get_geojson(LAND_USE_URL)

    # First count all 20+ unit source records by SF Planning geography type.
    source_20plus = [
        f for f in raw.get("features", []) if f.get("geometry") and (unit_count(f) or 0) >= 20
    ]
    geography_counts = collections.Counter(geography_type(f) or "unknown" for f in source_20plus)

    # For canvassing-route use, precision matters more than showing every
    # planning aggregate. Retain only actual parcel-level geometries. Broad
    # "analytical" areas caused misleading filled regions (e.g. Presidio);
    # "multiple_parcels" are also withheld until we design a representation
    # that does not imply one giant building/property footprint.
    fc = trim_feature_collection(
        raw,
        LAND_USE_FIELDS,
        predicate=lambda f: (unit_count(f) or 0) >= 20 and geography_type(f) == "parcel",
    )
    del raw
    validate_multifamily(fc)

    excluded = {
        "analytical": int(geography_counts.get("analytical", 0)),
        "multiple_parcels": int(geography_counts.get("multiple_parcels", 0)),
        "unknown": int(geography_counts.get("unknown", 0)),
    }
    return (
        fc,
        {
            "mode": "official",
            "label": "SF Planning / DataSF",
            "url": LAND_USE_URL,
            "dataset_id": LAND_USE_DATASET_ID,
        },
        dict(geography_counts),
        excluded,
    )


def main():
    if not TEMPLATE.exists():
        raise SystemExit(f"Missing template: {TEMPLATE}")

    retrieved = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    precincts, precinct_source = fetch_precincts()
    multifamily, multifamily_source, geography_counts, excluded = fetch_multifamily()

    p_meta = metadata(PRECINCT_DATASET_ID)
    m_meta = metadata(LAND_USE_DATASET_ID)

    manifest = {
        "retrieved_at": retrieved,
        "precincts": {
            **precinct_source,
            "feature_count": len(precincts["features"]),
            "source_rows_updated_at": iso_from_unix(p_meta.get("rowsUpdatedAt")),
        },
        "multifamily": {
            **multifamily_source,
            "feature_count": len(multifamily["features"]),
            "display_filter": "resunits >= 20 AND geography_type = parcel",
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
            "multifamily_source_url": multifamily_source["url"],
            "multifamily_data_as_of": manifest["multifamily"]["data_as_of"],
            "multifamily_display_filter": manifest["multifamily"]["display_filter"],
            "excluded_geographies": excluded,
        },
        "precincts": precincts,
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
    (OUT / "data-manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (OUT / ".nojekyll").write_text("", encoding="utf-8")

    print(
        f"built {OUT / 'index.html'} with "
        f"{len(precincts['features'])} precincts and "
        f"{len(multifamily['features'])} parcel-level 20+ unit records"
    )
    print(f"source 20+ geography counts: {dict(geography_counts)}")
    print(f"excluded from apartment layer: {excluded}")
    print(f"manifest: {OUT / 'data-manifest.json'}")


if __name__ == "__main__":
    main()
