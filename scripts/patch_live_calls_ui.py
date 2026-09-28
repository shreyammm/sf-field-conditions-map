#!/usr/bin/env python3
"""Add a live, short-window law-enforcement dispatch activity layer."""
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "_site" / "index.html"
s = p.read_text(encoding="utf-8")


def rep(old: str, new: str, label: str):
    global s
    if old not in s:
        raise SystemExit(f"live-call UI patch anchor missing: {label}")
    s = s.replace(old, new, 1)


# Bright orange intentionally separates this layer from the purple/blue housing
# parcels. Open calls are solid; recently closed calls are hollow.
rep(
    ".wk:hover{fill:#115e59;stroke:#ecfdf5;stroke-width:2}",
    ".wk:hover{fill:#115e59;stroke:#ecfdf5;stroke-width:2}"
    ".lcg{fill:#f97316;fill-opacity:.20;stroke:#c2410c;stroke-opacity:.72;stroke-width:1.5;vector-effect:non-scaling-stroke;cursor:pointer;pointer-events:all}"
    ".lcg:hover{fill-opacity:.33;stroke-opacity:1;stroke-width:2.2}"
    ".lcp{fill:#f97316;fill-opacity:.90;stroke:#fff;stroke-width:1.5;vector-effect:non-scaling-stroke;cursor:pointer;pointer-events:all}"
    ".lcp.closed{fill:#fff7ed;fill-opacity:.96;stroke:#ea580c;stroke-width:1.8}"
    ".lcp.mixed{fill:#fdba74;fill-opacity:.94;stroke:#fff;stroke-width:1.5}"
    ".lcp:hover{stroke:#7c2d12;stroke-width:2.2}"
    ".incidentctl{margin:8px 0 12px;padding:9px;border:1px solid #eaecf0;border-radius:8px;background:#fcfcfd}"
    ".incidentctl select{width:100%;margin-top:7px;border:1px solid #d0d5dd;border-radius:7px;padding:7px 8px;font:inherit;font-size:12px;color:#344054;background:#fff}"
    ".livepills{grid-template-columns:repeat(3,1fr)}"
    ".livecheck{display:flex;align-items:center;gap:6px;font-size:12px;color:#475467;margin-top:8px}"
    ".livecheck input{accent-color:#ea580c}"
    ".refreshbtn{margin-top:8px;border:1px solid #d0d5dd;background:#fff;border-radius:7px;padding:6px 8px;font:inherit;font-size:12px;color:#344054;cursor:pointer}"
    ".refreshbtn:hover{background:#f9fafb}",
    "live-call CSS",
)

planning_block = '''<div style="margin:8px 0 12px">
  <div class="label" style="font-size:12px">Plan for a date <span class="muted">(optional)</span></div>
  <div class="dtrow"><input id="cTime" type="date" aria-label="Planning date in San Francisco"><button id="cNow" type="button">Today</button><button id="cClear" type="button">Clear</button></div>
  <div class="muted" style="margin-top:5px">Choose a date to show temporary closures scheduled at any point that day. Closure details still show the official start/end hours. Street-work permits use the same date when that layer is enabled.</div>
</div>'''
live_controls = planning_block + '''
<div class="row"><div><div class="label">Recent public-safety activity</div><div class="muted">Live law-enforcement dispatches · privacy-mapped intersections</div></div><label class="switch"><input id="iToggle" type="checkbox"><span></span></label></div>
<div class="incidentctl">
  <div class="label" style="font-size:12px">How recent?</div>
  <div class="pills livepills" id="iPills" style="margin-top:7px"><button class="pill" data-hours="1">1 hr</button><button class="pill" data-hours="3">3 hr</button><button class="pill active" data-hours="6">6 hr</button><button class="pill" data-hours="12">12 hr</button><button class="pill" data-hours="24">24 hr</button><button class="pill" data-hours="48">48 hr</button></div>
  <select id="iAgency" aria-label="Law enforcement agency"><option value="Police">Police only</option><option value="ALL">All law-enforcement agencies</option></select>
  <label class="livecheck"><input id="iOpenOnly" type="checkbox">Show only calls that are still open</label>
  <button id="iRefresh" type="button" class="refreshbtn">Refresh live data</button>
  <div class="muted" style="margin-top:7px">DataSF's real-time dispatch feed is a rolling 48-hour window, normally refreshed every 10 minutes with about a 10-minute additional delay. These are dispatched calls, not confirmed crimes. Some sensitive calls suppress public location fields.</div>
</div>'''
rep(planning_block, live_controls, "live-call controls")

