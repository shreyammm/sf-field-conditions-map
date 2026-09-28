#!/usr/bin/env python3
"""Add the final reported-incident UI after the planning-date mutation."""
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "_site" / "index.html"
s = p.read_text(encoding="utf-8")


def rep(old: str, new: str, label: str):
    global s
    if old not in s:
        raise SystemExit(f"incident UI patch anchor missing: {label}")
    s = s.replace(old, new, 1)


# Styling deliberately avoids alarm-red and makes the layer opt-in. At low zoom
# circles are screen-space density aggregates; at higher zoom they represent
# SFPD's privacy-mapped intersection points (possibly multiple reports per point).
rep(
    ".wk:hover{fill:#115e59;stroke:#ecfdf5;stroke-width:2}",
    ".wk:hover{fill:#115e59;stroke:#ecfdf5;stroke-width:2}"
    ".ig{fill:#7c3aed;fill-opacity:.18;stroke:#6d28d9;stroke-opacity:.48;stroke-width:1.2;vector-effect:non-scaling-stroke;cursor:pointer;pointer-events:all}"
    ".ig:hover{fill-opacity:.28;stroke-opacity:.8;stroke-width:1.8}"
    ".ip{fill:#7c3aed;fill-opacity:.72;stroke:#fff;stroke-width:1.2;vector-effect:non-scaling-stroke;cursor:pointer;pointer-events:all}"
    ".ip:hover{fill-opacity:.92;stroke:#ede9fe;stroke-width:2}"
    ".incidentctl{margin:8px 0 12px;padding:9px;border:1px solid #eaecf0;border-radius:8px;background:#fcfcfd}"
    ".incidentctl select{width:100%;margin-top:7px;border:1px solid #d0d5dd;border-radius:7px;padding:7px 8px;font:inherit;font-size:12px;color:#344054;background:#fff}",
    "incident CSS",
)

planning_block = '''<div style="margin:8px 0 12px">
  <div class="label" style="font-size:12px">Plan for a date <span class="muted">(optional)</span></div>
  <div class="dtrow"><input id="cTime" type="date" aria-label="Planning date in San Francisco"><button id="cNow" type="button">Today</button><button id="cClear" type="button">Clear</button></div>
  <div class="muted" style="margin-top:5px">Choose a date to show temporary closures scheduled at any point that day. Closure details still show the official start/end hours. Street-work permits use the same date when that layer is enabled.</div>
</div>'''
incident_controls = planning_block + '''
<div class="row"><div><div class="label">Recent reported safety incidents</div><div class="muted">SFPD reports · privacy-mapped to nearby intersections</div></div><label class="switch"><input id="iToggle" type="checkbox"><span></span></label></div>
<div class="incidentctl">
  <div class="label" style="font-size:12px">Reported incident lookback</div>
  <div class="pills" id="iPills" style="margin-top:7px"><button class="pill active" data-days="30">30 days</button><button class="pill" data-days="90">90 days</button><button class="pill" data-days="180">180 days</button><button class="pill" data-days="365">1 year</button></div>
  <select id="iCategory" aria-label="SFPD incident category"><option value="ALL">All SFPD categories</option></select>
  <div class="muted" style="margin-top:7px">Independent of the planning date above. At city scale the map aggregates nearby reports for readability; zoom in for SFPD's privacy-mapped intersection points. Raw report counts are not normalized for population or activity and are not a neighborhood risk score.</div>
</div>'''
rep(planning_block, incident_controls, "incident layer controls")

work_legend = '<div class="legend"><span class="sw" style="width:10px;height:10px;border-radius:50%;background:#0f766e;border:1px solid #fff;box-shadow:0 0 0 1px #0f766e"></span><span class="legendtext">Public Works street-work / ROW permit whose permit window overlaps selected date</span><span class="info" title="Official permit point. A permit is authorization to occupy/use street or sidewalk space; it is not a confirmed closure or exact work footprint.">ⓘ</span></div>'
incident_legend = work_legend + '\n<div class="legend"><span class="sw" style="width:11px;height:11px;border-radius:50%;background:rgba(124,58,237,.34);border:1px solid #6d28d9"></span><span class="legendtext">Recent SFPD reported incidents</span><span class="info" title="SFPD maps public incident locations to nearby intersections for anonymity. Low-zoom circles aggregate nearby reports for readability. This is reported-incident context, not a risk score.">ⓘ</span></div>'
rep(work_legend, incident_legend, "incident legend")

