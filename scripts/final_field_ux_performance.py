#!/usr/bin/env python3
"""Final field-use hardening: focus correctness, mobile UX, and payload/runtime performance."""
from __future__ import annotations
import json, pathlib, re

ROOT=pathlib.Path(__file__).resolve().parents[1]
SITE=ROOT/'_site'/'index.html'
MANIFEST=ROOT/'_site'/'data-manifest.json'
html=SITE.read_text(encoding='utf-8')


def rep(old,new,label,count=1):
    global html
    if old not in html:
        raise SystemExit(f'field UX hardening anchor missing: {label}')
    html=html.replace(old,new,count)

# ---- Mobile field workflow: map stays visible, controls become a lower sheet. ----
mobile_css='''\n/* final field-use hardening */
.st-context{opacity:.16;pointer-events:none!important;cursor:default!important}
.focusbadge{position:absolute;left:14px;top:14px;z-index:5;max-width:min(62vw,420px);padding:7px 10px;border:1px solid #d0d5dd;border-radius:999px;background:rgba(255,255,255,.96);box-shadow:0 1px 3px rgba(16,24,40,.12);font-size:12px;font-weight:700;color:#344054;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.focusbadge[hidden]{display:none}
@media(max-width:860px){
  html,body{height:100%;overflow:hidden}
  .app{display:grid;grid-template-columns:1fr;grid-template-rows:minmax(54dvh,1fr) minmax(0,46dvh);height:100dvh}
  .mapwrap{grid-row:1;min-height:0;height:auto}
  .side{grid-row:2;min-height:0;overflow:auto;padding:12px 14px 24px;border-right:0;border-top:1px solid #e4e7ec;border-bottom:0;overscroll-behavior:contain}
  .side>h1,.side>.muted,.side>.callout{display:none}
  #precinctFocusSection{border-top:0;margin-top:0;padding-top:0}
  .focusrow button,.focusactions button,.pill,.refreshbtn,.dtrow button{min-height:42px}
  .tools button{width:44px;height:44px}
  .switch{width:46px;height:28px}.switch span:before{width:22px;height:22px}.switch input:checked+span:before{transform:translateX(18px)}
  .banner{left:10px;right:10px;bottom:10px;max-width:none;font-size:11px;padding:6px 8px}
  .focusbadge{left:10px;top:10px;max-width:calc(100% - 122px)}
}
'''
rep('</style>',mobile_css+'</style>','mobile CSS')

# Keep methodology available but collapsed by default; the field workflow starts with action controls.
html=html.replace('<details class="method" open>','<details class="method">',1)
rep('id="pSearchMsg" class="muted"','id="pSearchMsg" class="muted" aria-live="polite"','search aria live')
rep('class="summarycard" id="focusSummary"','class="summarycard" id="focusSummary" aria-live="polite"','summary aria live')
rep('<div class="tip" id="tip"></div>','<div class="focusbadge" id="focusBadge" hidden></div>\n<div class="tip" id="tip"></div>','focus badge')

# Stronger small-boundary interpretation: public dispatch points are useful context, not exact precinct statistics.
html=html.replace(
    'Dispatch locations are privacy-masked public points; priority is operational dispatch urgency, not confirmed crime severity.',
    'Dispatch locations are privacy-masked public points. For precinct-size selections, treat their counts as approximate map context rather than exact precinct incident statistics; priority is operational dispatch urgency, not confirmed crime severity.',
    1,
)
html=html.replace(
    'privacy-mapped public point falls within a selected precinct. Because DataSF masks incident locations to intersections, a point near a precinct boundary can be assigned differently from the underlying incident location.',
    'privacy-mapped public point falls within a selected precinct. DataSF specifically cautions that anonymized locations can cross boundaries and should not be treated as precise small-area incident counts, so precinct dispatch totals here are approximate map context only.',
    1,
)
html=html.replace(
    '${Number(S.n)}+ unit parcels · ${unitTotal.toLocaleString()} source residential units',
    '${Number(S.n)}+ unit parcels · ${unitTotal.toLocaleString()} residential units on those displayed parcels',
    1,
)
html=html.replace(
    'mapped dispatches · last ${Number(S.ihours)}h · ${open.toLocaleString()} open',
    'privacy-mapped dispatch points · last ${Number(S.ihours)}h · ${open.toLocaleString()} open',
    1,
)

