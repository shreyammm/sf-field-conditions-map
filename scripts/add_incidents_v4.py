#!/usr/bin/env python3
"""Embed recent SFPD reported incidents for route-context display.

The source table has one row per Incident ID + Incident Code, so one police
report can occupy several source rows. To keep the static map compact without
double-counting those rows as separate reports, DataSF first groups rows by
Incident ID, category, incident time, and SFPD's privacy-mapped public point.
The build then merges those compact rows to exactly one displayed feature per
Incident ID while preserving every category represented on the report.

Displayed locations are SFPD public-data locations mapped to nearby
intersections for anonymity. This is reported-incident context, not a safety or
neighborhood risk score.
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
EMBED_DAYS = 370
PAGE_SIZE = 5_000
MAX_COMPACT_ROWS = 250_000
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
            req = urllib.request.Request(
                QUERY_URL, data=body, headers=HEADERS, method="POST"
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
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


def local_iso(value):
    if value in (None, ""):
        return None
    text = str(value).strip().replace(" ", "T")
    if len(text) < 10:
        return None
    if len(text) == 10:
        text += "T00:00:00"
    elif len(text) == 16:
        text += ":00"
    else:
        text = text[:19]
    try:
        dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    return text


def intish(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def compact_count(row):
    """Read the aggregate count even if DataSF rewrites the alias name."""
    for key in ("code_rows", "count", "count_1", "count_star"):
        if key in row:
            return max(1, intish(row.get(key), 1))
    for key, value in row.items():
        if "count" in str(key).lower():
            parsed = intish(value, -1)
            if parsed >= 1:
                return parsed
    return 1


def point_from_row(row):
    try:
        lat = float(row.get("latitude"))
        lon = float(row.get("longitude"))
    except (TypeError, ValueError):
        return None
    if not (-122.60 <= lon <= -122.25 and 37.65 <= lat <= 37.90):
        return None
    return [lon, lat]


def fetch_compact_rows(start_date: dt.date, end_date: dt.date):
    start_ts = start_date.isoformat() + "T00:00:00.000"
    next_ts = (end_date + dt.timedelta(days=1)).isoformat() + "T00:00:00.000"
    base = (
        "SELECT `incident_id`, `incident_category`, `incident_datetime`, "
        "`intersection`, `police_district`, `analysis_neighborhood`, "
        "`latitude`, `longitude`, count(*) AS code_rows "
        f"WHERE `incident_datetime` >= '{start_ts}' "
        f"AND `incident_datetime` < '{next_ts}' "
        "GROUP BY `incident_id`, `incident_category`, `incident_datetime`, "
        "`intersection`, `police_district`, `analysis_neighborhood`, "
        "`latitude`, `longitude` "
        "ORDER BY `incident_datetime` ASC, `incident_id` ASC, "
        "`incident_category` ASC, `latitude` ASC, `longitude` ASC"
    )

    rows = []
    offset = 0
    previous_signature = None
    while True:
        page = post_query(f"{base} LIMIT {PAGE_SIZE} OFFSET {offset}")
        if page:
            signature = (
                str(page[0].get("incident_id") or ""),
                str(page[-1].get("incident_id") or ""),
                str(page[0].get("incident_datetime") or ""),
                str(page[-1].get("incident_datetime") or ""),
                len(page),
            )
            if signature == previous_signature:
                raise ValueError(
                    "DataSF compact pagination repeated a page at offset "
                    f"{offset}: {signature}"
                )
            previous_signature = signature
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += len(page)
        if len(rows) > MAX_COMPACT_ROWS:
            raise ValueError(
                "Unexpectedly large compact SFPD query: "
                f">{MAX_COMPACT_ROWS} rows"
            )
    return rows


def main():
    html = SITE.read_text(encoding="utf-8")
    match, payload = parse_payload(html)

    retrieved_sf = dt.datetime.now(ZoneInfo("America/Los_Angeles"))
    end_date = retrieved_sf.date()
    start_date = end_date - dt.timedelta(days=EMBED_DAYS - 1)
    compact_rows = fetch_compact_rows(start_date, end_date)
    if not 3_000 <= len(compact_rows) <= MAX_COMPACT_ROWS:
        raise ValueError(
            f"Unexpected compact SFPD row count: {len(compact_rows)}"
        )

    by_incident = collections.defaultdict(list)
    omitted = collections.Counter()
    for row in compact_rows:
        incident_id = str(row.get("incident_id") or "").strip()
        if not incident_id:
            omitted["missing_incident_id"] += 1
            continue
        when = local_iso(row.get("incident_datetime"))
        if not when:
            omitted["invalid_incident_datetime"] += 1
            continue
        by_incident[incident_id].append(row)

    features = []
    category_counts = collections.Counter()
    multi_category_reports = 0
    point_variant_reports = 0
    represented_source_rows = 0
    incident_dates = []

    for incident_id, group in by_incident.items():
        valid = [(row, point_from_row(row)) for row in group]
        valid = [(row, point) for row, point in valid if point]
        if not valid:
            omitted["missing_or_invalid_privacy_mapped_point"] += 1
            continue

        # A report can appear in more than one category/source-point grouping.
        # Use the latest incident timestamp as the single display anchor while
        # retaining all category memberships and the count of point variants.
        canonical, point = max(
            valid,
            key=lambda item: (
                local_iso(item[0].get("incident_datetime")) or "",
                str(item[0].get("incident_category") or ""),
                str(item[0].get("intersection") or ""),
            ),
        )
        when = local_iso(canonical.get("incident_datetime"))
        if not when:
            omitted["invalid_canonical_incident_datetime"] += 1
            continue

        categories = sorted(
            {
                str(row.get("incident_category") or "Uncategorized").strip()
                or "Uncategorized"
                for row in group
            }
        )
        if len(categories) > 1:
            multi_category_reports += 1
        for category in categories:
            category_counts[category] += 1

        point_variants = {
            (round(source_point[0], 7), round(source_point[1], 7))
            for _, source_point in valid
        }
        if len(point_variants) > 1:
            point_variant_reports += 1

        source_rows = sum(compact_count(row) for row in group)
        props = {
            "incident_id": incident_id,
            "incident_datetime": when,
            "categories": categories,
            "source_row_count": source_rows,
            "source_point_variant_count": len(point_variants),
        }
        for field in (
            "intersection",
            "police_district",
            "analysis_neighborhood",
        ):
            value = str(canonical.get(field) or "").strip()
            if value:
                props[field] = value

        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": point},
                "properties": props,
            }
        )
        represented_source_rows += source_rows
        incident_dates.append(when[:10])

    if len(features) < 3_000:
        raise ValueError(
            "Too few geocoded SFPD incident reports after Incident-ID "
            f"deduplication: {len(features)}"
        )

    features.sort(
        key=lambda feature: (
            feature["properties"]["incident_datetime"],
            feature["properties"]["incident_id"],
        )
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
            "incident_window_start": start_date.isoformat(),
            "incident_window_end": end_date.isoformat(),
            "incident_lookback_days_embedded": EMBED_DAYS,
            "incident_compact_source_row_count": len(compact_rows),
            "incident_source_incident_id_count": len(by_incident),
            "incident_display_report_count": len(features),
            "incident_source_rows_represented": represented_source_rows,
            "incident_omitted_counts": dict(omitted),
            "incident_category_report_memberships": dict(category_counts),
            "incident_multi_category_report_count": multi_category_reports,
            "incident_point_variant_report_count": point_variant_reports,
            "incident_min_date": min(incident_dates),
            "incident_max_date": max(incident_dates),
            "incident_counting_rule": (
                "one displayed report per incident_id; DataSF source rows are "
                "first compacted by incident/category/time/privacy-mapped point; "
                "categories are unioned across compact rows"
            ),
            "incident_location_note": (
                "SFPD maps all public incident locations to nearby intersections "
                "to protect anonymity; displayed points are not exact incident "
                "locations."
            ),
            "incident_interpretation": (
                "recent SFPD reported-incident context only; not a neighborhood "
                "risk score or proof of present danger"
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
        "embedded_window_start": start_date.isoformat(),
        "embedded_window_end": end_date.isoformat(),
        "embedded_lookback_days": EMBED_DAYS,
        "compact_source_row_count": len(compact_rows),
        "source_incident_id_count": len(by_incident),
        "display_report_count": len(features),
        "source_rows_represented": represented_source_rows,
        "omitted_counts": dict(omitted),
        "category_report_memberships": dict(category_counts),
        "multi_category_report_count": multi_category_reports,
        "point_variant_report_count": point_variant_reports,
        "min_incident_date": min(incident_dates),
        "max_incident_date": max(incident_dates),
        "counting_rule": (
            "deduplicate to Incident ID after server compaction by category, "
            "incident time, and privacy-mapped point"
        ),
        "location_privacy": (
            "SFPD maps public incident locations to nearby intersections; "
            "points are approximate"
        ),
        "interpretation": (
            "reported-incident context; no precinct/neighborhood risk score is "
            "computed"
        ),
    }
    MANIFEST.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(
        f"incidents: {len(features)} displayed reports from "
        f"{len(compact_rows)} compact rows / {len(by_incident)} Incident IDs; "
        f"{represented_source_rows} source rows represented; "
        f"omitted={dict(omitted)}"
    )
    print(
        f"incident buffer: {start_date} through {end_date}; actual dates "
        f"{min(incident_dates)} through {max(incident_dates)}"
    )
    print(f"incident categories: {dict(category_counts)}")
    print(
        f"multi-category reports: {multi_category_reports}; "
        f"point-variant reports: {point_variant_reports}"
    )


if __name__ == "__main__":
    main()
