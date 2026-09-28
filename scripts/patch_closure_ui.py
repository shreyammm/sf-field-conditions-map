#!/usr/bin/env python3
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "_site" / "index.html"
s = p.read_text(encoding="utf-8")

def repl(old, new, label):
    global s
    if old not in s:
        raise SystemExit(f"closure UI patch anchor missing: {label}")
    s = s.replace(old, new, 1)

repl(
    ".hlow{stroke-opacity:.48;stroke-dasharray:3 2}",
    ".hlow{stroke-opacity:.48;stroke-dasharray:3 2}"
    ".cl{fill:none;stroke:#2563eb;stroke-width:3.2;vector-effect:non-scaling-stroke;pointer-events:stroke;cursor:pointer;stroke-linecap:round;paint-order:stroke;filter:drop-shadow(0 0 1px rgba(255,255,255,.95))}"
    ".cl:hover{stroke:#1d4ed8;stroke-width:4.5}"
    ".dtrow{display:flex;gap:6px;align-items:center;margin-top:6px}"
    ".dtrow input{min-width:0;flex:1;border:1px solid #d0d5dd;border-radius:7px;padding:7px 8px;font:inherit;font-size:12px;color:#344054;background:#fff}"
    ".dtrow button{border:1px solid #d0d5dd;border-radius:7px;background:#fff;padding:7px 9px;font:inherit;font-size:12px;color:#344054;cursor:pointer}"
    ".dtrow button:hover{background:#f9fafb}",
    "closure CSS",
)

hill_row = '<div class="row"><div><div class="label">Hill steepness</div><div class="muted">Estimated from official 5-ft elevation contours</div></div><label class="switch"><input id="hToggle" type="checkbox" checked><span></span></label></div>'
closure_controls = hill_row + '''
<div class="row"><div><div class="label">Temporary street closures</div><div class="muted">SFMTA-permitted · filtered by SF date/time</div></div><label class="switch"><input id="cToggle" type="checkbox" checked><span></span></label></div>
<div style="margin:8px 0 12px">
  <div class="label" style="font-size:12px">Closure time (San Francisco)</div>
  <div class="dtrow"><input id="cTime" type="datetime-local" step="60" aria-label="Closure date and time in San Francisco"><button id="cNow" type="button">Now</button></div>
  <div class="muted" style="margin-top:5px">Shows closure lines whose official SFMTA start/end window contains the selected SF local time.</div>
</div>'''
repl(hill_row, closure_controls, "closure controls")

legend_anchor = '<div class="legend"><span class="ln" style="border-top:2px dashed #e76f51;opacity:.48"></span><span class="legendtext">Dashed/faded color = low-confidence estimate</span></div>'
repl(
    legend_anchor,
    legend_anchor + '\n<div class="legend"><span class="ln" style="border-top:3px solid #2563eb"></span><span class="legendtext">SFMTA-permitted temporary closure active at selected time</span><span class="info" title="Vehicle/street disruption line from the official SFMTA closure feed. It does not necessarily mean pedestrian access is blocked.">ⓘ</span></div>',
    "closure legend",
)

method_anchor = '<div class="methoditem"><strong>Street styling</strong><br>'
closure_method = (
    '<div class="methoditem"><strong>Temporary street closures</strong><br>'
    'Downloaded at build time from SFMTA / DataSF dataset <span class="code">8x25-yybr</span>. '
    'The source contains permitted temporary closure line geometry for Shared Spaces, certain special events, and some construction work. '
    'The map compares the selected <em>San Francisco local wall time</em> with each row’s <span class="code">start_dt</span> and <span class="code">end_dt</span> and draws only overlapping lines. '
    'The line is a street/vehicle disruption indicator, not proof that pedestrians cannot pass. '
    'SFMTA explicitly notes that this feed does not include every closure managed by Public Works, SFPD, or other City departments.'
    '</div>\n' + method_anchor
)
repl(method_anchor, closure_method, "closure methodology")

