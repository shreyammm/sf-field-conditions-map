#!/usr/bin/env python3
"""Add precinct focus/search/summary UX and priority-colored live dispatch markers.

Runs after all existing semantic/freshness passes so this script patches the exact
artifact users receive. It also annotates embedded features with precinct
membership computed from the official precinct polygons.
"""
from __future__ import annotations

import json
import pathlib
import re
from collections import Counter

from shapely.geometry import shape, Point
from shapely.strtree import STRtree

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = ROOT / "_site" / "index.html"
MANIFEST = ROOT / "_site" / "data-manifest.json"

html = SITE.read_text(encoding="utf-8")


def rep(old: str, new: str, label: str, count: int = 1):
    global html
    if old not in html:
        raise SystemExit(f"precinct workspace patch anchor missing: {label}")
    html = html.replace(old, new, count)


def parse_payload(text: str):
    m = re.search(r"window\.SF_FIELD_DATA=(\{.*?\});\s*</script>", text, re.S)
    if not m:
        raise SystemExit("embedded payload not found")
    return m, json.loads(m.group(1))


def precinct_id(props: dict) -> str:
    return str(props.get("prec_2022") or props.get("precinct") or props.get("id") or "").strip()


payload_match, data = parse_payload(html)
precinct_features = (data.get("precincts") or {}).get("features") or []
if not precinct_features:
    raise SystemExit("no precinct features")

prec_geoms = []
prec_ids = []
for f in precinct_features:
    pid = precinct_id(f.get("properties") or {})
    if not pid:
        raise SystemExit("precinct missing id")
    g = shape(f.get("geometry"))
    if g.is_empty or not g.is_valid:
        g = g.buffer(0)
    if g.is_empty:
        raise SystemExit(f"invalid precinct geometry: {pid}")
    prec_geoms.append(g)
    prec_ids.append(pid)
    (f.setdefault("properties", {}))["focus_precinct"] = pid

if len(set(prec_ids)) != len(prec_ids):
    raise SystemExit("duplicate precinct ids")

tree = STRtree(prec_geoms)
valid_ids = set(prec_ids)


def point_precinct(coord) -> str | None:
    try:
        pt = Point(float(coord[0]), float(coord[1]))
    except Exception:
        return None
    hits = []
    for idx in tree.query(pt, predicate="intersects"):
        i = int(idx)
        if prec_geoms[i].covers(pt):
            hits.append(prec_ids[i])
    return sorted(hits)[0] if hits else None


def line_precincts(geom) -> list[str]:
    try:
        g = shape(geom)
    except Exception:
        return []
    if g.is_empty:
        return []
    ids = []
    for idx in tree.query(g, predicate="intersects"):
        i = int(idx)
        inter = g.intersection(prec_geoms[i])
        # Require actual line overlap, not a single boundary/corner touch.
        if not inter.is_empty and float(inter.length) > 1e-10:
            ids.append(prec_ids[i])
    return sorted(set(ids))


def assign_point_collection(name: str):
    missing = 0
    for f in ((data.get(name) or {}).get("features") or []):
        g = f.get("geometry") or {}
        coord = g.get("coordinates") if g.get("type") == "Point" else None
        pid = point_precinct(coord) if coord else None
        p = f.setdefault("properties", {})
        if pid:
            p["focus_precinct"] = pid
        else:
            p.pop("focus_precinct", None)
            missing += 1
    return missing


def assign_line_collection(name: str):
    missing = 0
    for f in ((data.get(name) or {}).get("features") or []):
        ids = line_precincts(f.get("geometry"))
        p = f.setdefault("properties", {})
        p["focus_precincts"] = ids
        if not ids:
            missing += 1
    return missing


# Parcel summary membership deliberately assigns each parcel to exactly one
# precinct via a representative point so group summaries cannot double-count a
# parcel that crosses or touches a precinct boundary.
parcel_missing = 0
for f in ((data.get("multifamily") or {}).get("features") or []):
    try:
        g = shape(f.get("geometry"))
        rp = g.representative_point()
        pid = point_precinct((rp.x, rp.y))
    except Exception:
        pid = None
    p = f.setdefault("properties", {})
    if pid:
        p["focus_precinct"] = pid
    else:
        p.pop("focus_precinct", None)
        parcel_missing += 1

street_missing = assign_line_collection("streets")
closure_missing = assign_line_collection("closures")
permit_missing = assign_point_collection("surface_permits")
live_missing = assign_point_collection("live_calls")

