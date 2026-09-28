#!/usr/bin/env python3
from pathlib import Path

p=Path(__file__).resolve().parents[1]/'_site'/'index.html'
s=p.read_text(encoding='utf-8')

def rep(old,new,label):
    global s
    if old not in s:
        raise SystemExit(f'surface refinement anchor missing: {label}')
    s=s.replace(old,new,1)

# This layer is intentionally opt-in: thousands of valid permit points can
# overlap a single date and would otherwise obscure the core route geography.
rep('<input id="wToggle" type="checkbox" checked>','<input id="wToggle" type="checkbox">','work toggle default')
rep('sc:true,swk:true,sp:true','sc:true,swk:false,sp:true','work state default')

rep('Public Works street-work / ROW permit active on selected date','Public Works street-work / ROW permit whose permit window overlaps selected date','legend wording')
rep('SF Public Works · current/upcoming surface work','SF Public Works · current/upcoming work/occupancy permits','toggle subtitle')
rep('Street work</b><span id="ws">','ROW permits</b><span id="ws">','status label')

# Do not equate an authorization window with crews physically working.
rep('${n.toLocaleString()} active</span><span class="muted"> · selected date', '${n.toLocaleString()} permit windows</span><span class="muted"> · overlap selected date', 'status count wording')
rep('Public Works permit point; not a confirmed closure or exact work footprint.','Public Works permit authorization point; the date window does not prove crews are working then, and this is not a confirmed closure or exact work footprint.','hover caveat')
rep('A permit authorizes street/sidewalk use; it does not prove the space is currently obstructed, closed, or impassable to pedestrians.','A permit authorizes street/sidewalk use during a permitted window; it does not prove crews are physically working on the selected date or that the space is obstructed, closed, or impassable to pedestrians.','click caveat')

p.write_text(s,encoding='utf-8')
print('refined surface-permit UI')
