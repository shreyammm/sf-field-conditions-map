#!/usr/bin/env python3
"""Make closure summaries and housing concentration easier to understand.

This runs after the final turf usability pass so it patches the exact deployable
HTML. It does not alter source data or geometry; it only improves visual
separation and summary semantics.
"""
from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = ROOT / "_site" / "index.html"
MANIFEST = ROOT / "_site" / "data-manifest.json"
html = SITE.read_text(encoding="utf-8")


def rep(old: str, new: str, label: str, count: int = 1):
    global html
    if old not in html:
        raise SystemExit(f"closure/housing clarity anchor missing: {label}")
    html = html.replace(old, new, count)


# Temporary closures previously used almost the same blue as selected precinct
# boundaries. Use a distinct temporary/disruption treatment instead.
rep(
    ".cl{fill:none;stroke:#2563eb;stroke-width:3.2;vector-effect:non-scaling-stroke;pointer-events:stroke;cursor:pointer;stroke-linecap:round;paint-order:stroke;filter:drop-shadow(0 0 1px rgba(255,255,255,.95))}.cl:hover{stroke:#1d4ed8;stroke-width:4.5}",
    ".cl{fill:none;stroke:#c11574;stroke-width:4;stroke-dasharray:8 4;vector-effect:non-scaling-stroke;pointer-events:stroke;cursor:pointer;stroke-linecap:round;paint-order:stroke;filter:drop-shadow(0 0 1.8px rgba(255,255,255,1))}.cl:hover{stroke:#851651;stroke-width:5.4}",
    "closure visual styling",
)
rep(
    '<div class="legend"><span class="ln" style="border-top:3px solid #2563eb"></span><span class="legendtext">SFMTA-permitted temporary closure scheduled on selected date</span><span class="info" title="Shown when the official closure interval overlaps any part of the selected San Francisco calendar day. Click for exact hours. It does not necessarily mean pedestrian access is blocked.">ⓘ</span></div>',
    '<div class="legend"><span class="ln" style="border-top:4px dashed #c11574"></span><span class="legendtext">SFMTA-permitted temporary closure scheduled on selected date</span><span class="info" title="Magenta dashed line = official source closure geometry whose interval overlaps any part of the selected San Francisco calendar day. Click for exact source hours. It does not necessarily mean pedestrian access is blocked.">ⓘ</span></div>',
    "closure legend",
)

# Housing is not true areal density. Make the unit-on-parcel encoding explicit.
rep("High-unit residential parcels", "Housing concentration by parcel", "housing layer title")
rep("SF Planning · parcel-level records only", "Color = residential units associated with one property lot", "housing layer subtitle")
rep("Minimum units on one parcel", "Show parcels with at least", "housing threshold label")
rep(
    "Unit count is a proxy for concentrated doors/shared-entry friction. It does not establish whether a building is actually accessible to canvassers.",
    "<strong>Darker color = more residential units associated with that parcel.</strong> A parcel is the property-lot boundary, not the building footprint. This is housing concentration, not units per acre, and it does not establish entrance/access.",
    "housing explanation",
)
rep("Parcel with 20–49 residential units", "20–49 residential units on this parcel", "housing legend 20")
rep("Parcel with 50–99 residential units", "50–99 residential units on this parcel", "housing legend 50")
rep("Parcel with 100–199 residential units", "100–199 residential units on this parcel", "housing legend 100")
rep("Parcel with 200+ residential units", "200+ residential units on this parcel", "housing legend 200")

css = r'''
/* closure + housing clarity */
.densitybreak{margin-top:5px;font-size:9.8px;line-height:1.35;color:#475467}.densitybreak strong{font-size:9.8px;color:#344054}.closureSummary{margin-top:8px;border:1px solid #f0abcf;border-radius:7px;background:#fff7fb;padding:7px 8px}.closureSummary summary{cursor:pointer;font-size:10.8px;font-weight:700;color:#851651}.closureitem{padding:7px 0;border-top:1px solid #fce7f3;font-size:10.5px;line-height:1.35;color:#475467}.closureitem:first-of-type{margin-top:6px}.closureitem b{color:#344054}.closurekey{display:inline-block;width:14px;border-top:3px dashed #c11574;margin-right:5px;vertical-align:middle}.closureSummary .muted{font-size:9.8px}.housinglegendhead{margin:8px 0 5px;font-size:10.5px;font-weight:700;color:#344054}.housinglegendhead span{font-weight:400;color:#667085}
'''
rep("</style>", css + "</style>", "clarity CSS")

# Add a small explanatory label immediately before the parcel color ramp.
parcel_legend_anchor = '<div class="legend"><span class="sw" style="background:#a7f3d0"></span><span class="legendtext">20–49 residential units on this parcel</span></div>'
rep(
    parcel_legend_anchor,
    '<div class="housinglegendhead">Housing concentration <span>· lighter → darker = more units on one parcel</span></div>' + parcel_legend_anchor,
    "housing legend heading",
)

