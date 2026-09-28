#!/usr/bin/env python3
"""Final semantic-accuracy pass over the user-visible artifact and manifest.

This runs after all feature/UI patches. It exists to keep wording, visual
semantics, runtime behavior, and the machine-readable manifest aligned with the
actual production computation.
"""
from __future__ import annotations

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = ROOT / "_site" / "index.html"
MANIFEST = ROOT / "_site" / "data-manifest.json"

html = SITE.read_text(encoding="utf-8")


def replace(old: str, new: str, label: str, count: int = 1):
    global html
    if old not in html:
        raise SystemExit(f"final accuracy pass anchor missing: {label}")
    html = html.replace(old, new, count)


# ---------- remove stale / overly broad methodology language ----------
replace(
    "No hill or routing score is calculated yet.",
    "Hill steepness is derived separately on these same segments; no combined routing or field-difficulty score is calculated.",
    "street methodology stale hill statement",
)
replace(
    "The build directly intersects each street centerline with those contours and computes rise/run only between consecutive crossings of different known elevations. Streets without enough direct contour crossings remain unclassified rather than receiving a guessed grade.",
    "The build directly intersects each non-freeway street centerline with those contours. Consecutive same-elevation crossings contribute zero net rise across that supported span; non-zero consecutive crossings must differ by about 5 feet. Non-5-foot jumps and implausible short-span artifacts are rejected rather than forced into a grade. Streets without enough accepted contour evidence remain unclassified.",
    "hill v2 computation wording",
)
replace(
    "Precinct polygons are reference lines only; apartment or future street conditions are not averaged into precinct scores.",
    "Precinct polygons are reference lines only; housing, hill, closure, permit, and dispatch layers are not averaged into precinct scores.",
    "precinct methodology wording",
)
# Avoid attributing our routing policy judgment to Public Works. The source layer
# names are official; exclusion as canvassing geometry is our product rule.
replace(
    "because Public Works describes those as non-real/pseudo/parking centerlines rather than physical streets.",
    "as a map policy because those source-layer categories are paper/pseudo/water/freeway-paper or private-parking context rather than the physical street centerlines this product uses for route context.",
    "street exclusion attribution",
)

# ---------- live dispatch: precise scope, stronger query contract ----------
html = html.replace("Recent public-safety activity", "Recent law-enforcement dispatch activity")
replace("<div class=\"label\" style=\"font-size:12px\">How recent?</div>",
        "<div class=\"label\" style=\"font-size:12px\">Calls received within</div>",
        "live lookback label")
replace(
    "DataSF's real-time dispatch feed is a rolling 48-hour window, normally refreshed every 10 minutes with about a 10-minute additional delay. These are dispatched calls, not confirmed crimes. Some sensitive calls suppress public location fields.",
    "DataSF's real-time feed normally contains calls closed in the last 48 hours plus calls that remain open; it refreshes every 10 minutes with about a 10-minute additional delay. This map filters by received time to the selected 1–48 hour window. These are dispatched calls, not confirmed crimes. Some sensitive calls suppress public location fields.",
    "live control source semantics",
)
replace(
    "The source is designed as a rolling 48-hour operational feed, normally refreshed every 10 minutes with about a 10-minute additional delay. The page loads a build-time fallback snapshot and then requests the current official DataSF feed directly; while the page stays open it requests a refresh every 10 minutes. Users can filter calls received in the last 1, 3, 6, 12, 24, or 48 hours and can limit the display to Police calls or calls that remain open.",
    "The upstream real-time dataset normally contains calls closed in the last 48 hours plus any calls that remain open, so rare older open/reopened rows can exist upstream. The map deliberately filters by received time and offers 1, 3, 6, 12, 24, or 48 hour windows. It embeds a recent fallback snapshot and, only when this optional layer is enabled, requests the current official DataSF feed; while enabled it refreshes at most every 10 minutes. Users can limit the display to Police calls or calls that remain open.",
    "live methodology source semantics",
)

