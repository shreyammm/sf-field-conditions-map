#!/usr/bin/env python3
"""Deployment-blocking audit for parcel display-vs-summary precinct semantics."""
from __future__ import annotations

import json
import pathlib
import re
from shapely.geometry import shape
from shapely.strtree import STRtree

ROOT = pathlib.Path(__file__).resolve().parents[1]
html = (ROOT / "_site" / "index.html").read_text(encoding="utf-8")
manifest = json.loads((ROOT / "_site" / "data-manifest.json").read_text(encoding="utf-8"))
issues=[]
def check(ok,msg):
    if not ok: issues.append(msg)

m=re.search(r"window\.SF_FIELD_DATA=(\{.*?\});\s*</script>",html,re.S)
check(bool(m),"embedded payload missing")
data=json.loads(m.group(1)) if m else {}
precincts=(data.get("precincts") or {}).get("features") or []
parcels=(data.get("multifamily") or {}).get("features") or []

def pid(p):
    return str(p.get("focus_precinct") or p.get("prec_2022") or p.get("precinct") or p.get("id") or "").strip()

pg=[]; ids=[]
for f in precincts:
    q=pid(f.get("properties") or {}); g=shape(f.get("geometry"))
    if not g.is_valid: g=g.buffer(0)
    ids.append(q); pg.append(g)
tree=STRtree(pg)
valid=set(ids)

def overlaps(g):
    if not g.is_valid: g=g.buffer(0)
    out=[]
    for idx in tree.query(g,predicate="intersects"):
        i=int(idx); inter=g.intersection(pg[i])
        if not inter.is_empty and float(inter.area)>1e-14: out.append(ids[i])
    return sorted(set(out))

display_missing=0; summary_missing=0; multi=0
for f in parcels:
    p=f.get("properties") or {}; g=shape(f.get("geometry"))
    actual=sorted(map(str,p.get("focus_precincts") or [])); expected=overlaps(g)
    check(actual==expected,f"parcel display memberships disagree with positive-area overlap: {p.get('mapblklot')} {actual} != {expected}")
    check(all(q in valid for q in actual),f"parcel has invalid display precinct: {p.get('mapblklot')}")
    if not actual: display_missing+=1
    if len(actual)>1: multi+=1
    q=str(p.get("focus_precinct") or "").strip()
    if not q:
        summary_missing+=1
    else:
        check(q in valid,f"parcel summary precinct invalid: {p.get('mapblklot')} / {q}")
        try:
            rp=g.representative_point()
            check(pg[ids.index(q)].covers(rp),f"parcel summary representative point not covered by assigned precinct: {p.get('mapblklot')} / {q}")
        except Exception as exc:
            issues.append(f"parcel representative point validation failed: {exc}")

check(display_missing<=2,f"too many parcels have no positive-area precinct overlap: {display_missing}")
check(summary_missing<=5,f"too many parcels omitted from unique summary assignment: {summary_missing}")
check(multi>0,"expected at least one parcel to overlap multiple precincts; display membership appears broken")
# UI must display by focus_precincts/inFocus, but summarize by exactly-one focus_precinct.
check("if(!inFocus(f,'m'))continue" in html,"focused parcel renderer is not using polygon-overlap focus membership")
summary_start=html.find("function renderFocusSummary()")
summary_end=html.find("function renderFocusAware()",summary_start)
summary=html[summary_start:summary_end] if summary_start>=0 and summary_end>summary_start else ""
check("PFOCUS.has(String((f.properties||{}).focus_precinct||''))" in summary,"parcel summary is not using unique representative-point assignment")
check("inFocus(f,'m')&&Number(units" not in summary,"parcel summary still uses multi-precinct display membership and can double-count")
check("Parcel display and parcel totals intentionally use different boundary rules" in html,"display-vs-summary methodology missing")
check("remains visible by polygon overlap but is omitted from the precinct total rather than assigned arbitrarily" in html,"official precinct gap behavior not explained")

pm=manifest.get("parcel_focus_semantics") or {}
check(pm.get("version")==1,"parcel focus manifest missing")
check(int(pm.get("display_unassigned",-1))==display_missing,"manifest display-unassigned count mismatch")
check(int(pm.get("summary_unassigned",-1))==summary_missing,"manifest summary-unassigned count mismatch")
check(int(pm.get("multi_precinct_display",-1))==multi,"manifest multi-precinct parcel count mismatch")
check("positive-area" in str(pm.get("display_rule") or ""),"manifest display rule missing positive-area overlap")
check("representative point" in str(pm.get("summary_rule") or ""),"manifest summary rule missing representative point")

if issues:
    print(f"PARCEL FOCUS AUDIT FAIL: {len(issues)} issue(s)")
    for x in issues[:100]: print(" -",x)
    raise SystemExit(1)
print("PARCEL FOCUS AUDIT PASS")
print(f"parcels={len(parcels)}; display_unassigned={display_missing}; summary_unassigned={summary_missing}; multi_precinct_display={multi}")
print("display: positive-area polygon overlap; summary: exactly-one representative-point assignment")
