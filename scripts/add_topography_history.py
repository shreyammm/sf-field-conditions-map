#!/usr/bin/env python3
"""Add official topographic contours and rolling SFPD incident-history context.

Both datasets are fetched at build time and embedded into the static artifact.
No additional browser network requests are introduced.
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

CONTOUR_ID = "rnbg-2qxw"
CONTOUR_URL = "https://data.sf.gov/api/v3/views/rnbg-2qxw/query.geojson?accessType=DOWNLOAD"
INCIDENT_ID = "wg3w-h783"
INCIDENT_API = "https://data.sf.gov/resource/wg3w-h783.json"
INCIDENT_META = "https://data.sf.gov/api/views/wg3w-h783"
SF_TZ = ZoneInfo("America/Los_Angeles")
HEADERS = {
    "User-Agent": "sf-field-conditions-map/1.0 (+https://github.com/shreyammm/sf-field-conditions-map)",
    "Accept": "application/json, application/geo+json;q=0.9, */*;q=0.1",
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
                time.sleep(attempt * 2)
    raise RuntimeError(f"Failed after {attempts} attempts: {url}\n{last}") from last


def payload_match(html: str):
    m = re.search(r"window\.SF_FIELD_DATA=(\{.*?\});\s*</script>", html, re.S)
    if not m:
        raise ValueError("Embedded payload not found")
    return m, json.loads(m.group(1))


def contour_elevation(f):
    p = f.get("properties") or {}
    for key in ("ELEVATION", "elevation"):
        try:
            if p.get(key) not in (None, ""):
                return float(p[key])
        except (TypeError, ValueError):
            pass
    return None


def build_topography():
    raw = get_json(CONTOUR_URL)
    if raw.get("type") != "FeatureCollection":
        raise ValueError("Contour source is not GeoJSON")
    src = raw.get("features") or []
    if not 10_000 <= len(src) <= 20_000:
        raise ValueError(f"Unexpected contour source count: {len(src)}")
    out, zs = [], []
    for f in src:
        z = contour_elevation(f)
        g = f.get("geometry") or {}
        if z is None or g.get("type") not in {"LineString", "MultiLineString"}:
            continue
        if abs(z / 5.0 - round(z / 5.0)) > 0.02:
            raise ValueError(f"Contour elevation off documented 5-ft interval: {z}")
        # Every fifth official line is displayed. This is a source subset, not
        # an interpolated terrain surface.
        if abs(z / 25.0 - round(z / 25.0)) > 0.02:
            continue
        zi = int(round(z))
        out.append({
            "type": "Feature",
            "geometry": g,
            "properties": {"elevation_ft": zi, "major": zi % 100 == 0},
        })
        zs.append(zi)
    if not 1_500 <= len(out) <= 5_000:
        raise ValueError(f"Unexpected 25-ft contour display count: {len(out)}")
    if not zs or min(zs) < -100 or max(zs) > 1_500:
        raise ValueError("Implausible SF contour elevation range")
    return {"type": "FeatureCollection", "features": out}, {
        "dataset_id": CONTOUR_ID,
        "source_url": CONTOUR_URL,
        "source_feature_count": len(src),
        "display_feature_count": len(out),
        "source_interval_ft": 5,
        "display_interval_ft": 25,
        "major_interval_ft": 100,
        "interpretation": "official contour geometry subset; no interpolated terrain surface",
    }


def parse_float(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def parse_local(v):
    s = str(v or "").strip().replace(" ", "T")
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s[:19])
    except ValueError:
        return None


def precinct_id(f):
    p = f.get("properties") or {}
    return str(p.get("prec_2022") or p.get("precinct") or p.get("id") or "").strip()


def precinct_index(payload):
    geoms, ids = [], []
    for f in (payload.get("precincts") or {}).get("features") or []:
        pid = precinct_id(f)
        if not pid:
            continue
        g = shape(f.get("geometry"))
        if not g.is_empty:
            geoms.append(g)
            ids.append(pid)
    return geoms, ids, STRtree(geoms)


def point_precincts(lon, lat, geoms, ids, tree):
    pt = Point(lon, lat)
    found = []
    for idx in tree.query(pt):
        if geoms[int(idx)].covers(pt):
            found.append(ids[int(idx)])
    return sorted(set(found))


def incident_rows(now_sf):
    start = (now_sf - dt.timedelta(days=366)).replace(tzinfo=None, microsecond=0)
    where = (
        f"incident_datetime >= '{start.isoformat(timespec='seconds')}' "
        "AND latitude IS NOT NULL AND longitude IS NOT NULL "
        "AND report_type_description IN ('Initial','Vehicle Initial','Coplogic Initial')"
    )
    select = "incident_id,incident_datetime,report_type_description,latitude,longitude,intersection"
    rows, offset, limit = [], 0, 50_000
    while True:
        qs = urllib.parse.urlencode({
            "$select": select,
            "$where": where,
            "$order": "incident_datetime DESC, incident_id",
            "$limit": limit,
            "$offset": offset,
        })
        batch = get_json(INCIDENT_API + "?" + qs)
        if not isinstance(batch, list):
            raise ValueError("Incident API response is not a list")
        rows.extend(batch)
        if len(batch) < limit:
            break
        offset += limit
        if offset >= 250_000:
            raise ValueError("Historical incident query hit 250k-row safety cap")
    if len(rows) < 10_000:
        raise ValueError(f"Historical incident query unexpectedly small: {len(rows)}")
    return rows, start


def build_history(payload, now_sf):
    rows, query_start = incident_rows(now_sf)
    now_naive = now_sf.replace(tzinfo=None)
    cut = {d: now_naive - dt.timedelta(days=d) for d in (30, 90, 180, 365)}

    # An incident ID can occupy multiple source rows because one report can have
    # multiple incident codes. Count each incident_id once.
    unique = {}
    bad = 0
    coord_conflicts = 0
    for r in rows:
        iid = str(r.get("incident_id") or "").strip()
        when = parse_local(r.get("incident_datetime"))
        lat, lon = parse_float(r.get("latitude")), parse_float(r.get("longitude"))
        if not iid or when is None or lat is None or lon is None or not (-122.60 <= lon <= -122.25 and 37.65 <= lat <= 37.90):
            bad += 1
            continue
        rec = {"when": when, "lat": lat, "lon": lon, "intersection": str(r.get("intersection") or "").strip()}
        prev = unique.get(iid)
        if prev is None:
            unique[iid] = rec
        else:
            if abs(prev["lat"] - lat) > 0.00005 or abs(prev["lon"] - lon) > 0.00005:
                coord_conflicts += 1
            if when > prev["when"]:
                unique[iid] = rec
    if len(unique) < 8_000:
        raise ValueError(f"Too few unique incident IDs after dedupe: {len(unique)}")

    groups = {}
    for r in unique.values():
        key = (round(r["lon"], 5), round(r["lat"], 5))
        g = groups.setdefault(key, {
            "counts": {30: 0, 90: 0, 180: 0, 365: 0},
            "names": collections.Counter(), "latest": None,
        })
        if r["intersection"]:
            g["names"][r["intersection"]] += 1
        if g["latest"] is None or r["when"] > g["latest"]:
            g["latest"] = r["when"]
        for days in cut:
            if r["when"] >= cut[days]:
                g["counts"][days] += 1

    pgeoms, pids, ptree = precinct_index(payload)
    features, unassigned = [], 0
    for (lon, lat), g in groups.items():
        if not g["counts"][365]:
            continue
        fps = point_precincts(lon, lat, pgeoms, pids, ptree)
        if not fps:
            unassigned += 1
        label = g["names"].most_common(1)[0][0] if g["names"] else ""
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "c30": g["counts"][30], "c90": g["counts"][90],
                "c180": g["counts"][180], "c365": g["counts"][365],
                "intersection": label,
                "latest_incident": g["latest"].isoformat(timespec="seconds") if g["latest"] else None,
                "focus_precincts": fps,
            },
        })
    if not 500 <= len(features) <= 10_000:
        raise ValueError(f"Historical mapped-point count implausible: {len(features)}")

    counts = {str(d): sum(int(f["properties"][f"c{d}"]) for f in features) for d in (30, 90, 180, 365)}
    if not (counts["30"] <= counts["90"] <= counts["180"] <= counts["365"]):
        raise ValueError(f"Historical incident windows are not monotonic: {counts}")

    meta = get_json(INCIDENT_META, attempts=2, timeout=45)
    updated = None
    try:
        updated = dt.datetime.fromtimestamp(int(meta.get("rowsUpdatedAt")), tz=dt.timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        pass

    return {"type": "FeatureCollection", "features": features}, {
        "dataset_id": INCIDENT_ID,
        "source_url": "https://data.sf.gov/d/wg3w-h783",
        "api_url": INCIDENT_API,
        "query_start_local": query_start.isoformat(timespec="seconds"),
        "report_filter": "Initial, Vehicle Initial, Coplogic Initial",
        "dedupe_rule": "one count per incident_id; repeated incident-code rows do not multiply counts",
        "source_rows_fetched": len(rows),
        "unique_incident_ids": len(unique),
        "mapped_public_points": len(features),
        "unassigned_public_points": unassigned,
        "invalid_rows_omitted": bad,
        "coordinate_conflicts_seen": coord_conflicts,
        "window_unique_incident_counts": counts,
        "source_rows_updated_at": updated,
        "location_interpretation": "public locations are privacy-mapped to nearby intersections, not exact event addresses",
        "count_interpretation": "unique approved initial incident reports; not convictions and not a severity score",
    }


def replace_one(s, old, new, label):
    if old not in s:
        raise ValueError(f"Topography/history UI anchor missing: {label}")
    return s.replace(old, new, 1)


def patch_ui(html):
    css = '''\n/* actual topography + historical incident context */\n.topoc{fill:none;stroke:#9a6b45;stroke-opacity:.24;stroke-width:.65;vector-effect:non-scaling-stroke;pointer-events:none}.topoc.major{stroke:#6f4b2f;stroke-opacity:.38;stroke-width:1.05}.histp{stroke:#fff;stroke-width:1.25;vector-effect:non-scaling-stroke;cursor:pointer;pointer-events:all;filter:drop-shadow(0 0 1px rgba(17,24,39,.18))}.histp:hover{stroke:#111827;stroke-width:2}.hr1{fill:#ddd6fe}.hr2{fill:#a78bfa}.hr3{fill:#7c3aed}.hr4{fill:#4c1d95}.histControls{margin:7px 0 3px}.histLegend{font-size:9.8px;line-height:1.35;color:#667085;margin-top:6px}.histLegend .dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin:0 3px 0 7px;vertical-align:-1px}.histLegend .dot:first-child{margin-left:0}.histFocus{margin-top:8px;padding:7px 8px;border:1px solid #ddd6fe;border-radius:7px;background:#faf9ff;font-size:10.5px;line-height:1.4;color:#475467}.histFocus b{color:#344054}\n'''
    html = replace_one(html, "</style>", css + "</style>", "style end")

    old = '<div class="row"><div><div class="label">Hill steepness</div><div class="muted">Estimated from official 5-ft elevation contours</div></div><label class="switch"><input id="hToggle" type="checkbox" checked><span></span></label></div>'
    new = '<div class="row"><div><div class="label">Topography</div><div class="muted">Official elevation contours · 25-ft display interval</div></div><label class="switch"><input id="topoToggle" type="checkbox" checked><span></span></label></div>\n<div class="row"><div><div class="label">Street steepness</div><div class="muted">Optional derived street-grade estimate</div></div><label class="switch"><input id="hToggle" type="checkbox"><span></span></label></div>'
    html = replace_one(html, old, new, "topography controls")

    live_anchor = '<div class="row"><div><div class="label">Recent law-enforcement dispatch activity</div>'
    start = html.find(live_anchor)
    if start < 0:
        raise ValueError("Recent dispatch controls not found")
    incident_end = html.find('</div>', html.find('class="incidentctl"', start))
    # Find the outer incidentctl close by using the next row marker after it.
    next_row = html.find('<div class="row">', incident_end + 6)
    insert_at = next_row if next_row > 0 else html.find('</section>', start)
    if insert_at < 0:
        raise ValueError("Unable to place historical controls")
    controls = '''<div class="row"><div><div class="label">Reported incident history</div><div class="muted">SFPD incident reports · privacy-mapped intersections</div></div><label class="switch"><input id="histToggle" type="checkbox"><span></span></label></div>\n<div class="histControls"><div class="label" style="font-size:12px;margin:6px 0">Historical window</div><div class="pills" id="histPills"><button class="pill" data-hdays="30">1 month</button><button class="pill active" data-hdays="90">3 months</button><button class="pill" data-hdays="180">6 months</button><button class="pill" data-hdays="365">1 year</button></div><div class="histLegend"><span class="dot" style="background:#ddd6fe"></span>&lt;2/mo <span class="dot" style="background:#a78bfa"></span>2–4.9/mo <span class="dot" style="background:#7c3aed"></span>5–9.9/mo <span class="dot" style="background:#4c1d95"></span>10+/mo</div><div class="muted" style="margin-top:6px">Fixed-size circles. Darker color = more unique incident reports per 30 days at that public privacy-mapped intersection. This is report volume, not severity, and not every report establishes a crime.</div></div>\n'''
    html = html[:insert_at] + controls + html[insert_at:]

    legend_anchor = '<div class="legend"><span class="ln street-ln"></span><span class="legendtext">Major / arterial street centerline</span>'
    i = html.find(legend_anchor)
    if i < 0:
        raise ValueError("Legend anchor missing")
    topo_legend = '<div class="legend"><span class="ln" style="border-top:1px solid #9a6b45"></span><span class="legendtext">Topographic contour · 25 ft</span><span class="info" title="Every fifth official 5-ft contour is shown for readability.">ⓘ</span></div>\n<div class="legend"><span class="ln" style="border-top:2px solid #6f4b2f"></span><span class="legendtext">Index contour · 100 ft</span></div>\n'
    html = html[:i] + topo_legend + html[i:]

    hill_method = '<div class="methoditem"><strong>Hill steepness</strong>'
    i = html.find(hill_method)
    if i < 0:
        raise ValueError("Hill methodology anchor missing")
    topo_method = '<div class="methoditem"><strong>Topography</strong><br>Uses the official DataSF Elevation Contours dataset <span class="code">rnbg-2qxw</span> <a class="src-link" href="https://data.sf.gov/d/rnbg-2qxw" target="_blank" rel="noopener noreferrer">official source ↗</a>. The source contains 5-foot elevation contours based on the San Francisco Elevation Datum. The map displays the source geometry at a 25-foot interval and emphasizes 100-foot index contours for readability. No synthetic elevation surface is interpolated.</div>\n'
    html = html[:i] + topo_method + html[i:]
    end = html.find('</details>', i)
    if end < 0:
        raise ValueError("Methodology details end missing")
    hist_method = '<div class="methoditem"><strong>Reported incident history</strong><br>Build-time snapshot from SFPD/DataSF dataset <span class="code">wg3w-h783</span> <a class="src-link" href="https://data.sf.gov/d/wg3w-h783" target="_blank" rel="noopener noreferrer">official source ↗</a>. The map keeps initial report types, counts each <span class="code">incident_id</span> once so multiple incident-code rows do not inflate totals, and groups the City\'s privacy-mapped public points by intersection coordinate. The 1/3/6/12-month buttons use rolling 30/90/180/365-day windows. Circle size is fixed; color encodes average unique reports per 30 days. These are approved police incident reports, not convictions, not a severity score, and the public points are not exact event addresses.</div>\n'
    html = html[:end] + hist_method + html[end:]

    src = '<a href="https://data.sf.gov/d/gnap-fj3t" target="_blank" rel="noopener noreferrer">Live dispatch calls ↗</a>'
    html = replace_one(html, src, src + '<a href="https://data.sf.gov/d/wg3w-h783" target="_blank" rel="noopener noreferrer">Reported incident history ↗</a>', "source directory")

    html = replace_one(html, '<g id="view"><g id="sl"></g>', '<g id="view"><g id="tl"></g><g id="sl"></g>', "topography SVG group")
    html = replace_one(html, '<g id="il"></g>', '<g id="hil"></g><g id="il"></g>', "historical SVG group")

    init_call = 'init();loadFocusFromUrl();'
    js = r'''
// ----- actual topography + historical incident context -----
const tl=$('tl'),hil=$('hil');S.stopo=true;S.sh=false;S.shi=false;S.hdays=90;
function renderTopo(){tl.replaceChildren();if(!S.stopo){tl.style.display='none';return}tl.style.display='';for(const f of(DATA.topography?.features||[])){const d=linePath(f.geometry);if(!d)continue;const e=document.createElementNS('http://www.w3.org/2000/svg','path');e.setAttribute('d',d);e.setAttribute('class','topoc'+((f.properties||{}).major?' major':''));tl.appendChild(e)}}
function hcount(p){return Number(p['c'+S.hdays]||0)}function hrate(p){return hcount(p)*30/Number(S.hdays||30)}function hclass(p){const r=hrate(p);return r>=10?'hr4':r>=5?'hr3':r>=2?'hr2':'hr1'}function hwindow(){return S.hdays===30?'last month':S.hdays===90?'last 3 months':S.hdays===180?'last 6 months':'last year'}
function hinfocus(p){if(!PFOCUS.size)return true;const ps=Array.isArray(p.focus_precincts)?p.focus_precincts:[];return ps.some(x=>PFOCUS.has(String(x)))}
function renderHistory(){hil.replaceChildren();if(!S.shi){hil.style.display='none';updateHistorySummary();return}hil.style.display='';for(const f of(DATA.historical_incidents?.features||[])){const p=f.properties||{},n=hcount(p);if(!n||!hinfocus(p))continue;const c=f.geometry?.coordinates;if(!Array.isArray(c)||c.length<2)continue;const q=proj(c),e=document.createElementNS('http://www.w3.org/2000/svg','circle');e.setAttribute('cx',q[0]);e.setAttribute('cy',q[1]);e.setAttribute('r',String(4.2/S.z));e.setAttribute('class','histp '+hclass(p));e.f=f;e.dataset.k='hi';bind(e);hil.appendChild(e)}updateHistorySummary()}
function selectedHistory(){let count=0,points=0;for(const f of(DATA.historical_incidents?.features||[])){const p=f.properties||{},n=hcount(p);if(n&&hinfocus(p)){count+=n;points++}}return{count,points,rate:count*30/Number(S.hdays||30)}}
function updateHistorySummary(){const box=$('focusSummary');if(!box)return;box.querySelector('.histFocus')?.remove();if(!S.shi||!PFOCUS.size)return;const x=selectedHistory(),d=document.createElement('div');d.className='histFocus';d.innerHTML=`<b>Reported incident context · ${esc(hwindow())}</b><br>${x.count.toLocaleString()} unique incident report${x.count===1?'':'s'} at ${x.points.toLocaleString()} public mapped intersection point${x.points===1?'':'s'} · ${x.rate.toFixed(1)} reports per 30 days across the selected area.<br><span class="muted">Privacy-mapped public points; report volume is not a severity score and does not establish that every report was a crime.</span>`;box.appendChild(d)}
const _hoverHist=hover;hover=function(e){if(e.dataset.k!=='hi')return _hoverHist(e);const p=e.f.properties||{},n=hcount(p),r=hrate(p),loc=p.intersection||'Privacy-mapped intersection';return `<strong>${esc(loc)}</strong>${n.toLocaleString()} unique SFPD incident report${n===1?'':'s'} · ${esc(hwindow())}<br>${r.toFixed(1)} per 30 days<br><span style="opacity:.82">Public location is privacy-mapped; color represents report volume, not severity.</span>`};
const _clickHist=clicked;clicked=function(e){if(e.dataset.k!=='hi')return _clickHist(e);const p=e.f.properties||{},n=hcount(p),r=hrate(p),loc=p.intersection||'Privacy-mapped intersection';return `<strong>Reported incident history</strong><br>${esc(loc)}<br>${n.toLocaleString()} unique approved initial incident report${n===1?'':'s'} in the ${esc(hwindow())} · ${r.toFixed(1)} per 30 days.<br><span class="muted">SFPD/DataSF maps public incident locations to nearby intersections for privacy. This is not an exact event address, a conviction count, or a severity score.</span>`};
$('topoToggle').onchange=e=>{S.stopo=e.target.checked;renderTopo()};$('hToggle').checked=false;$('histToggle').onchange=e=>{S.shi=e.target.checked;renderHistory()};$('histPills').onclick=e=>{const b=e.target.closest('[data-hdays]');if(!b)return;S.hdays=Number(b.dataset.hdays);$('histPills').querySelectorAll('[data-hdays]').forEach(x=>x.classList.toggle('active',x===b));renderHistory()};
const _zoomHist=zoom;zoom=function(f,px=W/2,py=H/2){_zoomHist(f,px,py);if(S.shi)renderHistory()};const _focusSummaryHist=renderFocusSummary;renderFocusSummary=function(){_focusSummaryHist();if(S.shi)renderHistory();else updateHistorySummary()};const _initTopoHist=init;init=function(){_initTopoHist();renderTopo();renderHistory()};
'''
    html = replace_one(html, init_call, js + init_call, "runtime insertion")
    return html


def main():
    html = SITE.read_text(encoding="utf-8")
    m, payload = payload_match(html)
    now_sf = dt.datetime.now(SF_TZ).replace(microsecond=0)
    topo, topo_meta = build_topography()
    hist, hist_meta = build_history(payload, now_sf)
    payload["topography"] = topo
    payload["historical_incidents"] = hist
    payload.setdefault("meta", {})["historical_incident_as_of"] = hist_meta.get("source_rows_updated_at")
    payload["meta"]["historical_incident_window_counts"] = hist_meta["window_unique_incident_counts"]
    packed = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = html[:m.start(1)] + packed + html[m.end(1):]
    html = patch_ui(html)
    SITE.write_text(html, encoding="utf-8")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["topography_display"] = topo_meta
    manifest["historical_incidents"] = hist_meta
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"topography/history added: {topo_meta['display_feature_count']} contour features; {hist_meta['mapped_public_points']} mapped incident points; windows={hist_meta['window_unique_incident_counts']}")


if __name__ == "__main__":
    main()