# Wrap the final selected-area summary. Keep the underlying source-record count,
# but group repeated closure records by source location description for the
# human-facing headline and show the exact source-record count underneath.
init_call = "init();loadFocusFromUrl();"
js = r'''
// ----- closure + housing clarity -----
function selectedHousingSummary(){
  const ps=(S.m?.features||[]).filter(f=>PFOCUS.has(String((f.properties||{}).focus_precinct||''))&&Number(units(f.properties||{}))>=S.n);
  const buckets={'20–49':0,'50–99':0,'100–199':0,'200+':0};let total=0;
  for(const f of ps){const u=Number(units(f.properties||{})||0);total+=u;if(u>=200)buckets['200+']++;else if(u>=100)buckets['100–199']++;else if(u>=50)buckets['50–99']++;else buckets['20–49']++}
  return{parcels:ps.length,total,buckets};
}
function closureLocationLabel(p){
  const s=String(p.loc_desc||'').trim();if(s)return s;
  const bits=[p.street,p.from_st&&('from '+p.from_st),p.to_st&&('to '+p.to_st)].filter(Boolean);return bits.join(' ')||'Mapped closure corridor';
}
function closureGroupsForSelection(){
  const q=dateOnly(S.ct);if(!q||!PFOCUS.size)return{records:[],groups:[]};
  const records=(S.c?.features||[]).filter(f=>inFocus(f,'c')&&closureActive(f,q));
  const map=new Map();
  for(const f of records){
    const p=f.properties||{},label=closureLocationLabel(p),key=label.toUpperCase().replace(/\s+/g,' ').trim();
    let g=map.get(key);if(!g){g={label,records:0,cases:new Set(),types:new Set(),impacts:new Set(),ranges:new Set()};map.set(key,g)}
    g.records++;if(p.case_num)g.cases.add(String(p.case_num));if(p.type)g.types.add(String(p.type));if(p.veh_imp)g.impacts.add(String(p.veh_imp));
    const a=String(p.start_local||'').slice(0,10),b=String(p.end_local||'').slice(0,10);if(a||b)g.ranges.add(a+'|'+b);
  }
  return{records,groups:[...map.values()].sort((a,b)=>a.label.localeCompare(b.label))};
}
function friendlyImpact(v){return String(v||'').replace(/-/g,' ').replace(/\s+/g,' ').trim()}
function friendlyRange(v){const [a,b]=String(v||'').split('|');if(!a&&!b)return'';if(a===b)return fmtDateOnly(a);return `${a?fmtDateOnly(a):'unknown'} – ${b?fmtDateOnly(b):'unknown'}`}
const _renderFocusSummaryBeforeClarity=renderFocusSummary;
renderFocusSummary=function(){
  _renderFocusSummaryBeforeClarity();if(!PFOCUS.size)return;
  const box=$('focusSummary'),metrics=box?.querySelectorAll('.summetric')||[];
  const h=selectedHousingSummary();
  if(metrics.length){
    const shown=Object.entries(h.buckets).filter(([label,n])=>n&&Number(label.split(/[–+]/)[0])>=Math.min(20,Number(S.n))).map(([label,n])=>`<strong>${n}</strong> × ${label}`).join(' · ');
    metrics[0].innerHTML=`<b>${h.total.toLocaleString()} units</b><span>on ${h.parcels.toLocaleString()} uniquely counted ${Number(S.n)}+ unit parcel${h.parcels===1?'':'s'}</span>${shown?`<div class="densitybreak">${shown}</div>`:''}`;
  }
  const q=dateOnly(S.ct),cg=closureGroupsForSelection();
  if(metrics.length>=3){
    metrics[2].innerHTML=q?`<b>${cg.groups.length.toLocaleString()}</b><span>mapped closure corridor${cg.groups.length===1?'':'s'} · ${cg.records.length.toLocaleString()} official source line record${cg.records.length===1?'':'s'}</span>`:'<b>—</b><span>choose a planning date</span>';
  }
  box?.querySelector('.closureSummary')?.remove();
  if(q&&cg.records.length){
    const d=document.createElement('details');d.className='closureSummary';
    const s=document.createElement('summary');s.innerHTML=`<span class="closurekey"></span>What are these closures? ${cg.groups.length} corridor${cg.groups.length===1?'':'s'} · ${cg.records.length} source record${cg.records.length===1?'':'s'}`;d.appendChild(s);
    cg.groups.slice(0,8).forEach(g=>{const row=document.createElement('div');row.className='closureitem';const ranges=[...g.ranges].map(friendlyRange).filter(Boolean),imp=[...g.impacts].map(friendlyImpact).filter(Boolean),types=[...g.types].filter(Boolean),caseN=g.cases.size;row.innerHTML=`<b>${esc(g.label)}</b>${imp.length?` · ${imp.map(esc).join(', ')}`:''}<br><span class="muted">${types.length?types.map(esc).join(', ')+' · ':''}${ranges.length?ranges.map(esc).join('; ')+' · ':''}${caseN?caseN+' source case'+(caseN===1?'':'s')+' · ':''}${g.records} map/source line record${g.records===1?'':'s'}</span>`;d.appendChild(row)});
    if(cg.groups.length>8){const more=document.createElement('div');more.className='closureitem muted';more.textContent=`+ ${cg.groups.length-8} more closure corridors`;d.appendChild(more)}
    const note=document.createElement('div');note.className='muted';note.style.marginTop='6px';note.textContent='Summary corridors are grouped by the source location description for readability. The map still draws every official source line geometry. Magenta dashed lines are closures; solid blue lines are selected precinct boundaries.';d.appendChild(note);box.appendChild(d);
  }
};
'''
rep(init_call, js + init_call, "clarity runtime")

SITE.write_text(html, encoding="utf-8")
manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
manifest["closure_housing_clarity"] = {
    "version": 1,
    "closure_visualization": "magenta dashed official source line geometry, intentionally distinct from solid-blue selected precinct boundaries",
    "closure_summary": "human-facing corridor count groups active selected-area source records by normalized source location description; exact source line-record count remains visible",
    "housing_summary": "headline is source residential units on uniquely assigned selected high-unit parcels, with parcel count and 20-49/50-99/100-199/200+ breakdown",
    "housing_interpretation": "unit count per parcel/property lot; not building footprint and not units per acre",
}
MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("closure/housing clarity applied: magenta dashed closures, grouped closure details, clearer housing concentration summary")
