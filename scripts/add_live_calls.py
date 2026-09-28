#!/usr/bin/env python3
"""Embed a fallback snapshot of DataSF's real-time law-enforcement calls.

The browser refreshes this same official dataset directly every 10 minutes. The
embedded copy is only a fallback for offline/CORS/API failures and lets the
build audit the data contract before deployment.

Important: dispatched calls are operational records, not confirmed crimes.
Public locations are privacy-masked to intersections and some sensitive calls
have location fields suppressed by the source.
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import pathlib
import re
import time
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = ROOT / "_site" / "index.html"
MANIFEST = ROOT / "_site" / "data-manifest.json"

DATASET_ID = "gnap-fj3t"
RESOURCE_URL = f"https://data.sf.gov/resource/{DATASET_ID}.json"
SOURCE_PAGE = (
    "https://data.sf.gov/Public-Safety/"
    "Law-Enforcement-Dispatched-Calls-for-Service-Real-/gnap-fj3t"
)
EXPLAINER_URL = (
    "https://sfdigitalservices.gitbook.io/dataset-explainers/"
    "law-enforcement-dispatched-calls-for-service"
)
LIMIT = 5000
SELECT_FIELDS = [
    "id",
    "received_datetime",
    "dispatch_datetime",
    "close_datetime",
    "call_type_original_desc",
    "call_type_final_desc",
    "priority_original",
    "priority_final",
    "agency",
    "disposition",
    "onview_flag",
    "intersection_name",
    "intersection_point",
    "analysis_neighborhood",
    "police_district",
    "call_last_updated_at",
    "data_as_of",
]
HEADERS = {
    "User-Agent": (
        "sf-field-conditions-map/1.0 "
        "(+https://github.com/shreyammm/sf-field-conditions-map)"
    ),
    "Accept": "application/json",
}


def get_json(url: str, attempts: int = 3, timeout: int = 120):
    last = None
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                payload = json.load(response)
            return payload
        except Exception as exc:
            last = exc
            if attempt < attempts:
                time.sleep(2 * attempt)
    raise RuntimeError(f"Failed after {attempts} attempts: {url}\n{last}") from last


def parse_payload(html: str):
    match = re.search(
        r"window\.SF_FIELD_DATA=(\{.*?\});\s*</script>", html, flags=re.S
    )
    if not match:
        raise ValueError("Embedded payload not found")
    return match, json.loads(match.group(1))


def clean_text(value):
    value = str(value or "").strip()
    return value or None


def parse_point(value):
    if not isinstance(value, dict) or value.get("type") != "Point":
        return None
    coords = value.get("coordinates")
    if not isinstance(coords, list) or len(coords) < 2:
        return None
    try:
        lon = float(coords[0])
        lat = float(coords[1])
    except (TypeError, ValueError):
        return None
    if not (-122.60 <= lon <= -122.25 and 37.65 <= lat <= 37.90):
        return None
    return [lon, lat]


def compact_call(row):
    point = parse_point(row.get("intersection_point"))
    if not point:
        return None
    received = clean_text(row.get("received_datetime"))
    if not received:
        return None
    props = {
        "id": clean_text(row.get("id")),
        "received_datetime": received,
        "open": not bool(clean_text(row.get("close_datetime"))),
    }
    for src, dst in (
        ("dispatch_datetime", "dispatch_datetime"),
        ("close_datetime", "close_datetime"),
        ("call_type_original_desc", "call_type_original"),
        ("call_type_final_desc", "call_type_final"),
        ("priority_original", "priority_original"),
        ("priority_final", "priority_final"),
        ("agency", "agency"),
        ("disposition", "disposition"),
        ("onview_flag", "onview_flag"),
        ("intersection_name", "intersection"),
        ("analysis_neighborhood", "analysis_neighborhood"),
        ("police_district", "police_district"),
        ("call_last_updated_at", "call_last_updated_at"),
        ("data_as_of", "data_as_of"),
    ):
        value = clean_text(row.get(src))
        if value is not None:
            props[dst] = value
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": point},
        "properties": props,
    }


def main():
    html = SITE.read_text(encoding="utf-8")
    match, payload = parse_payload(html)

    params = {
        "$select": ",".join(SELECT_FIELDS),
        "$limit": str(LIMIT),
        "$order": "received_datetime DESC",
    }
    url = RESOURCE_URL + "?" + urllib.parse.urlencode(params)
    rows = get_json(url)
    if not isinstance(rows, list):
        raise ValueError("Real-time calls endpoint did not return an array")
    if not 100 <= len(rows) <= LIMIT:
        raise ValueError(f"Implausible real-time call row count: {len(rows)}")

    features = []
    ids = set()
    omitted = collections.Counter()
    agencies = collections.Counter()
    priorities = collections.Counter()
    open_count = 0
    data_as_of_values = []
    received_values = []

    for row in rows:
        iid = clean_text(row.get("id"))
        if iid and iid in ids:
            omitted["duplicate_id"] += 1
            continue
        if iid:
            ids.add(iid)
        agency = clean_text(row.get("agency")) or "Unknown"
        agencies[agency] += 1
        priorities[clean_text(row.get("priority_final")) or "Unknown"] += 1
        if not clean_text(row.get("close_datetime")):
            open_count += 1
        if clean_text(row.get("data_as_of")):
            data_as_of_values.append(clean_text(row.get("data_as_of")))
        if clean_text(row.get("received_datetime")):
            received_values.append(clean_text(row.get("received_datetime")))

        feature = compact_call(row)
        if not feature:
            omitted["no_public_mapped_point_or_time"] += 1
            continue
        features.append(feature)

    if not 50 <= len(features) <= LIMIT:
        raise ValueError(f"Implausible mapped real-time call count: {len(features)}")

    retrieved_sf = dt.datetime.now(ZoneInfo("America/Los_Angeles")).replace(
        microsecond=0
    )
    data_as_of = max(data_as_of_values) if data_as_of_values else None
    min_received = min(received_values) if received_values else None
    max_received = max(received_values) if received_values else None

    payload["live_calls"] = {
        "type": "FeatureCollection",
        "features": features,
    }
    meta = payload.setdefault("meta", {})
    meta.update(
        {
            "live_calls_dataset_id": DATASET_ID,
            "live_calls_source_page": SOURCE_PAGE,
            "live_calls_explainer_url": EXPLAINER_URL,
            "live_calls_resource_url": RESOURCE_URL,
            "live_calls_runtime_refresh_minutes": 10,
            "live_calls_upstream_delay_minutes": 10,
            "live_calls_retrieved_sf": retrieved_sf.isoformat(),
            "live_calls_data_as_of": data_as_of,
            "live_calls_source_row_count": len(rows),
            "live_calls_mapped_feature_count": len(features),
            "live_calls_unmapped_or_invalid_count": omitted[
                "no_public_mapped_point_or_time"
            ],
            "live_calls_open_source_count": open_count,
            "live_calls_agency_counts": dict(agencies),
            "live_calls_priority_counts": dict(priorities),
            "live_calls_min_received": min_received,
            "live_calls_max_received": max_received,
            "live_calls_omitted_counts": dict(omitted),
            "live_calls_location_note": (
                "Public calls-for-service locations are privacy-masked to "
                "intersections; some sensitive calls have location fields "
                "suppressed by the source."
            ),
            "live_calls_interpretation": (
                "Operational law-enforcement dispatch activity, not confirmed "
                "crime incidents or a neighborhood safety/risk score."
            ),
        }
    )

    packed = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")
    ).replace("</", "<\\/")
    SITE.write_text(
        html[: match.start(1)] + packed + html[match.end(1) :],
        encoding="utf-8",
    )

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["live_calls"] = {
        "dataset_id": DATASET_ID,
        "source_page": SOURCE_PAGE,
        "explainer_url": EXPLAINER_URL,
        "resource_url": RESOURCE_URL,
        "runtime_refresh_minutes": 10,
        "upstream_delay_minutes": 10,
        "retrieved_sf": retrieved_sf.isoformat(),
        "data_as_of": data_as_of,
        "source_row_count": len(rows),
        "mapped_feature_count": len(features),
        "unmapped_or_invalid_count": omitted[
            "no_public_mapped_point_or_time"
        ],
        "open_source_count": open_count,
        "agency_counts": dict(agencies),
        "priority_counts": dict(priorities),
        "min_received": min_received,
        "max_received": max_received,
        "omitted_counts": dict(omitted),
        "location_privacy": (
            "Public locations are intersection-level privacy-masked points; "
            "sensitive records may suppress location."
        ),
        "interpretation": (
            "Dispatched-call activity only; not confirmed crime or a risk score."
        ),
    }
    MANIFEST.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(
        f"live calls: {len(features)} mapped / {len(rows)} source rows; "
        f"open={open_count}; omitted={dict(omitted)}"
    )
    print(
        f"live calls received: {min_received} through {max_received}; "
        f"data_as_of={data_as_of}"
    )
    print(f"live call agencies: {dict(agencies)}")


if __name__ == "__main__":
    main()
