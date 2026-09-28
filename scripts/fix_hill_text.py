#!/usr/bin/env python3
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'_site'/'index.html'
s=p.read_text(encoding='utf-8')
s=s.replace('calculates average absolute elevation change over horizontal street length.','fits a smoothed longitudinal elevation trend across those samples and converts that trend to percent grade.')
p.write_text(s,encoding='utf-8')
