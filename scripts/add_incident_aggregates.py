#!/usr/bin/env python3
"""Embed privacy-preserving SFPD reported-incident aggregates.

Why aggregate at build time:
The official SFPD table is one row per Incident ID + Incident Code, so one
report can occupy multiple rows. A rolling year contains hundreds of thousands
of source rows and is too large for a self-contained browser map. DataSF/SoQL
therefore counts DISTINCT Incident IDs at SFPD's public privacy-mapped point for
four fixed lookback windows (30/90/180/365 days). We store both an ALL-category
view and category-specific views. This preserves report deduplication within a
point/category grouping while keeping the production artifact tractable.

DataSF v3 pagination has proven inconsistent for large grouped queries in
GitHub Actions. Production therefore obtains complete grouped results by
recursively partitioning each requested time window until every grouped query
returns below the API row cap, then sums the disjoint time-slice counts back to
the requested 30/90/180/365-day window.

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
        if "count" in str(key).lower():
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
    start_dt = dt.datetime.combine(start, dt.time.min)
    stop_dt = dt.datetime.combine(end_date + dt.timedelta(days=1), dt.time.min)
    return start, start_dt, stop_dt


def ts(value: dt.datetime):
    return value.strftime("%Y-%m-%dT%H:%M:%S.000")


def where_clause(start_ts: str, next_ts: str):
    return (
        f"`incident_datetime` >= '{start_ts}' "
        f"AND `incident_datetime` < '{next_ts}' "
        "AND `latitude` IS NOT NULL AND `longitude` IS NOT NULL"
    )


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


def grouped_key(row, include_category: bool):
    fields = []
    if include_category:
        fields.append(str(row.get("incident_category") or "Uncategorized").strip() or "Uncategorized")
    fields.extend(
        [
            str(row.get("intersection") or "").strip(),
            str(row.get("police_district") or "").strip(),
            str(row.get("analysis_neighborhood") or "").strip(),
            str(row.get("latitude") or "").strip(),
            str(row.get("longitude") or "").strip(),
        ]
    )
    return tuple(fields)


def fetch_grouped_interval(query_fn, start_dt, stop_dt):
    """Fetch one half-open interval; split recursively if the API hits its cap."""
    query = query_fn(ts(start_dt), ts(stop_dt)) + f" LIMIT {PAGE_SIZE}"
    rows = post_query(query)
    if len(rows) < PAGE_SIZE:
        return rows, 1

    span = stop_dt - start_dt
    if span <= dt.timedelta(hours=1):
        raise ValueError(
            "Incident aggregate still reaches the DataSF row cap in an interval "
            f"of one hour or less: {ts(start_dt)} to {ts(stop_dt)}"
        )
    midpoint = start_dt + span / 2
    left_rows, left_queries = fetch_grouped_interval(query_fn, start_dt, midpoint)
    right_rows, right_queries = fetch_grouped_interval(query_fn, midpoint, stop_dt)
    return left_rows + right_rows, left_queries + right_queries + 1


def fetch_grouped_complete(query_fn, start_dt, stop_dt, include_category=False):
    """Return requested-window groups after merging disjoint time partitions."""
    raw_rows, query_count = fetch_grouped_interval(query_fn, start_dt, stop_dt)
    merged = {}
    for row in raw_rows:
        n = aggregate_count(row)
        if n < 0:
            raise ValueError(f"Could not parse aggregate count: {row}")
        key = grouped_key(row, include_category)
        if key not in merged:
            merged[key] = dict(row)
            merged[key]["report_count"] = n
        else:
            merged[key]["report_count"] = intish(merged[key].get("report_count"), 0) + n
    return list(merged.values()), len(raw_rows), query_count


def exact_city_count(start_dt: dt.datetime, stop_dt: dt.datetime):
    rows = post_query(
        "SELECT count(distinct `incident_id`) AS report_count "
        f"WHERE {where_clause(ts(start_dt), ts(stop_dt))} LIMIT 1"
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
        start, start_dt, stop_dt = window_bounds(end_date, days)
        all_rows, all_raw_group_rows, all_query_count = fetch_grouped_complete(
            all_query, start_dt, stop_dt, include_category=False
        )
        category_rows, category_raw_group_rows, category_query_count = fetch_grouped_complete(
            category_query, start_dt, stop_dt, include_category=True
        )
        exact_count = exact_city_count(start_dt, stop_dt)

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
        # appears at more than one privacy-mapped point across source rows. A
        # large difference signals a source/query problem and blocks deployment.
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
            "all_partition_raw_group_rows": all_raw_group_rows,
            "category_partition_raw_group_rows": category_raw_group_rows,
            "all_partition_query_count": all_query_count,
            "category_partition_query_count": category_query_count,
        }
        print(
            f"incidents {days}d: exact_reports={exact_count}; "
            f"all_groups={all_kept} from {all_raw_group_rows} partition rows / "
            f"{all_query_count} queries; point_memberships={all_point_memberships}; "
            f"category_groups={category_kept} from {category_raw_group_rows} "
            f"partition rows / {category_query_count} queries"
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
                "SFPD incident_category, for fixed 30/90/180/365-day windows; "
                "large grouped queries are partitioned into disjoint incident-time "
                "intervals and re-summed by the same point/category key"
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
            "and category-specific aggregates stored separately; API-cap-sized "
            "grouped queries are recursively time-partitioned and re-summed"
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
