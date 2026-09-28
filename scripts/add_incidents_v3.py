#!/usr/bin/env python3
"""Embed recent SFPD incident reports with server-side row compaction.

The SFPD source has one row per Incident ID + Incident Code, so a single report
can occupy several raw rows. We ask DataSF to compact raw rows by Incident ID,
SFPD category, and privacy-mapped source location before pagination, then merge
those compact rows to one displayed report per Incident ID. This keeps the
self-contained map small without treating incident-code rows as separate events.
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
SOURCE_PAGE = "https://data.sf.gov/Public-Safety/Police-Department-Incident-Reports-2018-to-Present/wg3w-h783/data"
EMBED_DAYS = 370
PAGE_SIZE = 5000
MAX_COMPACT_ROWS = 250000
HEADERS = {
    "User-Agent": "sf-field-conditions-map/1.0 (+https://github.com/shreyammm/sf-field-conditions-map)",
    "Accept": "application/json",
    "Content-Type": "application/json",
}


def post_query(query: str, attempts: int = 3, timeout: int = 180):
    body = json.dumps({
        "query": query,
        "page": {"pageNumber": 1, "pageSize": PAGE_SIZE},
        "includeSynthetic": False,
    }, separators=(",", ":")).encode("utf-8")
    last = None
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(QUERY_URL, data=body, headers=HEADERS, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as r:
                obj = json.load(r)
            if isinstance(obj, list):
                return obj
            if isinstance(obj, dict):
                for key in ("data", "results", "rows"):
                    if isinstance(obj.get(key), list):
                        return obj[key]
            raise ValueError("DataSF v3 response did not contain a row array")
        except Exception as exc:
            last = exc
            if attempt < attempts:
                time.sleep(2 * attempt)
    raise RuntimeError(f"Failed after {attempts} attempts: {QUERY_URL}\n{last}") from last


def parse_payload(html):
    m = re.search(r"window\.SF_FIELD_DATA=(\{.*?\});\s*</script>", html, re.S)
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


def intish(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def point_from_row(row):
    try:
        lat = float(row.get("latitude"))
        lon = float(row.get("longitude"))
    except (TypeError, ValueError):
        return None
    if not (-122.60 <= lon <= -122.25 and 37.65 <= lat <= 37.90):
        return None
    return [lon, lat]


def year_where(start_date, end_date):
    years = [str(y) for y in range(start_date.year, end_date.year + 1)]
    return "`incident_year` IN (" + ",".join("'" + y + "'" for y in years) + ")"


def source_count(start_date, end_date):
    rows = post_query(f"SELECT count(*) AS `n` WHERE {year_where(start_date, end_date)}")
    if not rows:
        raise ValueError("SFPD source count query returned no rows")
    n = intish(rows[0].get("n"), -1)
    if n < 5000 or n > 600000:
        raise ValueError(f"Unexpected SFPD raw row count for source years: {n}")
    return n


def fetch_compact_rows(start_date, end_date):
    # Group by the source privacy-mapped point and category. We intentionally
    # preserve distinct point variants for an Incident ID rather than averaging
    # them. max(report_datetime) lets the client choose a canonical/latest row.
    base = (
        "SELECT `incident_id`, `incident_category`, "
        "max(`incident_datetime`) AS `incident_datetime`, "
        "max(`report_datetime`) AS `report_datetime`, "
        "`intersection`, `police_district`, `analysis_neighborhood`, "
        "`latitude`, `longitude`, count(*) AS `source_row_count` "
        f"WHERE {year_where(start_date, end_date)} "
        "GROUP BY `incident_id`, `incident_category`, `intersection`, "
        "`police_district`, `analysis_neighborhood`, `latitude`, `longitude` "
        "ORDER BY `incident_datetime` ASC, `incident_id` ASC, "
        "`incident_category` ASC, `latitude` ASC, `longitude` ASC"
    )
    rows = []
    offset = 0
    last_sig = None
    while True:
        page = post_query(f"{base} LIMIT {PAGE_SIZE} OFFSET {offset}")
        if page:
            sig = (
                str(page[0].get("incident_id") or ""),
                str(page[-1].get("incident_id") or ""),
                str(page[0].get("incident_datetime") or ""),
                str(page[-1].get("incident_datetime") or ""),
                len(page),
            )
            if sig == last_sig:
                raise ValueError(f"DataSF compact pagination repeated a page at offset {offset}: {sig}")
            last_sig = sig
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += len(page)
        if len(rows) > MAX_COMPACT_ROWS:
            raise ValueError(f"Unexpectedly large compact SFPD query: >{MAX_COMPACT_ROWS} rows")
    return rows


def main():
    html = SITE.read_text(encoding="utf-8")
    match, payload = parse_payload(html)
    retrieved_sf = dt.datetime.now(ZoneInfo("America/Los_Angeles"))
    end_date = retrieved_sf.date()
    start_date = end_date - dt.timedelta(days=EMBED_DAYS - 1)

    raw_year_rows = source_count(start_date, end_date)
    compact = fetch_compact_rows(start_date, end_date)
    if not 3000 <= len(compact) <= MAX_COMPACT_ROWS:
        raise ValueError(f"Unexpected compact SFPD row count: {len(compact)}")

    # The server query uses whole incident_year values for robustness and speed;
    # trim the compact rows to the exact 370-day buffer here.
    by_incident = collections.defaultdict(list)
    omitted = collections.Counter()
    compact_in_window = 0
    for row in compact:
        when = local_iso(row.get("incident_datetime"))
        if not when:
            omitted["invalid_incident_datetime"] += 1
            continue
        day = when[:10]
        if not (start_date.isoformat() <= day <= end_date.isoformat()):
            omitted["outside_exact_buffer"] += 1
            continue
        iid = str(row.get("incident_id") or "").strip()
        if not iid:
            omitted["missing_incident_id"] += 1
            continue
        compact_in_window += 1
        by_incident[iid].append(row)

    features = []
    category_counts = collections.Counter()
    multi_category = 0
    point_variant = 0
    represented_source_rows = 0
    dates = []

    for iid, group in by_incident.items():
        valid = [(r, point_from_row(r)) for r in group]
        valid = [(r, pt) for r, pt in valid if pt]
        if not valid:
            omitted["missing_or_invalid_privacy_mapped_point"] += 1
            continue
        canonical, point = max(
            valid,
            key=lambda x: (
                local_iso(x[0].get("report_datetime")) or "",
                local_iso(x[0].get("incident_datetime")) or "",
                str(x[0].get("incident_category") or ""),
            ),
        )
        when = local_iso(canonical.get("incident_datetime"))
        if not when:
            omitted["invalid_canonical_incident_datetime"] += 1
            continue
        cats = sorted({str(r.get("incident_category") or "Uncategorized").strip() or "Uncategorized" for r in group})
        if len(cats) > 1:
            multi_category += 1
        for cat in cats:
            category_counts[cat] += 1
        variants = {
            (round(pt[0], 7), round(pt[1], 7)) for _, pt in valid
        }
        if len(variants) > 1:
            point_variant += 1
        source_rows = sum(max(1, intish(r.get("source_row_count"), 1)) for r in group)
        props = {
            "incident_id": iid,
            "incident_datetime": when,
            "categories": cats,
            "source_row_count": source_rows,
            "source_point_variant_count": len(variants),
        }
        for field in ("intersection", "police_district", "analysis_neighborhood"):
            val = str(canonical.get(field) or "").strip()
            if val:
                props[field] = val
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": point},
            "properties": props,
        })
        represented_source_rows += source_rows
        dates.append(when[:10])

    if len(features) < 3000:
        raise ValueError(f"Too few geocoded SFPD reports after deduplication: {len(features)}")
    features.sort(key=lambda f: (f["properties"]["incident_datetime"], f["properties"]["incident_id"]))

    payload["incidents"] = {"type": "FeatureCollection", "features": features}
    meta = payload.setdefault("meta", {})
    meta.update({
        "incident_dataset_id": DATASET_ID,
        "incident_source_page": SOURCE_PAGE,
        "incident_resource_url": QUERY_URL,
        "incident_retrieved_sf": retrieved_sf.replace(microsecond=0).isoformat(),
        "incident_window_start": start_date.isoformat(),
        "incident_window_end": end_date.isoformat(),
        "incident_lookback_days_embedded": EMBED_DAYS,
        "incident_source_year_row_count": raw_year_rows,
        "incident_compact_source_row_count": len(compact),
        "incident_compact_rows_in_exact_buffer": compact_in_window,
        "incident_display_report_count": len(features),
        "incident_source_rows_represented": represented_source_rows,
        "incident_omitted_counts": dict(omitted),
        "incident_category_report_memberships": dict(category_counts),
        "incident_multi_category_report_count": multi_category,
        "incident_point_variant_report_count": point_variant,
        "incident_min_date": min(dates),
        "incident_max_date": max(dates),
        "incident_counting_rule": "one displayed report per incident_id; categories unioned across compact source rows; source incident-code row counts retained",
        "incident_location_note": "SFPD maps all public incident locations to nearby intersections to protect anonymity; displayed points are not exact incident locations.",
        "incident_interpretation": "recent SFPD reported-incident context only; not a neighborhood risk score or proof of present danger",
    })
    packed = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    SITE.write_text(html[:match.start(1)] + packed + html[match.end(1):], encoding="utf-8")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["incidents"] = {
        "dataset_id": DATASET_ID,
        "source_page": SOURCE_PAGE,
        "resource_url": QUERY_URL,
        "retrieved_sf": retrieved_sf.replace(microsecond=0).isoformat(),
        "embedded_window_start": start_date.isoformat(),
        "embedded_window_end": end_date.isoformat(),
        "embedded_lookback_days": EMBED_DAYS,
        "source_year_row_count": raw_year_rows,
        "compact_source_row_count": len(compact),
        "compact_rows_in_exact_buffer": compact_in_window,
        "display_report_count": len(features),
        "source_rows_represented": represented_source_rows,
        "omitted_counts": dict(omitted),
        "category_report_memberships": dict(category_counts),
        "multi_category_report_count": multi_category,
        "point_variant_report_count": point_variant,
        "min_incident_date": min(dates),
        "max_incident_date": max(dates),
        "counting_rule": "deduplicate to incident_id after server compaction by category and privacy-mapped point",
        "location_privacy": "SFPD maps public incident locations to nearby intersections; points are approximate",
        "interpretation": "reported-incident context; no precinct/neighborhood risk score is computed",
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"incidents: {len(features)} displayed reports; {compact_in_window} compact rows in exact buffer; {represented_source_rows} raw incident-code rows represented")
    print(f"incident source years raw rows: {raw_year_rows}; compact rows: {len(compact)}")
    print(f"incident buffer: {start_date} through {end_date}; actual dates {min(dates)} through {max(dates)}")
    print(f"incident categories: {dict(category_counts)}")
    print(f"multi-category reports: {multi_category}; point-variant reports: {point_variant}; omitted={dict(omitted)}")


if __name__ == "__main__":
    main()
