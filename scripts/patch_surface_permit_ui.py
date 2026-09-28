#!/usr/bin/env python3
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "_site" / "index.html"
s = p.read_text(encoding="utf-8")

def repl(old, new, label):
    global s
    if old not in s:
        raise SystemExit(f"surface-permit UI patch anchor missing: {label}")
    s = s.replace(old, new, 1)

# Styling: point markers deliberately stay points rather than guessed work extents.
repl(
    ".cl:hover{stroke:#1d4ed8;stroke-width:4.5}",
    ".cl:hover{stroke:#1d4ed8;stroke-width:4.5}"
    ".wk{fill:#0f766e;stroke:#fff;stroke-width:1.3;vector-effect:non-scaling-stroke;cursor:pointer;pointer-events:all;opacity:.9}"
    ".wk:hover{fill:#115e59;stroke:#ecfdf5;stroke-width:2}",
    "work permit CSS",
)

closure_row = '<div class="row"><div><div class="label">Temporary street closures</div><div class="muted">SFMTA-permitted · filtered by SF date/time</div></div><label class="switch"><input id="cToggle" type="checkbox" checked><span></span></label></div>'
work_row = closure_row + '\n<div class="row"><div><div class="label">Street work / ROW permits</div><div class="muted">SF Public Works · current/upcoming surface work</div></div><label class="switch"><input id="wToggle" type="checkbox" checked><span></span></label></div>'
repl(closure_row, work_row, "work layer toggle")

repl(
    '<div class="label" style="font-size:12px">Closure time (San Francisco)</div>',
    '<div class="label" style="font-size:12px">Field date/time (San Francisco)</div>',
    "shared time label",
)
repl(
    '<div class="muted" style="margin-top:5px">Shows closure lines whose official SFMTA start/end window contains the selected SF local time.</div>',
    '<div class="muted" style="margin-top:5px">Closures use exact start/end time. Public Works permit markers use the selected calendar date because permit windows are often day-level. Permit coverage is only treated as complete within the current/upcoming snapshot window shown below.</div>',
    "shared time explanation",
)

closure_legend = '<div class="legend"><span class="ln" style="border-top:3px solid #2563eb"></span><span class="legendtext">SFMTA-permitted temporary closure active at selected time</span><span class="info" title="Vehicle/street disruption line from the official SFMTA closure feed. It does not necessarily mean pedestrian access is blocked.">ⓘ</span></div>'
work_legend = closure_legend + '\n<div class="legend"><span class="sw" style="width:10px;height:10px;border-radius:50%;background:#0f766e;border:1px solid #fff;box-shadow:0 0 0 1px #0f766e"></span><span class="legendtext">Public Works street-work / ROW permit active on selected date</span><span class="info" title="Official permit point. A permit is authorization to occupy/use street or sidewalk space; it is not a confirmed closure or exact work footprint.">ⓘ</span></div>'
repl(closure_legend, work_legend, "work legend")

closure_method_start = '<div class="methoditem"><strong>Temporary street closures</strong><br>'
work_method = (
    '<div class="methoditem"><strong>Street work / right-of-way permits</strong><br>'
    'Downloaded at build time from SF Public Works / DataSF dataset <span class="code">bpc9-7sus</span>, “Active and upcoming street surface permits.” '
    'That source combines several surface-use permit categories, including vending/amenity uses. For this route layer we keep only <span class="code">Excavation</span>, <span class="code">TempOccup</span>, <span class="code">StrtImprov</span>, <span class="code">ExcStreet</span>, <span class="code">AddlStSpac</span>, <span class="code">StorCont</span>, <span class="code">MinorEnc</span>, and <span class="code">StreetSpace</span>. '
    'Vending, food-facility, parklet, blank-type, and NightNoise rows are excluded because they are not a clean physical-work/occupancy signal. '
    'Markers use the official permit <em>point</em> location and are filtered by the selected calendar date, inclusive of the permit start/end dates. The point is not an exact work footprint, and a permit does not establish a street closure or pedestrian blockage. '
    'Because the source contains currently active permits plus permits starting within roughly the next 14 days, the map suppresses this layer outside the documented snapshot support window rather than implying historical or far-future completeness.'
    '</div>\n' + closure_method_start
)
repl(closure_method_start, work_method, "work methodology")

repl(
    '<div><b>Closures</b><span id="cs">Reading embedded closure snapshot…</span></div>',
    '<div><b>Closures</b><span id="cs">Reading embedded closure snapshot…</span></div>\n<div><b>Street work</b><span id="ws">Reading embedded permit snapshot…</span></div>',
    "work source status",
)

