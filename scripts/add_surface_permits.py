#!/usr/bin/env python3
"""Embed current/upcoming SF Public Works street-surface work/occupancy permits.

Source: DataSF bpc9-7sus, a daily current/upcoming street-surface permit view.
The source also includes vending/amenity permits. For route context we keep only
permit types plausibly associated with construction, excavation, temporary
street/sidewalk occupation, street improvement, storage containers, or
encroachment.

Important source behavior: one permit can publish multiple location rows at the
same official point. Those rows may carry different street/cross-street text.
Production therefore aggregates only rows with the same permit number, type,
exact point, and permit window, while preserving every distinct source location,
description, status, neighborhood, and district on the resulting marker. The
point is never expanded into a guessed work footprint or closure line.
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import pathlib
import re
import time
import urllib.request
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = ROOT / "_site" / "index.html"
MANIFEST = ROOT / "_site" / "data-manifest.json"

DATASET_ID = "bpc9-7sus"
SOURCE_URL = "https://data.sf.gov/api/v3/views/bpc9-7sus/query.geojson?accessType=DOWNLOAD"
HEADERS = {
    "User-Agent": "sf-field-conditions-map/1.0 (+https://github.com/shreyammm/sf-field-conditions-map)",
    "Accept": "application/json, application/geo+json;q=0.9, */*;q=0.1",
}

# Deliberately exclude vending, food-facility, parklet, blank, and NightNoise
# rows. Those can be real street uses, but they are not a clean construction /
# physical-occupancy signal for this route-planning layer.
KEEP_TYPES = {
    "Excavation": "Excavation",
    "TempOccup": "Temporary occupancy",
    "StrtImprov": "Street improvement",
    "ExcStreet": "Street excavation / work",
    "AddlStSpac": "Additional street space",
    "StorCont": "Storage container",
    "MinorEnc": "Minor encroachment",
    "StreetSpace": "Street space",
}


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


def parse_payload(html):
    m = re.search(r"window\.SF_FIELD_DATA=(\{.*?\});\s*</script>", html, flags=re.S)
    if not m:
        raise ValueError("Embedded payload not found")
    return m, json.loads(m.group(1))


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


def valid_sf_point(geometry):
    if not geometry or geometry.get("type") != "Point":
        return False
    c = geometry.get("coordinates") or []
    if len(c) < 2:
        return False
    try:
        lon, lat = float(c[0]), float(c[1])
    except (TypeError, ValueError):
        return False
    return -122.56 <= lon <= -122.32 and 37.69 <= lat <= 37.84


def unique_values(rows, field):
    vals = {
        str((row.get("properties") or {}).get(field) or "").strip()
        for row in rows
        if str((row.get("properties") or {}).get(field) or "").strip()
    }
    return sorted(vals)


def unique_locations(rows):
    seen = set()
    out = []
    for row in rows:
        p = row.get("properties") or {}
        street = str(p.get("street_name") or "").strip()
        cross = str(p.get("cross_street") or "").strip()
        key = (street, cross)
        if key in seen or not (street or cross):
            continue
        seen.add(key)
        out.append({"street": street, "cross_street": cross})
    out.sort(key=lambda x: (x["street"], x["cross_street"]))
    return out


def main():
    html = SITE.read_text(encoding="utf-8")
    match, payload = parse_payload(html)
    source = get_json(SOURCE_URL)
    if source.get("type") != "FeatureCollection" or not isinstance(source.get("features"), list):
        raise ValueError("Surface-permit source is not a GeoJSON FeatureCollection")

    retrieved_sf = dt.datetime.now(ZoneInfo("America/Los_Angeles"))
    retrieval_date = retrieved_sf.date()

    fs = source["features"]
    nsrc = len(fs)
    if not 500 <= nsrc <= 20_000:
        raise ValueError(f"Unexpected surface-permit source count: {nsrc}")

    source_types = collections.Counter()
    source_statuses = collections.Counter()
    omitted = collections.Counter()
    data_as_of = []
    groups = collections.defaultdict(list)

    for f in fs:
        p = f.get("properties") or {}
        typ = str(p.get("permit_type") or "").strip()
        status = str(p.get("status") or "").strip().upper()
        source_types[typ or "(blank)"] += 1
        source_statuses[status or "(blank)"] += 1

        if typ not in KEEP_TYPES:
            omitted["non_work_or_unclassified_type"] += 1
            continue
        if status not in {"ACTIVE", "APPROVED"}:
            omitted["non_active_or_approved_status"] += 1
            continue
        if not valid_sf_point(f.get("geometry")):
            omitted["missing_or_invalid_point"] += 1
            continue

        start = local_iso(p.get("permit_start_date"))
        end = local_iso(p.get("permit_end_date"))
        if not start or not end or end < start:
            omitted["invalid_or_missing_date_window"] += 1
            continue

        permit_no = str(p.get("permit_number") or "").strip()
        if not permit_no:
            omitted["missing_permit_number"] += 1
            continue

        geom = f["geometry"]
        lon, lat = map(float, geom["coordinates"][:2])
        # Exact source point coordinates: do not spatially snap or merge nearby
        # but distinct permits/locations.
        aggregation_key = (permit_no, typ, lon, lat, start, end)
        groups[aggregation_key].append(f)

        if p.get("data_as_of") not in (None, ""):
            data_as_of.append(str(p.get("data_as_of")))

    kept = []
    kept_types = collections.Counter()
    aggregation_groups = 0
    aggregation_extra_rows = 0
    multi_location_groups = 0
    multi_description_groups = 0
    multi_status_groups = 0
    max_rows_per_marker = 1

    for key, rows in groups.items():
        permit_no, typ, lon, lat, start, end = key
        statuses = unique_values(rows, "status")
        descriptions = unique_values(rows, "permit_description")
        locations = unique_locations(rows)
        approved_dates = unique_values(rows, "approved_date")
        neighborhoods = unique_values(rows, "analysis_neighborhood")
        districts = unique_values(rows, "supervisor_district")
        row_asofs = unique_values(rows, "data_as_of")
        row_loaded = unique_values(rows, "data_loaded_at")

        if len(rows) > 1:
            aggregation_groups += 1
            aggregation_extra_rows += len(rows) - 1
            max_rows_per_marker = max(max_rows_per_marker, len(rows))
        if len(locations) > 1:
            multi_location_groups += 1
        if len(descriptions) > 1:
            multi_description_groups += 1
        if len(statuses) > 1:
            multi_status_groups += 1

        props = {
            "permit_number": permit_no,
            "permit_type": typ,
            "permit_type_label": KEEP_TYPES[typ],
            "permit_start_date": start,
            "permit_end_date": end,
            "start_local": start,
            "end_local": end,
            "source_row_count": len(rows),
            "source_location_count": len(locations),
            "source_locations": locations,
            "source_statuses": statuses,
            "source_descriptions": descriptions,
            "source_approved_dates": approved_dates,
            "source_neighborhoods": neighborhoods,
            "source_supervisor_districts": districts,
            "source_data_as_of_min": min(row_asofs) if row_asofs else None,
            "source_data_as_of_max": max(row_asofs) if row_asofs else None,
            "source_data_loaded_at_max": max(row_loaded) if row_loaded else None,
        }
        # Convenience scalar fields are only emitted when they are unambiguous.
        if len(statuses) == 1:
            props["status"] = statuses[0]
        if len(descriptions) == 1:
            props["permit_description"] = descriptions[0]
        if len(locations) == 1:
            props["street_name"] = locations[0]["street"]
            props["cross_street"] = locations[0]["cross_street"]
        if len(neighborhoods) == 1:
            props["analysis_neighborhood"] = neighborhoods[0]
        if len(districts) == 1:
            props["supervisor_district"] = districts[0]

        kept.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": props,
        })
        kept_types[typ] += 1

    if len(kept) < 500:
        raise ValueError(f"Too few route-relevant street-work permit markers after filtering: {len(kept)}")

    latest_row_asof = max(data_as_of) if data_as_of else None
    support_start = retrieval_date.isoformat()
    support_end = (retrieval_date + dt.timedelta(days=14)).isoformat()

    aggregation_meta = {
        "marker_groups_with_multiple_source_rows": aggregation_groups,
        "additional_source_rows_aggregated": aggregation_extra_rows,
        "marker_groups_with_multiple_source_locations": multi_location_groups,
        "marker_groups_with_multiple_descriptions": multi_description_groups,
        "marker_groups_with_multiple_statuses": multi_status_groups,
        "max_source_rows_per_marker": max_rows_per_marker,
        "rule": "same permit_number + permit_type + exact source point + permit start/end window; preserve all distinct source descriptors",
    }

    payload["surface_permits"] = {"type": "FeatureCollection", "features": kept}
    meta = payload.setdefault("meta", {})
    meta.update({
        "surface_permit_dataset_id": DATASET_ID,
        "surface_permit_source_url": SOURCE_URL,
        "surface_permit_source_count": nsrc,
        "surface_permit_eligible_source_row_count": sum(len(v) for v in groups.values()),
        "surface_permit_display_count": len(kept),
        "surface_permit_source_type_counts": dict(source_types),
        "surface_permit_display_type_counts": dict(kept_types),
        "surface_permit_status_counts": dict(source_statuses),
        "surface_permit_omitted_counts": dict(omitted),
        "surface_permit_aggregation": aggregation_meta,
        "surface_permit_latest_row_data_as_of": latest_row_asof,
        "surface_permit_retrieved_sf": retrieved_sf.replace(microsecond=0).isoformat(),
        "surface_permit_supported_from": support_start,
        "surface_permit_supported_through": support_end,
        "surface_permit_time_basis": "selected San Francisco calendar date; permit windows treated as date-inclusive",
        "surface_permit_scope_note": (
            "Current/upcoming Public Works street-surface work/occupancy permit markers only. "
            "One marker may preserve multiple source location rows that share the same official point. "
            "A permit indicates authorized street/sidewalk use, not a confirmed closure or exact work footprint."
        ),
    })

    packed = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    SITE.write_text(html[:match.start(1)] + packed + html[match.end(1):], encoding="utf-8")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["surface_permits"] = {
        "dataset_id": DATASET_ID,
        "source_url": SOURCE_URL,
        "source_feature_count": nsrc,
        "eligible_source_row_count": sum(len(v) for v in groups.values()),
        "embedded_marker_count": len(kept),
        "source_type_counts": dict(source_types),
        "display_type_counts": dict(kept_types),
        "status_counts": dict(source_statuses),
        "omitted_counts": dict(omitted),
        "aggregation": aggregation_meta,
        "latest_row_data_as_of": latest_row_asof,
        "retrieved_sf": retrieved_sf.replace(microsecond=0).isoformat(),
        "supported_from": support_start,
        "supported_through": support_end,
        "filter_types": list(KEEP_TYPES),
        "interpretation": (
            "Public Works active/upcoming surface-work or occupancy permit point. "
            "Co-located source location rows for one permit/window are preserved on one marker. "
            "Not a confirmed street closure, not a pedestrian-access determination, "
            "and not an exact work footprint."
        ),
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"surface permits: {len(kept)} markers from {sum(len(v) for v in groups.values())} eligible rows / {nsrc} source rows; omitted={dict(omitted)}")
    print(f"surface permit source types: {dict(source_types)}")
    print(f"surface permit kept marker types: {dict(kept_types)}")
    print(f"surface permit source statuses: {dict(source_statuses)}")
    print(f"surface permit aggregation: {aggregation_meta}")
    print(
        f"surface permit support window: {support_start} through {support_end}; "
        f"retrieved_sf={retrieved_sf.replace(microsecond=0).isoformat()}; "
        f"latest_row_data_as_of={latest_row_asof}"
    )


if __name__ == "__main__":
    main()
