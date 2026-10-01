#!/usr/bin/env python3
"""Final turf-cutting usability pass over the exact deployable HTML.

Adds an explicit precinct-picking mode, avoids stale fallback dispatch counts in
selected-area summaries, and keeps the citywide street overview lightweight
until the user zooms in or selects precincts.
"""
from __future__ import annotations

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = ROOT / "_site" / "index.html"
MANIFEST = ROOT / "_site" / "data-manifest.json"
html = SITE.read_text(encoding="utf-8")


def rep(old: str, new: str, label: str, count: int = 1):
    global html
    if old not in html:
        raise SystemExit(f"turf usability anchor missing: {label}")
    html = html.replace(old, new, count)


# The real-time feed contains Police, Sheriff, MTA and other responding agencies;
# don't imply every agency in the feed is a law-enforcement agency.
html = html.replace(
    '<option value="ALL">All law-enforcement agencies</option>',
    '<option value="ALL">All agencies in this feed</option>',
    1,
)

# A clear map-selection mode makes precinct polygons easy to tap/click without
# permanently blocking interaction with streets, parcels, permits and calls.
focus_actions = '<div class="focusactions"><button id="pFit" type="button">Focus selected</button><button id="pClearFocus" type="button">Clear</button><button id="pShare" type="button">Copy link</button></div>'
focus_actions_new = '<div class="focusactions"><button id="pPick" type="button" aria-pressed="false">Select on map</button><button id="pFit" type="button">Focus selected</button><button id="pClearFocus" type="button">Clear</button><button id="pShare" type="button">Copy link</button></div>'
rep(focus_actions, focus_actions_new, "precinct pick button")

css = r'''
/* final turf usability */
.prec.prec-pick:not(.focus-selected){pointer-events:all;cursor:pointer;fill:rgba(23,92,211,.045)}
.prec.prec-pick:hover{pointer-events:all;fill:rgba(23,92,211,.15);stroke:#175cd3;stroke-width:2.3}
#pPick[aria-pressed="true"]{background:#175cd3;color:#fff;border-color:#175cd3}
.st-overview{pointer-events:none!important;cursor:default!important}
.summaryfreshwarn{margin-top:7px;padding:6px 7px;border:1px solid #fedf89;border-radius:6px;background:#fffaeb;color:#93370d;font-size:10.5px;line-height:1.35}
'''
rep("</style>", css + "</style>", "turf usability CSS")