old_fields = "const LIVE_CALLS_FIELDS='id,received_datetime,dispatch_datetime,close_datetime,call_type_original_desc,call_type_final_desc,priority_original,priority_final,agency,disposition,onview_flag,intersection_name,intersection_point,analysis_neighborhood,police_district,call_last_updated_at,data_as_of';"
new_fields = "const LIVE_CALLS_FIELDS='id,cad_number,received_datetime,dispatch_datetime,close_datetime,call_type_original_desc,call_type_final_desc,priority_original,priority_final,agency,disposition,onview_flag,intersection_name,intersection_point,analysis_neighborhood,police_district,call_last_updated_at,data_as_of';"
replace(old_fields, new_fields, "live runtime fields")
old_url = "const LIVE_CALLS_URL='https://data.sf.gov/resource/gnap-fj3t.json?$select='+encodeURIComponent(LIVE_CALLS_FIELDS)+'&$limit=5000&$order='+encodeURIComponent('received_datetime DESC');"
new_url = "const LIVE_CALLS_LIMIT=10000,LIVE_CALLS_QUERY_HOURS=49;const liveCallsUrl=()=>{const cutoff=new Date(sfNowWallMs()-LIVE_CALLS_QUERY_HOURS*3600000).toISOString().slice(0,19)+'.000';return'https://data.sf.gov/resource/gnap-fj3t.json?$select='+encodeURIComponent(LIVE_CALLS_FIELDS)+'&$where='+encodeURIComponent(\"received_datetime >= '\"+cutoff+\"'\")+'&$limit='+LIVE_CALLS_LIMIT+'&$order='+encodeURIComponent('received_datetime DESC')};"
replace(old_url, new_url, "live runtime bounded query")

refresh_pattern = re.compile(r"async function refreshLiveCalls\(\)\{.*?\}\nfunction typeSummary", re.S)
match = refresh_pattern.search(html)
if not match:
    raise SystemExit("final accuracy pass anchor missing: refreshLiveCalls")
new_refresh = r'''async function refreshLiveCalls(){if(LIVE.refreshing)return;LIVE.refreshing=true;LIVE.error='';const b=$('iRefresh');if(b)b.textContent='Refreshing…';try{const r=await fetch(liveCallsUrl(),{cache:'no-store'});if(!r.ok)throw new Error('HTTP '+r.status);const rows=await r.json();if(!Array.isArray(rows))throw new Error('Unexpected API response');if(rows.length>=LIVE_CALLS_LIMIT)throw new Error('Live query reached its safety cap; keeping audited fallback instead of risking truncation');const dataAsOf=rows.map(x=>String(x.data_as_of||'')).filter(Boolean).sort().pop();const dataAge=(sfNowWallMs()-wallMs(dataAsOf))/60000;if(!dataAsOf||!Number.isFinite(dataAge)||dataAge>180||dataAge<-30)throw new Error('Live DataSF feed failed freshness check; keeping audited fallback');const seen=new Set(),unique=[];for(const row of rows){const key=String(row.cad_number||'').trim();if(!key)throw new Error('Live DataSF row missing CAD number');if(seen.has(key))throw new Error('Duplicate CAD number in live DataSF response');seen.add(key);unique.push(row)}const now=sfNowWallMs(),cut=now-LIVE_CALLS_QUERY_HOURS*3600000,fs=unique.map(liveRowFeature).filter(Boolean).filter(f=>{const t=wallMs((f.properties||{}).received_datetime);return Number.isFinite(t)&&t>=cut&&t<=now+15*60000});if(fs.length<50)throw new Error('Too few recent mapped calls returned');LIVE.features=fs;LIVE.source='live API';LIVE.fetchedAt=new Date();LIVE.dataAsOf=dataAsOf;renderI()}catch(err){LIVE.error=String(err?.message||err);renderI()}finally{LIVE.refreshing=false;if(b)b.textContent='Refresh live data'}}
function typeSummary'''
html = html[:match.start()] + new_refresh + html[match.end():]

# Do not make a cross-origin request simply by opening the map. The live layer
# refreshes immediately when the user enables it, then only while enabled.
replace(
    "renderI();refreshLiveCalls();setInterval(refreshLiveCalls,600000);const srcActive=",
    "renderI();setInterval(()=>{if(S.si)refreshLiveCalls()},600000);const srcActive=",
    "live optional runtime refresh",
)