work_legend = '<div class="legend"><span class="sw" style="width:10px;height:10px;border-radius:50%;background:#0f766e;border:1px solid #fff;box-shadow:0 0 0 1px #0f766e"></span><span class="legendtext">Public Works street-work / ROW permit whose permit window overlaps selected date</span><span class="info" title="Official permit point. A permit is authorization to occupy/use street or sidewalk space; it is not a confirmed closure or exact work footprint.">ⓘ</span></div>'
live_legend = work_legend + '''
<div class="legend"><span class="sw" style="width:11px;height:11px;border-radius:50%;background:#f97316;border:1px solid #fff;box-shadow:0 0 0 1px #ea580c"></span><span class="legendtext">Open law-enforcement dispatch call</span><span class="info" title="Official real-time DataSF dispatch activity. Public locations are privacy-mapped to intersections. A dispatch does not establish that a crime occurred.">ⓘ</span></div>
<div class="legend"><span class="sw" style="width:11px;height:11px;border-radius:50%;background:#fff7ed;border:2px solid #ea580c"></span><span class="legendtext">Recently closed law-enforcement dispatch call</span></div>'''
rep(work_legend, live_legend, "live-call legend")

method_anchor = '<div class="methoditem"><strong>Temporary street closures</strong><br>'
live_method = (
    '<div class="methoditem"><strong>Recent public-safety activity</strong><br>'
    'Uses DataSF dataset <span class="code">gnap-fj3t</span>, “Law Enforcement Dispatched Calls for Service: Real-Time.” '
    'The source is designed as a rolling 48-hour operational feed, normally refreshed every 10 minutes with about a 10-minute additional delay. '
    'The page loads a build-time fallback snapshot and then requests the current official DataSF feed directly; while the page stays open it requests a refresh every 10 minutes. '
    'Users can filter calls received in the last 1, 3, 6, 12, 24, or 48 hours and can limit the display to Police calls or calls that remain open. '
    'Public locations are privacy-masked to intersections, and the source suppresses location fields for certain sensitive call types. '
    'Calls for service are operational dispatch records: callers can be mistaken, not every dispatch is a crime, and not every crime creates a dispatch. '
    'The map therefore does not compute a neighborhood or precinct “safety score.” Solid orange markers are still-open calls; hollow orange markers are closed calls; low-zoom circles combine nearby public mapped points only for readability.'
    '</div>\n' + method_anchor
)
rep(method_anchor, live_method, "live-call methodology")

rep(
    '<div><b>ROW permits</b><span id="ws">Reading embedded permit snapshot…</span></div>',
    '<div><b>ROW permits</b><span id="ws">Reading embedded permit snapshot…</span></div>\n<div><b>Live calls</b><span id="is">Reading embedded real-time snapshot…</span></div>',
    "live-call source status",
)
rep(
    'Click a street, closure, street-work permit, precinct, or colored parcel to pin details here.',
    'Click a street, closure, street-work permit, live dispatch marker, precinct, or colored parcel to pin details here.',
    "live-call selected prompt",
)

