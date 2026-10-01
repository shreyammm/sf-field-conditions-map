#!/usr/bin/env python3
"""Make precinct-focused parcel display geometric while keeping summaries unique.

A parcel can physically overlap more than one precinct. For map display, show it
in every selected precinct with positive-area overlap. For selected-area totals,
continue assigning it to at most one precinct using the existing representative
point so group summaries never double-count the same parcel. If that point falls
in an official precinct-geometry gap, omit the parcel from the summary rather
than guessing, while still displaying it wherever its polygon truly overlaps.
"""
from __future__ import annotations

import json
import pathlib
import re

from shapely.geometry import shape
from shapely.strtree import STRtree

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = ROOT / "_site" / "index.html"
MANIFEST = ROOT / "_site" / "data-manifest.json"

html = SITE.read_text(encoding="utf-8")
m = re.search(r"window\.SF_FIELD_DATA=(\{.*?\});\s*</script>", html, re.S)
if not m:
    raise SystemExit("parcel focus fix: embedded payload missing")
data = json.loads(m.group(1))


def pid(props):
    return str(props.get("focus_precinct") or props.get("prec_2022") or props.get("precinct") or props.get("id") or "").strip()

precincts = (data.get("precincts") or {}).get("features") or []
if not precincts:
    raise SystemExit("parcel focus fix: precincts missing")
prec_geoms, prec_ids = [], []
for f in precincts:
    q = pid(f.get("properties") or {})
    g = shape(f.get("geometry"))
    if not q or g.is_empty:
        raise SystemExit("parcel focus fix: invalid precinct feature")
    if not g.is_valid:
        g = g.buffer(0)
    prec_ids.append(q)
    prec_geoms.append(g)
tree = STRtree(prec_geoms)


def area_precincts(geom):
    try:
        g = shape(geom)
    except Exception:
        return []
    if g.is_empty:
        return []
    if not g.is_valid:
        g = g.buffer(0)
    if g.is_empty:
        return []
    out = []
    for idx in tree.query(g, predicate="intersects"):
        i = int(idx)
        inter = g.intersection(prec_geoms[i])
        # Ignore a parcel that merely touches a boundary/corner. Positive area is
        # the display contract for polygons.
        if not inter.is_empty and float(inter.area) > 1e-14:
            out.append(prec_ids[i])
    return sorted(set(out))

parcels = (data.get("multifamily") or {}).get("features") or []
display_missing = 0
summary_missing = 0
multi_precinct = 0
for f in parcels:
    p = f.setdefault("properties", {})
    ids = area_precincts(f.get("geometry"))
    p["focus_precincts"] = ids
    if not ids:
        display_missing += 1
    if len(ids) > 1:
        multi_precinct += 1
    q = str(p.get("focus_precinct") or "").strip()
    if not q:
        summary_missing += 1

# Patch the selected-area parcel total to use exactly-one representative-point
# assignment. Map rendering continues using inFocus(), whose focusIds() prefers
# focus_precincts and therefore uses positive-area overlap for parcel display.
old_summary = "const parcels=(S.m?.features||[]).filter(f=>inFocus(f,'m')&&Number(units(f.properties||{}))>=S.n)"
new_summary = "const parcels=(S.m?.features||[]).filter(f=>PFOCUS.has(String((f.properties||{}).focus_precinct||''))&&Number(units(f.properties||{}))>=S.n)"
if old_summary not in html:
    raise SystemExit("parcel focus fix: summary filter anchor missing")
html = html.replace(old_summary, new_summary, 1)

method_re = re.compile(r'<div class="methoditem"><strong>Precinct focus and summary</strong><br>.*?</div>', re.S)
mm = method_re.search(html)
if not mm:
    raise SystemExit("parcel focus fix: precinct methodology anchor missing")
new_method = '''<div class="methoditem"><strong>Precinct focus and summary</strong><br>Precinct selection is a display and aggregation tool only. It does not score, rank, or recommend precincts. <strong>Parcel display and parcel totals intentionally use different boundary rules:</strong> a high-unit parcel is shown when its parcel polygon has positive-area overlap with any selected precinct, so a parcel that physically crosses a precinct boundary is not hidden. For summary totals, each parcel is assigned to at most one precinct using a representative point guaranteed to lie inside the parcel, preventing double counting when several precincts are selected. If that representative point falls in a gap in the official precinct geometry, the parcel remains visible by polygon overlap but is omitted from the precinct total rather than assigned arbitrarily. Street and closure features are in focus when their line geometry has non-zero-length overlap with a selected precinct. Permit and dispatch markers use their public point coordinate. DataSF dispatch locations are privacy-masked, so precinct-sized dispatch totals are approximate map context rather than exact incident statistics. Summary hill values are counts of source street <em>segments intersecting the selection</em>, not miles of roadway.</div>'''
html = html[:mm.start()] + new_method + html[mm.end():]

# Make the selected-area note explicit about the unique summary rule and rare gap.
old_note = "Housing totals use one representative-point precinct assignment per parcel to avoid double counting."
new_note = "Housing map display uses parcel-polygon overlap; totals use one representative-point precinct assignment per parcel to avoid double counting, with any official-geometry-gap assignment omitted rather than guessed."
if old_note not in html:
    raise SystemExit("parcel focus fix: summary note anchor missing")
html = html.replace(old_note, new_note, 1)

# Repack after adding polygon-overlap memberships. Recompute the payload match
# after all preceding HTML edits so replacement offsets cannot become stale.
packed = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
m2 = re.search(r"window\.SF_FIELD_DATA=(\{.*?\});\s*</script>", html, re.S)
if not m2:
    raise SystemExit("parcel focus fix: embedded payload missing before final repack")
html = html[:m2.start(1)] + packed + html[m2.end(1):]
SITE.write_text(html, encoding="utf-8")

manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
pw = manifest.setdefault("precinct_workspace", {})
pw["parcel_display_assignment"] = "display parcel in every selected precinct with positive-area intersection of official parcel and precinct polygons"
pw["parcel_summary_assignment"] = "count parcel in at most one precinct using polygon representative point; leave unassigned if that point is not covered by official precinct geometry"
pw["parcel_display_unassigned_count"] = display_missing
pw["parcel_summary_unassigned_count"] = summary_missing
pw["parcel_multi_precinct_display_count"] = multi_precinct
manifest["parcel_focus_semantics"] = {
    "version": 1,
    "display_rule": pw["parcel_display_assignment"],
    "summary_rule": pw["parcel_summary_assignment"],
    "display_unassigned": display_missing,
    "summary_unassigned": summary_missing,
    "multi_precinct_display": multi_precinct,
}
# Record actual payload bytes after this final semantic annotation as well.
fh = manifest.setdefault("field_ux_hardening", {})
fh["final_payload_bytes_after_parcel_focus"] = len(packed.encode("utf-8"))
MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

print(
    f"parcel focus semantics: parcels={len(parcels)}; display_unassigned={display_missing}; "
    f"summary_unassigned={summary_missing}; multi_precinct_display={multi_precinct}"
)