# Apply open/closed/mixed semantics to low-zoom aggregates too. Previously every
# low-zoom aggregate used the open-call color even when all represented calls
# were closed, which could mislead interpretation.
replace(
    "if(cls==='lcp'){const n=Number(p.count||0),o=Number(p.open_count||0);if(o===0)c+=' closed';else if(o<n)c+=' mixed'}",
    "if(cls==='lcp'||cls==='lcg'){const n=Number(p.count||0),o=Number(p.open_count||0);if(o===0)c+=' closed';else if(o<n)c+=' mixed'}",
    "low zoom live status class",
)
replace(
    ".lcg:hover{fill-opacity:.65;stroke:#022c22;stroke-opacity:1;stroke-width:2.5}",
    ".lcg:hover{fill-opacity:.65;stroke:#022c22;stroke-opacity:1;stroke-width:2.5}.lcg.closed{fill:#34d399;fill-opacity:.58;stroke:#065f46;stroke-width:2.1}.lcg.mixed{fill:#059669;fill-opacity:.68;stroke:#064e3b;stroke-width:2.1}",
    "low zoom live status CSS",
)
html = html.replace("This orange circle combines", "This map circle combines")
html = html.replace(
    "Solid orange means at least one call at this mapped point is still open; a hollow orange marker means all represented calls are closed.",
    "Marker color distinguishes whether represented calls are all open, all closed, or a mix of open and closed calls.",
)

# Add an explicit aggregate legend so large low-zoom circles cannot be mistaken
# for exact source points.
legend_anchor = '<div class="legend"><span class="sw" style="width:11px;height:11px;border-radius:50%;background:#34d399;border:2px solid #065f46"></span><span class="legendtext">Recently closed law-enforcement dispatch call</span></div>'
if legend_anchor not in html:
    raise SystemExit("final accuracy pass anchor missing: live closed legend")
html = html.replace(
    legend_anchor,
    legend_anchor + '<div class="legend"><span class="sw" style="width:15px;height:15px;border-radius:50%;background:rgba(6,78,59,.46);border:2px solid #052e16"></span><span class="legendtext">Larger circle at low zoom = multiple nearby privacy-mapped dispatch points</span><span class="info" title="Display aggregation only. Hover/click shows the represented call count and open/closed count; zoom in to separate source point clusters.">ⓘ</span></div>',
    1,
)

# ---------- source freshness visibility for date-planning layers ----------
# Helper works on date-only strings without timezone assumptions.
replace(
    "const dateOnly=v=>String(v||'').slice(0,10);",
    "const dateOnly=v=>String(v||'').slice(0,10);const dayAge=d=>{if(!/^\\d{4}-\\d{2}-\\d{2}$/.test(String(d||'')))return NaN;const now=sfNowLocal().slice(0,10),a=Date.parse(d+'T00:00:00Z'),b=Date.parse(now+'T00:00:00Z');return Number.isFinite(a)&&Number.isFinite(b)?Math.round((b-a)/86400000):NaN};",
    "date freshness helper",
)
old_render_w = re.search(r"function renderW\(\)\{.*?\}\nfunction renderC", html, re.S)
if not old_render_w:
    raise SystemExit("final accuracy pass anchor missing: renderW/renderC")
block = old_render_w.group(0)
block = block.replace(
    "retr=DATA.meta?.surface_permit_retrieved_sf?String(DATA.meta.surface_permit_retrieved_sf).slice(0,10):'unknown';$('ws').innerHTML=",
    "retr=DATA.meta?.surface_permit_retrieved_sf?String(DATA.meta.surface_permit_retrieved_sf).slice(0,10):'unknown',src=DATA.meta?.surface_permit_latest_row_data_as_of?String(DATA.meta.surface_permit_latest_row_data_as_of).slice(0,10):'unknown',srcAge=dayAge(src),srcTxt=src!=='unknown'?` · latest source timestamp ${esc(src)}${Number.isFinite(srcAge)?` (${srcAge}d ago)`:''}`:'';$('ws').innerHTML=",
)
block = block.replace(
    "snapshot supported ${esc(a)}–${esc(b)}</span>`:supported?",
    "snapshot supported ${esc(a)}–${esc(b)}${srcTxt}</span>`:supported?",
)
block = block.replace(
    "snapshot retrieved ${esc(retr)} · supported ${esc(a)}–${esc(b)}</span>`:",
    "snapshot retrieved ${esc(retr)}${srcTxt} · supported ${esc(a)}–${esc(b)}</span>`:",
)
block = block.replace(
    "supported ${esc(a)}–${esc(b)}</span>`}function renderC",
    "supported ${esc(a)}–${esc(b)}${srcTxt}</span>`}function renderC",
)
html = html[:old_render_w.start()] + block + html[old_render_w.end():]

