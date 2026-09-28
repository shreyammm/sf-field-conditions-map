#!/usr/bin/env python3
"""Convert the dynamic-layer control to an optional day-level planning date.

Default map state has no planning date, so no temporary closures or ROW permits
are drawn. Selecting a date shows every SFMTA closure whose local start/end
interval overlaps any portion of that San Francisco calendar day. Exact closure
hours remain visible in hover/click details. ROW permits use the same calendar
date but remain opt-in because of their density.
"""
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "_site" / "index.html"
s = p.read_text(encoding="utf-8")


def repl(old: str, new: str, label: str):
    global s
    if old not in s:
        raise SystemExit(f"planning-date UI patch anchor missing: {label}")
    s = s.replace(old, new, 1)


repl(
    '<div class="row"><div><div class="label">Temporary street closures</div><div class="muted">SFMTA-permitted · filtered by SF date/time</div></div><label class="switch"><input id="cToggle" type="checkbox" checked><span></span></label></div>',
    '<div class="row"><div><div class="label">Temporary street closures</div><div class="muted">SFMTA-permitted · choose a planning date to display</div></div><label class="switch"><input id="cToggle" type="checkbox" checked><span></span></label></div>',
    "closure layer subtitle",
)

repl(
    '''<div style="margin:8px 0 12px">
  <div class="label" style="font-size:12px">Field date/time (San Francisco)</div>
  <div class="dtrow"><input id="cTime" type="datetime-local" step="60" aria-label="Field date and time in San Francisco"><button id="cNow" type="button">Now</button></div>
  <div class="muted" style="margin-top:5px">Closures use exact start/end time. Public Works permit markers use the selected calendar date because permit windows are often day-level. Permit coverage is only treated as complete within the current/upcoming snapshot window shown below.</div>
</div>''',
    '''<div style="margin:8px 0 12px">
  <div class="label" style="font-size:12px">Plan for a date <span class="muted">(optional)</span></div>
  <div class="dtrow"><input id="cTime" type="date" aria-label="Planning date in San Francisco"><button id="cNow" type="button">Today</button><button id="cClear" type="button">Clear</button></div>
  <div class="muted" style="margin-top:5px">Choose a date to show temporary closures scheduled at any point that day. Closure details still show the official start/end hours. Street-work permits use the same date when that layer is enabled.</div>
</div>''',
    "optional planning date controls",
)

repl(
    '<div class="legend"><span class="ln" style="border-top:3px solid #2563eb"></span><span class="legendtext">SFMTA-permitted temporary closure active at selected time</span><span class="info" title="Vehicle/street disruption line from the official SFMTA closure feed. It does not necessarily mean pedestrian access is blocked.">ⓘ</span></div>',
    '<div class="legend"><span class="ln" style="border-top:3px solid #2563eb"></span><span class="legendtext">SFMTA-permitted temporary closure scheduled on selected date</span><span class="info" title="Shown when the official closure interval overlaps any part of the selected San Francisco calendar day. Click for exact hours. It does not necessarily mean pedestrian access is blocked.">ⓘ</span></div>',
    "closure legend day wording",
)

repl(
    'The map compares the selected <em>San Francisco local wall time</em> with each row’s <span class="code">start_dt</span> and <span class="code">end_dt</span> and draws only overlapping lines. ',
    'The map is date-optional. After a user selects a San Francisco calendar date, it draws a closure when that date overlaps any portion of the row’s <span class="code">start_dt</span>–<span class="code">end_dt</span> interval. Exact source hours remain visible in hover/click details. ',
    "closure methodology day wording",
)

old_closure_active = "const closureActive=(f,t)=>{const p=f.properties||{},a=normLocal(p.start_local||p.start_dt),b=normLocal(p.end_local||p.end_dt),q=normLocal(t);return!!(a&&b&&q&&a<=q&&q<=b)};"
new_closure_active = "const closureActive=(f,t)=>{const q=String(t||'').slice(0,10);if(!/^\\d{4}-\\d{2}-\\d{2}$/.test(q))return false;const p=f.properties||{},a=normLocal(p.start_local||p.start_dt),b=normLocal(p.end_local||p.end_dt);if(!a||!b)return false;const [y,m,d]=q.split('-').map(Number),nx=new Date(Date.UTC(y,m-1,d+1)).toISOString().slice(0,10),dayStart=q+'T00:00:00',nextStart=nx+'T00:00:00';return a<nextStart&&b>=dayStart};"
repl(old_closure_active, new_closure_active, "day-overlap closure predicate")

