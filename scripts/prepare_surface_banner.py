#!/usr/bin/env python3
from pathlib import Path
import re
p=Path(__file__).resolve().parents[1]/'_site'/'index.html'
s=p.read_text(encoding='utf-8')
replacement='<div class="banner">Street centerlines now carry a derived hill-steepness estimate from official 5-ft elevation contours; future closures can attach to the same segments.</div>'
s2,n=re.subn(r'<div class="banner">.*?</div>',replacement,s,count=1,flags=re.S)
if n!=1:
    raise SystemExit(f'expected one banner, replaced {n}')
p.write_text(s2,encoding='utf-8')
