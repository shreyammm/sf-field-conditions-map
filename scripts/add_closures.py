#!/usr/bin/env python3
"""Embed SFMTA permitted temporary street closures for date/time filtering.

The public map remains self-contained: the build downloads the official daily
SFMTA snapshot and embeds the trimmed line features. End users do not need a
runtime DataSF request.
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import pathlib
import re
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = ROOT / "_site" / "index.html"
MANIFEST = ROOT / "_site" / "data-manifest.json"

DATASET_ID = "8x25-yybr"
SOURCE_URL = "https://data.sf.gov/api/v3/views/8x25-yybr/query.geojson?accessType=DOWNLOAD"

HEADERS = {
    "User-Agent": "sf-field-conditions-map/1.0 (+https://github.com/shreyammm/sf-field-conditions-map)",
    "Accept": "application/json, application/geo+json;q=0.9, */*;q=0.1",
}

KEEP_FIELDS = {
    "objectid",
    "case_num",
    "case_name",
    "type",
    "status",
    "start_date",
    "start_time",
    "start_dt",
    "end_date",
    "end_time",
    "end_dt",
    "loc_desc",
    "cnn",
    "street",
    "from_st",
    "to_st",
    "direction",
    "veh_imp",
    "info",
    "start_utc",
    "end_utc",
    "data_as_of",
    "data_loaded_at",
    "created_date",
    "last_edited_date",
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


def local_dt(value):
    """Normalize a Socrata floating local timestamp for lexical comparisons."""
    if value in (None, ""):
        return None
    s = str(value).strip().replace(" ", "T")
    if len(s) < 16:
        return None
    candidate = s[:19] if len(s) >= 19 else s + ":00"
    try:
        dt.datetime.fromisoformat(candidate)
    except ValueError:
        return None
    return candidate


def main():
    html = SITE.read_text(encoding="utf-8")
    match, payload = parse_payload(html)

    source = get_json(SOURCE_URL)
    if source.get("type") != "FeatureCollection" or not isinstance(source.get("features"), list):
        raise ValueError("Closure source is not a GeoJSON FeatureCollection")

    source_features = source["features"]
    source_count = len(source_features)
    if not 50 <= source_count <= 20_000:
        raise ValueError(f"Unexpected closure source feature count: {source_count}")

    street_cnns = {
        str((f.get("properties") or {}).get("cnn") or "").strip()
        for f in payload.get("streets", {}).get("features", [])
    }
    street_cnns.discard("")

    kept = []
    omitted = collections.Counter()
    status_counts = collections.Counter()
    type_counts = collections.Counter()
    cnn_with = 0
    cnn_match = 0
    objectids = set()
    data_as_of_values = []
    starts = []
    ends = []

    for feature in source_features:
        p = feature.get("properties") or {}
        status = str(p.get("status") or "").strip()
        status_counts[status or "(blank)"] += 1

        if status and status.upper() != "PERMITTED":
            omitted["non_permitted_status"] += 1
            continue

        geom = feature.get("geometry") or {}
        if geom.get("type") not in {"LineString", "MultiLineString"}:
            omitted["missing_or_non_line_geometry"] += 1
            continue

        start = local_dt(p.get("start_dt"))
        end = local_dt(p.get("end_dt"))
        if start is None or end is None or end < start:
            omitted["invalid_time_window"] += 1
            continue

        oid = str(p.get("objectid") or "").strip()
        if oid:
            if oid in objectids:
                raise ValueError(f"Duplicate closure objectid in source: {oid}")
            objectids.add(oid)

        cnn = str(p.get("cnn") or "").strip()
        if cnn:
            cnn_with += 1
            if cnn in street_cnns:
                cnn_match += 1

        ctype = str(p.get("type") or "").strip() or "Unspecified"
        type_counts[ctype] += 1

        if p.get("data_as_of") not in (None, ""):
            data_as_of_values.append(str(p.get("data_as_of")))
        starts.append(start)
        ends.append(end)

        trimmed_props = {k: p.get(k) for k in KEEP_FIELDS if k in p}
        trimmed_props["start_local"] = start
        trimmed_props["end_local"] = end

        kept.append({
            "type": "Feature",
            "geometry": geom,
            "properties": trimmed_props,
        })

    if not kept:
        raise ValueError("Closure source produced zero valid line features")
    if omitted["invalid_time_window"] > max(10, int(0.05 * source_count)):
        raise ValueError(
            f"Too many closure rows have invalid/missing time windows: "
            f"{omitted['invalid_time_window']}/{source_count}"
        )
    if omitted["missing_or_non_line_geometry"] > max(10, int(0.05 * source_count)):
        raise ValueError(
            f"Too many closure rows have missing/non-line geometry: "
            f"{omitted['missing_or_non_line_geometry']}/{source_count}"
        )

    match_rate = (cnn_match / cnn_with) if cnn_with else None
    if cnn_with >= 100 and match_rate is not None and match_rate < 0.80:
        raise ValueError(f"Unexpectedly low closure CNN match rate: {cnn_match}/{cnn_with}")

    payload["closures"] = {"type": "FeatureCollection", "features": kept}

    meta = payload.setdefault("meta", {})
    meta["closure_dataset_id"] = DATASET_ID
    meta["closure_source_url"] = SOURCE_URL
    meta["closure_source_count"] = source_count
    meta["closure_display_count"] = len(kept)
    meta["closure_omitted_counts"] = dict(omitted)
    meta["closure_status_counts"] = dict(status_counts)
    meta["closure_type_counts"] = dict(type_counts)
    meta["closure_cnn_present_count"] = cnn_with
    meta["closure_cnn_match_count"] = cnn_match
    meta["closure_cnn_match_rate"] = round(match_rate, 4) if match_rate is not None else None
    meta["closure_data_as_of"] = max(data_as_of_values) if data_as_of_values else None
    meta["closure_min_start_local"] = min(starts)
    meta["closure_max_end_local"] = max(ends)
    meta["closure_time_basis"] = "America/Los_Angeles local floating start_dt/end_dt"
    meta["closure_scope_note"] = (
        "SFMTA-permitted temporary closures only; does not include every closure "
        "managed by Public Works, SFPD, or other agencies."
    )

    packed = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    SITE.write_text(html[:match.start(1)] + packed + html[match.end(1):], encoding="utf-8")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["closures"] = {
        "dataset_id": DATASET_ID,
        "source_url": SOURCE_URL,
        "source_feature_count": source_count,
        "embedded_feature_count": len(kept),
        "omitted_counts": dict(omitted),
        "status_counts": dict(status_counts),
        "type_counts": dict(type_counts),
        "cnn_present_count": cnn_with,
        "cnn_match_count": cnn_match,
        "cnn_match_rate": round(match_rate, 4) if match_rate is not None else None,
        "data_as_of": max(data_as_of_values) if data_as_of_values else None,
        "min_start_local": min(starts),
        "max_end_local": max(ends),
        "time_basis": "America/Los_Angeles local floating start_dt/end_dt",
        "filter_rule": "show feature when start_local <= selected SF local datetime <= end_local",
        "interpretation": (
            "official SFMTA-permitted temporary street-closure line geometry; "
            "not proof that pedestrian access is blocked and not a complete inventory "
            "of closures managed by other City departments"
        ),
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"closures: {len(kept)}/{source_count} embedded; omitted={dict(omitted)}")
    print(f"closure statuses: {dict(status_counts)}")
    print(f"closure types: {dict(type_counts)}")
    print(f"closure CNN match: {cnn_match}/{cnn_with} ({match_rate:.1%})" if cnn_with else "closure CNN match: no CNN values")
    print(f"closure local time range: {min(starts)} to {max(ends)}")
    print(f"closure data_as_of: {max(data_as_of_values) if data_as_of_values else 'unknown'}")


if __name__ == "__main__":
    main()