repl(
    '<div><b>Hills</b><span id="hs">Reading derived grades…</span></div>',
    '<div><b>Hills</b><span id="hs">Reading derived grades…</span></div>\n<div><b>Closures</b><span id="cs">Reading embedded closure snapshot…</span></div>',
    "closure status",
)
repl(
    'Click a street segment, precinct, or colored parcel to pin details here.',
    'Click a street, closure, precinct, or colored parcel to pin details here.',
    "selected prompt",
)
repl(
    '<g id="sl"></g><g id="pl"></g><g id="ml"></g><g id="ll"></g>',
    '<g id="sl"></g><g id="pl"></g><g id="ml"></g><g id="cl"></g><g id="ll"></g>',
    "closure SVG group",
)
repl(
    "const $=id=>document.getElementById(id),svg=$('map'),view=$('view'),sl=$('sl'),pl=$('pl'),ml=$('ml'),ll=$('ll'),tip=$('tip'),detail=$('detail');",
    "const $=id=>document.getElementById(id),svg=$('map'),view=$('view'),sl=$('sl'),pl=$('pl'),ml=$('ml'),cl=$('cl'),ll=$('ll'),tip=$('tip'),detail=$('detail');",
    "closure DOM handle",
)
repl(
    "const S={p:DATA?.precincts||null,s:DATA?.streets||null,m:DATA?.multifamily||null,b:null,n:20,ss:true,sh:true,sp:true,sm:true,z:1,x:0,y:0,drag:false,lx:0,ly:0};",
    "const S={p:DATA?.precincts||null,s:DATA?.streets||null,m:DATA?.multifamily||null,c:DATA?.closures||null,b:null,n:20,ss:true,sh:true,sc:true,sp:true,sm:true,ct:null,z:1,x:0,y:0,drag:false,lx:0,ly:0};",
    "closure state",
)

helpers = '''const normLocal=v=>{const x=String(v||'').trim().replace(' ','T');return x.length>=16?(x.length>=19?x.slice(0,19):x+':00'):''};
const sfNowLocal=()=>{const a=new Intl.DateTimeFormat('en-US',{timeZone:'America/Los_Angeles',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date()),o={};a.forEach(x=>{if(x.type!=='literal')o[x.type]=x.value});return`${o.year}-${o.month}-${o.day}T${o.hour}:${o.minute}`};
const fmtSFLocal=v=>{const x=normLocal(v);if(!x)return'—';const m=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],[d,t]=x.split('T'),[y,mo,da]=d.split('-').map(Number),[hh,mm]=t.split(':').map(Number),ap=hh>=12?'PM':'AM',h=(hh%12)||12;return`${m[mo-1]} ${da}, ${y} ${h}:${String(mm).padStart(2,'0')} ${ap} SF time`};
const closureActive=(f,t)=>{const p=f.properties||{},a=normLocal(p.start_local||p.start_dt),b=normLocal(p.end_local||p.end_dt),q=normLocal(t);return!!(a&&b&&q&&a<=q&&q<=b)};
const closureName=p=>String(p.case_name||p.loc_desc||p.street||'Temporary street closure').trim();
const closureWhere=p=>{const st=String(p.street||'').trim(),a=String(p.from_st||'').trim(),b=String(p.to_st||'').trim();return st+(a||b?` between ${a||'segment start'} and ${b||'segment end'}`:'')};
const closureTimeText=p=>`${fmtSFLocal(p.start_local||p.start_dt)} to ${fmtSFLocal(p.end_local||p.end_dt)}`;
function add(parent,d,cls,f,k){'''
repl("function add(parent,d,cls,f,k){", helpers, "closure helpers")

render_c = '''function renderC(){cl.replaceChildren();let n=0;(S.c?.features||[]).forEach(f=>{if(!closureActive(f,S.ct))return;const d=linePath(f.geometry);if(d){add(cl,d,'cl',f,'c');n++}});cl.style.display=S.sc?'':'none';const snap=DATA.meta?.closure_data_as_of?String(DATA.meta.closure_data_as_of).slice(0,10):'unknown';$('cs').innerHTML=`<span class="${n?'ok':'warn'}">${n.toLocaleString()} active</span><span class="muted"> · selected SF time · snapshot ${esc(snap)}</span>`}
function renderP(){pl.replaceChildren();'''
repl("function renderP(){pl.replaceChildren();", render_c, "render closures")