rep(
    '<g id="sl"></g><g id="pl"></g><g id="ml"></g><g id="wl"></g><g id="cl"></g><g id="ll"></g>',
    '<g id="sl"></g><g id="pl"></g><g id="ml"></g><g id="wl"></g><g id="il"></g><g id="cl"></g><g id="ll"></g>',
    "live-call SVG group",
)
rep(
    "const $=id=>document.getElementById(id),svg=$('map'),view=$('view'),sl=$('sl'),pl=$('pl'),ml=$('ml'),wl=$('wl'),cl=$('cl'),ll=$('ll'),tip=$('tip'),detail=$('detail');",
    "const $=id=>document.getElementById(id),svg=$('map'),view=$('view'),sl=$('sl'),pl=$('pl'),ml=$('ml'),wl=$('wl'),il=$('il'),cl=$('cl'),ll=$('ll'),tip=$('tip'),detail=$('detail');",
    "live-call DOM handle",
)
rep(
    "const S={p:DATA?.precincts||null,s:DATA?.streets||null,m:DATA?.multifamily||null,c:DATA?.closures||null,w:DATA?.surface_permits||null,b:null,n:20,ss:true,sh:true,sc:true,swk:false,sp:true,sm:true,ct:null,z:1,x:0,y:0,drag:false,lx:0,ly:0};",
    "const S={p:DATA?.precincts||null,s:DATA?.streets||null,m:DATA?.multifamily||null,c:DATA?.closures||null,w:DATA?.surface_permits||null,lc:DATA?.live_calls||null,b:null,n:20,ss:true,sh:true,sc:true,swk:false,si:false,ihours:6,iagency:'Police',iopen:false,sp:true,sm:true,ct:null,z:1,x:0,y:0,drag:false,lx:0,ly:0};",
    "live-call state",
)

proj_anchor = "function proj([lon,lat]){const b=S.b,s=Math.min((W-2*PAD)/(b.c-b.a),(H-2*PAD)/(b.d-b.b)),dw=(b.c-b.a)*s,dh=(b.d-b.b)*s;return[(W-dw)/2+(lon-b.a)*s,(H-dh)/2+(b.d-lat)*s]}"
rep(
    proj_anchor,
    proj_anchor + "\nfunction invProj([x,y]){const b=S.b,s=Math.min((W-2*PAD)/(b.c-b.a),(H-2*PAD)/(b.d-b.b)),dw=(b.c-b.a)*s,dh=(b.d-b.b)*s;return[b.a+(x-(W-dw)/2)/s,b.d-(y-(H-dh)/2)/s]}",
    "live-call inverse projection",
)

