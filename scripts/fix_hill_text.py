#!/usr/bin/env python3
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'_site'/'index.html'
s=p.read_text(encoding='utf-8')
old='The build samples five points along each street segment, estimates elevation from nearby distinct contour levels, and calculates average absolute elevation change over horizontal street length.'
new='The build directly intersects each street centerline with the official contour lines and computes rise/run only between consecutive crossings of different known elevations. Streets without enough direct contour crossings remain unclassified rather than receiving a guessed grade.'
s=s.replace(old,new)
s=s.replace('The build samples five points along each street segment, estimates elevation from nearby distinct contour levels, and fits a smoothed longitudinal elevation trend across those samples and converts that trend to percent grade.',new)
p.write_text(s,encoding='utf-8')
