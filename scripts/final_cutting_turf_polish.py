#!/usr/bin/env python3
"""Final low-risk usability pass for people cutting turf.

This intentionally changes presentation/interaction only. It does not alter
source records, spatial membership, layer counts, or any turf summary math.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = ROOT / "_site" / "index.html"
MANIFEST = ROOT / "_site" / "data-manifest.json"


def replace_one(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise ValueError(f"Final turf polish anchor missing: {label}")
    return text.replace(old, new, 1)


def friendly_date(value):
    s = str(value or "").strip()
    if not s:
        return "date not reported"
    try:
        d = dt.date.fromisoformat(s[:10])
        return f"{d.strftime('%b')} {d.day}, {d.year}"
    except ValueError:
        return s[:10]


def main():
    html = SITE.read_text(encoding="utf-8")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    parcel_date = friendly_date((manifest.get("multifamily") or {}).get("data_as_of"))

    # Make the precinct search an explicitly named form control for screen
    # readers while preserving the existing visual label and keyboard behavior.
    html = replace_one(
        html,
        '<input id="pSearch" type="text" inputmode="text" autocomplete="off" placeholder="e.g. 7101, 7102">',
        '<input id="pSearch" type="text" inputmode="text" autocomplete="off" aria-label="Precinct IDs" placeholder="e.g. 7101, 7102">',
        "precinct search accessibility label",
    )

    # Contours are much more interpretable to non-GIS users when the visual
    # meaning is stated directly at the toggle, not only in methodology.
    html = replace_one(
        html,
        'Official elevation contours · 25-ft display interval',
        'Official contours · closer lines = steeper terrain · 25-ft interval',
        "topography plain-language explanation",
    )

    # The access-screen layer is static-ish Planning data, unlike dispatches or
    # closures. Put its actual snapshot date where a turf cutter will see it,
    # while preserving the audited access-limitation wording verbatim.
    html = replace_one(
        html,
        'SF Planning parcel unit count · access is not confirmed',
        f'SF Planning parcel unit count · access is not confirmed · snapshot {parcel_date}',
        "parcel snapshot date",
    )

    # Historical points can mean thousands of SVG circles citywide. Keep the
    # layer truthful and legible by drawing individual public intersections only
    # after the user zooms in or focuses precincts. We deliberately do not invent
    # clusters/heatmaps because those would change the existing point semantics.
    hist_note = '<div id="histDrawHint" class="muted" aria-live="polite" style="margin-top:6px">At the citywide view, zoom in or select precincts to draw individual reported-incident intersections.</div>'
    anchor = '<div class="muted" style="margin-top:6px">Fixed-size circles. Darker color = more unique incident reports per 30 days at that public privacy-mapped intersection. This is report volume, not severity, and not every report establishes a crime.</div>'
    html = replace_one(html, anchor, anchor + hist_note, "historical draw hint")

    init_call = 'init();loadFocusFromUrl();'
    js = r'''
// ----- final turf-cutting clarity/performance polish -----
const HIST_DETAIL_ZOOM=2.2;
const _renderHistoryTurfPolish=renderHistory;
renderHistory=function(){
  const hint=$('histDrawHint');
  const defer=!!(S.shi&&!PFOCUS.size&&S.z<HIST_DETAIL_ZOOM);
  if(hint){
    hint.style.display=S.shi&&defer?'block':'none';
    hint.textContent=defer?'Zoom in or select precincts to draw individual reported-incident intersections.':'';
  }
  if(defer){
    hil.replaceChildren();
    hil.style.display='none';
    updateHistorySummary();
    return;
  }
  _renderHistoryTurfPolish();
};
'''
    html = replace_one(html, init_call, js + init_call, "historical detail guard")

    manifest["final_turf_polish"] = {
        "version": 1,
        "historical_point_rendering": "individual historical public intersection points are deferred while no precinct is selected and zoom < 2.2; no clustering or heatmap inference is introduced",
        "parcel_snapshot_visible_in_controls": True,
        "topography_plain_language_cue": "closer contour lines = steeper terrain",
        "precinct_search_accessible_name": True,
    }

    SITE.write_text(html, encoding="utf-8")
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"final turf polish applied: parcel snapshot={parcel_date}; historical point detail zoom={2.2}")


if __name__ == "__main__":
    main()