helper_anchor = "function addMarker(parent,coord,cls,f,k){"
helpers = r'''const LIVE_CALLS_FIELDS='id,received_datetime,dispatch_datetime,close_datetime,call_type_original_desc,call_type_final_desc,priority_original,priority_final,agency,disposition,onview_flag,intersection_name,intersection_point,analysis_neighborhood,police_district,call_last_updated_at,data_as_of';
const LIVE_CALLS_URL='https://data.sf.gov/resource/gnap-fj3t.json?$select='+encodeURIComponent(LIVE_CALLS_FIELDS)+'&$limit=5000&$order='+encodeURIComponent('received_datetime DESC');
const LIVE={features:S.lc?.features||[],source:'embedded fallback',fetchedAt:null,dataAsOf:String(DATA.meta?.live_calls_data_as_of||''),error:'',refreshing:false};
const wallMs=s=>{const m=String(s||'').match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?/);return m?Date.UTC(+m[1],+m[2]-1,+m[3],+m[4],+m[5],+(m[6]||0)):NaN};
const sfNowWallMs=()=>{const ps=new Intl.DateTimeFormat('en-US',{timeZone:'America/Los_Angeles',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).formatToParts(new Date()),v={};ps.forEach(p=>{if(p.type!=='literal')v[p.type]=p.value});return Date.UTC(+v.year,+v.month-1,+v.day,+v.hour,+v.minute,+v.second)};
const liveSourceUrl=()=>String(DATA.meta?.live_calls_source_page||'https://data.sf.gov/Public-Safety/Law-Enforcement-Dispatched-Calls-for-Service-Real-/gnap-fj3t');
const liveType=p=>String(p.call_type_final||p.call_type_original||'Dispatched call');
function liveRowFeature(r){const c=r?.intersection_point?.coordinates;if(!Array.isArray(c)||c.length<2)return null;const lon=Number(c[0]),lat=Number(c[1]);if(!Number.isFinite(lon)||!Number.isFinite(lat)||lon<-122.60||lon>-122.25||lat<37.65||lat>37.90||!r.received_datetime)return null;const p={id:String(r.id||''),received_datetime:String(r.received_datetime),open:!r.close_datetime};[['dispatch_datetime','dispatch_datetime'],['close_datetime','close_datetime'],['call_type_original_desc','call_type_original'],['call_type_final_desc','call_type_final'],['priority_original','priority_original'],['priority_final','priority_final'],['agency','agency'],['disposition','disposition'],['onview_flag','onview_flag'],['intersection_name','intersection'],['analysis_neighborhood','analysis_neighborhood'],['police_district','police_district'],['call_last_updated_at','call_last_updated_at'],['data_as_of','data_as_of']].forEach(([a,b])=>{if(r[a]!=null&&String(r[a]).trim())p[b]=String(r[a]).trim()});return{type:'Feature',geometry:{type:'Point',coordinates:[lon,lat]},properties:p}}
function liveFiltered(){const now=sfNowWallMs(),cut=now-Number(S.ihours||6)*3600000;return(LIVE.features||[]).filter(f=>{const p=f.properties||{},t=wallMs(p.received_datetime),agency=String(p.agency||'');return Number.isFinite(t)&&t>=cut&&t<=now+15*60000&&(S.iagency==='ALL'||agency===S.iagency)&&(!S.iopen||p.open===true)})}
function liveAccumulator(){return{n:0,open:0,x:0,y:0,types:new Map(),intersections:new Set(),hoods:new Set(),districts:new Set(),calls:[],sourcePoints:0}}
function liveAccumulate(a,f,xy){const p=f.properties||{};a.n++;if(p.open===true)a.open++;a.x+=xy[0];a.y+=xy[1];a.sourcePoints++;const t=liveType(p);a.types.set(t,(a.types.get(t)||0)+1);if(p.intersection)a.intersections.add(String(p.intersection));if(p.analysis_neighborhood)a.hoods.add(String(p.analysis_neighborhood));if(p.police_district)a.districts.add(String(p.police_district));a.calls.push({received_datetime:p.received_datetime||'',type:t,priority:p.priority_final||p.priority_original||'',open:p.open===true,intersection:p.intersection||'',agency:p.agency||'',disposition:p.disposition||''})}
function liveDisplayFeature(a,mode,coord){return{type:'Feature',geometry:{type:'Point',coordinates:coord},properties:{live_display_mode:mode,count:a.n,open_count:a.open,source_point_groups:a.sourcePoints,type_counts:Object.fromEntries([...a.types.entries()].sort((x,y)=>y[1]-x[1]||x[0].localeCompare(y[0]))),intersections:[...a.intersections].slice(0,10),intersection_count:a.intersections.size,neighborhoods:[...a.hoods].slice(0,8),districts:[...a.districts].slice(0,8),calls:a.calls.sort((x,y)=>String(y.received_datetime).localeCompare(String(x.received_datetime))).slice(0,10),hours:S.ihours,agency_filter:S.iagency,open_only:S.iopen,data_as_of:LIVE.dataAsOf,source:LIVE.source}}}
function addLiveMarker(parent,coord,cls,f,r){if(!coord||coord.length<2)return;const[x,y]=proj(coord),e=document.createElementNS('http://www.w3.org/2000/svg','circle'),p=f.properties||{};e.setAttribute('cx',x.toFixed(1));e.setAttribute('cy',y.toFixed(1));e.setAttribute('r',(r/S.z).toFixed(2));let c=cls;if(cls==='lcp'){const n=Number(p.count||0),o=Number(p.open_count||0);if(o===0)c+=' closed';else if(o<n)c+=' mixed'}e.setAttribute('class',c);e.dataset.k='i';e.f=f;parent.appendChild(e);bind(e)}
function liveFreshness(){const now=sfNowWallMs(),d=wallMs(LIVE.dataAsOf);return Number.isFinite(d)?Math.max(0,(now-d)/60000):Infinity}
async function refreshLiveCalls(){if(LIVE.refreshing)return;LIVE.refreshing=true;LIVE.error='';const b=$('iRefresh');if(b)b.textContent='Refreshing…';try{const r=await fetch(LIVE_CALLS_URL,{cache:'no-store'});if(!r.ok)throw new Error('HTTP '+r.status);const rows=await r.json();if(!Array.isArray(rows))throw new Error('Unexpected API response');const fs=rows.map(liveRowFeature).filter(Boolean);if(fs.length<50)throw new Error('Too few mapped calls returned');LIVE.features=fs;LIVE.source='live API';LIVE.fetchedAt=new Date();LIVE.dataAsOf=rows.map(x=>String(x.data_as_of||'')).filter(Boolean).sort().pop()||LIVE.dataAsOf;renderI()}catch(err){LIVE.error=String(err?.message||err);renderI()}finally{LIVE.refreshing=false;if(b)b.textContent='Refresh live data'}}
function typeSummary(p,max=5){const es=Object.entries(p.type_counts||{}).sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0]));return es.slice(0,max).map(([k,v])=>`${k} (${v})`).join(', ')+(es.length>max?` +${es.length-max} more`:'')}
'''
rep(helper_anchor, helpers + helper_anchor, "live-call helpers")

