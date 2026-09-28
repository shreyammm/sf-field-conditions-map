#!/usr/bin/env python3
"""Embed recent SFPD reported incidents using deterministic SoQL pagination."""
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
MAX_ROWS = 300000
FIELDS = [
    "row_id", "incident_datetime", "report_datetime", "incident_id",
    "incident_category", "incident_subcategory", "intersection",
    "police_district", "analysis_neighborhood", "latitude", "longitude",
]
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


def point_from_row(row):
    try:
        lat = float(row.get("latitude"))
        lon = float(row.get("longitude"))
    except (TypeError, ValueError):
        return None
    if not (-122.60 <= lon <= -122.25 and 37.65 <= lat <= 37.90):
        return None
    return [lon, lat]


def fetch_rows(start_date, end_date):
    select = ", ".join(f"`{x}`" for x in FIELDS)
    start_ts = start_date.isoformat() + "T00:00:00.000"
    next_ts = (end_date + dt.timedelta(days=1)).isoformat() + "T00:00:00.000"
    base = (
        f"SELECT {select} WHERE `incident_datetime` >= '{start_ts}' "
        f"AND `incident_datetime` < '{next_ts}' "
        "ORDER BY `incident_datetime` ASC, `row_id` ASC"
    )
    rows = []
    offset = 0
    last_signature = None
    while True:
        page = post_query(f"{base} LIMIT {PAGE_SIZE} OFFSET {offset}")
        if page:
            sig = (
                str(page[0].get("row_id") or ""),
                str(page[-1].get("row_id") or ""),
                len(page),
            )
            if sig == last_signature:
                raise ValueError(f"DataSF pagination repeated a page at offset {offset}: {sig}")
            last_signature = sig
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += len(page)
        if len(rows) > MAX_ROWS:
            raise ValueError(f"Unexpectedly large recent SFPD query: >{MAX_ROWS} source rows")
    return rows


def main():
    html = SITE.read_text(encoding="utf-8")
    match, payload = parse_payload(html)
    retrieved_sf = dt.datetime.now(ZoneInfo("America/Los_Angeles"))
    end_date = retrieved_sf.date()
    start_date = end_date - dt.timedelta(days=EMBED_DAYS - 1)
    rows = fetch_rows(start_date, end_date)
    if not 5000 <= len(rows) <= MAX_ROWS:
        raise ValueError(f"Unexpected SFPD recent-buffer row count: {len(rows)}")

    by_incident = collections.defaultdict(list)
    omitted = collections.Counter()
    for row in rows:
        iid = str(row.get("incident_id") or "").strip()
        if not iid:
            omitted["missing_incident_id"] += 1
            continue
        if not local_iso(row.get("incident_datetime")):
            omitted["invalid_incident_datetime"] += 1
            continue
        by_incident[iid].append(row)

    features = []
    category_counts = collections.Counter()
    multi_category = 0
    point_variant = 0
    represented_rows = 0
    dates = []

    for iid, group in by_incident.items():
        valid = [(r, point_from_row(r)) for r in group]
        valid = [(r, pt) for r, pt in valid if pt]
        if not valid:
            omitted["missing_or_invalid_privacy_mapped_point"] += 1
            continue
        canonical, point = max(
            valid,
            key=lambda x: (local_iso(x[0].get("report_datetime")) or "", str(x[0].get("row_id") or "")),
        )
        when = local_iso(canonical.get("incident_datetime"))
        if not when:
            omitted["invalid_canonical_incident_datetime"] += 1
            continue
        cats = sorted({str(r.get("incident_category") or "Uncategorized").strip() or "Uncategorized" for r in group})
        subs = sorted({str(r.get("incident_subcategory") or "").strip() for r in group if str(r.get("incident_subcategory") or "").strip()})
        if len(cats) > 1:
            multi_category += 1
        for cat in cats:
            category_counts[cat] += 1
        variants = {(round(pt[0], 7), round(pt[1], 7)) for _, pt in valid}
        if len(variants) > 1:
            point_variant += 1
        props = {
            "incident_id": iid,
            "incident_datetime": when,
            "categories": cats,
            "source_row_count": len(group),
            "source_point_variant_count": len(variants),
        }
        if subs:
            props["subcategories"] = subs
        for field in ("intersection", "police_district", "analysis_neighborhood"):
            val = str(canonical.get(field) or "").strip()
            if val:
                props[field] = val
        features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": point}, "properties": props})
        represented_rows += len(group)
        dates.append(when[:10])

    if len(features) < 3000:
        raise ValueError(f"Too few geocoded incident reports after deduplication: {len(features)}")
    features.sort(key=lambda f: ((f["properties"].get("incident_datetime") or ""), (f["properties"].get("incident_id") or "")))

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
        "incident_source_row_count": len(rows),
        "incident_source_incident_id_count": len(by_incident),
        "incident_display_report_count": len(features),
        "incident_source_rows_represented": represented_rows,
        "incident_omitted_counts": dict(omitted),
        "incident_category_report_memberships": dict(category_counts),
        "incident_multi_category_report_count": multi_category,
        "incident_point_variant_report_count": point_variant,
        "incident_min_date": min(dates),
        "incident_max_date": max(dates),
        "incident_counting_rule": "one displayed report per incident_id; categories unioned across source rows",
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
        "source_row_count": len(rows),
        "source_incident_id_count": len(by_incident),
        "display_report_count": len(features),
        "source_rows_represented": represented_rows,
        "omitted_counts": dict(omitted),
        "category_report_memberships": dict(category_counts),
        "multi_category_report_count": multi_category,
        "point_variant_report_count": point_variant,
        "min_incident_date": min(dates),
        "max_incident_date": max(dates),
        "counting_rule": "deduplicate to incident_id; union categories across source rows",
        "location_privacy": "SFPD maps public incident locations to nearby intersections; points are approximate",
        "interpretation": "reported-incident context; no precinct/neighborhood risk score is computed",
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"incidents: {len(features)} displayed reports from {len(rows)} source rows / {len(by_incident)} incident IDs; omitted={dict(omitted)}")
    print(f"incident buffer: {start_date} through {end_date}; actual dates {min(dates)} through {max(dates)}")
    print(f"incident categories: {dict(category_counts)}")
    print(f"multi-category reports: {multi_category}; point-variant reports: {point_variant}")


if __name__ == "__main__":
    main()
