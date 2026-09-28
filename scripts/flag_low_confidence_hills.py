#!/usr/bin/env python3
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'_site'/'index.html'
s=p.read_text(encoding='utf-8')
old='.hunk{stroke:#d0d5dd!important;stroke-dasharray:2 2}'
new='.hunk{stroke:#d0d5dd!important;stroke-dasharray:2 2}.hlow{stroke-opacity:.48;stroke-dasharray:3 2}'
if old not in s:
    raise SystemExit('low-confidence CSS anchor missing')
s=s.replace(old,new,1)
old2="hillClass=p=>{const g=hillGrade(p);if(!Number.isFinite(g))return'hunk';if(g>=20)return'hg20';if(g>=15)return'hg15';if(g>=10)return'hg10';if(g>=5)return'hg5';return'hg0'}"
new2="hillClass=p=>{const g=hillGrade(p);if(!Number.isFinite(g))return'hunk';const b=g>=20?'hg20':g>=15?'hg15':g>=10?'hg10':g>=5?'hg5':'hg0';return hillConfidence(p)==='low'?b+' hlow':b}"
if old2 not in s:
    raise SystemExit('low-confidence class anchor missing')
s=s.replace(old2,new2,1)
needle='<div class="legend"><span class="ln" style="border-top:2px dashed #d0d5dd"></span><span class="legendtext">Insufficient direct contour crossings</span></div>'
insert=needle+'\n<div class="legend"><span class="ln" style="border-top:2px dashed #e76f51;opacity:.48"></span><span class="legendtext">Dashed/faded color = low-confidence estimate</span></div>'
if needle not in s:
    raise SystemExit('low-confidence legend anchor missing')
s=s.replace(needle,insert,1)
p.write_text(s,encoding='utf-8')
print('flagged low-confidence hill estimates')