meta = data.setdefault("meta", {})
meta["precinct_workspace"] = {
    "precinct_count": len(prec_ids),
    "selection_semantics": "selected precinct ids are a display/focus filter only; no targeting, turnout, persuasion, or risk score is computed",
    "parcel_assignment": "exactly one precinct from polygon representative point; prevents double counting across selected precinct groups",
    "street_and_closure_assignment": "feature is in focus when its line geometry has non-zero-length intersection with at least one selected precinct polygon",
    "point_assignment": "permit and embedded dispatch points are assigned by the public point coordinate to the covering precinct polygon",
    "runtime_dispatch_assignment": "live API points are assigned client-side by point-in-polygon against the same embedded precinct geometry",
    "unassigned_counts": {
        "parcels": parcel_missing,
        "streets": street_missing,
        "closures": closure_missing,
        "surface_permits": permit_missing,
        "live_calls_fallback": live_missing,
    },
}

# Repack payload before patching UI text/scripts.
packed = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
html = html[: payload_match.start(1)] + packed + html[payload_match.end(1) :]

# ------------------------------ CSS ---------------------------------------
css_anchor = ".ok{color:#067647}.warn{color:#b54708}"
css = r'''.ok{color:#067647}.warn{color:#b54708}
.focusbox{margin:8px 0 4px;padding:10px;border:1px solid #d0d5dd;border-radius:9px;background:#fcfcfd}.focusrow{display:flex;gap:6px}.focusrow input{min-width:0;flex:1;border:1px solid #d0d5dd;border-radius:7px;padding:7px 8px;font:inherit;font-size:12px}.focusrow button,.focusactions button{border:1px solid #d0d5dd;border-radius:7px;background:#fff;padding:7px 9px;font:inherit;font-size:12px;color:#344054;cursor:pointer}.focusrow button:hover,.focusactions button:hover{background:#f9fafb}.focuschips{display:flex;gap:5px;flex-wrap:wrap;margin-top:8px}.focuschip{display:inline-flex;align-items:center;gap:5px;background:#eef4ff;border:1px solid #b2ccff;color:#1849a9;border-radius:99px;padding:4px 7px;font-size:11px;font-weight:650}.focuschip button{border:0;background:transparent;color:#1849a9;padding:0;cursor:pointer;font-weight:800}.focusactions{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}.summarycard{margin-top:8px;border:1px solid #d0d5dd;border-radius:9px;background:#fff;padding:10px}.summaryhead{font-size:13px;font-weight:700;color:#344054;margin-bottom:7px}.summarygrid{display:grid;grid-template-columns:1fr 1fr;gap:7px}.summetric{border:1px solid #eaecf0;border-radius:7px;padding:7px;background:#f9fafb}.summetric b{display:block;font-size:15px;color:#101828}.summetric span{font-size:10.5px;line-height:1.3;color:#667085}.summarynote{margin-top:8px;font-size:10.5px;line-height:1.4;color:#667085}.prec.focus-selected{fill:rgba(23,92,211,.08);stroke:#175cd3;stroke-width:2.2;stroke-dasharray:none}.prec.focus-unselected{opacity:.16}.focus-dim{opacity:.08!important;pointer-events:none!important}.focus-hide{display:none!important}.livepri{vector-effect:non-scaling-stroke;cursor:pointer;pointer-events:all;filter:drop-shadow(0 0 1.2px rgba(255,255,255,.95));fill-opacity:.94}.livepri.priA{fill:#b42318}.livepri.priB{fill:#d97706}.livepri.priC{fill:#15803d}.livepri.priI{fill:#475467}.livepri.priU{fill:#667085}.livepri.live-open{stroke:#fff;stroke-width:2.5}.livepri.live-closed{stroke:#344054;stroke-width:1.25;fill-opacity:.78}.livepri.live-mixed{stroke:#fff;stroke-width:1.7;stroke-dasharray:2 1}.livepri:hover{stroke:#101828;stroke-width:2.8;fill-opacity:1}'''
rep(css_anchor, css, "workspace CSS")

# ------------------------------ controls ----------------------------------
layers_anchor = '<section class="sec"><h2>Layers</h2>'
focus_ui = r'''<section class="sec" id="precinctFocusSection"><h2>Precinct focus</h2>
<div class="focusbox">
  <div class="label" style="font-size:12px">Search or paste precinct IDs</div>
  <div class="focusrow" style="margin-top:6px"><input id="pSearch" type="text" inputmode="text" autocomplete="off" placeholder="e.g. 7101, 7102"><button id="pAdd" type="button">Add</button></div>
  <div id="pSearchMsg" class="muted" style="margin-top:5px">Paste one or several precinct IDs separated by commas or spaces, or click precinct boundaries on the map.</div>
  <div id="pChips" class="focuschips"><span class="muted">No precincts selected · showing all of SF</span></div>
  <div class="focusactions"><button id="pFit" type="button">Focus selected</button><button id="pClearFocus" type="button">Clear</button><button id="pShare" type="button">Copy link</button></div>
</div>
<div class="summarycard" id="focusSummary"><div class="summaryhead">Selected area summary</div><div class="muted">Select one or more precincts to summarize the same public-data layers shown on the map.</div></div>
</section>

''' + layers_anchor
rep(layers_anchor, focus_ui, "precinct focus controls")