# Label candidates retain their feature so focus mode can suppress out-of-area street labels.
rep('out.push({info,c,name})','out.push({info,c,name,f})','label feature reference')
rep(
    'priority=LABEL_CANDIDATES.filter(x=>x.c>=2&&x.c<=maxClass).sort((a,b)=>a.c-b.c||b.info.len-a.info.len)',
    "priority=LABEL_CANDIDATES.filter(x=>x.c>=2&&x.c<=maxClass&&(!PFOCUS.size||inFocus(x.f,'s'))).sort((a,b)=>a.c-b.c||b.info.len-a.info.len)",
    'focused street labels',
)

# Replace naive 514-polygon scan with a bounding-box index and boundary-inclusive test.
old_geom=r'''function pointInRing(pt,ring){let inside=false;const x=pt[0],y=pt[1];for(let i=0,j=ring.length-1;i<ring.length;j=i++){const xi=Number(ring[i][0]),yi=Number(ring[i][1]),xj=Number(ring[j][0]),yj=Number(ring[j][1]);const hit=((yi>y)!==(yj>y))&&(x<(xj-xi)*(y-yi)/(yj-yi+0.0)+xi);if(hit)inside=!inside}return inside}
function pointInGeom(pt,g){if(!g)return false;const inPoly=poly=>{if(!poly?.length||!pointInRing(pt,poly[0]))return false;for(let i=1;i<poly.length;i++)if(pointInRing(pt,poly[i]))return false;return true};return g.type==='Polygon'?inPoly(g.coordinates):g.type==='MultiPolygon'?(g.coordinates||[]).some(inPoly):false}
function precinctForPoint(coord){if(!coord||coord.length<2)return'';for(const f of S.p?.features||[])if(pointInGeom(coord,f.geometry))return String((f.properties||{}).focus_precinct||pid(f.properties||{}));return''}'''
new_geom=r'''function geomBBox(g){let minx=Infinity,miny=Infinity,maxx=-Infinity,maxy=-Infinity,pts=[];coords(g,pts);for(const p of pts){const x=Number(p[0]),y=Number(p[1]);if(!Number.isFinite(x)||!Number.isFinite(y))continue;minx=Math.min(minx,x);maxx=Math.max(maxx,x);miny=Math.min(miny,y);maxy=Math.max(maxy,y)}return Number.isFinite(minx)?[minx,miny,maxx,maxy]:null}
const PRECINCT_INDEX=(S.p?.features||[]).map(f=>({id:String((f.properties||{}).focus_precinct||pid(f.properties||{})),g:f.geometry,b:geomBBox(f.geometry)})).filter(x=>x.id&&x.b).sort((a,b)=>a.id.localeCompare(b.id));
function pointOnSegment(pt,a,b,eps=1e-10){const x=Number(pt[0]),y=Number(pt[1]),x1=Number(a[0]),y1=Number(a[1]),x2=Number(b[0]),y2=Number(b[1]),dx=x2-x1,dy=y2-y1,cross=(x-x1)*dy-(y-y1)*dx;if(Math.abs(cross)>eps)return false;const dot=(x-x1)*dx+(y-y1)*dy;if(dot<-eps)return false;const len2=dx*dx+dy*dy;return dot<=len2+eps}
function pointInRing(pt,ring){let inside=false;const x=Number(pt[0]),y=Number(pt[1]);for(let i=0,j=ring.length-1;i<ring.length;j=i++){if(pointOnSegment(pt,ring[j],ring[i]))return true;const xi=Number(ring[i][0]),yi=Number(ring[i][1]),xj=Number(ring[j][0]),yj=Number(ring[j][1]);const hit=((yi>y)!==(yj>y))&&(x<(xj-xi)*(y-yi)/(yj-yi)+xi);if(hit)inside=!inside}return inside}
function pointInGeom(pt,g){if(!g)return false;const inPoly=poly=>{if(!poly?.length||!pointInRing(pt,poly[0]))return false;for(let i=1;i<poly.length;i++){if(pointInRing(pt,poly[i]))return false}return true};return g.type==='Polygon'?inPoly(g.coordinates):g.type==='MultiPolygon'?(g.coordinates||[]).some(inPoly):false}
function precinctForPoint(coord){if(!coord||coord.length<2)return'';const x=Number(coord[0]),y=Number(coord[1]);if(!Number.isFinite(x)||!Number.isFinite(y))return'';for(const q of PRECINCT_INDEX){const b=q.b;if(x<b[0]||x>b[2]||y<b[1]||y>b[3])continue;if(pointInGeom(coord,q.g))return q.id}return''}
const _workspaceLiveRowFeature=liveRowFeature;liveRowFeature=function(r){const f=_workspaceLiveRowFeature(r);if(f){const q=precinctForPoint(f.geometry?.coordinates);if(q)f.properties.focus_precinct=q}return f}'''
rep(old_geom,new_geom,'indexed inclusive precinct lookup')