repl(
    'Click a street, closure, precinct, or colored parcel to pin details here.',
    'Click a street, closure, street-work permit, precinct, or colored parcel to pin details here.',
    "selected prompt",
)
repl(
    "detail.textContent='Hover for a quick explanation. Click a street, closure, precinct, or colored parcel to pin details here.'};",
    "detail.textContent='Hover for a quick explanation. Click a street, closure, street-work permit, precinct, or colored parcel to pin details here.'};",
    "blank prompt",
)

repl(
    '<g id="sl"></g><g id="pl"></g><g id="ml"></g><g id="cl"></g><g id="ll"></g>',
    '<g id="sl"></g><g id="pl"></g><g id="ml"></g><g id="wl"></g><g id="cl"></g><g id="ll"></g>',
    "work svg group",
)
repl(
    "const $=id=>document.getElementById(id),svg=$('map'),view=$('view'),sl=$('sl'),pl=$('pl'),ml=$('ml'),cl=$('cl'),ll=$('ll'),tip=$('tip'),detail=$('detail');",
    "const $=id=>document.getElementById(id),svg=$('map'),view=$('view'),sl=$('sl'),pl=$('pl'),ml=$('ml'),wl=$('wl'),cl=$('cl'),ll=$('ll'),tip=$('tip'),detail=$('detail');",
    "work dom handle",
)
repl(
    "const S={p:DATA?.precincts||null,s:DATA?.streets||null,m:DATA?.multifamily||null,c:DATA?.closures||null,b:null,n:20,ss:true,sh:true,sc:true,sp:true,sm:true,ct:null,z:1,x:0,y:0,drag:false,lx:0,ly:0};",
    "const S={p:DATA?.precincts||null,s:DATA?.streets||null,m:DATA?.multifamily||null,c:DATA?.closures||null,w:DATA?.surface_permits||null,b:null,n:20,ss:true,sh:true,sc:true,swk:true,sp:true,sm:true,ct:null,z:1,x:0,y:0,drag:false,lx:0,ly:0};",
    "work state",
)

# Permit helpers are inserted immediately before the generic SVG path helper.
helper_anchor = "function add(parent,d,cls,f,k){"
helpers = '''const dateOnly=v=>String(v||'').slice(0,10);
const fmtDateOnly=v=>{const d=dateOnly(v);if(!/^\\d{4}-\\d{2}-\\d{2}$/.test(d))return'—';const m=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],[y,mo,da]=d.split('-').map(Number);return`${m[mo-1]} ${da}, ${y}`};
const workSupportDate=t=>{const d=dateOnly(t),a=String(DATA.meta?.surface_permit_supported_from||''),b=String(DATA.meta?.surface_permit_supported_through||'');return!!(d&&a&&b&&a<=d&&d<=b)};
const workActive=(f,t)=>{if(!workSupportDate(t))return false;const p=f.properties||{},q=dateOnly(t),a=dateOnly(p.start_local||p.permit_start_date),b=dateOnly(p.end_local||p.permit_end_date);return!!(a&&b&&a<=q&&q<=b)};
const workWhere=p=>[String(p.street_name||'').trim(),String(p.cross_street||'').trim()?`near ${String(p.cross_street).trim()}`:''].filter(Boolean).join(' ');
const workWindow=p=>`${fmtDateOnly(p.start_local||p.permit_start_date)} – ${fmtDateOnly(p.end_local||p.permit_end_date)}`;
const workLabel=p=>String(p.permit_type_label||p.permit_type||'Street work / ROW permit');
function addMarker(parent,coord,cls,f,k){if(!coord||coord.length<2)return;const[x,y]=proj(coord),e=document.createElementNS('http://www.w3.org/2000/svg','circle');e.setAttribute('cx',x.toFixed(1));e.setAttribute('cy',y.toFixed(1));e.setAttribute('r',(3.5/S.z).toFixed(2));e.setAttribute('class',cls);e.dataset.k=k;e.f=f;parent.appendChild(e);bind(e)}
'''
repl(helper_anchor, helpers + helper_anchor, "work helpers")

render_anchor = "function renderC(){"
render_work = '''function renderW(){wl.replaceChildren();const supported=workSupportDate(S.ct);let n=0;if(supported)(S.w?.features||[]).forEach(f=>{if(!workActive(f,S.ct))return;const g=f.geometry||{};if(g.type==='Point'){addMarker(wl,g.coordinates,'wk',f,'w');n++}});wl.style.display=S.swk?'':'none';const a=DATA.meta?.surface_permit_supported_from||'—',b=DATA.meta?.surface_permit_supported_through||'—',asof=DATA.meta?.surface_permit_data_as_of?String(DATA.meta.surface_permit_data_as_of).slice(0,10):'unknown';$('ws').innerHTML=supported?`<span class="${n?'ok':'warn'}">${n.toLocaleString()} active</span><span class="muted"> · selected date · data as of ${esc(asof)} · supported ${esc(a)}–${esc(b)}</span>`:`<span class="warn">outside snapshot window</span><span class="muted"> · supported ${esc(a)}–${esc(b)}</span>`}
'''
repl(render_anchor, render_work + render_anchor, "render work permits")

