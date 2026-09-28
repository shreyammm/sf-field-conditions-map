#!/usr/bin/env python3
"""Embed a rolling year of recent SFPD reported incidents for route context.

The public map uses the official SFPD/DataSF incident-report dataset. SFPD maps
incident locations to nearby intersections for privacy. We deduplicate source
rows to one feature per Incident ID so multi-code reports are not double-counted.
The browser then offers 30/90/180/365-day lookbacks and category filtering.

This is reported-incident context, not a neighborhood risk score.
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
RESOURCE_URL = "https://data.sfgov.org/resource/wg3w-h783.json"
SOURCE_PAGE = "https://data.sf.gov/Public-Safety/Police-Department-Incident-Reports-2018-to-Present/wg3w-h783/about_data"
LOOKBACK_DAYS = 365
PAGE_SIZE = 50_000
SELECT = ",".join([
    "row_id", "incident_datetime", "report_datetime", "incident_id",
    "incident_category", "incident_subcategory", "intersection",
    "police_district", "analysis_neighborhood", "latitude", "longitude",
])
HEADERS = {
    "User-Agent": "sf-field-conditions-map/1.0 (+https://github.com/shreyammm/sf-field-conditions-map)",
    "Accept": "application/json",
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


def parse_payload(html: str):
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
    if len(s) == 10:
        s += "T00:00:00"
    elif len(s) == 16:
        s += ":00"
    else:
        s = s[:19]
    try:
        dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    return s


def point_from_row(row):
    try:
        lat = float(row.get("latitude"))
        lon = float(row.get("longitude"))
    except (TypeError, ValueError):
        return None
    if not (-122.60 <= lon <= -122.25 and 37.65 <= lat <= 37.90):
        return None
    return [lon, lat]


def fetch_rows(start_date: dt.date, end_date: dt.date):
    rows = []
    offset = 0
    start_ts = start_date.isoformat() + "T00:00:00.000"
    next_ts = (end_date + dt.timedelta(days=1)).isoformat() + "T00:00:00.000"
    where = f"incident_datetime >= '{start_ts}' AND incident_datetime < '{next_ts}'"
    while True:
        params = {
            "$select": SELECT,
            "$where": where,
            "$order": "incident_datetime ASC,row_id ASC",
            "$limit": str(PAGE_SIZE),
            "$offset": str(offset),
        }
        url = RESOURCE_URL + "?" + urllib.parse.urlencode(params)
        page = get_json(url)
        if not isinstance(page, list):
            raise ValueError("SFPD resource query did not return a row array")
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += len(page)
        if offset > 350_000:
            raise ValueError("Unexpectedly large one-year SFPD query; refusing to embed")
    return rows


def main():
    html = SITE.read_text(encoding="utf-8")
    match, payload = parse_payload(html)

    retrieved_sf = dt.datetime.now(ZoneInfo("America/Los_Angeles"))
    end_date = retrieved_sf.date()
    start_date = end_date - dt.timedelta(days=LOOKBACK_DAYS - 1)
    rows = fetch_rows(start_date, end_date)
    if not 5_000 <= len(rows) <= 350_000:
        raise ValueError(f"Unexpected SFPD source row count for one-year window: {len(rows)}")

    by_incident = collections.defaultdict(list)
    omitted = collections.Counter()
    for row in rows:
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
    represented_rows = 0
    incident_dates = []

    for incident_id, group in by_incident.items():
        valid = [(row, point_from_row(row)) for row in group]
        valid = [(row, pt) for row, pt in valid if pt]
        if not valid:
            omitted["missing_or_invalid_privacy_mapped_point"] += 1
            continue

        # Use the latest report row as the canonical location/text when a report
        # has supplements, while retaining the union of incident categories.
        def sort_key(item):
            row, _ = item
            return (
                local_iso(row.get("report_datetime")) or "",
                str(row.get("row_id") or ""),
            )

        canonical, point = max(valid, key=sort_key)
        when = local_iso(canonical.get("incident_datetime"))
        if not when:
            omitted["invalid_canonical_incident_datetime"] += 1
            continue

        categories = sorted({
            str(r.get("incident_category") or "Uncategorized").strip() or "Uncategorized"
            for r in group
        })
        subcategories = sorted({
            str(r.get("incident_subcategory") or "").strip()
            for r in group if str(r.get("incident_subcategory") or "").strip()
        })
        if len(categories) > 1:
            multi_category_reports += 1
        for cat in categories:
            category_counts[cat] += 1

        point_variants = {
            (round(pt[0], 7), round(pt[1], 7))
            for _, pt in valid
        }
        if len(point_variants) > 1:
            point_variant_reports += 1

        props = {
            "incident_id": incident_id,
            "incident_datetime": when,
            "categories": categories,
            "source_row_count": len(group),
            "source_point_variant_count": len(point_variants),
        }
        if subcategories:
            props["subcategories"] = subcategories
        for field in ("intersection", "police_district", "analysis_neighborhood"):
            value = str(canonical.get(field) or "").strip()
            if value:
                props[field] = value

        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": point},
            "properties": props,
        })
        represented_rows += len(group)
        incident_dates.append(when[:10])

    if len(features) < 3_000:
        raise ValueError(f"Too few geocoded SFPD incident reports after deduplication: {len(features)}")

    features.sort(key=lambda f: (
        (f.get("properties") or {}).get("incident_datetime") or "",
        (f.get("properties") or {}).get("incident_id") or "",
    ))

    payload["incidents"] = {"type": "FeatureCollection", "features": features}
    meta = payload.setdefault("meta", {})
    meta.update({
        "incident_dataset_id": DATASET_ID,
        "incident_source_page": SOURCE_PAGE,
        "incident_resource_url": RESOURCE_URL,
        "incident_retrieved_sf": retrieved_sf.replace(microsecond=0).isoformat(),
        "incident_window_start": start_date.isoformat(),
        "incident_window_end": end_date.isoformat(),
        "incident_lookback_days_embedded": LOOKBACK_DAYS,
        "incident_source_row_count": len(rows),
        "incident_source_incident_id_count": len(by_incident),
        "incident_display_report_count": len(features),
        "incident_source_rows_represented": represented_rows,
        "incident_omitted_counts": dict(omitted),
        "incident_category_report_memberships": dict(category_counts),
        "incident_multi_category_report_count": multi_category_reports,
        "incident_point_variant_report_count": point_variant_reports,
        "incident_min_date": min(incident_dates) if incident_dates else None,
        "incident_max_date": max(incident_dates) if incident_dates else None,
        "incident_counting_rule": "one displayed report per incident_id; categories are unioned across source rows for that incident_id",
        "incident_location_note": "SFPD maps all public incident locations to nearby intersections to protect anonymity; displayed points are not exact incident locations.",
        "incident_interpretation": "recent approved SFPD reported-incident context only; not a neighborhood risk score or proof of present danger",
    })

    packed = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    SITE.write_text(html[:match.start(1)] + packed + html[match.end(1):], encoding="utf-8")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["incidents"] = {
        "dataset_id": DATASET_ID,
        "source_page": SOURCE_PAGE,
        "resource_url": RESOURCE_URL,
        "retrieved_sf": retrieved_sf.replace(microsecond=0).isoformat(),
        "embedded_window_start": start_date.isoformat(),
        "embedded_window_end": end_date.isoformat(),
        "embedded_lookback_days": LOOKBACK_DAYS,
        "source_row_count": len(rows),
        "source_incident_id_count": len(by_incident),
        "display_report_count": len(features),
        "source_rows_represented": represented_rows,
        "omitted_counts": dict(omitted),
        "category_report_memberships": dict(category_counts),
        "multi_category_report_count": multi_category_reports,
        "point_variant_report_count": point_variant_reports,
        "min_incident_date": min(incident_dates) if incident_dates else None,
        "max_incident_date": max(incident_dates) if incident_dates else None,
        "counting_rule": "deduplicate to incident_id, union categories across source rows",
        "location_privacy": "SFPD maps public incident locations to nearby intersections; map points are approximate, not exact incident locations",
        "interpretation": "reported-incident context; no precinct/neighborhood risk score is computed",
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(
        f"incidents: {len(features)} displayed reports from {len(rows)} source rows / "
        f"{len(by_incident)} incident IDs; omitted={dict(omitted)}"
    )
    print(f"incident window: {start_date} through {end_date}; actual dates {min(incident_dates)} through {max(incident_dates)}")
    print(f"incident categories: {dict(category_counts)}")
    print(f"multi-category reports: {multi_category_reports}; point-variant reports: {point_variant_reports}")


if __name__ == "__main__":
    main()