# Aggregated display features remember the represented precincts; they are never reclassified from a centroid.
rep(
    "function workspaceAccumulator(){return{n:0,open:0,x:0,y:0,types:new Map(),priorities:new Map(),intersections:new Set(),hoods:new Set(),districts:new Set(),calls:[],sourcePoints:0}}",
    "function workspaceAccumulator(){return{n:0,open:0,x:0,y:0,types:new Map(),priorities:new Map(),precincts:new Set(),intersections:new Set(),hoods:new Set(),districts:new Set(),calls:[],sourcePoints:0}}",
    'workspace accumulator precincts',
)
rep(
    "a.priorities.set(pr,(a.priorities.get(pr)||0)+1);if(p.intersection)",
    "a.priorities.set(pr,(a.priorities.get(pr)||0)+1);if(p.focus_precinct)a.precincts.add(String(p.focus_precinct));if(p.intersection)",
    'workspace accumulate precinct',
)
rep(
    "properties:{live_display_mode:mode,count:a.n,open_count:a.open,source_point_groups:a.sourcePoints,type_counts:Object.fromEntries([...a.types.entries()].sort((x,y)=>y[1]-x[1]||x[0].localeCompare(y[0]))),priority_counts:ps,highest_priority:highest,",
    "properties:{live_display_mode:mode,count:a.n,open_count:a.open,source_point_groups:a.sourcePoints,focus_precincts:[...a.precincts],type_counts:Object.fromEntries([...a.types.entries()].sort((x,y)=>y[1]-x[1]||x[0].localeCompare(y[0]))),priority_counts:ps,highest_priority:highest,",
    'display feature precinct membership',
)

# The critical correctness fix: select precincts BEFORE clustering. In focus mode, do not
# spatially aggregate across public points at all; the selected area is already small.
rep(
    "renderI=function(){il.replaceChildren();const fs=liveFiltered(),low=S.z<2.4;if(S.si&&fs.length){",
    "renderI=function(){il.replaceChildren();const raw=liveFiltered(),fs=PFOCUS.size?raw.filter(f=>inFocus(f,'i')):raw,low=S.z<2.4&&!PFOCUS.size;if(S.si&&fs.length){",
    'focus-before-live-clustering',
)
# There are two renderers at this point (the legacy base renderer and the final
# workspace priority override). Both reference the status suffix, so both must
# receive a declaration; otherwise the final renderer can throw at runtime even
# though static JavaScript syntax checks pass.
rep(
    "extra=S.iopen?' · open only':'';$('is').innerHTML=",
    "extra=S.iopen?' · open only':'',focusTxt=PFOCUS.size?' · selected precincts':'';$('is').innerHTML=",
    'live selected status',
    count=2,
)
rep(
    "${esc(agency)}${extra} · A/B/C",
    "${esc(agency)}${extra}${focusTxt} · A/B/C",
    'live selected status text',
)

# Focus rendering: selected streets remain interactive; the rest of SF is collapsed
# into a few neutral, non-interactive context paths. Parcels outside focus are not built.
focus_perf=r'''
const _renderSFull=renderS,_renderMFull=renderM;
renderS=function(){if(!PFOCUS.size){_renderSFull();return}sl.replaceChildren();const rank={0:0,5:1,4:2,3:3,2:4,6:5,1:6},ctx=new Map(),selected=[];for(const f of S.s?.features||[]){const p=f.properties||{},d=linePath(f.geometry);if(!d)continue;const c=streetClass(p);if(inFocus(f,'s'))selected.push({f,p,d,c});else{const a=ctx.get(c)||[];a.push(d);ctx.set(c,a)}}for(const [c,parts] of [...ctx.entries()].sort((a,b)=>(rank[a[0]]??0)-(rank[b[0]]??0))){const e=document.createElementNS('http://www.w3.org/2000/svg','path');e.setAttribute('d',parts.join(' '));e.setAttribute('class','st st-context sc'+c);e.setAttribute('aria-hidden','true');sl.appendChild(e)}selected.sort((a,b)=>(rank[a.c]??0)-(rank[b.c]??0)).forEach(x=>{const hc=S.sh&&x.c!==1&&x.c!==6?' '+hillClass(x.p):'';add(sl,x.d,'st sc'+x.c+hc,x.f,'s')});sl.style.display=(S.ss||S.sh)?'':'none';LABEL_CANDIDATES=null;renderLabels()};
renderM=function(){if(!PFOCUS.size){_renderMFull();return}ml.replaceChildren();let n=0;for(const f of S.m?.features||[]){if(!inFocus(f,'m'))continue;const u=units(f.properties||{});if(!Number.isFinite(u)||u<S.n)continue;const d=polyPath(f.geometry);if(d){add(ml,d,'mf '+bucket(u),f,'m');n++}}ml.style.display=S.sm?'':'none';$('ts').textContent=S.n+'+ units · '+n+' parcels in focus'};
'''
rep('function selectedPrecinctFeatures(){',focus_perf+'function selectedPrecinctFeatures(){','focus rendering optimizations')