# Make the priority encoding visible next to the live controls, not only in the legend.
rep(
    '<button id="iRefresh" type="button" class="refreshbtn">Refresh live data</button>',
    '<button id="iRefresh" type="button" class="refreshbtn">Refresh live data</button><div class="muted" style="margin-top:7px"><strong>Marker color:</strong> A red = highest dispatch urgency · B amber = intermediate · C green = lower/routine. Circle size is fixed; outline indicates open/closed status.</div>',
    "live priority control hint",
)

# ------------------------------ legend ------------------------------------
old_live_legends = re.compile(
    r'<div class="legend"><span class="sw" style="width:11px;height:11px;border-radius:50%;background:#064e3b.*?Larger circle at low zoom = multiple nearby privacy-mapped dispatch points.*?</div>',
    re.S,
)
match = old_live_legends.search(html)
if not match:
    raise SystemExit("precinct workspace patch anchor missing: old live legends")
new_live_legends = r'''<div class="legend"><span class="sw" style="width:11px;height:11px;border-radius:50%;background:#b42318;border:2px solid #fff;box-shadow:0 0 0 1px #b42318"></span><span class="legendtext">Dispatch Priority A · highest official urgency</span><span class="info" title="DEM priority hierarchy: present/imminent danger to life, major property damage, serious-harm suspect may be nearby, major crime scene protection, or at-risk missing person. Generalized examples only.">ⓘ</span></div>
<div class="legend"><span class="sw" style="width:11px;height:11px;border-radius:50%;background:#d97706;border:2px solid #fff;box-shadow:0 0 0 1px #d97706"></span><span class="legendtext">Dispatch Priority B · intermediate official urgency</span><span class="info" title="DEM priority hierarchy: potential property damage, suspect may be nearby, or incident just occurred. Generalized examples only.">ⓘ</span></div>
<div class="legend"><span class="sw" style="width:11px;height:11px;border-radius:50%;background:#15803d;border:2px solid #fff;box-shadow:0 0 0 1px #15803d"></span><span class="legendtext">Dispatch Priority C · lower/routine official urgency</span><span class="info" title="DEM priority hierarchy: no present/potential danger to life or property, suspect no longer nearby, or scene protected. Generalized examples only.">ⓘ</span></div>
<div class="legend"><span class="sw" style="width:11px;height:11px;border-radius:50%;background:#475467;border:2px solid #fff;box-shadow:0 0 0 1px #475467"></span><span class="legendtext">Priority I / unavailable</span></div>
<div class="legend"><span class="sw" style="width:11px;height:11px;border-radius:50%;background:#667085;border:2px solid #fff"></span><span class="legendtext">Circle size is fixed; low-zoom clusters use the highest priority represented</span><span class="info" title="Size does not encode call count or severity. Nearby privacy-mapped points are clustered only for readability. Hover/click shows the represented count and A/B/C breakdown.">ⓘ</span></div>'''
html = html[:match.start()] + new_live_legends + html[match.end():]

# --------------------------- methodology text -----------------------------
old_method_re = re.compile(r'<div class="methoditem"><strong>Recent law-enforcement dispatch activity</strong><br>.*?</div>', re.S)
mm = old_method_re.search(html)
if not mm:
    raise SystemExit("precinct workspace patch anchor missing: live methodology")
new_method = '''<div class="methoditem"><strong>Recent law-enforcement dispatch activity</strong><br>Uses DataSF dataset <span class="code">gnap-fj3t</span> <a class="src-link" href="https://data.sf.gov/d/gnap-fj3t" target="_blank" rel="noopener noreferrer">official source ↗</a>, “Law Enforcement Dispatched Calls for Service: Real-Time.” The map filters by received time to the selected 1–48 hour window and requests the official live feed only while this optional layer is enabled. Public locations are privacy-masked to intersections, and some sensitive calls suppress location. These are dispatch records, not confirmed crimes, so the map does not calculate a crime or neighborhood safety score. Marker <em>color</em> uses DEM’s documented dispatch-priority hierarchy: A is highest urgency, B intermediate, C lower/routine, and I information-only when present. The map uses <span class="code">priority_final</span> when available and falls back to <span class="code">priority_original</span>; dispatchers may update priority as more information becomes available. Circle size is fixed and does not encode severity or count. At low zoom, nearby public points are combined for readability and the cluster color uses the highest priority represented; hover/click provides the full priority breakdown. The previous forest-green open/closed encoding is no longer used; open/closed status is shown by marker outline and in details.</div>'''
html = html[:mm.start()] + new_method + html[mm.end():]

