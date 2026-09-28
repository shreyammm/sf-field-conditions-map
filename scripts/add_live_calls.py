#!/usr/bin/env python3
"""Embed an audited fallback snapshot of DataSF real-time law-enforcement calls.

The optional browser layer refreshes this same official dataset while enabled.
The embedded copy is the fallback for API/CORS failures and is deliberately
limited to calls *received* in the last 49 SF-local wall-clock hours because the
product's longest selectable lookback is 48 hours.

DataSF documents the upstream real-time table as closed calls from the last
48 hours plus any calls still open; therefore the upstream table can contain
older open/reopened exceptions. Those older rows cannot appear in this map's
1-48 hour received-time views and are not embedded.

Dispatched calls are operational records, not confirmed crimes. Public
locations are privacy-masked to intersections and some sensitive calls have
location fields suppressed by the source.
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
DISPLAY_MAX_HOURS = 48
QUERY_WINDOW_HOURS = 49
LIMIT = 10_000
MAX_STALE_MINUTES = 180
SELECT_FIELDS = [
    "id",
    "cad_number",
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
                return json.load(response)
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


def local_naive(value):
    text = clean_text(value)
    if not text:
        return None
    text = text.replace(" ", "T")
    try:
        return dt.datetime.fromisoformat(text[:19])
    except ValueError:
        return None


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
    received = clean_text(row.get("received_datetime"))
    if not point or not received:
        return None
    props = {
        # Public row id is retained only as an internal feature identifier. The
        # documented CAD number is used for uniqueness validation but is not
        # embedded because the UI does not need to expose it.
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

    retrieved_sf = dt.datetime.now(ZoneInfo("America/Los_Angeles")).replace(
        microsecond=0
    )
    retrieved_wall = retrieved_sf.replace(tzinfo=None)
    cutoff_wall = retrieved_wall - dt.timedelta(hours=QUERY_WINDOW_HOURS)
    cutoff_text = cutoff_wall.isoformat(timespec="milliseconds")

    params = {
        "$select": ",".join(SELECT_FIELDS),
        "$where": f"received_datetime >= '{cutoff_text}'",
        "$limit": str(LIMIT),
        "$order": "received_datetime DESC",
    }
    url = RESOURCE_URL + "?" + urllib.parse.urlencode(params)
    rows = get_json(url)
    if not isinstance(rows, list):
        raise ValueError("Real-time calls endpoint did not return an array")
    if not 100 <= len(rows) < LIMIT:
        raise ValueError(
            f"Implausible or possibly truncated real-time query count: {len(rows)} "
            f"(limit {LIMIT})"
        )

    features = []
    cad_numbers = set()
    ids = set()
    omitted = collections.Counter()
    agencies = collections.Counter()
    priorities = collections.Counter()
    open_count = 0
    data_as_of_values = []
    received_values = []

    for row in rows:
        cad = clean_text(row.get("cad_number"))
        if not cad:
            raise ValueError("Real-time source row missing documented cad_number")
        if cad in cad_numbers:
            raise ValueError(f"Duplicate CAD number in real-time source query: {cad}")
        cad_numbers.add(cad)

        iid = clean_text(row.get("id"))
        if iid:
            if iid in ids:
                raise ValueError(f"Duplicate public row id in real-time source query: {iid}")
            ids.add(iid)

        received = clean_text(row.get("received_datetime"))
        received_dt = local_naive(received)
        if not received_dt:
            omitted["missing_or_invalid_received_time"] += 1
            continue
        # The server query should enforce this. Re-check locally so API/query
        # drift cannot silently leak older records into the fallback snapshot.
        if received_dt < cutoff_wall - dt.timedelta(minutes=1):
            raise ValueError(
                f"Real-time query returned row before requested cutoff: {received} < {cutoff_text}"
            )

        agency = clean_text(row.get("agency")) or "Unknown"
        agencies[agency] += 1
        priorities[clean_text(row.get("priority_final")) or "Unknown"] += 1
        if not clean_text(row.get("close_datetime")):
            open_count += 1
        if clean_text(row.get("data_as_of")):
            data_as_of_values.append(clean_text(row.get("data_as_of")))
        received_values.append(received)

        feature = compact_call(row)
        if not feature:
            omitted["no_public_mapped_point"] += 1
            continue
        features.append(feature)

    if not 50 <= len(features) < LIMIT:
        raise ValueError(f"Implausible mapped real-time call count: {len(features)}")
    if not data_as_of_values:
        raise ValueError("Real-time source did not provide data_as_of")

    data_as_of = max(data_as_of_values)
    data_as_of_dt = local_naive(data_as_of)
    if data_as_of_dt is None:
        raise ValueError(f"Invalid real-time data_as_of: {data_as_of}")
    source_age_minutes = (retrieved_wall - data_as_of_dt).total_seconds() / 60
    if not -30 <= source_age_minutes <= MAX_STALE_MINUTES:
        raise ValueError(
            f"Real-time feed freshness outside guardrail: {source_age_minutes:.1f} minutes old"
        )

    min_received = min(received_values) if received_values else None
    max_received = max(received_values) if received_values else None
    max_received_dt = local_naive(max_received)
    newest_call_age_minutes = (
        (retrieved_wall - max_received_dt).total_seconds() / 60
        if max_received_dt
        else float("inf")
    )
    if newest_call_age_minutes > MAX_STALE_MINUTES:
        raise ValueError(
            f"Newest dispatched call is unexpectedly old: {newest_call_age_minutes:.1f} minutes"
        )

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
            "live_calls_display_max_hours": DISPLAY_MAX_HOURS,
            "live_calls_query_window_hours": QUERY_WINDOW_HOURS,
            "live_calls_query_limit": LIMIT,
            "live_calls_retrieved_sf": retrieved_sf.isoformat(),
            "live_calls_data_as_of": data_as_of,
            "live_calls_source_age_minutes": round(source_age_minutes, 1),
            "live_calls_newest_call_age_minutes": round(newest_call_age_minutes, 1),
            "live_calls_source_row_count": len(rows),
            "live_calls_cad_unique_count": len(cad_numbers),
            "live_calls_mapped_feature_count": len(features),
            "live_calls_unmapped_or_invalid_count": (
                omitted["no_public_mapped_point"]
                + omitted["missing_or_invalid_received_time"]
            ),
            "live_calls_open_source_count": open_count,
            "live_calls_agency_counts": dict(agencies),
            "live_calls_priority_counts": dict(priorities),
            "live_calls_min_received": min_received,
            "live_calls_max_received": max_received,
            "live_calls_omitted_counts": dict(omitted),
            "live_calls_counting_rule": (
                "one source row per unique documented cad_number; UI displays only "
                "calls whose received_datetime falls inside the selected 1-48 hour window"
            ),
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
        "display_max_hours": DISPLAY_MAX_HOURS,
        "query_window_hours": QUERY_WINDOW_HOURS,
        "query_limit": LIMIT,
        "query_rule": (
            "received_datetime >= build SF-local wall time minus 49 hours; "
            "49h buffer supports a maximum 48h user lookback"
        ),
        "retrieved_sf": retrieved_sf.isoformat(),
        "data_as_of": data_as_of,
        "source_age_minutes": round(source_age_minutes, 1),
        "newest_call_age_minutes": round(newest_call_age_minutes, 1),
        "source_row_count": len(rows),
        "cad_unique_count": len(cad_numbers),
        "mapped_feature_count": len(features),
        "unmapped_or_invalid_count": (
            omitted["no_public_mapped_point"]
            + omitted["missing_or_invalid_received_time"]
        ),
        "open_source_count": open_count,
        "agency_counts": dict(agencies),
        "priority_counts": dict(priorities),
        "min_received": min_received,
        "max_received": max_received,
        "omitted_counts": dict(omitted),
        "counting_rule": (
            "validate unique cad_number; UI counts mapped dispatch records, filtered "
            "by received_datetime; cad_number is not embedded in display properties"
        ),
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
        f"live calls: {len(features)} mapped / {len(rows)} recent source rows; "
        f"CAD unique={len(cad_numbers)}; open={open_count}; omitted={dict(omitted)}"
    )
    print(
        f"live calls received: {min_received} through {max_received}; "
        f"data_as_of={data_as_of}; source_age={source_age_minutes:.1f}m; "
        f"newest_call_age={newest_call_age_minutes:.1f}m"
    )
    print(f"live call agencies: {dict(agencies)}")


if __name__ == "__main__":
    main()