render_c = re.search(r"function renderC\(\)\{.*?\}\nfunction renderP", html, re.S)
if not render_c:
    raise SystemExit("final accuracy pass anchor missing: renderC")
cblock = render_c.group(0)
cblock = cblock.replace(
    "const sourceLabel=DATA.meta?.closure_data_as_of?'source date':'retrieved';$('cs').innerHTML=",
    "const sourceLabel=DATA.meta?.closure_data_as_of?'source data as of':'retrieved',sourceAge=dayAge(sourceDate),stale=Number.isFinite(sourceAge)&&sourceAge>2,ageTxt=Number.isFinite(sourceAge)?` · ${sourceAge}d old`:'';$('cs').innerHTML=",
)
cblock = cblock.replace(
    "${esc(sourceLabel)} ${esc(sourceDate)}</span>`:`<span class=\"${n?'ok':'warn'}\">",
    "${esc(sourceLabel)} ${esc(sourceDate)}${ageTxt}</span>`:`<span class=\"${n?'ok':'warn'}\">",
)
cblock = cblock.replace(
    "${esc(sourceLabel)} ${esc(sourceDate)}</span>`}function renderP",
    "<span class=\"${stale?'warn':'muted'}\"> · ${esc(sourceLabel)} ${esc(sourceDate)}${ageTxt}${stale?' · verify source if planning is time-sensitive':''}</span>`}function renderP",
)
# The previous replacement leaves the original opening muted span in the selected
# branch if its exact form changed. Normalize the selected-date template directly.
cblock = re.sub(
    r"<span class=\"muted\"> · \$\{esc\(fmtDateOnly\(q\)\)\} · \$\{esc\(sourceLabel\)\} \$\{esc\(sourceDate\)\}\$\{ageTxt\}</span>",
    "<span class=\"muted\"> · ${esc(fmtDateOnly(q))}</span><span class=\"${stale?'warn':'muted'}\"> · ${esc(sourceLabel)} ${esc(sourceDate)}${ageTxt}${stale?' · verify source if planning is time-sensitive':''}</span>",
    cblock,
)
html = html[:render_c.start()] + cblock + html[render_c.end():]

# ---------- machine-readable manifest must match final UI semantics ----------
manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
closures = manifest.setdefault("closures", {})
closures["filter_rule"] = (
    "status = Permitted AND official local start/end interval overlaps any "
    "portion of selected San Francisco calendar date"
)
closures["ui_time_semantics"] = (
    "date-only planning filter; exact source hours remain in feature details"
)
live = manifest.setdefault("live_calls", {})
live["runtime_behavior"] = (
    "official DataSF query is requested only when the optional live layer is "
    "enabled; refreshes at most every 10 minutes while enabled; audited embedded "
    "fallback remains if runtime query/freshness/uniqueness checks fail"
)
live["runtime_query_rule"] = (
    "request cad_number and display fields for calls received in preceding 49 "
    "SF-local wall-clock hours; reject response at 10,000-row cap; validate unique "
    "cad_number and <=180-minute data_as_of freshness"
)
manifest["final_accuracy_pass"] = {
    "version": 1,
    "principles": [
        "source geometry is never expanded into guessed footprints",
        "derived hill values are labeled estimates with confidence/support",
        "closure/permit authorizations are not described as pedestrian blockage",
        "live dispatches are not described as confirmed crimes",
        "precincts remain reference geometry and receive no derived targeting/risk score",
    ],
}
MANIFEST.write_text(
    json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
)
SITE.write_text(html, encoding="utf-8")
print("applied final semantic accuracy pass")
