#!/usr/bin/env python3
"""Embed privacy-preserving SFPD reported-incident aggregates.

Why aggregate at build time:
The official SFPD table is one row per Incident ID + Incident Code, so one
report can occupy multiple rows. A rolling year contains hundreds of thousands
of source rows and is too large for a self-contained browser map. DataSF/SoQL
therefore counts DISTINCT Incident IDs at SFPD's public privacy-mapped point for
four fixed lookback windows (30/90/180/365 days). We store both an ALL-category
view and category-specific views. This preserves exact report deduplication
within each point/category grouping while keeping the production artifact
tractable.

The layer is descriptive reported-incident context only. It does not compute a
precinct/neighborhood safety score, prediction, or voter-targeting variable.
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

DATASET_ID = "wg3w-h783"
QUERY_URL = f"https://data.sfgov.org/api/v3/views/{DATASET_ID}/query.json"
SOURCE_PAGE = (
    "https://data.sf.gov/Public-Safety/"
    "Police-Department-Incident-Reports-2018-to-Present/wg3w-h783/data"
)
LOOKBACKS = (30, 90, 180, 365)
PAGE_SIZE = 5_000
MAX_ROWS_PER_QUERY = 100_000
HEADERS = {
    "User-Agent": (
        "sf-field-conditions-map/1.0 "
        "(+https://github.com/shreyammm/sf-field-conditions-map)"
    ),
    "Accept": "application/json",
    "Content-Type": "application/json",
}


def post_query(query: str, attempts: int = 3, timeout: int = 180):
    body = json.dumps(
        {
            "query": query,
            "page": {"pageNumber": 1, "pageSize": PAGE_SIZE},
            "includeSynthetic": False,
        },
        separators=(",", ":"),
    ).encode("utf-8")
    last = None
    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(
                QUERY_URL, data=body, headers=HEADERS, method="POST"
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.load(response)
            if isinstance(payload, list):
                return payload
            if isinstance(payload, dict):
                for key in ("data", "results", "rows"):
                    if isinstance(payload.get(key), list):
                        return payload[key]
            raise ValueError(
                "DataSF v3 response did not contain a recognizable row array"
            )
        except Exception as exc:
            last = exc
            if attempt < attempts:
                time.sleep(2 * attempt)
    raise RuntimeError(
        f"Failed after {attempts} attempts: {QUERY_URL}\n{last}"
    ) from last


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
    """Read count(distinct ...) robustly if SODA3 rewrites an alias."""
    for key in (
        "report_count",
        "count_distinct_incident_id",
        "count_distinct",
        "count",
        "count_1",
    ):
        if key in row:
            n = intish(row.get(key))
            if n >= 0:
                return n
    for key, value in row.items():
        low = str(key).lower()
        if "count" in low:
            n = intish(value)
            if n >= 0:
                return n
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
        f"`incident_datetime` >= '{start_ts}' "
        f"AND `incident_datetime` < '{next_ts}' "
        "AND `latitude` IS NOT NULL AND `longitude` IS NOT NULL"
    )


def fetch_grouped(query_base: str):
    rows = []
    offset = 0
    previous_signature = None
    while True:
        page = post_query(f"{query_base} LIMIT {PAGE_SIZE} OFFSET {offset}")
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
                    f"DataSF aggregate pagination repeated at offset {offset}"
                )
            previous_signature = signature
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += len(page)
        if len(rows) > MAX_ROWS_PER_QUERY:
            raise ValueError(
                f"Incident aggregate query exceeded {MAX_ROWS_PER_QUERY} rows"
            )
    return rows


def all_query(start_ts: str, next_ts: str):
    return (
        "SELECT `intersection`, `police_district`, `analysis_neighborhood`, "
        "`latitude`, `longitude`, "
        "count(distinct `incident_id`) AS report_count "
        f"WHERE {where_clause(start_ts, next_ts)} "
        "GROUP BY `intersection`, `police_district`, `analysis_neighborhood`, "
        "`latitude`, `longitude` "
        "ORDER BY `latitude` ASC, `longitude` ASC, `intersection` ASC"
    )


def category_query(start_ts: str, next_ts: str):
    return (
        "SELECT `incident_category`, `intersection`, `police_district`, "
        "`analysis_neighborhood`, `latitude`, `longitude`, "
        "count(distinct `incident_id`) AS report_count "
        f"WHERE {where_clause(start_ts, next_ts)} "
        "GROUP BY `incident_category`, `intersection`, `police_district`, "
        "`analysis_neighborhood`, `latitude`, `longitude` "
        "ORDER BY `incident_category` ASC, `latitude` ASC, `longitude` ASC, "
        "`intersection` ASC"
    )


def exact_city_count(start_ts: str, next_ts: str):
    rows = post_query(
        "SELECT count(distinct `incident_id`) AS report_count "
        f"WHERE {where_clause(start_ts, next_ts)}"
    )
    if len(rows) != 1:
        raise ValueError(
            f"Expected one citywide incident count row, received {len(rows)}"
        )
    n = aggregate_count(rows[0])
    if n < 1:
        raise ValueError(
            f"Could not parse citywide distinct Incident-ID count: {rows[0]}"
        )
    return n


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
    for field in (
        "intersection",
        "police_district",
        "analysis_neighborhood",
    ):
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
        all_rows = fetch_grouped(all_query(start_ts, next_ts))
        category_rows = fetch_grouped(category_query(start_ts, next_ts))
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
        # Point memberships can slightly exceed the exact city total if a report
        # changes public mapped location across source rows. Large inflation is a
        # source/query anomaly and should stop deployment.
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
        }
        print(
            f"incidents {days}d: exact_reports={exact_count}; "
            f"all_groups={all_kept}/{len(all_rows)}; "
            f"point_memberships={all_point_memberships}; "
            f"category_groups={category_kept}/{len(category_rows)}"
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
            "incident_resource_url": QUERY_URL,
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
        "resource_url": QUERY_URL,
        "retrieved_sf": retrieved_sf.replace(microsecond=0).isoformat(),
        "windows": window_meta,
        "lookback_options": list(LOOKBACKS),
        "categories": sorted(categories),
        "embedded_aggregate_feature_count": len(features),
        "invalid_aggregate_rows": dict(invalid_rows),
        "counting_rule": (
            "count distinct Incident IDs at source privacy-mapped points; ALL "
            "and category-specific aggregates are stored separately"
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
