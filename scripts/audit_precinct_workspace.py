#!/usr/bin/env python3
"""Deployment-blocking audit for precinct focus/summary and dispatch-priority styling."""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import tempfile
from collections import Counter

from shapely.geometry import Point, shape

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = ROOT / "_site" / "index.html"
MANIFEST = ROOT / "_site" / "data-manifest.json"
html = SITE.read_text(encoding="utf-8")
manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
m = re.search(r"window\.SF_FIELD_DATA=(\{.*?\});\s*</script>", html, re.S)
if not m:
    raise SystemExit("PRECINCT WORKSPACE AUDIT FAIL: embedded data missing")
data = json.loads(m.group(1))
issues = []

def check(ok, msg):
    if not ok:
        issues.append(msg)

def props(f):
    return f.get("properties") or {}

def pid(p):
    return str(p.get("prec_2022") or p.get("precinct") or p.get("id") or "").strip()

precincts = (data.get("precincts") or {}).get("features") or []
ids = [pid(props(f)) for f in precincts]
check(len(ids) == 514, f"expected 514 precincts, got {len(ids)}")
check(all(ids) and len(ids) == len(set(ids)), "precinct IDs missing/duplicated")
check(all(str(props(f).get("focus_precinct") or "") == pid(props(f)) for f in precincts), "precinct focus ids not self-consistent")
valid = set(ids)
geom_by_id = {pid(props(f)): shape(f.get("geometry")) for f in precincts}

# Parcel assignment: exactly one precinct at most and representative point must lie in it.
parcels = (data.get("multifamily") or {}).get("features") or []
unassigned_parcels = 0
for f in parcels:
    p = props(f)
    q = str(p.get("focus_precinct") or "")
    if not q:
        unassigned_parcels += 1
        continue
    check(q in valid, f"parcel assigned invalid precinct {q}")
    try:
        rp = shape(f.get("geometry")).representative_point()
        check(geom_by_id[q].covers(rp), f"parcel representative point not covered by assigned precinct {q}")
    except Exception as exc:
        issues.append(f"parcel geometry check failed: {exc}")
check(unassigned_parcels <= 5, f"too many unassigned parcels: {unassigned_parcels}")

# Point layers: embedded point must lie in assigned precinct; privacy-suppressed calls
# are already absent from this mapped collection.
for name in ("surface_permits", "live_calls"):
    fs = (data.get(name) or {}).get("features") or []
    missing = 0
    for f in fs:
        p = props(f); q = str(p.get("focus_precinct") or "")
        if not q:
            missing += 1; continue
        check(q in valid, f"{name} invalid precinct {q}")
        c = (f.get("geometry") or {}).get("coordinates") or []
        if len(c) >= 2:
            check(geom_by_id[q].covers(Point(float(c[0]), float(c[1]))), f"{name} point outside assigned precinct {q}")
    check(missing <= 5, f"{name} has too many unassigned mapped points: {missing}")

# Line membership must contain only valid precinct IDs and represent positive-length overlap.
for name in ("streets", "closures"):
    fs = (data.get(name) or {}).get("features") or []
    missing = 0
    for f in fs:
        p = props(f); qs = p.get("focus_precincts")
        check(isinstance(qs, list), f"{name} focus_precincts missing/not list")
        if not isinstance(qs, list):
            continue
        check(len(qs) == len(set(map(str, qs))), f"{name} duplicate focus precinct membership")
        if not qs: missing += 1
        try:
            g = shape(f.get("geometry"))
            for q0 in qs:
                q = str(q0)
                check(q in valid, f"{name} invalid precinct {q}")
                if q in geom_by_id:
                    check(g.intersection(geom_by_id[q]).length > 1e-10, f"{name} listed precinct has no positive-length overlap: {q}")
        except Exception as exc:
            issues.append(f"{name} geometry/membership check failed: {exc}")
    if name == "streets": check(missing <= 20, f"too many streets outside all precincts: {missing}")
    else: check(missing == 0, f"closures outside all precincts: {missing}")

# UI / semantics.
for token, label in [
    ('id="pSearch"', "precinct search input"), ('id="pChips"', "selection chips"),
    ('id="pFit"', "focus selected button"), ('id="pClearFocus"', "clear selection button"),
    ('id="pShare"', "share link button"), ('id="focusSummary"', "selected-area summary"),
    ("searchParams.set('precincts'", "URL precinct state"), ('function fitSelected()', "fit selection"),
    ('function renderFocusSummary()', "summary computation"), ('function applyFocusStyles()', "map focus styling"),
    ('togglePrecinct(', "click-to-toggle precinct"),
]:
    check(token in html, f"missing {label}")