method_anchor = '<div class="methoditem"><strong>Temporary street closures</strong><br>'
incident_method = (
    '<div class="methoditem"><strong>Recent reported safety incidents</strong><br>'
    'Downloaded daily from SFPD / DataSF dataset <span class="code">wg3w-h783</span>, “Police Department Incident Reports: 2018 to Present.” '
    'The build embeds a rolling buffer of recent records and deduplicates source rows to one displayed report per <span class="code">incident_id</span>; SFPD incident categories from all source rows for that report are preserved rather than forcing one category. '
    'Users can choose 30, 90, 180, or 365 days and optionally filter to one SFPD category. '
    'SFPD states that all public incident locations are mapped to nearby intersections to protect anonymity, so displayed points are approximate rather than exact incident locations. '
    'At lower zoom the browser groups nearby displayed reports into translucent circles for readability; at higher zoom it shows clusters at the source privacy-mapped intersection coordinates. '
    'Counts are raw approved incident-report counts, not population-adjusted rates, predictions, or neighborhood safety/risk scores. Multiple categories can belong to one report, so category-membership totals may exceed the number of reports.'
    '</div>\n' + method_anchor
)
rep(method_anchor, incident_method, "incident methodology")

rep(
    '<div><b>ROW permits</b><span id="ws">Reading embedded permit snapshot…</span></div>',
    '<div><b>ROW permits</b><span id="ws">Reading embedded permit snapshot…</span></div>\n<div><b>Incidents</b><span id="is">Reading embedded SFPD snapshot…</span></div>',
    "incident source status",
)
rep(
    'Hover for a quick explanation. Click a street, closure, street-work permit, precinct, or colored parcel to pin details here.',
    'Hover for a quick explanation. Click a street, closure, street-work permit, reported-incident marker, precinct, or colored parcel to pin details here.',
    "incident selected prompt",
)

rep(
    '<g id="sl"></g><g id="pl"></g><g id="ml"></g><g id="wl"></g><g id="cl"></g><g id="ll"></g>',
    '<g id="sl"></g><g id="pl"></g><g id="ml"></g><g id="wl"></g><g id="il"></g><g id="cl"></g><g id="ll"></g>',
    "incident SVG group",
)
rep(
    "const $=id=>document.getElementById(id),svg=$('map'),view=$('view'),sl=$('sl'),pl=$('pl'),ml=$('ml'),wl=$('wl'),cl=$('cl'),ll=$('ll'),tip=$('tip'),detail=$('detail');",
    "const $=id=>document.getElementById(id),svg=$('map'),view=$('view'),sl=$('sl'),pl=$('pl'),ml=$('ml'),wl=$('wl'),il=$('il'),cl=$('cl'),ll=$('ll'),tip=$('tip'),detail=$('detail');",
    "incident DOM handle",
)
rep(
    "const S={p:DATA?.precincts||null,s:DATA?.streets||null,m:DATA?.multifamily||null,c:DATA?.closures||null,w:DATA?.surface_permits||null,b:null,n:20,ss:true,sh:true,sc:true,swk:false,sp:true,sm:true,ct:null,z:1,x:0,y:0,drag:false,lx:0,ly:0};",
    "const S={p:DATA?.precincts||null,s:DATA?.streets||null,m:DATA?.multifamily||null,c:DATA?.closures||null,w:DATA?.surface_permits||null,i:DATA?.incidents||null,b:null,n:20,ss:true,sh:true,sc:true,swk:false,si:false,idays:30,icat:'ALL',sp:true,sm:true,ct:null,z:1,x:0,y:0,drag:false,lx:0,ly:0};",
    "incident state",
)

