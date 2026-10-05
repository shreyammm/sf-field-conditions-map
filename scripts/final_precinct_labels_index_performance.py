#!/usr/bin/env python3
"""Final turf-cutter clarity/performance pass.

Adds optional precinct labels, a transparent precinct reported-incident ranking
view, stronger Supervisor District colors, and runtime optimizations that reduce
unnecessary DOM/render work without changing source geometry or summary math.
"""
from __future__ import annotations

import json
import pathlib
import re

from shapely.geometry import shape

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = ROOT / "_site" / "index.html"
MANIFEST = ROOT / "_site" / "data-manifest.json"


def replace_one(s: str, old: str, new: str, label: str) -> str:
    if old not in s:
        raise ValueError(f"Final labels/index/performance anchor missing: {label}")
    return s.replace(old, new, 1)


def payload_match(html: str):
    m = re.search(r"window\.SF_FIELD_DATA=(\{.*?\});\s*</script>", html, re.S)
    if not m:
        raise ValueError("Embedded payload not found")
    return m, json.loads(m.group(1))


def precinct_id(f):
    p = f.get("properties") or {}
    return str(p.get("prec_2022") or p.get("precinct") or p.get("id") or "").strip()


def main():
    html = SITE.read_text(encoding="utf-8")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    m, payload = payload_match(html)

    # Representative points are guaranteed to lie inside each precinct polygon,
    # unlike a simple centroid which can land outside a concave polygon.
    label_points = {}
    for f in (payload.get("precincts") or {}).get("features") or []:
        pid = precinct_id(f)
        g = shape(f.get("geometry"))
        if not pid or g.is_empty or not g.is_valid:
            raise ValueError(f"Cannot build precinct label point: {pid!r}")
        p = g.representative_point()
        label_points[pid] = [p.x, p.y]
    if not 400 <= len(label_points) <= 800:
        raise ValueError(f"Unexpected precinct label count: {len(label_points)}")
    payload["precinct_label_points"] = label_points

    # Replace payload before changing HTML length so byte offsets stay valid.
    packed = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = html[:m.start(1)] + packed + html[m.end(1):]

    # Fix a real UI bug: the parcel-threshold handler previously cleared the
    # visual active state on unrelated dispatch/history pills because it used a
    # document-wide .pill selector.
    html = replace_one(
        html,
        "document.querySelectorAll('.pill').forEach(x=>x.classList.toggle('active',x===b));renderM()",
        "document.querySelectorAll('#pills .pill').forEach(x=>x.classList.toggle('active',x===b));renderM()",
        "scoped parcel threshold pills",
    )

    # Stronger categorical Supervisor District palette. It remains a low-opacity
    # background and never encodes rank or any operational score.
    old_palette = "const DISTRICT_COLORS={1:'#8dd3c7',2:'#ffffb3',3:'#bebada',4:'#fb8072',5:'#80b1d3',6:'#fdb462',7:'#b3de69',8:'#fccde5',9:'#d9d9d9',10:'#bc80bd',11:'#ccebc5'};"
    new_palette = "const DISTRICT_COLORS={1:'#4E79A7',2:'#F28E2B',3:'#E15759',4:'#76B7B2',5:'#59A14F',6:'#EDC948',7:'#B07AA1',8:'#FF9DA7',9:'#9C755F',10:'#7F8C8D',11:'#17BECF'};"
    html = replace_one(html, old_palette, new_palette, "district palette")
    html = replace_one(
        html,
        ".distfill{stroke:#667085;stroke-opacity:.72;stroke-width:1.15;fill-opacity:.13;",
        ".distfill{stroke:#344054;stroke-opacity:.82;stroke-width:1.25;fill-opacity:.19;",
        "district base opacity",
    )
    html = replace_one(
        html,
        ".distfill.focus-district{fill-opacity:.18;stroke-opacity:.9}",
        ".distfill.focus-district{fill-opacity:.27;stroke-opacity:.98}",
        "district focus opacity",
    )
    old_swatches = "#8dd3c7 0 9%,#ffffb3 9% 18%,#bebada 18% 27%,#fb8072 27% 36%,#80b1d3 36% 45%,#fdb462 45% 54%,#b3de69 54% 63%,#fccde5 63% 72%,#d9d9d9 72% 81%,#bc80bd 81% 90%,#ccebc5 90%"
    new_swatches = "#4E79A7 0 9%,#F28E2B 9% 18%,#E15759 18% 27%,#76B7B2 27% 36%,#59A14F 36% 45%,#EDC948 45% 54%,#B07AA1 54% 63%,#FF9DA7 63% 72%,#9C755F 72% 81%,#7F8C8D 81% 90%,#17BECF 90%"
    html = html.replace(old_swatches, new_swatches)
    for old, new in zip(
        ['#8dd3c7','#ffffb3','#bebada','#fb8072','#80b1d3','#fdb462','#b3de69','#fccde5','#d9d9d9','#bc80bd','#ccebc5'],
        ['#4E79A7','#F28E2B','#E15759','#76B7B2','#59A14F','#EDC948','#B07AA1','#FF9DA7','#9C755F','#7F8C8D','#17BECF'],
    ):
        # Replace the 11 small key swatches only after the JS palette has already
        # been replaced, so this does not create duplicate const declarations.
        html = html.replace(f'background:{old}', f'background:{new}', 1)

    css = r'''
/* precinct labels + incident ranking + final performance polish */
.preclabel{font:700 10.5px system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;fill:#263238;stroke:#fff;stroke-width:3;paint-order:stroke fill;stroke-linejoin:round;pointer-events:none;text-anchor:middle;dominant-baseline:central;letter-spacing:.1px}.preclabel.selected{fill:#123b75;font-weight:800}.labelhint,.parcelperfhint{margin-top:5px;font-size:10px;line-height:1.35;color:#667085}.incidentRank{margin-top:8px;border:1px solid #d0d5dd;border-radius:8px;background:#fff}.incidentRank>summary{cursor:pointer;padding:8px 9px;font-size:11.5px;font-weight:700;color:#344054}.incidentRankBody{padding:0 9px 9px}.incidentRankExplain{font-size:10.5px;line-height:1.4;color:#667085;margin-bottom:7px}.incidentRankFilter{width:100%;box-sizing:border-box;border:1px solid #d0d5dd;border-radius:6px;padding:6px 7px;font:inherit;font-size:11px;margin-bottom:6px}.incidentRankScroll{max-height:260px;overflow:auto;border:1px solid #eaecf0;border-radius:6px}.incidentRankTable{width:100%;border-collapse:collapse;font-size:10px}.incidentRankTable th,.incidentRankTable td{padding:5px 6px;border-bottom:1px solid #f2f4f7;text-align:right;white-space:nowrap}.incidentRankTable th{position:sticky;top:0;background:#f9fafb;color:#475467;z-index:1}.incidentRankTable th:nth-child(2),.incidentRankTable td:nth-child(2){text-align:left}.incidentRankTable tr.focusrowrank{background:#eff8ff}.incidentIndexSummary{margin:0 0 8px;padding:7px 8px;border:1px solid #d1e9ff;border-radius:7px;background:#f5fbff;font-size:10.5px;line-height:1.4;color:#344054}.incidentIndexSummary b{color:#175cd3}.indexBadge{display:inline-block;min-width:31px;text-align:center;border-radius:999px;padding:1px 5px;background:#eaf2ff;color:#1849a9;font-weight:750}.perfnotice{font-size:10px;color:#667085;margin-top:5px}
'''
    html = replace_one(html, "</style>", css + "</style>", "style end")

    precinct_row = '<div class="row"><div><div class="label">Precinct boundaries</div><div class="muted">Reference only · SF Department of Elections</div></div><label class="switch"><input id="pToggle" type="checkbox" checked><span></span></label></div>'
    precinct_rows = precinct_row + '\n<div class="row"><div><div class="label">Precinct labels</div><div class="muted">Optional precinct IDs · representative point inside each official polygon</div><div id="precLabelHint" class="labelhint"></div></div><label class="switch"><input id="precLabelToggle" type="checkbox"><span></span></label></div>'
    html = replace_one(html, precinct_row, precinct_rows, "precinct label control")

    access_row = '<div class="row"><div><div class="label">Shared-entry access screen</div><div class="muted">SF Planning parcel unit count · access is not confirmed · snapshot '
    ai = html.find(access_row)
    if ai < 0:
        raise ValueError("Shared-entry access row not found")
    row_end = html.find('</div>\n<div class="label" style="margin:12px 0 7px">', ai)
    if row_end < 0:
        raise ValueError("Shared-entry access row end not found")
    row_end += len('</div>')
    parcel_hint = '<div id="parcelPerfHint" class="parcelperfhint">At whole-city zoom, individual parcel shapes are deferred for speed. Zoom in or select precincts to draw them.</div>'
    html = html[:row_end] + parcel_hint + html[row_end:]

    hist_hint = '<div id="histDrawHint" class="muted" aria-live="polite" style="margin-top:6px">At the citywide view, zoom in or select precincts to draw individual reported-incident intersections.</div>'
    rank_ui = hist_hint + r'''
<details id="incidentRankDetails" class="incidentRank"><summary>Precinct reported-incident context ranking</summary><div class="incidentRankBody"><div class="incidentRankExplain"><strong>Index 0–100:</strong> citywide rank of severity-weighted mapped incident reports per 30 days for the selected historical window. Higher = more weighted report activity in this dataset, <strong>not</strong> a probability of harm or a neighborhood safety score. Product-defined weights: tier 4 serious/direct violence, tier 3 other violence/weapons/fire/sexual offenses, tier 2 burglary/vehicle theft, tier 1 selected property/other offenses. Ambiguous, administrative and non-criminal categories are excluded rather than guessed.</div><input id="incidentRankFilter" class="incidentRankFilter" type="search" inputmode="numeric" autocomplete="off" placeholder="Filter precinct ID"><div id="incidentRankBody" class="incidentRankScroll"><div class="muted" style="padding:8px">Open this section to build the ranking table.</div></div></div></details>'''
    html = replace_one(html, hist_hint, rank_ui, "incident ranking UI")

    html = replace_one(html, '<g id="cl"></g><g id="ll"></g>', '<g id="cl"></g><g id="pnl"></g><g id="ll"></g>', "precinct label SVG group")

    # Add methodology immediately after the existing reported-incident methodology.
    method_anchor = '<div class="methoditem"><strong>Reported incident history</strong><br>'
    mi = html.find(method_anchor)
    if mi < 0:
        raise ValueError("Reported incident methodology not found")
    mend = html.find('</div>', mi)
    if mend < 0:
        raise ValueError("Reported incident methodology end not found")
    mend += len('</div>')
    index_method = '''<div class="methoditem"><strong>Precinct reported-incident context index</strong><br>Uses the same SFPD/DataSF incident-report dataset <span class="code">wg3w-h783</span>. Each <span class="code">incident_id</span> is counted once. If an incident has multiple incident-code rows, the index uses the highest product-defined severity tier represented by those rows. The four tiers are documented in the ranking panel and build manifest; categories that are ambiguous, administrative, non-criminal, or not explicitly mapped are excluded rather than assigned a guessed severity. For each 30/90/180/365-day window, weighted report load is normalized to 30 days and ranked across current election precincts to create a 0–100 relative index. Because SFPD public coordinates are privacy-mapped to nearby intersections, a public point that falls on more than one precinct is split equally across the covering precincts rather than arbitrarily assigned. This is an approximate operational context index, <strong>not</strong> an SFPD severity measure, confirmed-crime rate, or neighborhood/canvasser safety probability.</div>'''
    html = html[:mend] + index_method + html[mend:]

    init_call = 'init();loadFocusFromUrl();'
    js = r'''
// ----- precinct labels + incident context ranking + performance hardening -----
const pnl=$('pnl');
S.spl=false;
const PINDEX=new Map((DATA.precinct_incident_index?.precincts||[]).map(r=>[String(r.precinct),r]));
function incidentWindowRecord(pid){return PINDEX.get(String(pid))?.windows?.[String(S.hdays)]||null}
function precinctLabelPoint(pid){return DATA.precinct_label_points?.[String(pid)]||null}
let PREC_LABEL_SIG='';
function renderPrecinctLabels(){
  const hint=$('precLabelHint');
  const sig=[S.spl,S.z.toFixed(3),S.x.toFixed(1),S.y.toFixed(1),[...PFOCUS].sort().join(',')].join('|');
  if(sig===PREC_LABEL_SIG)return;PREC_LABEL_SIG=sig;pnl.replaceChildren();
  if(!S.spl){pnl.style.display='none';if(hint)hint.textContent='';return}
  pnl.style.display='';
  if(!PFOCUS.size&&S.z<1.3){if(hint)hint.textContent='Zoom in to 1.3× or select precincts to show labels without crowding.';return}
  if(hint)hint.textContent=PFOCUS.size?'Showing labels for selected precincts.':'Labels are automatically de-cluttered at this zoom.';
  const ids=PFOCUS.size?[...PFOCUS].sort():[...PINDEX.keys()].sort();
  const used=new Set(),cell=46,margin=24;
  for(const pid of ids){
    const c=precinctLabelPoint(pid);if(!Array.isArray(c)||c.length<2)continue;const q=proj(c),sx=q[0]*S.z+S.x,sy=q[1]*S.z+S.y;
    if(sx<-margin||sx>W+margin||sy<-margin||sy>H+margin)continue;
    if(!PFOCUS.size){const key=Math.floor(sx/cell)+','+Math.floor(sy/cell);if(used.has(key))continue;used.add(key)}
    const t=document.createElementNS('http://www.w3.org/2000/svg','text');t.setAttribute('x',q[0]);t.setAttribute('y',q[1]);t.setAttribute('font-size',String(10.5/S.z));t.setAttribute('stroke-width',String(3/S.z));t.setAttribute('class','preclabel'+(PFOCUS.has(pid)?' selected':''));t.textContent=pid;pnl.appendChild(t);
  }
}
$('precLabelToggle').onchange=e=>{S.spl=e.target.checked;PREC_LABEL_SIG='';renderPrecinctLabels()};

function rankRows(){return (DATA.precinct_incident_index?.precincts||[]).map(r=>({pid:String(r.precinct),w:r.windows?.[String(S.hdays)]||{}})).sort((a,b)=>Number(a.w.rank||9999)-Number(b.w.rank||9999)||a.pid.localeCompare(b.pid))}
function renderIncidentRanking(){
  const details=$('incidentRankDetails'),body=$('incidentRankBody');if(!details||!body||!details.open)return;
  const q=String($('incidentRankFilter')?.value||'').trim(),rows=rankRows().filter(r=>!q||r.pid.includes(q)),frag=document.createDocumentFragment(),table=document.createElement('table');table.className='incidentRankTable';
  table.innerHTML='<thead><tr><th>Rank</th><th>Precinct</th><th>Index</th><th>Weighted /30d</th><th>Reports /30d</th></tr></thead>';const tb=document.createElement('tbody');
  for(const r of rows){const tr=document.createElement('tr');if(PFOCUS.has(r.pid))tr.className='focusrowrank';tr.innerHTML=`<td>${Number(r.w.rank||0).toLocaleString()}</td><td>${esc(r.pid)}</td><td><span class="indexBadge">${Number(r.w.index||0).toFixed(0)}</span></td><td>${Number(r.w.weighted_per30||0).toFixed(1)}</td><td>${Number(r.w.reports_per30||0).toFixed(1)}</td>`;tb.appendChild(tr)}
  table.appendChild(tb);frag.appendChild(table);body.replaceChildren(frag);
}
$('incidentRankDetails').addEventListener('toggle',renderIncidentRanking);$('incidentRankFilter').addEventListener('input',renderIncidentRanking);
function updateIncidentIndexSummary(){
  const box=$('focusSummary');box?.querySelector('.incidentIndexSummary')?.remove();if(!box||!PFOCUS.size)return;
  const rows=[...PFOCUS].map(pid=>({pid,w:incidentWindowRecord(pid)})).filter(x=>x.w).sort((a,b)=>Number(a.w.rank)-Number(b.w.rank)||a.pid.localeCompare(b.pid));if(!rows.length)return;
  const d=document.createElement('div');d.className='incidentIndexSummary';const shown=rows.slice(0,8).map(r=>`P${esc(r.pid)} <span class="indexBadge">${Number(r.w.index).toFixed(0)}</span> (#${Number(r.w.rank)})`).join(' · '),more=rows.length>8?` · +${rows.length-8} more`:'';
  d.innerHTML=`<b>Reported-incident context · ${S.hdays===30?'1 mo':S.hdays===90?'3 mo':S.hdays===180?'6 mo':'1 yr'}:</b> ${shown}${more}<br><span style="color:#667085">Index ranks severity-weighted mapped reports; it is not a safety probability. Public locations are privacy-mapped, so precinct attribution is approximate.</span>`;
  const sd=box.querySelector('.summarydistrict'),head=box.querySelector('.summaryhead');if(sd)sd.insertAdjacentElement('afterend',d);else if(head)head.insertAdjacentElement('afterend',d);else box.prepend(d);
}
const _renderFocusSummaryFinal=renderFocusSummary;
renderFocusSummary=function(){_renderFocusSummaryFinal();updateIncidentIndexSummary();renderPrecinctLabels();renderIncidentRanking()};

// Keep parcel geometry interactive where turf cutters need it, but avoid making
// 2,000+ SVG parcel nodes at the whole-city starting view.
const PARCEL_DETAIL_ZOOM=1.75;
const _renderMFinalDetail=renderM;
function parcelDetailNeeded(){return !!PFOCUS.size||S.z>=PARCEL_DETAIL_ZOOM}
renderM=function(){
  const hint=$('parcelPerfHint');
  if(!parcelDetailNeeded()){
    ml.replaceChildren();ml.style.display='none';const n=(S.m?.features||[]).filter(f=>Number(units(f.properties||{}))>=S.n).length;$('ts').textContent=`${S.n}+ units · ${n.toLocaleString()} parcels available · zoom/select to draw`;if(hint)hint.style.display=S.sm?'block':'none';return;
  }
  if(hint)hint.style.display='none';_renderMFinalDetail();
};

// Historical points are static for the build. Avoid rebuilding identical SVG
// circles when wrapper chains request the same render more than once.
const _renderHistoryBeforeCache=renderHistory;let HIST_RENDER_SIG='';
renderHistory=function(){const sig=[S.shi,S.hdays,S.z.toFixed(3),[...PFOCUS].sort().join(',')].join('|');if(sig===HIST_RENDER_SIG){updateHistorySummary();return}HIST_RENDER_SIG=sig;_renderHistoryBeforeCache()};

// Remove duplicate selected-area work: renderI already reapplies focus styles
// and refreshes the selected-area summary at the end of a focus-aware render.
renderFocusAware=function(){renderS();renderP();renderM();renderW();renderC();renderI()};

const _zoomFinal=zoom;
zoom=function(...args){const beforeParcel=parcelDetailNeeded();_zoomFinal(...args);if(beforeParcel!==parcelDetailNeeded())renderM();PREC_LABEL_SIG='';renderPrecinctLabels()};
const _fitFinal=fitSelected;fitSelected=function(){_fitFinal();PREC_LABEL_SIG='';renderPrecinctLabels();renderIncidentRanking()};
$('home').addEventListener('click',()=>{renderM();PREC_LABEL_SIG='';renderPrecinctLabels()});

// Wheel events arrive in bursts. Update the transform immediately, then rebuild
// expensive fixed-screen-size overlays once after the burst rather than on every
// wheel tick. Button zooms continue through the normal zoom() function above.
let wheelTimer=null,wheelStreetDetail=(!PFOCUS.size&&S.z>=STREET_DETAIL_ZOOM),wheelParcelDetail=parcelDetailNeeded();
svg.onwheel=ev=>{
  ev.preventDefault();const p=point(ev),f=ev.deltaY<0?1.18:1/1.18,nz=Math.max(1,Math.min(12,S.z*f)),q=nz/S.z;S.x=p.x-(p.x-S.x)*q;S.y=p.y-(p.y-S.y)*q;S.z=nz;apply();
  if(wheelTimer)clearTimeout(wheelTimer);wheelTimer=setTimeout(()=>{const sd=(!PFOCUS.size&&S.z>=STREET_DETAIL_ZOOM),pd=parcelDetailNeeded();if(sd!==wheelStreetDetail){renderS();wheelStreetDetail=sd}else renderLabels();if(pd!==wheelParcelDetail){renderM();wheelParcelDetail=pd}renderI();if(S.shi)renderHistory();PREC_LABEL_SIG='';renderPrecinctLabels()},85);
};

const _histPillsFinal=$('histPills').onclick;$('histPills').onclick=e=>{_histPillsFinal?.(e);renderIncidentRanking();renderFocusSummary()};
'''
    html = replace_one(html, init_call, js + init_call, "final runtime")

    manifest["final_map_hardening_v2"] = {
        "version": 2,
        "precinct_labels": "optional labels use Shapely representative points guaranteed inside each official precinct polygon; citywide labels are zoom-gated and screen-grid de-cluttered",
        "district_palette": "11 stronger categorical colors at 0.19 background opacity; color remains non-ordinal and can be disabled",
        "parcel_initial_rendering": "individual high-unit parcel SVG geometry is deferred below zoom 1.75 when no precinct focus is active; exact parcel geometry is rendered on zoom/focus",
        "historical_render_cache": "historical incident SVG points are not rebuilt when visibility/window/zoom/focus signature is unchanged",
        "wheel_rendering": "wheel transform updates immediately; expensive fixed-screen-size overlays are rebuilt once after an 85 ms wheel burst",
        "pill_scope_bugfix": "parcel threshold active-state update is scoped to #pills and no longer clears dispatch/history pill styling",
        "focus_rendering": "duplicate explicit focus-style/summary call removed because renderI already performs those final updates",
    }
    SITE.write_text(html, encoding="utf-8")
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"final labels/index/performance pass added: labels={len(label_points)}; parcel detail zoom=1.75; wheel debounce=85ms")


if __name__ == "__main__":
    main()