render_anchor = "function renderW(){"
render_live = r'''function renderI(){il.replaceChildren();const fs=liveFiltered(),low=S.z<2.4;if(S.si&&fs.length){if(low){const cell=58/S.z,groups=new Map();fs.forEach(f=>{const c=f.geometry?.coordinates;if(!c)return;const xy=proj(c),key=Math.floor(xy[0]/cell)+','+Math.floor(xy[1]/cell);let a=groups.get(key);if(!a){a=liveAccumulator();groups.set(key,a)}liveAccumulate(a,f,xy)});groups.forEach(a=>{const xy=[a.x/a.n,a.y/a.n],coord=invProj(xy),feature=liveDisplayFeature(a,'low_zoom_aggregate',coord),r=Math.min(19,4+Math.sqrt(a.n)*.85);addLiveMarker(il,coord,'lcg',feature,r)})}else{const groups=new Map();fs.forEach(f=>{const c=f.geometry?.coordinates;if(!c)return;const key=Number(c[0]).toFixed(5)+','+Number(c[1]).toFixed(5);let a=groups.get(key);if(!a){a=liveAccumulator();groups.set(key,a)}liveAccumulate(a,f,proj(c))});groups.forEach(a=>{const xy=[a.x/a.n,a.y/a.n],coord=invProj(xy),feature=liveDisplayFeature(a,'privacy_mapped_point',coord),r=Math.min(11,3.8+Math.log2(a.n+1)*.78);addLiveMarker(il,coord,'lcp',feature,r)})}}il.style.display=S.si?'':'none';const open=fs.filter(f=>(f.properties||{}).open===true).length,mins=liveFreshness(),fresh=mins<=45,src=LIVE.source==='live API'?'live API':'fallback snapshot',agency=S.iagency==='ALL'?'all agencies':'Police',extra=S.iopen?' · open only':'';$('is').innerHTML=`<span class="${fresh?'ok':'warn'}">${fs.length.toLocaleString()} mapped dispatch${fs.length===1?'':'es'}</span><span class="muted"> · last ${Number(S.ihours)}h · ${esc(agency)}${extra} · ${open.toLocaleString()} open · ${esc(src)}${Number.isFinite(mins)?` · data ~${Math.round(mins)} min old`:''}${LIVE.error?' · refresh failed':''}</span>`}
'''
rep(render_anchor, render_live + render_anchor, "render live calls")