old_render_w = '''function renderW(){wl.replaceChildren();const supported=workSupportDate(S.ct);let n=0;if(supported)(S.w?.features||[]).forEach(f=>{if(!workActive(f,S.ct))return;const g=f.geometry||{};if(g.type==='Point'){n++;if(S.swk)addMarker(wl,g.coordinates,'wk',f,'w')}});wl.style.display=S.swk?'':'none';const a=DATA.meta?.surface_permit_supported_from||'—',b=DATA.meta?.surface_permit_supported_through||'—',retr=DATA.meta?.surface_permit_retrieved_sf?String(DATA.meta.surface_permit_retrieved_sf).slice(0,10):'unknown';$('ws').innerHTML=supported?`<span class="${n?'ok':'warn'}">${n.toLocaleString()} permit windows</span><span class="muted"> · overlap selected date · snapshot retrieved ${esc(retr)} · supported ${esc(a)}–${esc(b)}</span>`:`<span class="warn">outside snapshot window</span><span class="muted"> · supported ${esc(a)}–${esc(b)}</span>`}'''
new_render_w = '''function renderW(){wl.replaceChildren();const q=dateOnly(S.ct),supported=workSupportDate(S.ct);let n=0;if(supported)(S.w?.features||[]).forEach(f=>{if(!workActive(f,S.ct))return;const g=f.geometry||{};if(g.type==='Point'){n++;if(S.swk)addMarker(wl,g.coordinates,'wk',f,'w')}});wl.style.display=S.swk&&!!q?'':'none';const a=DATA.meta?.surface_permit_supported_from||'—',b=DATA.meta?.surface_permit_supported_through||'—',retr=DATA.meta?.surface_permit_retrieved_sf?String(DATA.meta.surface_permit_retrieved_sf).slice(0,10):'unknown';$('ws').innerHTML=!q?`<span class="muted">Choose a planning date to filter permit windows · snapshot supported ${esc(a)}–${esc(b)}</span>`:supported?`<span class="${n?'ok':'warn'}">${n.toLocaleString()} permit windows</span><span class="muted"> · overlap ${esc(fmtDateOnly(q))} · snapshot retrieved ${esc(retr)} · supported ${esc(a)}–${esc(b)}</span>`:`<span class="warn">selected date outside permit snapshot window</span><span class="muted"> · supported ${esc(a)}–${esc(b)}</span>`}'''
repl(old_render_w, new_render_w, "permit no-date behavior")

old_render_c = '''function renderC(){cl.replaceChildren();let n=0;(S.c?.features||[]).forEach(f=>{if(!closureActive(f,S.ct))return;const d=linePath(f.geometry);if(d){add(cl,d,'cl',f,'c');n++}});cl.style.display=S.sc?'':'none';const sourceDate=DATA.meta?.closure_data_as_of?String(DATA.meta.closure_data_as_of).slice(0,10):DATA.meta?.retrieved_at?String(DATA.meta.retrieved_at).slice(0,10):'unknown';const sourceLabel=DATA.meta?.closure_data_as_of?'source date':'retrieved';$('cs').innerHTML=`<span class="${n?'ok':'warn'}">${n.toLocaleString()} active</span><span class="muted"> · selected SF time · ${esc(sourceLabel)} ${esc(sourceDate)}</span>`}'''
new_render_c = '''function renderC(){cl.replaceChildren();const q=dateOnly(S.ct);let n=0;if(q)(S.c?.features||[]).forEach(f=>{if(!closureActive(f,q))return;const d=linePath(f.geometry);if(d){add(cl,d,'cl',f,'c');n++}});cl.style.display=S.sc&&!!q?'':'none';const sourceDate=DATA.meta?.closure_data_as_of?String(DATA.meta.closure_data_as_of).slice(0,10):DATA.meta?.retrieved_at?String(DATA.meta.retrieved_at).slice(0,10):'unknown';const sourceLabel=DATA.meta?.closure_data_as_of?'source date':'retrieved';$('cs').innerHTML=!q?`<span class="muted">Choose a planning date to display temporary closures · ${esc(sourceLabel)} ${esc(sourceDate)}</span>`:`<span class="${n?'ok':'warn'}">${n.toLocaleString()} scheduled</span><span class="muted"> · ${esc(fmtDateOnly(q))} · ${esc(sourceLabel)} ${esc(sourceDate)}</span>`}'''
repl(old_render_c, new_render_c, "closure no-date/day behavior")

repl(
    "$('cToggle').onchange=e=>{S.sc=e.target.checked;cl.style.display=S.sc?'':'none'};",
    "$('cToggle').onchange=e=>{S.sc=e.target.checked;renderC()};",
    "closure toggle rerender",
)
repl(
    "$('cTime').onchange=e=>{S.ct=e.target.value;renderC();renderW()};",
    "$('cTime').onchange=e=>{S.ct=e.target.value;renderC();renderW()};",
    "planning date change",
)
repl(
    "$('cNow').onclick=()=>{S.ct=sfNowLocal();$('cTime').value=S.ct;renderC();renderW()};",
    "$('cNow').onclick=()=>{S.ct=sfNowLocal().slice(0,10);$('cTime').value=S.ct;renderC();renderW()};\n$('cClear').onclick=()=>{S.ct='';$('cTime').value='';renderC();renderW()};",
    "today and clear controls",
)

repl(
    "S.ct=sfNowLocal();$('cTime').value=S.ct;renderS();renderP();renderM();renderW();renderC();",
    "S.ct='';$('cTime').value='';renderS();renderP();renderM();renderW();renderC();",
    "no planning date by default",
)

p.write_text(s, encoding="utf-8")
print("applied optional planning-date UI")
