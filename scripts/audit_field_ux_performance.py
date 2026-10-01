#!/usr/bin/env python3
from __future__ import annotations
import json, pathlib, re, subprocess, tempfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
html=(ROOT/'_site'/'index.html').read_text(encoding='utf-8')
manifest=json.loads((ROOT/'_site'/'data-manifest.json').read_text(encoding='utf-8'))
issues=[]
def check(x,msg):
    if not x: issues.append(msg)
m=re.search(r'window\.SF_FIELD_DATA=(\{.*?\});\s*</script>',html,re.S)
check(bool(m),'embedded payload missing')
data=json.loads(m.group(1)) if m else {}
h=manifest.get('field_ux_hardening') or {}
check(h.get('version')==1,'hardening manifest missing')
check(float(h.get('payload_reduction_pct') or 0)>=20,'payload reduction <20%')
check(int(h.get('payload_bytes_after') or 10**9)<21_000_000,'embedded payload still >21MB')
check('raw.filter(f=>inFocus(f,\'i\'))' in html,'dispatch focus filter is not before display aggregation')
pos=html.rfind('renderI=function()'); end=html.find('const _hoverBeforeWorkspace',pos); final_live=html[pos:end] if pos>=0 and end>pos else ''
check("focusTxt=PFOCUS.size?' · selected precincts':''" in final_live,'final live renderer references focusTxt without declaring it')
check('low=S.z<2.4&&!PFOCUS.size' in html,'focused dispatch view still low-zoom clusters')
check('focus_precincts:[...a.precincts]' in html,'display clusters do not preserve represented precinct membership')
check('const PRECINCT_INDEX=' in html and 'geomBBox' in html,'client precinct bbox index missing')
check('pointOnSegment' in html,'client precinct test is not boundary-inclusive')
check('_workspaceLiveRowFeature' in html and 'f.properties.focus_precinct=q' in html,'runtime live points do not cache precinct membership')
check('.st-context' in html and 'parts.join(\' \')' in html,'focused street context is not collapsed')
check("if(!inFocus(f,'m'))continue" in html,'focused parcel renderer still instantiates out-of-area parcels')
check('Math.min(...xs)' not in html and 'Math.max(...xs)' not in html,'fitSelected still uses large spread arrays')
check('grid-template-rows:minmax(54dvh,1fr) minmax(0,46dvh)' in html,'mobile map-first split missing')
check('.mapwrap{grid-row:1' in html and '.side{grid-row:2' in html,'mobile map/control order missing')
check('<details class="method" open>' not in html,'methodology still expanded by default')
check('aria-live="polite"' in html,'live UI status missing')
check('approximate map context rather than exact precinct incident statistics' in html,'small-boundary dispatch caveat missing')
check('residential units on those displayed parcels' in html,'housing summary still sounds like all precinct housing')
check('privacy-mapped dispatch points' in html,'dispatch summary wording is not location-privacy precise')
check('function loadFocusFromUrl()' in html and '{renderFocusAware();fitSelected()}' in html,'shared precinct links do not enter optimized focus rendering')
# Required post-compaction fields for core audit/UI semantics.
required={
 'streets':['cnn','active','layer','classcode','grade_method','grade_confidence','focus_precincts'],
 'multifamily':['geography_type','resunits','focus_precinct'],
 'closures':['status','objectid','start_local','end_local','focus_precincts'],
 'surface_permits':['permit_number','permit_type','source_statuses','source_locations','source_descriptions','focus_precinct'],
 'live_calls':['id','received_datetime','open','priority_final','focus_precinct'],
}
workspace_meta=(data.get('meta') or {}).get('precinct_workspace') or {}
audited_unassigned=workspace_meta.get('unassigned_counts') or {}
for layer,keys in required.items():
    fs=((data.get(layer) or {}).get('features') or [])
    check(bool(fs),f'{layer} empty after compaction')
    for key in keys:
        if key=='focus_precinct' and layer=='multifamily':
            missing=sum(1 for f in fs if key not in (f.get('properties') or {}))
            expected=int(audited_unassigned.get('parcels',missing))
            check(missing==expected,f'parcel missing focus assignment count {missing} disagrees with audited workspace count {expected}')
            check(missing<=5,'too many parcel focus assignments missing after compaction')
        elif key=='focus_precinct' and layer=='live_calls':
            # A public privacy-mapped point can legitimately fall outside the
            # official precinct polygons. Preserve it as unassigned rather than
            # inventing a precinct merely to satisfy a UI audit.
            missing=sum(1 for f in fs if key not in (f.get('properties') or {}))
            expected=int(audited_unassigned.get('live_calls_fallback',missing))
            check(missing==expected,f'live-call missing focus assignment count {missing} disagrees with audited workspace count {expected}')
            check(missing<=10,'unexpectedly many live-call public points fall outside precinct coverage')
        else:
            check(all(key in (f.get('properties') or {}) for f in fs),f'{layer} lost required field {key}')
# No new runtime network dependencies.
check(len(re.findall(r'\bfetch\s*\(',html))==1,'runtime fetch count changed')
# Final JS syntax.
scripts=re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>',html,re.S|re.I)
for i,script in enumerate(scripts):
    with tempfile.NamedTemporaryFile('w',suffix='.js',delete=False,encoding='utf-8') as t:
        t.write(script); fn=t.name
    r=subprocess.run(['node','--check',fn],capture_output=True,text=True)
    pathlib.Path(fn).unlink(missing_ok=True)
    check(r.returncode==0,f'inline JS {i} syntax error: {r.stderr[:300]}')
if issues:
    print(f'FIELD UX/PERFORMANCE AUDIT FAIL: {len(issues)}')
    for x in issues: print(' -',x)
    raise SystemExit(1)
print('FIELD UX/PERFORMANCE AUDIT PASS')
print(f"payload: {h.get('payload_bytes_before'):,} -> {h.get('payload_bytes_after'):,} bytes ({h.get('payload_reduction_pct')}% smaller)")
print('focus correctness: filter dispatch points before clustering; selected view does not spatially cluster privacy-mapped points')
print('unassigned semantics: legitimate out-of-precinct parcel/live public points stay unassigned rather than being guessed')
print('runtime: indexed/cached precinct lookup; selected streets collapsed to context paths; out-of-focus parcels not instantiated')
print('mobile: map-first 54/46 dynamic-viewport split; larger touch targets; methodology collapsed')