helper_anchor = "function addMarker(parent,coord,cls,f,k){"
helpers = r'''const shiftISODate=(d,delta)=>{if(!/^\d{4}-\d{2}-\d{2}$/.test(String(d||'')))return'';const[y,m,da]=d.split('-').map(Number);const x=new Date(Date.UTC(y,m-1,da+delta));return x.toISOString().slice(0,10)};
const incidentEndDate=()=>String(DATA.meta?.incident_max_date||DATA.meta?.incident_window_end||'').slice(0,10);
const incidentStartDate=()=>shiftISODate(incidentEndDate(),-(Number(S.idays||30)-1));
const incidentCats=p=>Array.isArray(p.categories)?p.categories.filter(Boolean):[];
let INCIDENT_CACHE={key:'',features:[]};
function incidentFiltered(){const end=incidentEndDate(),start=incidentStartDate(),key=[start,end,S.icat].join('|');if(INCIDENT_CACHE.key===key)return INCIDENT_CACHE.features;const fs=(S.i?.features||[]).filter(f=>{const p=f.properties||{},d=String(p.incident_datetime||'').slice(0,10),cats=incidentCats(p);return!!(d&&start&&end&&start<=d&&d<=end&&(S.icat==='ALL'||cats.includes(S.icat)))});INCIDENT_CACHE={key,features:fs};return fs}
const incidentSourceUrl=()=>String(DATA.meta?.incident_source_page||'https://data.sf.gov/Public-Safety/Police-Department-Incident-Reports-2018-to-Present/wg3w-h783/about_data');
function incidentAccumulator(){return{n:0,x:0,y:0,cats:new Map(),intersections:new Set(),hoods:new Set(),reports:[]}}
function incidentAccumulate(a,f,xy){const p=f.properties||{};a.n++;a.x+=xy[0];a.y+=xy[1];incidentCats(p).forEach(c=>a.cats.set(c,(a.cats.get(c)||0)+1));if(p.intersection)a.intersections.add(String(p.intersection));if(p.analysis_neighborhood)a.hoods.add(String(p.analysis_neighborhood));a.reports.push({incident_datetime:p.incident_datetime||'',categories:incidentCats(p),intersection:p.intersection||''})}
function incidentFeature(a,mode,coord){const cats=Object.fromEntries([...a.cats.entries()].sort((x,y)=>y[1]-x[1]||x[0].localeCompare(y[0]))),reports=a.reports.sort((x,y)=>String(y.incident_datetime).localeCompare(String(x.incident_datetime))).slice(0,8);return{type:'Feature',geometry:{type:'Point',coordinates:coord},properties:{incident_display_mode:mode,count:a.n,category_counts:cats,intersections:[...a.intersections].slice(0,8),intersection_count:a.intersections.size,neighborhoods:[...a.hoods].slice(0,8),neighborhood_count:a.hoods.size,reports,start_date:incidentStartDate(),end_date:incidentEndDate(),category_filter:S.icat}}}
function addIncidentMarker(parent,coord,cls,f,r){if(!coord||coord.length<2)return;const[x,y]=proj(coord),e=document.createElementNS('http://www.w3.org/2000/svg','circle');e.setAttribute('cx',x.toFixed(1));e.setAttribute('cy',y.toFixed(1));e.setAttribute('r',(r/S.z).toFixed(2));e.setAttribute('class',cls);e.dataset.k='i';e.f=f;parent.appendChild(e);bind(e)}
function incidentCategorySummary(p,max=4){const es=Object.entries(p.category_counts||{}).sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0]));return es.slice(0,max).map(([k,v])=>`${k} (${v})`).join(', ')+(es.length>max?` +${es.length-max} more`:'')}
function initIncidentControls(){const sel=$('iCategory'),cats=Object.keys(DATA.meta?.incident_category_report_memberships||{}).sort((a,b)=>a.localeCompare(b));cats.forEach(c=>{const o=document.createElement('option');o.value=c;o.textContent=c;sel.appendChild(o)})}
'''
rep(helper_anchor, helpers + helper_anchor, "incident helpers")

render_anchor = "function renderW(){"
render_incidents = r'''function renderI(){il.replaceChildren();const fs=incidentFiltered(),end=incidentEndDate(),start=incidentStartDate(),cat=S.icat==='ALL'?'all categories':S.icat,low=S.z<2.4;if(S.si&&fs.length){if(low){const cell=58/S.z,groups=new Map();fs.forEach(f=>{const c=f.geometry?.coordinates;if(!c)return;const xy=proj(c),key=Math.floor(xy[0]/cell)+','+Math.floor(xy[1]/cell);let a=groups.get(key);if(!a){a=incidentAccumulator();groups.set(key,a)}incidentAccumulate(a,f,xy)});groups.forEach(a=>{const xy=[a.x/a.n,a.y/a.n],coord=invProj(xy),feature=incidentFeature(a,'low_zoom_aggregate',coord),r=Math.min(18,4+Math.sqrt(a.n)*1.25);addIncidentMarker(il,coord,'ig',feature,r)})}else{const groups=new Map();fs.forEach(f=>{const c=f.geometry?.coordinates;if(!c)return;const key=Number(c[0]).toFixed(5)+','+Number(c[1]).toFixed(5);let a=groups.get(key);if(!a){a=incidentAccumulator();groups.set(key,a)}incidentAccumulate(a,f,proj(c))});groups.forEach(a=>{const xy=[a.x/a.n,a.y/a.n],coord=invProj(xy),feature=incidentFeature(a,'privacy_mapped_point',coord),r=Math.min(10,3.6+Math.log2(a.n+1)*.85);addIncidentMarker(il,coord,'ip',feature,r)})}}il.style.display=S.si?'':'none';const mode=low?'heat-style map aggregation':'privacy-mapped intersection points';$('is').innerHTML=`<span class="${S.si?'ok':'muted'}">${fs.length.toLocaleString()} reports${S.si?' shown':' in window'}</span><span class="muted"> · ${esc(fmtDateOnly(start))}–${esc(fmtDateOnly(end))} · ${esc(cat)}${S.si?' · '+esc(mode):' · layer off'}</span>`}
'''
rep(render_anchor, render_incidents + render_anchor, "render incidents")