rep(
    "function hover(e){const p=e.f.properties||{};if(e.dataset.k==='w'){",
    r'''function hover(e){const p=e.f.properties||{};if(e.dataset.k==='i'){const n=Number(p.count||0),o=Number(p.open_count||0),ints=Array.isArray(p.intersections)?p.intersections:[],where=p.live_display_mode==='privacy_mapped_point'&&ints.length?ints[0]:'Nearby privacy-mapped dispatch points',types=typeSummary(p,3);return`<strong>${n.toLocaleString()} recent dispatch${n===1?'':'es'} · ${o.toLocaleString()} open</strong>${where?esc(where)+'<br>':''}Last ${Number(p.hours)} hours${types?'<br>'+esc(types):''}<br><span style="opacity:.82">${p.live_display_mode==='low_zoom_aggregate'?'Nearby public mapped points combined for readability. Zoom in to separate them.':'Public location is privacy-mapped to an intersection.'} Dispatch activity is not the same as confirmed crime.</span>`}if(e.dataset.k==='w'){''',
    "live-call hover",
)

rep(
    "function clicked(e){const p=e.f.properties||{};if(e.dataset.k==='w'){",
    r'''function clicked(e){const p=e.f.properties||{};if(e.dataset.k==='i'){const n=Number(p.count||0),o=Number(p.open_count||0),ints=Array.isArray(p.intersections)?p.intersections:[],hoods=Array.isArray(p.neighborhoods)?p.neighborhoods:[],districts=Array.isArray(p.districts)?p.districts:[],calls=Array.isArray(p.calls)?p.calls:[],types=Object.entries(p.type_counts||{}).sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0])),locHtml=ints.length?`<br><strong>Privacy-mapped intersection${Number(p.intersection_count||ints.length)===1?'':'s'}</strong><br>${ints.map(x=>'• '+esc(x)).join('<br>')}${Number(p.intersection_count||ints.length)>ints.length?`<br>• +${Number(p.intersection_count)-ints.length} more`:''}`:'',typeHtml=types.length?`<br><strong>Dispatch types</strong><br>${types.slice(0,8).map(([k,v])=>'• '+esc(k)+': '+Number(v).toLocaleString()).join('<br>')}${types.length>8?`<br>• +${types.length-8} more`:''}`:'',callHtml=calls.length?`<br><strong>Most recent represented calls</strong><br>${calls.map(c=>'• '+esc(fmtSFLocal(c.received_datetime))+' · '+esc(c.type)+(c.priority?' · priority '+esc(c.priority):'')+' · '+(c.open?'<strong>open</strong>':'closed')+(c.disposition&&!c.open?' · '+esc(c.disposition):'')).join('<br>')}`:'',placeHtml=(hoods.length||districts.length)?`<br>${hoods.length?'Neighborhood label: '+esc(hoods.join(', '))+'<br>':''}${districts.length?'Police district: '+esc(districts.join(', ')):''}`:'',mode=p.live_display_mode==='low_zoom_aggregate'?`<br><span class="muted">This orange circle combines ${Number(p.source_point_groups||0).toLocaleString()} nearby public mapped point group${Number(p.source_point_groups||0)===1?'':'s'} for readability. Zoom in to separate them.</span>`:`<br><span class="muted">Solid orange means at least one call at this mapped point is still open; a hollow orange marker means all represented calls are closed.</span>`;return`<strong>${n.toLocaleString()} recent law-enforcement dispatch${n===1?'':'es'}</strong><br>${o.toLocaleString()} still open · received in last ${Number(p.hours)} hours<br>Agency filter: ${esc(p.agency_filter==='ALL'?'All law-enforcement agencies':p.agency_filter)}${locHtml}${placeHtml}${typeHtml}${callHtml}${mode}<br><br>${sourceLink(liveSourceUrl(),'Open DataSF real-time dispatch dataset')}<br><span class="muted">This feed is operational dispatch activity, not a crime count. Callers can be mistaken, not every dispatch is criminal, and not every crime creates a dispatch. DataSF privacy-maps public locations to intersections and suppresses location for some sensitive calls. Feed data as of: ${esc(fmtSFLocal(p.data_as_of))}.</span>`}if(e.dataset.k==='w'){''',
    "live-call click",
)

