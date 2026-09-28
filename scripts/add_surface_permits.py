#!/usr/bin/env python3
"""Embed current/upcoming SF Public Works street-surface work/occupancy permits.

Source: DataSF bpc9-7sus, a daily current/upcoming street-surface permit view.
The source also includes vending/amenity permits. For route context we keep only
permit types plausibly associated with construction, excavation, temporary
street/sidewalk occupation, street improvement, storage containers, or
encroachment. Geometry is shown as the official point location; it is not
expanded into a guessed work footprint or closure line.
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

KEEP_FIELDS = {
    "permit_number",
    "permit_type",
    "permit_description",
    "status",
    "approved_date",
    "permit_start_date",
    "permit_end_date",
    "street_name",
    "cross_street",
    "analysis_neighborhood",
    "supervisor_district",
    "data_as_of",
    "data_loaded_at",
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
    kept_types = collections.Counter()
    data_as_of = []
    kept = []
    seen = set()

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

        geom = f["geometry"]
        lon, lat = geom["coordinates"][:2]
        permit_no = str(p.get("permit_number") or "").strip()
        dedupe_key = (permit_no, typ, round(float(lon), 7), round(float(lat), 7), start, end)
        if dedupe_key in seen:
            omitted["exact_duplicate_row"] += 1
            continue
        seen.add(dedupe_key)

        props = {k: p.get(k) for k in KEEP_FIELDS if k in p}
        props["permit_type_label"] = KEEP_TYPES[typ]
        props["start_local"] = start
        props["end_local"] = end
        kept.append({"type": "Feature", "geometry": geom, "properties": props})
        kept_types[typ] += 1
        if p.get("data_as_of") not in (None, ""):
            data_as_of.append(str(p.get("data_as_of")))

    if len(kept) < 500:
        raise ValueError(f"Too few route-relevant street-work permits after filtering: {len(kept)}")

    # bpc9-7sus is documented as a current snapshot plus permits starting in
    # roughly the next 14 days. The row-level data_as_of values vary by record
    # and are therefore not used as the snapshot date. Use the actual San
    # Francisco retrieval date for the completeness window.
    latest_row_asof = max(data_as_of) if data_as_of else None
    support_start = retrieval_date.isoformat()
    support_end = (retrieval_date + dt.timedelta(days=14)).isoformat()

    payload["surface_permits"] = {"type": "FeatureCollection", "features": kept}
    meta = payload.setdefault("meta", {})
    meta.update({
        "surface_permit_dataset_id": DATASET_ID,
        "surface_permit_source_url": SOURCE_URL,
        "surface_permit_source_count": nsrc,
        "surface_permit_display_count": len(kept),
        "surface_permit_source_type_counts": dict(source_types),
        "surface_permit_display_type_counts": dict(kept_types),
        "surface_permit_status_counts": dict(source_statuses),
        "surface_permit_omitted_counts": dict(omitted),
        "surface_permit_latest_row_data_as_of": latest_row_asof,
        "surface_permit_retrieved_sf": retrieved_sf.replace(microsecond=0).isoformat(),
        "surface_permit_supported_from": support_start,
        "surface_permit_supported_through": support_end,
        "surface_permit_time_basis": "selected San Francisco calendar date; permit windows treated as date-inclusive",
        "surface_permit_scope_note": (
            "Current/upcoming Public Works street-surface work/occupancy permits only. "
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
        "embedded_feature_count": len(kept),
        "source_type_counts": dict(source_types),
        "display_type_counts": dict(kept_types),
        "status_counts": dict(source_statuses),
        "omitted_counts": dict(omitted),
        "latest_row_data_as_of": latest_row_asof,
        "retrieved_sf": retrieved_sf.replace(microsecond=0).isoformat(),
        "supported_from": support_start,
        "supported_through": support_end,
        "filter_types": list(KEEP_TYPES),
        "interpretation": (
            "Public Works active/upcoming surface-work or occupancy permit point. "
            "Not a confirmed street closure, not a pedestrian-access determination, "
            "and not an exact work footprint."
        ),
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"surface permits: {len(kept)}/{nsrc} embedded; omitted={dict(omitted)}")
    print(f"surface permit source types: {dict(source_types)}")
    print(f"surface permit kept types: {dict(kept_types)}")
    print(f"surface permit statuses: {dict(source_statuses)}")
    print(
        f"surface permit support window: {support_start} through {support_end}; "
        f"retrieved_sf={retrieved_sf.replace(microsecond=0).isoformat()}; "
        f"latest_row_data_as_of={latest_row_asof}"
    )


if __name__ == "__main__":
    main()