hover_new = '''function hover(e){const p=e.f.properties||{};if(e.dataset.k==='c'){const where=closureWhere(p),typ=p.type||'Temporary closure';return`<strong>${esc(closureName(p))}</strong>${where?esc(where)+'<br>':''}${esc(typ)} · ${esc(closureTimeText(p))}<br><span style="opacity:.82">SFMTA-permitted closure/disruption. Check details; this does not automatically mean pedestrian access is blocked.</span>`}if(e.dataset.k==='s'){'''
repl("function hover(e){const p=e.f.properties||{};if(e.dataset.k==='s'){", hover_new, "closure hover")

click_new = '''function clicked(e){const p=e.f.properties||{};if(e.dataset.k==='c'){const where=closureWhere(p),impact=p.veh_imp?`<br>Vehicle impact: ${esc(p.veh_imp)}`:'',dir=p.direction?`<br>Direction: ${esc(p.direction)}`:'',info=p.info?`<br>Info: ${esc(p.info)}`:'',caseNo=p.case_num?`<br>Case: ${esc(p.case_num)}`:'';return`<strong>${esc(closureName(p))}</strong>${where?'<br>'+esc(where):''}<br>Type: ${esc(p.type||'Temporary closure')}<br>Scheduled: ${esc(closureTimeText(p))}${impact}${dir}${caseNo}${info}<br><span class="muted">Official SFMTA permitted-closure geometry. This feed is not a complete inventory of closures managed by other City departments and a street closure does not necessarily prohibit pedestrian passage.</span>`}if(e.dataset.k==='s'){'''
repl("function clicked(e){const p=e.f.properties||{};if(e.dataset.k==='s'){", click_new, "closure click")

repl(
    "detail.textContent='Hover for a quick explanation. Click a street segment, precinct, or colored parcel to pin details here.'};",
    "detail.textContent='Hover for a quick explanation. Click a street, closure, precinct, or colored parcel to pin details here.'};",
    "blank-map prompt",
)
repl(
    "$('hToggle').onchange=e=>{S.sh=e.target.checked;renderS()};",
    "$('hToggle').onchange=e=>{S.sh=e.target.checked;renderS()};\n$('cToggle').onchange=e=>{S.sc=e.target.checked;cl.style.display=S.sc?'':'none'};\n$('cTime').onchange=e=>{S.ct=e.target.value;renderC()};\n$('cNow').onclick=()=>{S.ct=sfNowLocal();$('cTime').value=S.ct;renderC()};",
    "closure interactions",
)
repl(
    "if(!DATA||!S.p?.features?.length||!S.s?.features?.length||!S.m?.features?.length){",
    "if(!DATA||!S.p?.features?.length||!S.s?.features?.length||!S.m?.features?.length||!S.c?.features?.length){",
    "closure init validation",
)
repl(
    "renderS();renderP();renderM();const srcActive=",
    "S.ct=sfNowLocal();$('cTime').value=S.ct;renderS();renderP();renderM();renderC();const srcActive=",
    "closure initial render",
)
repl(
    "const gc=DATA.meta?.grade_category_counts||{},graded=Number(DATA.meta?.graded_street_count||0),low=Number(DATA.meta?.grade_low_confidence_count||0);$('hs').innerHTML=`<span class=\"ok\">${graded.toLocaleString()} classified</span><span class=\"muted\"> · ${low.toLocaleString()} low/unavailable · 20%+: ${Number(gc['20+']||0).toLocaleString()}</span>`;",
    "const gc=DATA.meta?.grade_category_counts||{},graded=Number(DATA.meta?.graded_street_count||0),unavail=Number(DATA.meta?.grade_unavailable_count??gc.unavailable??0),na=Number(DATA.meta?.grade_not_applicable_count??gc.not_applicable??0);$('hs').innerHTML=`<span class=\"ok\">${graded.toLocaleString()} classified</span><span class=\"muted\"> · ${unavail.toLocaleString()} unavailable · ${na.toLocaleString()} freeway/ramp N/A · 20%+: ${Number(gc['20+']||0).toLocaleString()}</span>`;",
    "hill status refinement",
)

p.write_text(s, encoding="utf-8")
print("patched closure UI")
