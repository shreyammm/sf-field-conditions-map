#!/usr/bin/env python3
"""Embed recent SFPD reported-incident aggregates for map context.

The source table can contain multiple rows for one Incident ID because a report
may contain multiple incident codes. Production therefore counts DISTINCT
Incident IDs rather than source rows. Counts are grouped at SFPD's public
privacy-mapped point for four fixed lookback windows, with both ALL-category and
category-specific views.

This layer is descriptive reported-incident context only. It does not compute a
precinct/neighborhood safety score, prediction, or voter-targeting variable.
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

DATASET_ID = "wg3w-h783"
# data.sf.gov is the current working Socrata resource host. The older
# data.sfgov.org resource hostname returns 403 from GitHub Actions.
RESOURCE_URL = f"https://data.sf.gov/resource/{DATASET_ID}.json"
SOURCE_PAGE = (
    "https://data.sf.gov/Public-Safety/"
    "Police-Department-Incident-Reports-2018-to-Present/wg3w-h783/data"
)
LOOKBACKS = (30, 90, 180, 365)
PAGE_SIZE = 50_000
MAX_GROUP_ROWS = 200_000
HEADERS = {
    "User-Agent": (
        "sf-field-conditions-map/1.0 "
        "(+https://github.com/shreyammm/sf-field-conditions-map)"
    ),
    "Accept": "application/json",
}


def get_rows(params: dict[str, str], attempts: int = 3, timeout: int = 120):
    url = RESOURCE_URL + "?" + urllib.parse.urlencode(params)
    last = None
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                payload = json.load(response)
            if not isinstance(payload, list):
                raise ValueError("DataSF resource response was not a row array")
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


def intish(value, default=-1):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def aggregate_count(row):
    for key in (
        "report_count",
        "count_distinct_incident_id",
        "count_distinct",
        "count",
        "count_1",
    ):
        if key in row:
            value = intish(row.get(key))
            if value >= 0:
                return value
    for key, value in row.items():
        if "count" in str(key).lower():
            parsed = intish(value)
            if parsed >= 0:
                return parsed
    return -1


def valid_point(row):
    try:
        lat = float(row.get("latitude"))
        lon = float(row.get("longitude"))
    except (TypeError, ValueError):
        return None
    if not (-122.60 <= lon <= -122.25 and 37.65 <= lat <= 37.90):
        return None
    return [lon, lat]


def window_bounds(end_date: dt.date, days: int):
    start = end_date - dt.timedelta(days=days - 1)
    start_ts = start.isoformat() + "T00:00:00.000"
    next_ts = (end_date + dt.timedelta(days=1)).isoformat() + "T00:00:00.000"
    return start, start_ts, next_ts


def where_clause(start_ts: str, next_ts: str):
    return (
        f"incident_datetime >= '{start_ts}' "
        f"AND incident_datetime < '{next_ts}' "
        "AND latitude IS NOT NULL AND longitude IS NOT NULL"
    )


def fetch_grouped(select: str, where: str, group: str, order: str):
    rows = []
    offset = 0
    previous_signature = None
    while True:
        page = get_rows(
            {
                "$select": select,
                "$where": where,
                "$group": group,
                "$order": order,
                "$limit": str(PAGE_SIZE),
                "$offset": str(offset),
            }
        )
        if page:
            first = page[0]
            last = page[-1]
            signature = (
                str(first.get("incident_category") or ""),
                str(first.get("latitude") or ""),
                str(first.get("longitude") or ""),
                str(last.get("incident_category") or ""),
                str(last.get("latitude") or ""),
                str(last.get("longitude") or ""),
                len(page),
            )
            if signature == previous_signature:
                raise ValueError(
                    f"DataSF grouped pagination repeated at offset {offset}"
                )
            previous_signature = signature
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += len(page)
        if len(rows) > MAX_GROUP_ROWS:
            raise ValueError(
                f"Incident grouped query exceeded {MAX_GROUP_ROWS} rows"
            )
    return rows


def fetch_all_groups(start_ts: str, next_ts: str):
    where = where_clause(start_ts, next_ts)
    return fetch_grouped(
        (
            "intersection,police_district,analysis_neighborhood,latitude,longitude,"
            "count(distinct incident_id) as report_count"
        ),
        where,
        "intersection,police_district,analysis_neighborhood,latitude,longitude",
        "latitude ASC,longitude ASC,intersection ASC",
    )


def fetch_category_groups(start_ts: str, next_ts: str):
    where = where_clause(start_ts, next_ts)
    return fetch_grouped(
        (
            "incident_category,intersection,police_district,analysis_neighborhood,"
            "latitude,longitude,count(distinct incident_id) as report_count"
        ),
        where,
        (
            "incident_category,intersection,police_district,analysis_neighborhood,"
            "latitude,longitude"
        ),
        "incident_category ASC,latitude ASC,longitude ASC,intersection ASC",
    )


def exact_city_count(start_ts: str, next_ts: str):
    rows = get_rows(
        {
            "$select": "count(distinct incident_id) as report_count",
            "$where": where_clause(start_ts, next_ts),
            "$limit": "1",
        }
    )
    if len(rows) != 1:
        raise ValueError(
            f"Expected one citywide incident count row, received {len(rows)}"
        )
    count = aggregate_count(rows[0])
    if count < 1:
        raise ValueError(f"Could not parse citywide report count: {rows[0]}")
    return count


def row_to_feature(row, days: int, category: str):
    point = valid_point(row)
    count = aggregate_count(row)
    if not point or count < 1:
        return None
    props = {
        "lookback_days": days,
        "category": category,
        "report_count": count,
    }
    for field in ("intersection", "police_district", "analysis_neighborhood"):
        value = str(row.get(field) or "").strip()
        if value:
            props[field] = value
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": point},
        "properties": props,
    }


def main():
    html = SITE.read_text(encoding="utf-8")
    match, payload = parse_payload(html)
    retrieved_sf = dt.datetime.now(ZoneInfo("America/Los_Angeles"))
    end_date = retrieved_sf.date()

    features = []
    window_meta = {}
    categories = set()
    invalid_rows = collections.Counter()

    for days in LOOKBACKS:
        start, start_ts, next_ts = window_bounds(end_date, days)
        all_rows = fetch_all_groups(start_ts, next_ts)
        category_rows = fetch_category_groups(start_ts, next_ts)
        exact_count = exact_city_count(start_ts, next_ts)

        all_kept = 0
        category_kept = 0
        all_point_memberships = 0
        category_memberships = collections.Counter()

        for row in all_rows:
            feature = row_to_feature(row, days, "ALL")
            if not feature:
                invalid_rows[f"{days}_all_invalid"] += 1
                continue
            features.append(feature)
            all_kept += 1
            all_point_memberships += feature["properties"]["report_count"]

        for row in category_rows:
            category = (
                str(row.get("incident_category") or "Uncategorized").strip()
                or "Uncategorized"
            )
            feature = row_to_feature(row, days, category)
            if not feature:
                invalid_rows[f"{days}_category_invalid"] += 1
                continue
            features.append(feature)
            categories.add(category)
            category_kept += 1
            category_memberships[category] += feature["properties"]["report_count"]

        if all_kept < 100 or category_kept < 100:
            raise ValueError(
                f"Unexpectedly sparse {days}-day incident aggregate: "
                f"all={all_kept}, category={category_kept}"
            )
        if all_point_memberships < exact_count:
            raise ValueError(
                f"{days}-day point memberships below exact city report count: "
                f"{all_point_memberships} < {exact_count}"
            )
        if all_point_memberships > exact_count * 1.05:
            raise ValueError(
                f"{days}-day point memberships exceed exact count by >5%: "
                f"{all_point_memberships} vs {exact_count}"
            )

        window_meta[str(days)] = {
            "start": start.isoformat(),
            "end": end_date.isoformat(),
            "exact_distinct_report_count": exact_count,
            "all_point_group_count": all_kept,
            "all_point_report_memberships": all_point_memberships,
            "category_point_group_count": category_kept,
            "category_report_memberships": dict(category_memberships),
            "all_source_group_rows": len(all_rows),
            "category_source_group_rows": len(category_rows),
        }
        print(
            f"incidents {days}d: exact_reports={exact_count}; "
            f"all_groups={all_kept}; point_memberships={all_point_memberships}; "
            f"category_groups={category_kept}"
        )

    if not 1_000 <= len(features) <= 250_000:
        raise ValueError(
            f"Unexpected embedded incident aggregate feature count: {len(features)}"
        )

    payload["incidents"] = {
        "type": "FeatureCollection",
        "features": features,
    }
    meta = payload.setdefault("meta", {})
    meta.update(
        {
            "incident_dataset_id": DATASET_ID,
            "incident_source_page": SOURCE_PAGE,
            "incident_resource_url": RESOURCE_URL,
            "incident_retrieved_sf": retrieved_sf.replace(
                microsecond=0
            ).isoformat(),
            "incident_windows": window_meta,
            "incident_lookback_options": list(LOOKBACKS),
            "incident_categories": sorted(categories),
            "incident_aggregate_feature_count": len(features),
            "incident_invalid_aggregate_rows": dict(invalid_rows),
            "incident_counting_rule": (
                "DataSF count(distinct incident_id) grouped at SFPD public "
                "privacy-mapped point, separately for ALL categories and each "
                "SFPD incident_category, for fixed 30/90/180/365-day windows"
            ),
            "incident_location_note": (
                "SFPD maps all public incident locations to nearby intersections "
                "to protect anonymity; displayed points are not exact incident "
                "locations."
            ),
            "incident_interpretation": (
                "recent SFPD reported-incident context only; raw counts are not "
                "population/activity normalized and are not a neighborhood risk "
                "score or proof of present danger"
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
    manifest["incidents"] = {
        "dataset_id": DATASET_ID,
        "source_page": SOURCE_PAGE,
        "resource_url": RESOURCE_URL,
        "retrieved_sf": retrieved_sf.replace(microsecond=0).isoformat(),
        "windows": window_meta,
        "lookback_options": list(LOOKBACKS),
        "categories": sorted(categories),
        "embedded_aggregate_feature_count": len(features),
        "invalid_aggregate_rows": dict(invalid_rows),
        "counting_rule": (
            "count distinct Incident IDs at source privacy-mapped points; ALL "
            "and category-specific aggregates stored separately"
        ),
        "location_privacy": (
            "SFPD maps public incident locations to nearby intersections; "
            "points are approximate"
        ),
        "interpretation": (
            "reported-incident context only; no precinct/neighborhood risk "
            "score is computed"
        ),
    }
    MANIFEST.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(
        f"incident aggregates: {len(features)} embedded features; "
        f"categories={len(categories)}; invalid={dict(invalid_rows)}"
    )


if __name__ == "__main__":
    main()
