#!/usr/bin/env python3
"""Build a transparent precinct-level reported-incident context index.

The index is derived from the same official SFPD incident-report source used by
reported-incident history. It is intentionally *not* called a crime-risk or
safety score: public incident locations are privacy-mapped to intersections,
reports can change, and the severity tiers below are a product-defined weighting
for operational context rather than an SFPD severity classification.
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import math
import pathlib
import re
import time
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

from shapely.geometry import Point, shape
from shapely.strtree import STRtree

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = ROOT / "_site" / "index.html"
MANIFEST = ROOT / "_site" / "data-manifest.json"
INCIDENT_ID = "wg3w-h783"
INCIDENT_API = "https://data.sf.gov/resource/wg3w-h783.json"
SF_TZ = ZoneInfo("America/Los_Angeles")
WINDOWS = (30, 90, 180, 365)
HEADERS = {
    "User-Agent": "sf-field-conditions-map/1.0 (+https://github.com/shreyammm/sf-field-conditions-map)",
    "Accept": "application/json,*/*;q=0.1",
}

TIER4_EXACT = {
    "homicide", "rape", "robbery",
    "human trafficking (a), commercial sex acts",
    "human trafficking (b), involuntary servitude",
    "human trafficking", "human trafficking, commercial sex acts",
}
TIER3_EXACT = {
    "arson", "weapons carrying etc", "weapons offense", "weapons offence",
    "other sexual offenses", "sex offense",
}
TIER2_EXACT = {"burglary", "motor vehicle theft"}
TIER1_EXACT = {
    "larceny theft", "stolen property", "vandalism", "malicious mischief",
    "fraud", "forgery and counterfeiting", "embezzlement", "drug offense",
    "drug violation", "prostitution", "disorderly conduct",
}


def norm(v) -> str:
    return " ".join(str(v or "").strip().lower().split())


def severity_tier(category, subcategory) -> int:
    c, s = norm(category), norm(subcategory)
    if c == "assault":
        return 4 if "aggravated" in s else 3
    if c in TIER4_EXACT:
        return 4
    if c in TIER3_EXACT:
        return 3
    if c in TIER2_EXACT:
        return 2
    if c in TIER1_EXACT:
        return 1
    return 0


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
                time.sleep(attempt * 2)
    raise RuntimeError(f"Failed after {attempts} attempts: {url}\n{last}") from last


def parse_payload(html: str):
    m = re.search(r"window\.SF_FIELD_DATA=(\{.*?\});\s*</script>", html, re.S)
    if not m:
        raise ValueError("Embedded payload not found")
    return m, json.loads(m.group(1))


def parse_local(v):
    s = str(v or "").strip().replace(" ", "T")
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s[:19])
    except ValueError:
        return None


def parse_float(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def precinct_id(f):
    p = f.get("properties") or {}
    return str(p.get("prec_2022") or p.get("precinct") or p.get("id") or "").strip()


def source_rows(query_start: dt.datetime):
    where = (
        f"incident_datetime >= '{query_start.isoformat(timespec='seconds')}' "
        "AND latitude IS NOT NULL AND longitude IS NOT NULL "
        "AND report_type_description IN ('Initial','Vehicle Initial','Coplogic Initial')"
    )
    select = (
        "incident_id,incident_datetime,incident_category,incident_subcategory,"
        "report_type_description,latitude,longitude"
    )
    rows, offset, limit = [], 0, 50_000
    while True:
        qs = urllib.parse.urlencode({
            "$select": select, "$where": where,
            "$order": "incident_datetime DESC,incident_id,incident_category,incident_subcategory",
            "$limit": limit, "$offset": offset,
        })
        batch = get_json(INCIDENT_API + "?" + qs)
        if not isinstance(batch, list):
            raise ValueError("Incident API response is not a list")
        rows.extend(batch)
        if len(batch) < limit:
            break
        offset += limit
        if offset >= 250_000:
            raise ValueError("Precinct incident-index query hit 250k-row safety cap")
    if len(rows) < 10_000:
        raise ValueError(f"Incident-index query unexpectedly small: {len(rows)}")
    return rows


def competition_ranks(values: dict[str, float]):
    ordered = sorted(values.items(), key=lambda kv: (-kv[1], kv[0]))
    ranks = {}
    prior = None
    current_rank = 0
    for pos, (pid, value) in enumerate(ordered, 1):
        if prior is None or abs(value - prior) > 1e-9:
            current_rank = pos
            prior = value
        ranks[pid] = current_rank
    n = max(1, len(ordered))
    index = {
        pid: (0.0 if values[pid] <= 0 else (100.0 if n == 1 else 100.0 * (n - rank) / (n - 1)))
        for pid, rank in ranks.items()
    }
    return ranks, index


def main():
    html = SITE.read_text(encoding="utf-8")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    m, payload = parse_payload(html)
    precincts = (payload.get("precincts") or {}).get("features") or []
    geoms, ids = [], []
    for f in precincts:
        pid = precinct_id(f)
        g = shape(f.get("geometry"))
        if not pid or g.is_empty or not g.is_valid:
            raise ValueError(f"Invalid precinct geometry/id while building incident index: {pid!r}")
        geoms.append(g); ids.append(pid)
    if len(ids) != len(set(ids)) or not 400 <= len(ids) <= 800:
        raise ValueError(f"Unexpected precinct id set: {len(ids)} / unique={len(set(ids))}")
    tree = STRtree(geoms)

    hist_meta = manifest.get("historical_incidents") or {}
    query_start = parse_local(hist_meta.get("query_start_local"))
    if query_start is None:
        query_start = dt.datetime.now(SF_TZ).replace(tzinfo=None, microsecond=0) - dt.timedelta(days=366)
    anchor = query_start + dt.timedelta(days=366)
    cut = {days: anchor - dt.timedelta(days=days) for days in WINDOWS}
    rows = source_rows(query_start)

    grouped = {}
    row_invalid = 0
    for r in rows:
        iid = str(r.get("incident_id") or "").strip()
        when = parse_local(r.get("incident_datetime"))
        lat, lon = parse_float(r.get("latitude")), parse_float(r.get("longitude"))
        if not iid or when is None or lat is None or lon is None or not (-122.60 <= lon <= -122.25 and 37.65 <= lat <= 37.90):
            row_invalid += 1; continue
        rec = grouped.setdefault(iid, {"when": when, "coords": collections.Counter(), "cats": set()})
        rec["when"] = max(rec["when"], when)
        rec["coords"][(round(lon, 7), round(lat, 7))] += 1
        rec["cats"].add((str(r.get("incident_category") or "").strip(), str(r.get("incident_subcategory") or "").strip()))
    if len(grouped) < 8_000:
        raise ValueError(f"Too few unique incident IDs for index: {len(grouped)}")

    observed_categories = collections.Counter()
    scored_category_incidents = collections.Counter()
    excluded_category_incidents = collections.Counter()
    per_precinct = {
        pid: {days: {"reports": 0.0, "weighted": 0.0, "tiers": {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}} for days in WINDOWS}
        for pid in ids
    }
    mapped_unique = mapped_365_unique = scored_mapped_unique = scored_mapped_365 = 0
    unscored_mapped_unique = unassigned_scored_unique = boundary_split_unique = coordinate_conflict_incidents = 0

    for iid, rec in grouped.items():
        if len(rec["coords"]) > 1:
            coordinate_conflict_incidents += 1
        (lon, lat), _ = rec["coords"].most_common(1)[0]
        pt = Point(lon, lat)
        hits = []
        for idx in tree.query(pt, predicate="intersects"):
            i = int(idx)
            if geoms[i].covers(pt):
                hits.append(ids[i])
        hits = sorted(set(hits))
        if hits:
            mapped_unique += 1
            if rec["when"] >= cut[365]:
                mapped_365_unique += 1

        tiers, cats_for_incident = [], set()
        for cat, sub in rec["cats"]:
            nc = norm(cat)
            if nc:
                cats_for_incident.add(cat.strip()); observed_categories[nc] += 1
            t = severity_tier(cat, sub)
            if t:
                tiers.append(t)
        tier = max(tiers) if tiers else 0
        if tier <= 0:
            if hits:
                unscored_mapped_unique += 1
            for cat in cats_for_incident or {"(blank)"}:
                excluded_category_incidents[cat] += 1
            continue
        for cat in cats_for_incident:
            if any(severity_tier(c, s) > 0 for c, s in rec["cats"] if c == cat):
                scored_category_incidents[cat] += 1
        if not hits:
            unassigned_scored_unique += 1; continue
        scored_mapped_unique += 1
        if rec["when"] >= cut[365]:
            scored_mapped_365 += 1
        if len(hits) > 1:
            boundary_split_unique += 1
        share = 1.0 / len(hits)
        for days in WINDOWS:
            if rec["when"] < cut[days]:
                continue
            for pid in hits:
                x = per_precinct[pid][days]
                x["reports"] += share; x["weighted"] += tier * share; x["tiers"][tier] += share

    ranks_by_window, index_by_window = {}, {}
    for days in WINDOWS:
        vals = {pid: per_precinct[pid][days]["weighted"] * 30.0 / days for pid in ids}
        ranks_by_window[days], index_by_window[days] = competition_ranks(vals)

    records = []
    for pid in sorted(ids):
        windows = {}
        for days in WINDOWS:
            x = per_precinct[pid][days]
            windows[str(days)] = {
                "reports": round(x["reports"], 3), "weighted": round(x["weighted"], 3),
                "reports_per30": round(x["reports"] * 30.0 / days, 2),
                "weighted_per30": round(x["weighted"] * 30.0 / days, 2),
                "index": round(index_by_window[days][pid], 1), "rank": int(ranks_by_window[days][pid]),
                "tiers": {str(t): round(x["tiers"][t], 3) for t in (1, 2, 3, 4)},
            }
        records.append({"precinct": pid, "windows": windows})

    assigned_scored_365 = sum(per_precinct[pid][365]["reports"] for pid in ids)
    if abs(assigned_scored_365 - scored_mapped_365) > 1e-6:
        raise ValueError(f"Split allocation did not preserve scored 365d total: {assigned_scored_365} vs {scored_mapped_365}")
    coverage_365 = round(100.0 * scored_mapped_365 / mapped_365_unique, 1) if mapped_365_unique else None
    payload["precinct_incident_index"] = {
        "source_dataset_id": INCIDENT_ID, "anchor_local": anchor.isoformat(timespec="seconds"),
        "meta": {"weighted_category_coverage_365d_pct": coverage_365}, "precincts": records,
    }
    packed = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = html[:m.start(1)] + packed + html[m.end(1):]
    SITE.write_text(html, encoding="utf-8")

    manifest["precinct_incident_index"] = {
        "dataset_id": INCIDENT_ID, "source_url": "https://data.sf.gov/d/wg3w-h783",
        "query_start_local": query_start.isoformat(timespec="seconds"), "anchor_local": anchor.isoformat(timespec="seconds"),
        "windows_days": list(WINDOWS),
        "report_filter": "Initial, Vehicle Initial, Coplogic Initial; non-null public latitude/longitude",
        "incident_dedupe_rule": "one record per incident_id; severity tier is maximum across that incident's source categories; most-common public coordinate used if source rows conflict",
        "boundary_allocation_rule": "privacy-mapped points covered by multiple precinct polygons are split equally across those precincts instead of being arbitrarily assigned; points outside precinct geometry are omitted",
        "score_formula": "for each window, weighted_per30 = sum(product-defined severity tier weights 1-4 after boundary splitting) * 30 / window_days; index 0-100 is a citywide rank transform of weighted_per30 with the highest burden at 100; rank 1 is highest weighted_per30",
        "severity_interpretation": "product-defined operational context weighting, not an SFPD severity classification and not a safety/risk probability",
        "severity_tiers": {
            "4": "Homicide, Rape, Robbery, Human Trafficking, and aggravated Assault",
            "3": "other Assault, Arson, Weapons categories, and Other Sexual Offenses/Sex Offense",
            "2": "Burglary and Motor Vehicle Theft",
            "1": "Larceny Theft, Stolen Property, Vandalism/Malicious Mischief, Fraud, Forgery/Counterfeiting, Embezzlement, Drug categories, Prostitution, and Disorderly Conduct",
            "0": "all other/ambiguous/non-criminal/admin categories excluded rather than assigned a guessed severity",
        },
        "source_rows_fetched": len(rows), "unique_incident_ids": len(grouped),
        "mapped_unique_incidents": mapped_unique, "scored_mapped_unique_incidents": scored_mapped_unique,
        "mapped_365d_incidents_with_precinct": mapped_365_unique, "scored_mapped_365d_incidents": scored_mapped_365,
        "weighted_category_coverage_365d_pct": coverage_365,
        "unscored_mapped_unique_incidents": unscored_mapped_unique,
        "unassigned_scored_unique_incidents": unassigned_scored_unique,
        "boundary_split_unique_incidents": boundary_split_unique,
        "coordinate_conflict_incidents": coordinate_conflict_incidents, "invalid_rows_omitted": row_invalid,
        "assigned_scored_365d_total": round(assigned_scored_365, 6),
        "observed_category_incident_rows": dict(sorted(observed_categories.items())),
        "scored_category_incidents": dict(sorted(scored_category_incidents.items())),
        "excluded_category_incidents": dict(sorted(excluded_category_incidents.items())),
        "privacy_caveat": "SFPD public locations are privacy-mapped to nearby intersections for anonymity and can move across precinct boundaries; precinct rankings are approximate geographic context",
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        "precinct incident index added: "
        f"precincts={len(records)}; source_rows={len(rows)}; unique={len(grouped)}; "
        f"mapped={mapped_unique}; scored_mapped={scored_mapped_unique}; "
        f"boundary_split={boundary_split_unique}; unassigned_scored={unassigned_scored_unique}; coverage365={coverage_365}%"
    )
    print("observed incident categories:", sorted(observed_categories))


if __name__ == "__main__":
    main()