rep(
    "function zoom(f,px=W/2,py=H/2){const nz=Math.max(1,Math.min(12,S.z*f)),q=nz/S.z;S.x=px-(px-S.x)*q;S.y=py-(py-S.y)*q;S.z=nz;apply();renderLabels()}",
    "function zoom(f,px=W/2,py=H/2){const nz=Math.max(1,Math.min(12,S.z*f)),q=nz/S.z;S.x=px-(px-S.x)*q;S.y=py-(py-S.y)*q;S.z=nz;apply();renderLabels();renderI()}",
    "live-call zoom rerender",
)
rep(
    "$('zin').onclick=()=>zoom(1.25);$('zout').onclick=()=>zoom(.8);$('home').onclick=()=>{S.z=1;S.x=S.y=0;apply();renderLabels()};",
    "$('zin').onclick=()=>zoom(1.25);$('zout').onclick=()=>zoom(.8);$('home').onclick=()=>{S.z=1;S.x=S.y=0;apply();renderLabels();renderI()};",
    "live-call home rerender",
)
rep(
    "svg.onclick=ev=>{if(!ev.target.dataset.k)detail.textContent='Hover for a quick explanation. Click a street, closure, street-work permit, precinct, or colored parcel to pin details here.'};",
    "svg.onclick=ev=>{if(!ev.target.dataset.k)detail.textContent='Hover for a quick explanation. Click a street, closure, street-work permit, live dispatch marker, precinct, or colored parcel to pin details here.'};",
    "live-call blank prompt",
)
rep(
    "$('wToggle').onchange=e=>{S.swk=e.target.checked;renderW()};",
    "$('wToggle').onchange=e=>{S.swk=e.target.checked;renderW()};\n$('iToggle').onchange=e=>{S.si=e.target.checked;renderI();if(S.si)refreshLiveCalls()};\n$('iAgency').onchange=e=>{S.iagency=e.target.value;renderI()};\n$('iOpenOnly').onchange=e=>{S.iopen=e.target.checked;renderI()};\n$('iRefresh').onclick=()=>refreshLiveCalls();\n$('iPills').onclick=e=>{const b=e.target.closest('[data-hours]');if(!b)return;S.ihours=Number(b.dataset.hours);document.querySelectorAll('#iPills .pill').forEach(x=>x.classList.toggle('active',x===b));renderI()};",
    "live-call interactions",
)
rep(
    "if(!DATA||!S.p?.features?.length||!S.s?.features?.length||!S.m?.features?.length||!S.c?.features?.length||!S.w?.features?.length){",
    "if(!DATA||!S.p?.features?.length||!S.s?.features?.length||!S.m?.features?.length||!S.c?.features?.length||!S.w?.features?.length||!S.lc?.features?.length){",
    "live-call init validation",
)
rep(
    "S.ct='';$('cTime').value='';renderS();renderP();renderM();renderW();renderC();const srcActive=",
    "S.ct='';$('cTime').value='';renderS();renderP();renderM();renderW();renderC();renderI();refreshLiveCalls();setInterval(refreshLiveCalls,600000);const srcActive=",
    "live-call initial render",
)

p.write_text(s, encoding="utf-8")
print("patched live law-enforcement dispatch UI")