hover_old = "function hover(e){const p=e.f.properties||{};if(e.dataset.k==='w'){"
hover_new = r'''function hover(e){const p=e.f.properties||{};if(e.dataset.k==='i'){const n=Number(p.count||0),cats=incidentCategorySummary(p,3),ints=Array.isArray(p.intersections)?p.intersections:[],where=p.incident_display_mode==='privacy_mapped_point'&&ints.length?ints[0]:(p.incident_display_mode==='low_zoom_aggregate'?'Several nearby privacy-mapped intersections':'Privacy-mapped intersection');return`<strong>${n.toLocaleString()} SFPD reported incident${n===1?'':'s'}</strong>${where?esc(where)+'<br>':''}${esc(fmtDateOnly(p.start_date))} – ${esc(fmtDateOnly(p.end_date))}${cats?'<br>'+esc(cats):''}<br><span style="opacity:.82">SFPD maps public incident locations to nearby intersections. ${p.incident_display_mode==='low_zoom_aggregate'?'This circle combines nearby reports for map readability. Zoom in for source intersection clusters. ':'This point can represent multiple reports at the same privacy-mapped intersection. '}Not a neighborhood risk score.</span>`}if(e.dataset.k==='w'){'''
rep(hover_old, hover_new, "incident hover")

click_old = "function clicked(e){const p=e.f.properties||{};if(e.dataset.k==='w'){"
click_new = r'''function clicked(e){const p=e.f.properties||{};if(e.dataset.k==='i'){const n=Number(p.count||0),cats=Object.entries(p.category_counts||{}).sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0])),ints=Array.isArray(p.intersections)?p.intersections:[],hoods=Array.isArray(p.neighborhoods)?p.neighborhoods:[],reports=Array.isArray(p.reports)?p.reports:[],catHtml=cats.length?`<br><strong>SFPD categories represented</strong><br>${cats.map(([k,v])=>'• '+esc(k)+': '+Number(v).toLocaleString()).join('<br>')}`:'',locHtml=ints.length?`<br><strong>Privacy-mapped intersection${Number(p.intersection_count||ints.length)===1?'':'s'}</strong><br>${ints.map(x=>'• '+esc(x)).join('<br>')}${Number(p.intersection_count||ints.length)>ints.length?`<br>• +${Number(p.intersection_count)-ints.length} more`:''}`:'',hoodHtml=hoods.length?`<br>Neighborhood label${Number(p.neighborhood_count||hoods.length)===1?'':'s'}: ${esc(hoods.join(', '))}${Number(p.neighborhood_count||hoods.length)>hoods.length?' + more':''}`:'',recent=reports.length?`<br><strong>Most recent represented report${reports.length===1?'':'s'}</strong><br>${reports.map(r=>'• '+esc(fmtSFLocal(r.incident_datetime))+(r.categories?.length?' · '+esc(r.categories.join(' / ')):'')).join('<br>')}`:'',mode=p.incident_display_mode==='low_zoom_aggregate'?'<br><span class="muted">This is a browser-side spatial aggregation of nearby privacy-mapped incident points for readability. Zoom in to separate source intersection clusters.</span>':'<br><span class="muted">This marker is at an SFPD privacy-mapped intersection coordinate and may represent multiple reports that share that source point.</span>';return`<strong>${n.toLocaleString()} SFPD reported incident${n===1?'':'s'}</strong><br>Window: ${esc(fmtDateOnly(p.start_date))} – ${esc(fmtDateOnly(p.end_date))}<br>Category filter: ${esc(p.category_filter==='ALL'?'All SFPD categories':p.category_filter)}${locHtml}${hoodHtml}${catHtml}${recent}${mode}<br><br>${sourceLink(incidentSourceUrl(),'Open SFPD/DataSF incident dataset')}<br><span class="muted">SFPD states that public incident locations are mapped to nearby intersections to protect anonymity. Counts here are deduplicated to one displayed report per Incident ID. A report can contain more than one category, so category totals can exceed the report count. Raw counts are not normalized for population/activity and should not be read as a prediction of danger or a neighborhood risk score.</span>`}if(e.dataset.k==='w'){'''
rep(click_old, click_new, "incident click")

