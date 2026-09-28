#!/usr/bin/env python3
from pathlib import Path

p=Path(__file__).resolve().parents[1]/'_site'/'index.html'
s=p.read_text(encoding='utf-8')

old='The build samples five points along each street segment, estimates elevation from nearby distinct contour levels, and calculates average absolute elevation change over horizontal street length.'
old2='The build samples five points along each street segment, estimates elevation from nearby distinct contour levels, and fits a smoothed longitudinal elevation trend across those samples and converts that trend to percent grade.'
old3='The build directly intersects each street centerline with the official contour lines and computes rise/run only between consecutive crossings of different known elevations. Streets without enough direct contour crossings remain unclassified rather than receiving a guessed grade.'
new=('The build directly intersects each non-freeway street centerline with the official contours. '
     'Consecutive same-elevation crossings contribute zero net rise across that supported span; '
     'non-zero consecutive crossings must differ by about 5 feet. Non-5-foot jumps and implausible short-span artifacts are rejected instead of being forced into a grade. '
     'Confidence also reflects how much of the street segment is directly supported by accepted contour intervals. Streets without enough evidence remain unclassified.')
for x in (old,old2,old3):
    s=s.replace(x,new)

s=s.replace('This is an <em>estimated average grade</em>, not an official engineering street-grade survey.',
            'This is a <em>contour-supported route-planning estimate over the directly supported portions of the street segment</em>, not an official engineering street-grade survey. Freeways and freeway ramps are left not-applicable rather than classified as canvassing hill streets.')

old_js="hillText=p=>{const g=hillGrade(p);return Number.isFinite(g)?`${g.toFixed(1)}% estimated average grade · ${hillConfidence(p)} confidence`:'grade unavailable — insufficient direct contour crossings'};"
new_js="hillText=p=>{const g=hillGrade(p),c=hillConfidence(p);return Number.isFinite(g)?`${g.toFixed(1)}% contour-supported grade estimate · ${c} confidence`:c==='not_applicable'?'hill grade not applied to freeway/ramp context':'grade unavailable — insufficient direct contour crossings'};"
if old_js not in s:
    raise SystemExit('hill text JS anchor missing')
s=s.replace(old_js,new_js,1)

old_click="${p.grade_crossing_intervals?`<br>Contour intervals used: ${esc(p.grade_crossing_intervals)} · supported span: ${esc(p.grade_supported_span_m)} m`:``}"
new_click="${p.grade_crossing_intervals?`<br>Contour intervals used: ${esc(p.grade_crossing_intervals)} · supported span: ${esc(p.grade_supported_span_m)} m · segment coverage: ${esc(Math.round(Number(p.grade_support_fraction||0)*100))}%`:``}"
if old_click not in s:
    raise SystemExit('hill click detail anchor missing')
s=s.replace(old_click,new_click,1)

p.write_text(s,encoding='utf-8')