# Insert wrappers immediately before the final init call. At this point all prior
# renderers/helpers exist, but the initial map has not been rendered yet.
init_call = "init();loadFocusFromUrl();"
js = r'''
// ----- final turf usability -----
let PRECINCT_PICK_MODE=false;
function applyPrecinctPickMode(){
  pl.querySelectorAll('[data-k="p"]').forEach(e=>e.classList.toggle('prec-pick',PRECINCT_PICK_MODE));
  const b=$('pPick');
  if(b){b.setAttribute('aria-pressed',PRECINCT_PICK_MODE?'true':'false');b.textContent=PRECINCT_PICK_MODE?'Done selecting':'Select on map'}
}
const _renderPBeforeTurfPick=renderP;
renderP=function(){_renderPBeforeTurfPick();applyPrecinctPickMode()};
$('pPick').onclick=()=>{
  PRECINCT_PICK_MODE=!PRECINCT_PICK_MODE;
  if(PRECINCT_PICK_MODE){
    S.sp=true;$('pToggle').checked=true;pl.style.display='';
    $('pSearchMsg').textContent='Map selection on: click or tap anywhere inside precincts to add/remove them. Choose “Done selecting” when finished.';
  }else{
    $('pSearchMsg').textContent='Paste one or several precinct IDs separated by commas or spaces, or use Select on map.';
  }
  applyPrecinctPickMode();
};

// Do not present an old embedded fallback as a meaningful zero in the selected
// area. The optional live layer remains opt-in; enabling/refreshing it replaces
// the fallback with the current official API response.
const _renderFocusSummaryBeforeFreshness=renderFocusSummary;
renderFocusSummary=function(){
  _renderFocusSummaryBeforeFreshness();
  if(!PFOCUS.size)return;
  const mins=liveFreshness(),fresh=Number.isFinite(mins)&&mins<=45;
  if(fresh)return;
  const box=$('focusSummary'),metrics=box?.querySelectorAll('.summetric')||[];
  if(metrics.length>=6){
    metrics[4].innerHTML='<b>—</b><span>live dispatch data not current · turn on/refresh the dispatch layer</span>';
    metrics[5].innerHTML='<b>—</b><span>priority breakdown available after a current live refresh</span>';
  }
  if(box&&!box.querySelector('.summaryfreshwarn')){
    const w=document.createElement('div');w.className='summaryfreshwarn';
    w.textContent='Recent dispatch summary is withheld because the embedded fallback is stale. Enable the dispatch layer to request the current official feed.';
    box.appendChild(w);
  }
};

// At the whole-city starting view, thousands of individual SVG street nodes add
// cost without adding usable click precision. Preserve the exact same geometry
// and visual classes in a small set of compound, non-interactive paths. Restore
// individual street features once the user zooms in or enters precinct focus.
const STREET_DETAIL_ZOOM=2.4;
const _renderSBeforeOverview=renderS;
function renderStreetOverview(){
  sl.replaceChildren();
  const groups=new Map();
  for(const f of S.s?.features||[]){
    const p=f.properties||{},c=streetClass(p),d=linePath(f.geometry);if(!d)continue;
    const hc=(S.sh&&c!==1&&c!==6&&typeof hillClass==='function')?hillClass(p):'';
    const key=String(c)+'|'+hc;
    let a=groups.get(key);if(!a){a={c,hc,parts:[]};groups.set(key,a)}a.parts.push(d);
  }
  for(const a of groups.values()){
    const e=document.createElementNS('http://www.w3.org/2000/svg','path');
    e.setAttribute('d',a.parts.join(' '));
    e.setAttribute('class','st st-overview sc'+a.c+(a.hc?' '+a.hc:''));
    e.setAttribute('aria-hidden','true');sl.appendChild(e);
  }
  sl.style.display=(S.ss||S.sh)?'':'none';LABEL_CANDIDATES=null;renderLabels();
}
renderS=function(){
  if(!PFOCUS.size&&S.z<STREET_DETAIL_ZOOM){renderStreetOverview();return}
  _renderSBeforeOverview();
};
const _zoomBeforeOverview=zoom;
zoom=function(...args){
  const before=!PFOCUS.size&&S.z<STREET_DETAIL_ZOOM;
  _zoomBeforeOverview(...args);
  const after=!PFOCUS.size&&S.z<STREET_DETAIL_ZOOM;
  if(before!==after)renderS();
};
const _homeBeforeOverview=$('home').onclick;
$('home').onclick=()=>{_homeBeforeOverview?.();renderS();applyFocusStyles();applyPrecinctPickMode()};

'''
rep(init_call, js + init_call, "final turf JS")

SITE.write_text(html, encoding="utf-8")
manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
manifest["turf_usability_hardening"] = {
    "version": 1,
    "precinct_map_selection": "explicit temporary pick mode makes polygon interiors clickable without permanently intercepting other map features",
    "dispatch_summary_freshness": "selected-area dispatch metrics are withheld when data age exceeds 45 minutes; user is prompted to enable/refresh the optional live layer",
    "citywide_street_rendering": "below zoom 2.4 and without precinct focus, exact street geometries are combined into non-interactive compound SVG paths by source/derived visual class; detailed feature nodes return on zoom/focus",
    "agency_label": "ALL means all responding agencies represented in the official feed, not only police/law-enforcement agencies",
}
MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("final turf usability applied: map-pick mode, stale-live guard, lightweight citywide street overview")