prec_method_anchor = '<div class="methoditem"><strong>Precinct boundaries</strong><br>'
prec_focus_method = '''<div class="methoditem"><strong>Precinct focus and summary</strong><br>Precinct selection is a display and aggregation tool only. It does not score, rank, or recommend precincts. Parcels are assigned to exactly one selected precinct using a representative point inside the parcel so a parcel is not double-counted across a group. Street and closure features are considered in focus when their line geometry has non-zero-length overlap with a selected precinct. Permit and dispatch markers use their public point coordinate; because dispatch coordinates are privacy-masked, a point near a precinct boundary can be assigned differently from the underlying non-public incident location. Summary hill values are counts of source street <em>segments intersecting the selection</em>, not miles of roadway.</div>\n''' + prec_method_anchor
rep(prec_method_anchor, prec_focus_method, "precinct focus methodology")

# ----------------------- JavaScript workspace helpers ----------------------
init_anchor = "function init(){"
workspace_js = r'''
const PFOCUS=new Set();
const PRIORITY_RANK={A:4,B:3,C:2,I:1};
const priorityCode=p=>{const x=String(p?.priority_final||p?.priority_original||'').trim().toUpperCase();return PRIORITY_RANK[x]?x:'U'};
const priorityClassFromCode=x=>x==='A'?'priA':x==='B'?'priB':x==='C'?'priC':x==='I'?'priI':'priU';
function pointInRing(pt,ring){let inside=false;const x=pt[0],y=pt[1];for(let i=0,j=ring.length-1;i<ring.length;j=i++){const xi=Number(ring[i][0]),yi=Number(ring[i][1]),xj=Number(ring[j][0]),yj=Number(ring[j][1]);const hit=((yi>y)!==(yj>y))&&(x<(xj-xi)*(y-yi)/(yj-yi+0.0)+xi);if(hit)inside=!inside}return inside}
function pointInGeom(pt,g){if(!g)return false;const inPoly=poly=>{if(!poly?.length||!pointInRing(pt,poly[0]))return false;for(let i=1;i<poly.length;i++)if(pointInRing(pt,poly[i]))return false;return true};return g.type==='Polygon'?inPoly(g.coordinates):g.type==='MultiPolygon'?(g.coordinates||[]).some(inPoly):false}
function precinctForPoint(coord){if(!coord||coord.length<2)return'';for(const f of S.p?.features||[])if(pointInGeom(coord,f.geometry))return String((f.properties||{}).focus_precinct||pid(f.properties||{}));return''}
function focusIds(f,k){const p=f?.properties||{};if(Array.isArray(p.focus_precincts))return p.focus_precincts.map(String);if(p.focus_precinct)return[String(p.focus_precinct)];if((k==='i'||k==='w')&&f?.geometry?.type==='Point'){const q=precinctForPoint(f.geometry.coordinates);return q?[q]:[]}return[]}
function inFocus(f,k){if(!PFOCUS.size)return true;return focusIds(f,k).some(x=>PFOCUS.has(String(x)))}
function selectedPrecinctFeatures(){return(S.p?.features||[]).filter(f=>PFOCUS.has(String((f.properties||{}).focus_precinct||pid(f.properties||{}))))}
function parsePrecinctInput(v){return[...new Set(String(v||'').split(/[\s,;]+/).map(x=>x.trim()).filter(Boolean))]}
function validPrecinctIds(){return new Set((S.p?.features||[]).map(f=>String((f.properties||{}).focus_precinct||pid(f.properties||{}))))}
function updateFocusUrl(){const u=new URL(location.href);if(PFOCUS.size)u.searchParams.set('precincts',[...PFOCUS].sort().join(','));else u.searchParams.delete('precincts');history.replaceState(null,'',u)}
function addPrecincts(raw){const ids=parsePrecinctInput(raw),valid=validPrecinctIds(),bad=[];ids.forEach(x=>valid.has(x)?PFOCUS.add(x):bad.push(x));$('pSearch').value='';$('pSearchMsg').textContent=bad.length?`Not found: ${bad.join(', ')} · valid selections were added.`:'Paste one or several precinct IDs separated by commas or spaces, or click precinct boundaries on the map.';updateFocusUrl();renderFocusUI();renderFocusAware()}
function togglePrecinct(id){id=String(id||'');if(!id)return;PFOCUS.has(id)?PFOCUS.delete(id):PFOCUS.add(id);updateFocusUrl();renderFocusUI();renderFocusAware()}
function renderFocusUI(){const chips=$('pChips');chips.replaceChildren();if(!PFOCUS.size){chips.innerHTML='<span class="muted">No precincts selected · showing all of SF</span>'}else[...PFOCUS].sort().forEach(id=>{const c=document.createElement('span');c.className='focuschip';c.append(document.createTextNode('Precinct '+id));const b=document.createElement('button');b.type='button';b.setAttribute('aria-label','Remove precinct '+id);b.textContent='×';b.onclick=()=>togglePrecinct(id);c.appendChild(b);chips.appendChild(c)});renderFocusSummary()}
function applyFocusStyles(){document.querySelectorAll('.focus-dim,.focus-hide,.focus-selected,.focus-unselected').forEach(e=>e.classList.remove('focus-dim','focus-hide','focus-selected','focus-unselected'));if(!PFOCUS.size)return;pl.querySelectorAll('[data-k="p"]').forEach(e=>{const id=String((e.f?.properties||{}).focus_precinct||pid(e.f?.properties||{}));e.classList.add(PFOCUS.has(id)?'focus-selected':'focus-unselected')});sl.querySelectorAll('[data-k="s"]').forEach(e=>{if(!inFocus(e.f,'s'))e.classList.add('focus-dim')});[ml,wl,il,cl].forEach(g=>g.querySelectorAll('[data-k]').forEach(e=>{if(!inFocus(e.f,e.dataset.k))e.classList.add('focus-hide')}))}
function fitSelected(){const fs=selectedPrecinctFeatures();if(!fs.length)return;const pts=[];fs.forEach(f=>coords(f.geometry,pts));if(!pts.length)return;const pxy=pts.map(proj),xs=pxy.map(p=>p[0]),ys=pxy.map(p=>p[1]),minx=Math.min(...xs),maxx=Math.max(...xs),miny=Math.min(...ys),maxy=Math.max(...ys),bw=Math.max(1,maxx-minx),bh=Math.max(1,maxy-miny),z=Math.max(1,Math.min(10,Math.min((W-100)/bw,(H-100)/bh)));S.z=z;S.x=W/2-((minx+maxx)/2)*z;S.y=H/2-((miny+maxy)/2)*z;apply();renderLabels();renderI();applyFocusStyles()}
function priorityCounts(fs){const c={A:0,B:0,C:0,I:0,U:0};fs.forEach(f=>c[priorityCode(f.properties||{})]++);return c}
function renderFocusSummary(){const box=$('focusSummary');if(!PFOCUS.size){box.innerHTML='<div class="summaryhead">Selected area summary</div><div class="muted">Select one or more precincts to summarize the same public-data layers shown on the map.</div>';return}const parcels=(S.m?.features||[]).filter(f=>inFocus(f,'m')&&Number(units(f.properties||{}))>=S.n),unitTotal=parcels.reduce((a,f)=>a+Number(units(f.properties||{})||0),0),streets=(S.s?.features||[]).filter(f=>inFocus(f,'s')&&!['1','6'].includes(String(streetClass(f.properties||{})))),classified=streets.filter(f=>Number.isFinite(hillGrade(f.properties||{}))),steep10=classified.filter(f=>hillGrade(f.properties||{})>=10).length,steep15=classified.filter(f=>hillGrade(f.properties||{})>=15).length,unavail=streets.filter(f=>!Number.isFinite(hillGrade(f.properties||{}))).length,q=dateOnly(S.ct),closures=q?(S.c?.features||[]).filter(f=>inFocus(f,'c')&&closureActive(f,q)).length:null,permits=q&&workSupportDate(q)?(S.w?.features||[]).filter(f=>inFocus(f,'w')&&workActive(f,q)).length:null,lf=liveFiltered().filter(f=>inFocus(f,'i')),pc=priorityCounts(lf),open=lf.filter(f=>(f.properties||{}).open===true).length,mins=liveFreshness(),ids=[...PFOCUS].sort();box.innerHTML=`<div class="summaryhead">${ids.length} precinct${ids.length===1?'':'s'} selected · ${ids.map(esc).join(', ')}</div><div class="summarygrid"><div class="summetric"><b>${parcels.length.toLocaleString()}</b><span>${Number(S.n)}+ unit parcels · ${unitTotal.toLocaleString()} source residential units</span></div><div class="summetric"><b>${classified.length.toLocaleString()}</b><span>hill-classified street segments · ${steep10.toLocaleString()} ≥10% · ${steep15.toLocaleString()} ≥15% · ${unavail.toLocaleString()} unavailable</span></div><div class="summetric"><b>${closures===null?'—':closures.toLocaleString()}</b><span>${closures===null?'choose a planning date':'SFMTA permitted closures overlapping '+esc(fmtDateOnly(q))}</span></div><div class="summetric"><b>${permits===null?'—':permits.toLocaleString()}</b><span>${!q?'choose a planning date':!workSupportDate(q)?'date outside permit snapshot support window':'ROW permit windows overlapping '+esc(fmtDateOnly(q))}</span></div><div class="summetric"><b>${lf.length.toLocaleString()}</b><span>mapped dispatches · last ${Number(S.ihours)}h · ${open.toLocaleString()} open</span></div><div class="summetric"><b>${pc.A}/${pc.B}/${pc.C}</b><span>dispatch priority A / B / C${pc.I||pc.U?` · ${pc.I+pc.U} I/unknown`:''}</span></div></div><div class="summarynote">Housing totals use one representative-point precinct assignment per parcel to avoid double counting. Hill figures count source street segments intersecting the selection, not roadway miles. Dispatch locations are privacy-masked public points; priority is operational dispatch urgency, not confirmed crime severity.${Number.isFinite(mins)?` Live feed data ~${Math.round(mins)} min old.`:''}</div>`}
function renderFocusAware(){renderS();renderP();renderM();renderW();renderC();renderI();applyFocusStyles();renderFocusSummary()}
function loadFocusFromUrl(){const ids=parsePrecinctInput(new URL(location.href).searchParams.get('precincts')||''),valid=validPrecinctIds();ids.forEach(x=>{if(valid.has(x))PFOCUS.add(x)});renderFocusUI();if(PFOCUS.size)fitSelected();applyFocusStyles()}

// Override marker aggregation so circle size no longer encodes call count.
function workspaceAccumulator(){return{n:0,open:0,x:0,y:0,types:new Map(),priorities:new Map(),intersections:new Set(),hoods:new Set(),districts:new Set(),calls:[],sourcePoints:0}}
function workspaceAccumulate(a,f,xy){const p=f.properties||{};a.n++;if(p.open===true)a.open++;a.x+=xy[0];a.y+=xy[1];a.sourcePoints++;const t=liveType(p),pr=priorityCode(p);a.types.set(t,(a.types.get(t)||0)+1);a.priorities.set(pr,(a.priorities.get(pr)||0)+1);if(p.intersection)a.intersections.add(String(p.intersection));if(p.analysis_neighborhood)a.hoods.add(String(p.analysis_neighborhood));if(p.police_district)a.districts.add(String(p.police_district));a.calls.push({received_datetime:p.received_datetime||'',type:t,priority:pr,open:p.open===true,intersection:p.intersection||'',agency:p.agency||'',disposition:p.disposition||''})}
function workspaceDisplayFeature(a,mode,coord){const ps=Object.fromEntries([...a.priorities.entries()].sort((x,y)=>(PRIORITY_RANK[y[0]]||0)-(PRIORITY_RANK[x[0]]||0))),highest=[...a.priorities.keys()].sort((x,y)=>(PRIORITY_RANK[y]||0)-(PRIORITY_RANK[x]||0))[0]||'U';return{type:'Feature',geometry:{type:'Point',coordinates:coord},properties:{live_display_mode:mode,count:a.n,open_count:a.open,source_point_groups:a.sourcePoints,type_counts:Object.fromEntries([...a.types.entries()].sort((x,y)=>y[1]-x[1]||x[0].localeCompare(y[0]))),priority_counts:ps,highest_priority:highest,intersections:[...a.intersections].slice(0,10),intersection_count:a.intersections.size,neighborhoods:[...a.hoods].slice(0,8),districts:[...a.districts].slice(0,8),calls:a.calls.sort((x,y)=>String(y.received_datetime).localeCompare(String(x.received_datetime))).slice(0,10),hours:S.ihours,agency_filter:S.iagency,open_only:S.iopen,data_as_of:LIVE.dataAsOf,source:LIVE.source}}}
function workspaceAddLiveMarker(parent,coord,f,r=6.2){if(!coord||coord.length<2)return;const[x,y]=proj(coord),e=document.createElementNS('http://www.w3.org/2000/svg','circle'),p=f.properties||{},priority=String(p.highest_priority||'U'),n=Number(p.count||0),o=Number(p.open_count||0);e.setAttribute('cx',x.toFixed(1));e.setAttribute('cy',y.toFixed(1));e.setAttribute('r',(r/S.z).toFixed(2));e.setAttribute('class','livepri '+priorityClassFromCode(priority)+' '+(o===n?'live-open':o===0?'live-closed':'live-mixed'));e.dataset.k='i';e.f=f;parent.appendChild(e);bind(e)}
renderI=function(){il.replaceChildren();const fs=liveFiltered(),low=S.z<2.4;if(S.si&&fs.length){if(low){const cell=58/S.z,groups=new Map();fs.forEach(f=>{const c=f.geometry?.coordinates;if(!c)return;const xy=proj(c),key=Math.floor(xy[0]/cell)+','+Math.floor(xy[1]/cell);let a=groups.get(key);if(!a){a=workspaceAccumulator();groups.set(key,a)}workspaceAccumulate(a,f,xy)});groups.forEach(a=>{const xy=[a.x/a.n,a.y/a.n],coord=invProj(xy),feature=workspaceDisplayFeature(a,'low_zoom_aggregate',coord);workspaceAddLiveMarker(il,coord,feature,6.5)})}else{const groups=new Map();fs.forEach(f=>{const c=f.geometry?.coordinates;if(!c)return;const key=Number(c[0]).toFixed(5)+','+Number(c[1]).toFixed(5);let a=groups.get(key);if(!a){a=workspaceAccumulator();groups.set(key,a)}workspaceAccumulate(a,f,proj(c))});groups.forEach(a=>{const xy=[a.x/a.n,a.y/a.n],coord=invProj(xy),feature=workspaceDisplayFeature(a,'privacy_mapped_point',coord);workspaceAddLiveMarker(il,coord,feature,5.5)})}}il.style.display=S.si?'':'none';const open=fs.filter(f=>(f.properties||{}).open===true).length,pc=priorityCounts(fs),mins=liveFreshness(),fresh=mins<=45,src=LIVE.source==='live API'?'live API':'fallback snapshot',agency=S.iagency==='ALL'?'all agencies':'Police',extra=S.iopen?' · open only':'';$('is').innerHTML=`<span class="${fresh?'ok':'warn'}">${fs.length.toLocaleString()} mapped dispatch${fs.length===1?'':'es'}</span><span class="muted"> · last ${Number(S.ihours)}h · ${esc(agency)}${extra} · A/B/C ${pc.A}/${pc.B}/${pc.C} · ${open.toLocaleString()} open · ${esc(src)}${Number.isFinite(mins)?` · data ~${Math.round(mins)} min old`:''}${LIVE.error?' · refresh failed':''}</span>`;applyFocusStyles();renderFocusSummary()}
const _hoverBeforeWorkspace=hover;hover=function(e){if(e.dataset.k!=='i')return _hoverBeforeWorkspace(e);const p=e.f.properties||{},n=Number(p.count||0),o=Number(p.open_count||0),ints=Array.isArray(p.intersections)?p.intersections:[],where=p.live_display_mode==='privacy_mapped_point'&&ints.length?ints[0]:'Nearby privacy-mapped dispatch points',pc=p.priority_counts||{},pr=String(p.highest_priority||'U');return`<strong>${n.toLocaleString()} recent dispatch${n===1?'':'es'} · highest priority ${esc(pr)}</strong>${where?esc(where)+'<br>':''}Priority A/B/C: ${Number(pc.A||0)}/${Number(pc.B||0)}/${Number(pc.C||0)} · ${o.toLocaleString()} open<br><span style="opacity:.82">Color uses official dispatch priority, not confirmed crime severity. ${p.live_display_mode==='low_zoom_aggregate'?'Nearby public points are clustered; color is the highest priority represented.':'Public location is privacy-mapped to an intersection.'}</span>`}
const _clickedBeforeWorkspace=clicked;clicked=function(e){if(e.dataset.k!=='i')return _clickedBeforeWorkspace(e);const p=e.f.properties||{},n=Number(p.count||0),o=Number(p.open_count||0),pc=p.priority_counts||{},calls=Array.isArray(p.calls)?p.calls:[],ints=Array.isArray(p.intersections)?p.intersections:[],mode=p.live_display_mode==='low_zoom_aggregate'?`<br><span class="muted">Low-zoom cluster of ${Number(p.source_point_groups||0).toLocaleString()} nearby public mapped point group${Number(p.source_point_groups||0)===1?'':'s'}. Cluster color uses the highest priority represented; circle size is fixed.</span>`:`<br><span class="muted">Public location is privacy-mapped to an intersection; circle size is fixed.</span>`,callHtml=calls.length?`<br><strong>Most recent represented calls</strong><br>${calls.map(c=>'• '+esc(fmtSFLocal(c.received_datetime))+' · Priority '+esc(c.priority||'U')+' · '+esc(c.type)+' · '+(c.open?'<strong>open</strong>':'closed')+(c.disposition&&!c.open?' · '+esc(c.disposition):'')).join('<br>')}`:'';return`<strong>${n.toLocaleString()} recent law-enforcement dispatch${n===1?'':'es'}</strong><br>Highest represented priority: <strong>${esc(p.highest_priority||'U')}</strong><br>Priority A / B / C: ${Number(pc.A||0)} / ${Number(pc.B||0)} / ${Number(pc.C||0)}${Number(pc.I||0)+Number(pc.U||0)?` · I/unknown: ${Number(pc.I||0)+Number(pc.U||0)}`:''}<br>${o.toLocaleString()} still open · received in last ${Number(p.hours)} hours${ints.length?`<br>Privacy-mapped intersection${ints.length===1?'':'s'}: ${ints.map(esc).join('; ')}`:''}${callHtml}${mode}<br><br>${sourceLink(liveSourceUrl(),'Open DataSF real-time dispatch dataset')}<br><span class="muted">Priority is DEM's operational urgency classification and may be updated as information changes. It is not a determination that a crime occurred. A=highest urgency, B=intermediate, C=lower/routine; generalized definitions come from the official Calls for Service documentation.</span>`}
const _bindBeforeWorkspace=bind;bind=function(e){_bindBeforeWorkspace(e);const old=e.onclick;e.onclick=ev=>{if(e.dataset.k==='p'){ev.stopPropagation();togglePrecinct(String((e.f?.properties||{}).focus_precinct||pid(e.f?.properties||{})));detail.innerHTML=clicked(e);return}old?.call(e,ev)}}
'''
rep(init_anchor, workspace_js + "\n" + init_anchor, "workspace JS")