rep(
    "function zoom(f,px=W/2,py=H/2){const nz=Math.max(1,Math.min(12,S.z*f)),q=nz/S.z;S.x=px-(px-S.x)*q;S.y=py-(py-S.y)*q;S.z=nz;apply();renderLabels()}",
    "function zoom(f,px=W/2,py=H/2){const nz=Math.max(1,Math.min(12,S.z*f)),q=nz/S.z;S.x=px-(px-S.x)*q;S.y=py-(py-S.y)*q;S.z=nz;apply();renderLabels();renderI()}",
    "incident zoom rerender",
)
rep(
    "$('zin').onclick=()=>zoom(1.25);$('zout').onclick=()=>zoom(.8);$('home').onclick=()=>{S.z=1;S.x=S.y=0;apply();renderLabels()};",
    "$('zin').onclick=()=>zoom(1.25);$('zout').onclick=()=>zoom(.8);$('home').onclick=()=>{S.z=1;S.x=S.y=0;apply();renderLabels();renderI()};",
    "incident home rerender",
)
rep(
    "svg.onclick=ev=>{if(!ev.target.dataset.k)detail.textContent='Hover for a quick explanation. Click a street, closure, street-work permit, precinct, or colored parcel to pin details here.'};",
    "svg.onclick=ev=>{if(!ev.target.dataset.k)detail.textContent='Hover for a quick explanation. Click a street, closure, street-work permit, reported-incident marker, precinct, or colored parcel to pin details here.'};",
    "incident map blank prompt",
)
rep(
    "$('wToggle').onchange=e=>{S.swk=e.target.checked;renderW()};",
    "$('wToggle').onchange=e=>{S.swk=e.target.checked;renderW()};\n$('iToggle').onchange=e=>{S.si=e.target.checked;renderI()};\n$('iCategory').onchange=e=>{S.icat=e.target.value;INCIDENT_CACHE.key='';renderI()};\n$('iPills').onclick=e=>{const b=e.target.closest('[data-days]');if(!b)return;S.idays=Number(b.dataset.days);INCIDENT_CACHE.key='';document.querySelectorAll('#iPills .pill').forEach(x=>x.classList.toggle('active',x===b));renderI()};",
    "incident interactions",
)

# add inverse projection immediately after the existing projection helper
proj_anchor = "function proj(c){const [minx,miny,maxx,maxy]=S.b;const sx=(W-2*PAD)/(maxx-minx),sy=(H-2*PAD)/(maxy-miny),k=Math.min(sx,sy),ox=(W-(maxx-minx)*k)/2,oy=(H-(maxy-miny)*k)/2;return[ox+(c[0]-minx)*k,H-(oy+(c[1]-miny)*k)]}"
inv = proj_anchor + "\nfunction invProj(xy){const [minx,miny,maxx,maxy]=S.b,sx=(W-2*PAD)/(maxx-minx),sy=(H-2*PAD)/(maxy-miny),k=Math.min(sx,sy),ox=(W-(maxx-minx)*k)/2,oy=(H-(maxy-miny)*k)/2;return[minx+(xy[0]-ox)/k,miny+((H-xy[1])-oy)/k]}"
rep(proj_anchor, inv, "inverse projection")

rep(
    "if(!DATA||!S.p?.features?.length||!S.s?.features?.length||!S.m?.features?.length||!S.c?.features?.length||!S.w?.features?.length){",
    "if(!DATA||!S.p?.features?.length||!S.s?.features?.length||!S.m?.features?.length||!S.c?.features?.length||!S.w?.features?.length||!S.i?.features?.length){",
    "incident init validation",
)
rep(
    "S.ct='';$('cTime').value='';renderS();renderP();renderM();renderW();renderC();const srcActive=",
    "S.ct='';$('cTime').value='';initIncidentControls();renderS();renderP();renderM();renderW();renderC();renderI();const srcActive=",
    "incident initial render",
)

p.write_text(s, encoding="utf-8")
print("patched reported-incident UI")