# Robust fit: avoid spreading potentially huge coordinate arrays into Math.min/Math.max.
old_fit="function fitSelected(){const fs=selectedPrecinctFeatures();if(!fs.length)return;const pts=[];fs.forEach(f=>coords(f.geometry,pts));if(!pts.length)return;const pxy=pts.map(proj),xs=pxy.map(p=>p[0]),ys=pxy.map(p=>p[1]),minx=Math.min(...xs),maxx=Math.max(...xs),miny=Math.min(...ys),maxy=Math.max(...ys),bw=Math.max(1,maxx-minx),bh=Math.max(1,maxy-miny),z=Math.max(1,Math.min(10,Math.min((W-100)/bw,(H-100)/bh)));S.z=z;S.x=W/2-((minx+maxx)/2)*z;S.y=H/2-((miny+maxy)/2)*z;apply();renderLabels();renderI();applyFocusStyles()}"
new_fit="function fitSelected(){const fs=selectedPrecinctFeatures();if(!fs.length)return;let minx=Infinity,maxx=-Infinity,miny=Infinity,maxy=-Infinity;for(const f of fs){const pts=[];coords(f.geometry,pts);for(const p of pts){const q=proj(p);minx=Math.min(minx,q[0]);maxx=Math.max(maxx,q[0]);miny=Math.min(miny,q[1]);maxy=Math.max(maxy,q[1])}}if(!Number.isFinite(minx))return;const bw=Math.max(1,maxx-minx),bh=Math.max(1,maxy-miny),z=Math.max(1,Math.min(10,Math.min((W-100)/bw,(H-100)/bh)));S.z=z;S.x=W/2-((minx+maxx)/2)*z;S.y=H/2-((miny+maxy)/2)*z;apply();renderLabels();renderI();applyFocusStyles()}"
rep(old_fit,new_fit,'robust selected fit')

# Search/paste should immediately zoom to the chosen working area.
old_add="function addPrecincts(raw){const ids=parsePrecinctInput(raw),valid=validPrecinctIds(),bad=[];ids.forEach(x=>valid.has(x)?PFOCUS.add(x):bad.push(x));$('pSearch').value='';$('pSearchMsg').textContent=bad.length?`Not found: ${bad.join(', ')} · valid selections were added.`:'Paste one or several precinct IDs separated by commas or spaces, or click precinct boundaries on the map.';updateFocusUrl();renderFocusUI();renderFocusAware()}"
new_add="function addPrecincts(raw){const ids=parsePrecinctInput(raw),valid=validPrecinctIds(),bad=[];ids.forEach(x=>valid.has(x)?PFOCUS.add(x):bad.push(x));$('pSearch').value='';$('pSearchMsg').textContent=bad.length?`Not found: ${bad.join(', ')} · valid selections were added.`:'Paste one or several precinct IDs separated by commas or spaces, or click precinct boundaries on the map.';updateFocusUrl();renderFocusUI();renderFocusAware();if(ids.some(x=>valid.has(x)))fitSelected()}"
rep(old_add,new_add,'auto fit search selection')
rep(
    "function loadFocusFromUrl(){const ids=parsePrecinctInput(new URL(location.href).searchParams.get('precincts')||''),valid=validPrecinctIds();ids.forEach(x=>{if(valid.has(x))PFOCUS.add(x)});renderFocusUI();if(PFOCUS.size)fitSelected();applyFocusStyles()}",
    "function loadFocusFromUrl(){const ids=parsePrecinctInput(new URL(location.href).searchParams.get('precincts')||''),valid=validPrecinctIds();ids.forEach(x=>{if(valid.has(x))PFOCUS.add(x)});renderFocusUI();if(PFOCUS.size){renderFocusAware();fitSelected()}else applyFocusStyles()}",
    'shared-link optimized focus load',
)

