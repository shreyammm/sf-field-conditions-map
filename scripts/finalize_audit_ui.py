#!/usr/bin/env python3
"""Small post-patch fixes found during the full-layer audit.

1. The shared field-time control must be labeled for both closures and permits.
2. The opt-in ROW-permit layer must not create thousands of hidden SVG circles
   while it is switched off. It still counts overlapping permit windows for the
   source-status text, but only creates markers when the layer is enabled.
"""
from pathlib import Path
import re

p = Path(__file__).resolve().parents[1] / "_site" / "index.html"
s = p.read_text(encoding="utf-8")

old_aria = 'aria-label="Closure date and time in San Francisco"'
new_aria = 'aria-label="Field date and time in San Francisco"'
if old_aria not in s:
    raise SystemExit("audit UI anchor missing: shared time aria-label")
s = s.replace(old_aria, new_aria, 1)

pattern = re.compile(r"function renderW\(\)\{.*?\}\nfunction renderC\(\)", re.S)
m = pattern.search(s)
if not m:
    raise SystemExit("audit UI anchor missing: renderW")

new_render = '''function renderW(){wl.replaceChildren();const supported=workSupportDate(S.ct);let n=0;if(supported)(S.w?.features||[]).forEach(f=>{if(!workActive(f,S.ct))return;const g=f.geometry||{};if(g.type==='Point'){n++;if(S.swk)addMarker(wl,g.coordinates,'wk',f,'w')}});wl.style.display=S.swk?'':'none';const a=DATA.meta?.surface_permit_supported_from||'—',b=DATA.meta?.surface_permit_supported_through||'—',retr=DATA.meta?.surface_permit_retrieved_sf?String(DATA.meta.surface_permit_retrieved_sf).slice(0,10):'unknown';$('ws').innerHTML=supported?`<span class="${n?'ok':'warn'}">${n.toLocaleString()} permit windows</span><span class="muted"> · overlap selected date · snapshot retrieved ${esc(retr)} · supported ${esc(a)}–${esc(b)}</span>`:`<span class="warn">outside snapshot window</span><span class="muted"> · supported ${esc(a)}–${esc(b)}</span>`}
function renderC()'''
s = s[:m.start()] + new_render + s[m.end():]

old_toggle = "$('wToggle').onchange=e=>{S.swk=e.target.checked;wl.style.display=S.swk?'':'none'};"
new_toggle = "$('wToggle').onchange=e=>{S.swk=e.target.checked;renderW()};"
if old_toggle not in s:
    raise SystemExit("audit UI anchor missing: work toggle handler")
s = s.replace(old_toggle, new_toggle, 1)

p.write_text(s, encoding="utf-8")
print("applied audited UI fixes")