# Wire controls before init call.
init_call_anchor = "init();\n})();"
controls_js = r'''$('pAdd').onclick=()=>addPrecincts($('pSearch').value);$('pSearch').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();addPrecincts(e.target.value)}};$('pClearFocus').onclick=()=>{PFOCUS.clear();updateFocusUrl();renderFocusUI();renderFocusAware()};$('pFit').onclick=()=>fitSelected();$('pShare').onclick=async()=>{updateFocusUrl();try{await navigator.clipboard.writeText(location.href);$('pSearchMsg').textContent='Shareable precinct-selection link copied.'}catch{$('pSearchMsg').textContent='Copy failed; use the current browser URL, which now contains the precinct selection.'}};
const _oldSToggle=$('sToggle').onchange,_oldHToggle=$('hToggle').onchange,_oldCToggle=$('cToggle').onchange,_oldWToggle=$('wToggle').onchange,_oldMToggle=$('mToggle').onchange,_oldPills=$('pills').onclick,_oldCTime=$('cTime').onchange,_oldCNow=$('cNow').onclick,_oldCClear=$('cClear').onclick,_oldIAgency=$('iAgency').onchange,_oldIOpen=$('iOpenOnly').onchange,_oldIPills=$('iPills').onclick;
$('sToggle').onchange=e=>{_oldSToggle?.(e);applyFocusStyles()};$('hToggle').onchange=e=>{_oldHToggle?.(e);applyFocusStyles()};$('cToggle').onchange=e=>{_oldCToggle?.(e);applyFocusStyles()};$('wToggle').onchange=e=>{_oldWToggle?.(e);applyFocusStyles()};$('mToggle').onchange=e=>{_oldMToggle?.(e);renderFocusSummary()};$('pills').onclick=e=>{_oldPills?.(e);applyFocusStyles();renderFocusSummary()};$('cTime').onchange=e=>{_oldCTime?.(e);applyFocusStyles();renderFocusSummary()};$('cNow').onclick=e=>{_oldCNow?.(e);applyFocusStyles();renderFocusSummary()};$('cClear').onclick=e=>{_oldCClear?.(e);applyFocusStyles();renderFocusSummary()};$('iAgency').onchange=e=>{_oldIAgency?.(e);renderFocusSummary()};$('iOpenOnly').onchange=e=>{_oldIOpen?.(e);renderFocusSummary()};$('iPills').onclick=e=>{_oldIPills?.(e);renderFocusSummary()};
init();loadFocusFromUrl();
})();'''
rep(init_call_anchor, controls_js, "workspace control wiring")

# Persist final artifact.
SITE.write_text(html, encoding="utf-8")

manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
manifest["precinct_workspace"] = meta["precinct_workspace"]
manifest["live_calls"]["priority_visualization"] = {
    "field_rule": "priority_final when present, otherwise priority_original",
    "A": "highest official DEM dispatch urgency",
    "B": "intermediate official DEM dispatch urgency",
    "C": "lower/routine official DEM dispatch urgency",
    "I": "information-only if present",
    "size_rule": "fixed marker size; no count/severity scaling",
    "cluster_rule": "low-zoom display clusters use highest represented priority for color and expose full A/B/C counts in hover/click",
    "interpretation": "operational dispatch priority; not confirmed crime severity",
}
MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

print(
    "precinct workspace: "
    f"precincts={len(prec_ids)}; parcel_unassigned={parcel_missing}; "
    f"street_unassigned={street_missing}; closure_unassigned={closure_missing}; "
    f"permit_unassigned={permit_missing}; live_unassigned={live_missing}"
)
print("live marker encoding: fixed size; color=A/B/C official dispatch priority; cluster color=highest represented priority")