# Field-use badge and home behavior are applied after all original handlers exist, before init.
hardening_runtime=r'''
const _renderFocusUIField=renderFocusUI;renderFocusUI=function(){_renderFocusUIField();const b=$('focusBadge');if(!b)return;if(PFOCUS.size){const ids=[...PFOCUS].sort();b.hidden=false;b.textContent=`${ids.length} precinct${ids.length===1?'':'s'} · ${ids.join(', ')}`}else{b.hidden=true;b.textContent=''}};
$('home').onclick=()=>{if(PFOCUS.size){fitSelected();return}S.z=1;S.x=S.y=0;apply();renderLabels();renderI()};
'''
rep('init();loadFocusFromUrl();',hardening_runtime+'init();loadFocusFromUrl();','field runtime wrappers')

# ---- Prune redundant display payload properties after every computation/audit annotation is complete. ----
payload_match=re.search(r"window\.SF_FIELD_DATA=(\{.*?\});\s*</script>",html,re.S)
if not payload_match:
    raise SystemExit('embedded payload missing during final field hardening')
payload=json.loads(payload_match.group(1))
before=len(payload_match.group(1).encode('utf-8'))
allow={
    'streets':{'cnn','street','streetname','st_type','f_st','t_st','classcode','layer','jurisdiction','active','estimated_grade_pct','grade_confidence','grade_method','grade_crossing_intervals','grade_supported_span_m','grade_support_fraction','focus_precincts'},
    'multifamily':{'geography_type','resunits','resunits_s','mapblklot','ludb_id','data_as_of','address','street','streetname','restype','landuse','focus_precinct','source_unit_count_min','source_unit_count_max','source_unit_count_conflict'},
    'closures':{'status','start_local','end_local','objectid','type','case_name','case_num','loc_desc','street','from_st','to_st','direction','veh_imp','info','focus_precincts','related_work_permit_count','related_work_permits'},
    'surface_permits':{'permit_number','permit_type','permit_type_label','start_local','end_local','source_row_count','source_locations','source_statuses','source_descriptions','source_neighborhoods','focus_precinct'},
    'live_calls':{'id','received_datetime','open','close_datetime','call_type_original','call_type_final','priority_original','priority_final','agency','disposition','intersection','analysis_neighborhood','police_district','data_as_of','focus_precinct'},
}
removed={}
for layer,fields in allow.items():
    fs=((payload.get(layer) or {}).get('features') or [])
    n=0
    for f in fs:
        p=f.get('properties') or {}
        # resunits_s is only useful as a fallback if primary resunits is missing.
        keep_fields=set(fields)
        if layer=='multifamily' and p.get('resunits') not in (None,''):
            keep_fields.discard('resunits_s')
        n += sum(1 for k in p if k not in keep_fields)
        f['properties']={k:v for k,v in p.items() if k in keep_fields}
    removed[layer]=n
packed=json.dumps(payload,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')
after=len(packed.encode('utf-8'))
html=html[:payload_match.start(1)]+packed+html[payload_match.end(1):]

manifest=json.loads(MANIFEST.read_text(encoding='utf-8'))
manifest['field_ux_hardening']={
    'version':1,
    'focus_correctness':'dispatch calls are filtered to selected precincts before any display clustering; focused mode shows privacy-mapped point groups without low-zoom spatial clustering',
    'runtime_precinct_lookup':'client bounding-box index plus boundary-inclusive point-in-polygon; runtime live points cache focus_precinct',
    'focused_rendering':'non-selected street context collapses to class-level SVG paths; out-of-focus parcels are not instantiated',
    'mobile_layout':'map-first split view using dynamic viewport units with larger touch targets',
    'payload_bytes_before':before,
    'payload_bytes_after':after,
    'payload_reduction_pct':round(100*(before-after)/before,1),
    'removed_redundant_property_count':removed,
    'dispatch_small_area_note':'privacy-mapped dispatch points in precinct selections are approximate map context, not exact precinct incident statistics',
}
MANIFEST.write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
SITE.write_text(html,encoding='utf-8')
print(f'field UX hardening applied: payload {before:,} -> {after:,} bytes ({100*(before-after)/before:.1f}% smaller)')
print('removed redundant properties:',removed)