check("It does not score, rank, or recommend precincts" in html, "neutral precinct-selection methodology missing")
check("representative point" in html and "double" in html.lower(), "parcel no-double-count explanation missing")
check("street segments intersecting the selection" in html, "hill segment interpretation missing")
check("privacy-masked" in html and "precinct boundary" in html, "dispatch boundary/privacy caveat missing")

# Priority encoding must use the documented source priority fields rather than a subjective crime score.
for token in ("priA", "priB", "priC", "Priority A", "Priority B", "Priority C"):
    check(token in html, f"priority encoding missing: {token}")
check("priority_final||p?.priority_original" in html, "priority field fallback rule missing")
check("Circle size is fixed" in html, "fixed-size priority marker methodology missing")
check("highest priority represented" in html.lower(), "cluster highest-priority semantics missing")
check("not confirmed crime severity" in html.lower() or "not confirmed crimes" in html.lower(), "dispatch-not-crime caveat missing")
check("no longer used" in html and "forest-green" in html, "old open/closed color encoding not explicitly superseded")

# The final override, not legacy code earlier in the bundle, must have fixed radii and no sqrt/log count scaling.
pos = html.rfind("renderI=function()")
end = html.find("const _hoverBeforeWorkspace", pos)
check(pos >= 0 and end > pos, "final renderI priority override missing")
if pos >= 0 and end > pos:
    final_render = html[pos:end]
    check("Math.sqrt(a.n)" not in final_render and "Math.log2(a.n" not in final_render, "final live marker size still scales with call count")
    check("workspaceAddLiveMarker(il,coord,feature,6.5)" in final_render and "workspaceAddLiveMarker(il,coord,feature,5.5)" in final_render, "final live marker fixed radii missing")
    check("workspaceDisplayFeature" in final_render and "priorityCounts(fs)" in final_render, "final live render does not use source priority")

# Summary must respect active filters/date and selected geography.
summary_start = html.find("function renderFocusSummary()")
summary_end = html.find("function renderFocusAware()", summary_start)
summary = html[summary_start:summary_end] if summary_start >= 0 and summary_end > summary_start else ""
for token in ("inFocus(f,'m')", "inFocus(f,'s')", "inFocus(f,'c')", "inFocus(f,'w')", "inFocus(f,'i')", "closureActive(f,q)", "workActive(f,q)", "liveFiltered()"):
    check(token in summary, f"summary missing filtered metric logic: {token}")

# Manifest must document the same semantics.
pwm = manifest.get("precinct_workspace") or {}
check(int(pwm.get("precinct_count") or 0) == 514, "manifest precinct workspace count incorrect")
pv = ((manifest.get("live_calls") or {}).get("priority_visualization") or {})
check(pv.get("field_rule") == "priority_final when present, otherwise priority_original", "manifest priority field rule incorrect")
check("fixed" in str(pv.get("size_rule") or "").lower(), "manifest does not document fixed marker size")
check("not confirmed crime" in str(pv.get("interpretation") or "").lower(), "manifest priority interpretation missing")

# Current embedded mapped fallback should have recognizable priority values.
pri = Counter()
for f in (data.get("live_calls") or {}).get("features") or []:
    p = props(f); pri[str(p.get("priority_final") or p.get("priority_original") or "U").upper()] += 1
check(sum(pri.values()) >= 50, "live fallback priority distribution unexpectedly empty")
check(set(pri).issubset({"A", "B", "C", "I", "U", ""}), f"unexpected dispatch priority codes: {sorted(pri)}")

# Final JS syntax check.
scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
check(bool(scripts), "no script blocks found")
if scripts:
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write(scripts[-1]); js_path = fh.name
    r = subprocess.run(["node", "--check", js_path], capture_output=True, text=True)
    check(r.returncode == 0, "final inline JS syntax failed: " + (r.stderr.strip()[:500] if r.stderr else "unknown"))
    pathlib.Path(js_path).unlink(missing_ok=True)

if issues:
    print(f"PRECINCT WORKSPACE AUDIT FAIL: {len(issues)} issue(s)")
    for x in issues[:100]: print(" -", x)
    raise SystemExit(1)

print("PRECINCT WORKSPACE AUDIT PASS")
print(f"precincts={len(ids)}; parcels={len(parcels)}; parcel_unassigned={unassigned_parcels}")
print("priority distribution:", dict(pri))
print("focus: multi-precinct search/paste + click selection + URL sharing + selected-area summary")
print("dispatch: fixed-size A/B/C priority colors; low-zoom cluster color = highest represented priority")