# Work permit hover/click branches precede closure branches.
repl(
    "function hover(e){const p=e.f.properties||{};if(e.dataset.k==='c'){",
    "function hover(e){const p=e.f.properties||{};if(e.dataset.k==='w'){const where=workWhere(p),desc=String(p.permit_description||'').trim();return`<strong>${esc(workLabel(p))}</strong>${where?esc(where)+'<br>':''}${esc(workWindow(p))}${desc?'<br>'+esc(desc):''}<br><span style=\"opacity:.82\">Public Works permit point; not a confirmed closure or exact work footprint.</span>`}if(e.dataset.k==='c'){",
    "work hover",
)
repl(
    "function clicked(e){const p=e.f.properties||{};if(e.dataset.k==='c'){",
    "function clicked(e){const p=e.f.properties||{};if(e.dataset.k==='w'){const where=workWhere(p),desc=String(p.permit_description||'').trim(),num=p.permit_number?`<br>Permit: ${esc(p.permit_number)}`:'',hood=p.analysis_neighborhood?`<br>Neighborhood: ${esc(p.analysis_neighborhood)}`:'';return`<strong>${esc(workLabel(p))}</strong>${where?'<br>'+esc(where):''}<br>Status: ${esc(p.status||'—')}<br>Permit window: ${esc(workWindow(p))}${num}${hood}${desc?'<br>Description: '+esc(desc):''}<br><span class=\"muted\">Official SF Public Works surface-permit point. A permit authorizes street/sidewalk use; it does not prove the space is currently obstructed, closed, or impassable to pedestrians. The marker is a point location, not the work footprint.</span>`}if(e.dataset.k==='c'){",
    "work click",
)

# Share the existing field-time control with both dynamic layers.
repl(
    "$('cToggle').onchange=e=>{S.sc=e.target.checked;cl.style.display=S.sc?'':'none'};\n$('cTime').onchange=e=>{S.ct=e.target.value;renderC()};\n$('cNow').onclick=()=>{S.ct=sfNowLocal();$('cTime').value=S.ct;renderC()};",
    "$('cToggle').onchange=e=>{S.sc=e.target.checked;cl.style.display=S.sc?'':'none'};\n$('wToggle').onchange=e=>{S.swk=e.target.checked;wl.style.display=S.swk?'':'none'};\n$('cTime').onchange=e=>{S.ct=e.target.value;renderC();renderW()};\n$('cNow').onclick=()=>{S.ct=sfNowLocal();$('cTime').value=S.ct;renderC();renderW()};",
    "shared time interactions",
)
repl(
    "if(!DATA||!S.p?.features?.length||!S.s?.features?.length||!S.m?.features?.length||!S.c?.features?.length){",
    "if(!DATA||!S.p?.features?.length||!S.s?.features?.length||!S.m?.features?.length||!S.c?.features?.length||!S.w?.features?.length){",
    "work init validation",
)
repl(
    "S.ct=sfNowLocal();$('cTime').value=S.ct;renderS();renderP();renderM();renderC();const srcActive=",
    "S.ct=sfNowLocal();$('cTime').value=S.ct;renderS();renderP();renderM();renderW();renderC();const srcActive=",
    "work initial render",
)

# Keep point markers the same apparent size while zooming the SVG group.
repl(
    "function apply(){view.setAttribute('transform',`translate(${S.x} ${S.y}) scale(${S.z})`)}",
    "function apply(){view.setAttribute('transform',`translate(${S.x} ${S.y}) scale(${S.z})`);wl.querySelectorAll('circle.wk').forEach(e=>e.setAttribute('r',(3.5/S.z).toFixed(2)))}",
    "marker zoom scaling",
)

repl(
    'Street centerlines now carry a derived hill-steepness estimate from official 5-ft elevation contours; future closures can attach to the same segments.',
    'Street centerlines provide route context; hills are derived from official contours, SFMTA closures are time-filtered lines, and Public Works street-work permits are date-filtered point locations. A permit marker is not itself a closure.',
    "banner",
)

p.write_text(s, encoding="utf-8")
print("patched surface-permit UI")
