#!/usr/bin/env python3
"""Replace the visible historical-point UI with a 365-day precinct frequency overlay.

The source remains SFPD/DataSF wg3w-h783 and the already-audited build-time
historical snapshot. Each incident_id was deduplicated upstream before counts
were aggregated at privacy-mapped public points. This pass sums only points
covered by exactly one current election precinct, then places precincts into
five raw-count quintile bands. It does not weight severity and does not
normalize for population, area, street miles, or foot traffic.

Supervisor Districts are shown as thick colored boundary outlines. Incident frequency is a user-controlled precinct highlight filter, not a full-map background.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = ROOT / "_site" / "index.html"
MANIFEST = ROOT / "_site" / "data-manifest.json"
DATASET_ID = "wg3w-h783"


def payload_match(html: str):
    m = re.search(r"window\.SF_FIELD_DATA=(\{.*?\});\s*</script>", html, re.S)
    if not m:
        raise ValueError("Embedded payload not found")
    return m, json.loads(m.group(1))


def precinct_id(feature):
    p = feature.get("properties") or {}
    return str(p.get("prec_2022") or p.get("precinct") or p.get("id") or "").strip()


def nearest_rank_cut(values, q: float) -> int:
    xs = sorted(int(x) for x in values)
    i = max(0, min(len(xs) - 1, math.ceil(q * len(xs)) - 1))
    return xs[i]


def band(value: int, cuts: list[int]) -> int:
    if value <= cuts[0]:
        return 1
    if value <= cuts[1]:
        return 2
    if value <= cuts[2]:
        return 3
    if value <= cuts[3]:
        return 4
    return 5


def competition_ranks(values: dict[str, int]) -> dict[str, int]:
    ordered = sorted(values.items(), key=lambda kv: (-kv[1], kv[0]))
    out = {}
    previous = None
    rank = 0
    for pos, (pid, value) in enumerate(ordered, 1):
        if previous is None or value != previous:
            rank = pos
            previous = value
        out[pid] = rank
    return out


def friendly_source_date(v) -> str:
    s = str(v or "").strip()
    if not s:
        return "source update unavailable"
    try:
        x = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        return f"source updated {x.strftime('%b')} {x.day}, {x.year}"
    except Exception:
        return f"source updated {s[:10]}"


def remove_method_item(html: str, title: str) -> str:
    pat = re.compile(
        rf'<div class="methoditem"><strong>{re.escape(title)}</strong><br>.*?</div>',
        re.S,
    )
    html2, n = pat.subn("", html, count=1)
    if n != 1:
        raise ValueError(f"Could not remove methodology item: {title}")
    return html2


def main():
    html = SITE.read_text(encoding="utf-8")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    m, payload = payload_match(html)

    precincts = (payload.get("precincts") or {}).get("features") or []
    hist = (payload.get("historical_incidents") or {}).get("features") or []
    if not 400 <= len(precincts) <= 800:
        raise ValueError(f"Unexpected precinct count: {len(precincts)}")
    if not 500 <= len(hist) <= 10_000:
        raise ValueError(f"Unexpected historical public-point count: {len(hist)}")

    counts: dict[str, int] = {}
    by_pid = {}
    for f in precincts:
        pid = precinct_id(f)
        if not pid or pid in counts:
            raise ValueError(f"Missing or duplicate precinct id: {pid!r}")
        counts[pid] = 0
        by_pid[pid] = f

    source_total = 0
    unassigned_reports = 0
    ambiguous_reports = 0
    unassigned_points = 0
    ambiguous_points = 0
    for f in hist:
        p = f.get("properties") or {}
        try:
            n = int(p.get("c365") or 0)
        except Exception as exc:
            raise ValueError("Malformed historical c365 count") from exc
        if n < 0:
            raise ValueError("Negative historical c365 count")
        source_total += n
        fps = sorted({str(x) for x in (p.get("focus_precincts") or []) if str(x) in counts})
        if len(fps) == 1:
            counts[fps[0]] += n
        elif not fps:
            unassigned_points += 1
            unassigned_reports += n
        else:
            ambiguous_points += 1
            ambiguous_reports += n

    assigned_total = sum(counts.values())
    if assigned_total + unassigned_reports + ambiguous_reports != source_total:
        raise ValueError("365-day precinct accounting does not reconcile")

    cuts = [nearest_rank_cut(counts.values(), q) for q in (0.20, 0.40, 0.60, 0.80)]
    if not all(cuts[i] < cuts[i + 1] for i in range(3)):
        raise ValueError(f"Quintile cut points are not distinct: {cuts}")
    ranks = competition_ranks(counts)
    band_counts = {str(i): 0 for i in range(1, 6)}
    for pid, value in counts.items():
        b = band(value, cuts)
        band_counts[str(b)] += 1
        p = by_pid[pid].setdefault("properties", {})
        p["incident_frequency_365"] = int(value)
        p["incident_frequency_band"] = int(b)
        p["incident_frequency_rank"] = int(ranks[pid])

    hist_meta = manifest.get("historical_incidents") or {}
    payload["precinct_incident_frequency"] = {
        "dataset_id": DATASET_ID,
        "window_days": 365,
        "band_cutpoints": cuts,
        "band_precinct_counts": band_counts,
        "assigned_report_count": assigned_total,
        "source_mapped_report_count": source_total,
        "unassigned_report_count": unassigned_reports,
        "ambiguous_report_count": ambiguous_reports,
        "source_rows_updated_at": hist_meta.get("source_rows_updated_at"),
    }

    packed = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = html[:m.start(1)] + packed + html[m.end(1):]

    old_row = '<div class="row"><div><div class="label">Reported incident history</div>'
    new_row = '<div class="row legacyHistoryHidden" aria-hidden="true"><div><div class="label">Reported incident history</div>'
    if old_row not in html:
        raise ValueError("Legacy historical row not found")
    html = html.replace(old_row, new_row, 1)
    html = html.replace('<div class="histControls">', '<div class="histControls legacyHistoryHidden" aria-hidden="true">', 1)
    # Remove the obsolete circle-encoding explanation entirely. The hidden
    # legacy controls stay only as inert binding targets for earlier JS.
    html = html.replace(
        '<div class="muted" style="margin-top:6px">Fixed-size circles. Darker color = more unique incident reports per 30 days at that public privacy-mapped intersection. This is report volume, not severity, and not every report establishes a crime.</div>',
        '',
        1,
    )

    html = remove_method_item(html, "Reported incident history")
    html = remove_method_item(html, "Precinct reported-incident context index")
    html = html.replace("Reported incident history ↗", "Reported incident frequency ↗", 1)

    css = r'''
/* 365-day precinct reported-incident frequency filter */
.legacyHistoryHidden{display:none!important}
.freqfill{fill:#7F56D9;fill-opacity:.18;stroke:#6941C6;stroke-width:1.8;stroke-opacity:.92;pointer-events:none;vector-effect:non-scaling-stroke}
.freqbox{margin:6px 0 10px;padding:9px;border:1px solid #d0d5dd;border-radius:8px;background:#fff;font-size:10px;line-height:1.4;color:#475467}
.freqfilterlabel{display:block;font-weight:800;color:#101828;margin-bottom:5px}
.freqselect{width:100%;box-sizing:border-box;border:1px solid #98a2b3;border-radius:6px;background:#fff;padding:7px 8px;font:inherit;font-size:11px;color:#344054}
.freqstatus{margin-top:6px;font-weight:700;color:#344054}
.freqnote{margin-top:4px;color:#667085}
.freqSummary{margin:0 0 8px;padding:7px 8px;border:1px solid #e4e7ec;border-radius:7px;background:#f9fafb;font-size:10.5px;line-height:1.4;color:#344054}.freqSummary b{color:#344054}
/* District identity is carried by a thick colored outline so it does not compete with the incident filter. */
.distfill{fill-opacity:0!important;stroke-width:3!important;stroke-opacity:.95!important}
.distfill.focus-district{fill-opacity:0!important;stroke-width:4.5!important;stroke-opacity:1!important}
.districtmini i{width:14px!important;height:4px!important;border:0!important;border-radius:99px!important}
'''

    if "</style>" not in html:
        raise ValueError("Style end not found")
    html = html.replace("</style>", css + "</style>", 1)

    svg_anchor = '<g id="view"><g id="dl"></g><g id="tl"></g>'
    if svg_anchor not in html:
        raise ValueError("District/topography layer anchor not found")
    html = html.replace(svg_anchor, '<g id="view"><g id="dl"></g><g id="ifl"></g><g id="tl"></g>', 1)

    mini_start = html.find('<div class="districtmini" id="districtMini"')
    if mini_start < 0:
        raise ValueError("District mini key not found")
    mini_end = html.find("</div>", mini_start)
    if mini_end < 0:
        raise ValueError("District mini key end not found")
    mini_end += len("</div>")

    c1, c2, c3, c4 = cuts
    ranges = [f"0–{c1}", f"{c1+1}–{c2}", f"{c2+1}–{c3}", f"{c3+1}–{c4}", f"{c4+1}+"]
    update_text = friendly_source_date(hist_meta.get("source_rows_updated_at"))
    frequency_ui = f'''
<div class="row"><div><div class="label">Past-year incident report filter</div><div class="muted">Unique mapped SFPD incident reports · rolling 365 days · {update_text}</div></div></div>
<div id="freqBox" class="freqbox"><label class="freqfilterlabel" for="freqFilter">Highlight precincts with:</label><select id="freqFilter" class="freqselect"><option value="0">All precincts</option><option value="1">{ranges[0]} reports · lowest 20%</option><option value="2">{ranges[1]} reports · 20–40%</option><option value="3">{ranges[2]} reports · 40–60%</option><option value="4">{ranges[3]} reports · 60–80%</option><option value="5">{ranges[4]} reports · highest 20%</option></select><div id="freqStatus" class="freqstatus">All precincts · no incident-frequency highlight applied</div><div class="freqnote">Choosing a band highlights only matching precincts. Exact counts appear on hover/click. This filter does <strong>not</strong> hide closures, terrain, access-screen parcels, permits, or recent dispatch activity. Raw report counts are not a safety score.</div></div>'''

    html = html[:mini_end] + frequency_ui + html[mini_end:]

    details_start = html.find('<summary>How this map is computed</summary>')
    if details_start < 0:
        raise ValueError("Methodology details start not found")
    details_end = html.find("</details>", details_start)
    if details_end < 0:
        raise ValueError("Methodology details end not found")
    frequency_method = f'''<div class="methoditem"><strong>Precinct reported-incident frequency filter</strong><br>Uses SFPD/DataSF dataset <span class="code">wg3w-h783</span> <a class="src-link" href="https://data.sf.gov/d/wg3w-h783" target="_blank" rel="noopener noreferrer">official source ↗</a>. The upstream build keeps initial report types and counts each <span class="code">incident_id</span> once, so multiple incident-code rows do not multiply an incident. Each privacy-mapped public point contributes to the one current election precinct that unambiguously covers it; points outside precinct geometry or covered by more than one precinct are omitted rather than duplicated or guessed. The filter groups precincts into citywide raw-count quintiles using this build's cut points: {c1}, {c2}, {c3}, and {c4} reports. Selecting a band highlights matching precincts only; operational layers remain visible. Supervisor District identity is shown separately with thick colored boundaries. This view does not weight severity and is not normalized for precinct area, population, street mileage, or foot traffic; it is reported-incident frequency context, not a crime rate or canvasser/neighborhood safety score.</div>'''

    html = html[:details_end] + frequency_method + html[details_end:]

    init_call = "init();loadFocusFromUrl();"
    if init_call not in html:
        raise ValueError("Final init call not found")
    js = r'''
// ----- 365-day precinct reported-incident frequency filter -----
const ifl=$('ifl');
S.freqBand=0;
function freq365(p){return Number((p||{}).incident_frequency_365||0)}
function freqBand(p){return Math.max(1,Math.min(5,Number((p||{}).incident_frequency_band||1)))}
function freqRank(p){return Number((p||{}).incident_frequency_rank||0)}
function freqBandLabel(p){const b=freqBand(p);return b===1?'lowest 20%':b===2?'20–40% band':b===3?'40–60% band':b===4?'60–80% band':'highest 20%'}
function freqBandRange(b){const c=DATA.precinct_incident_frequency?.band_cutpoints||[];if(c.length!==4)return '';return b===1?`0–${c[0]}`:b===2?`${c[0]+1}–${c[1]}`:b===3?`${c[1]+1}–${c[2]}`:b===4?`${c[2]+1}–${c[3]}`:`${c[3]+1}+`}
function renderIncidentFrequency(){
  ifl.replaceChildren();
  const b=Number(S.freqBand||0),status=$('freqStatus');
  if(!b){ifl.style.display='none';if(status)status.textContent='All precincts · no incident-frequency highlight applied';return}
  ifl.style.display='';
  let n=0;
  for(const f of(DATA.precincts?.features||[])){
    const p=f.properties||{};if(freqBand(p)!==b)continue;
    const d=polyPath(f.geometry);if(!d)continue;
    const e=document.createElementNS('http://www.w3.org/2000/svg','path');
    e.setAttribute('d',d);e.setAttribute('class','freqfill');e.setAttribute('aria-hidden','true');ifl.appendChild(e);n++;
  }
  if(status)status.textContent=`${n} precinct${n===1?'':'s'} highlighted · ${freqBandRange(b)} reports · ${b===1?'lowest 20%':b===5?'highest 20%':freqBandLabel({incident_frequency_band:b})}`;
}
$('freqFilter').onchange=e=>{S.freqBand=Number(e.target.value||0);renderIncidentFrequency();renderFocusSummary()};

// Reframe Supervisor Districts as thick colored boundary outlines rather than fills.
renderDistricts=function(){
  dl.replaceChildren();
  if(!S.sd){dl.style.display='none';$('districtMini').style.display='none';return}
  dl.style.display='';$('districtMini').style.display='';
  for(const f of(DATA.supervisor_districts?.features||[])){
    const p=f.properties||{},n=Number(p.district),d=polyPath(f.geometry);if(!d||!DISTRICT_COLORS[n])continue;
    const e=document.createElementNS('http://www.w3.org/2000/svg','path');
    e.setAttribute('d',d);e.setAttribute('class','distfill');e.setAttribute('fill','none');e.style.stroke=DISTRICT_COLORS[n];
    e.dataset.district=String(n);dl.appendChild(e);
  }
  updateDistrictFocus();
};

S.shi=false;
updateIncidentIndexSummary=function(){document.querySelector('.incidentIndexSummary')?.remove()};
renderHistory=function(){S.shi=false;hil.replaceChildren();hil.style.display='none';updateHistorySummary()};

const _hoverBeforeFrequency=hover;
hover=function(e){
  const base=_hoverBeforeFrequency(e);if(e.dataset.k!=='p')return base;
  const p=e.f?.properties||{},n=freq365(p),r=freqRank(p);
  return `${base}<br><strong>${n.toLocaleString()} mapped SFPD incident reports · past 365 days</strong>${r?` · raw-count rank #${r}`:''}<br><span style="opacity:.82">${freqBandRange(freqBand(p))} reports · ${freqBandLabel(p)} of SF precincts. Raw frequency only; not adjusted for precinct size/population/foot traffic and not a safety score.</span>`;
};
const _clickedBeforeFrequency=clicked;
clicked=function(e){
  const base=_clickedBeforeFrequency(e);if(e.dataset.k!=='p')return base;
  const p=e.f?.properties||{},n=freq365(p),r=freqRank(p);
  return `${base}<br><br><strong>Past-year incident report frequency</strong><br>${n.toLocaleString()} unique mapped SFPD incident report${n===1?'':'s'} · ${freqBandRange(freqBand(p))} band · ${freqBandLabel(p)}${r?` · raw-count rank #${r} of ${(DATA.precincts?.features||[]).length}`:''}<br><span class="muted">Raw frequency only. Counts are not adjusted for precinct size, resident population, street mileage, or foot traffic. Public locations are privacy-mapped, and a report does not by itself establish that a crime occurred.</span>`;
};

const _renderFocusSummaryFrequency=renderFocusSummary;
renderFocusSummary=function(){
  _renderFocusSummaryFrequency();const box=$('focusSummary');box?.querySelector('.freqSummary')?.remove();box?.querySelector('.incidentIndexSummary')?.remove();box?.querySelector('.histFocus')?.remove();
  if(!box||!PFOCUS.size)return;
  const rows=selectedPrecinctFeatures().map(f=>({pid:String((f.properties||{}).focus_precinct||pid(f.properties||{})),p:f.properties||{}})).sort((a,b)=>freqRank(a.p)-freqRank(b.p)||a.pid.localeCompare(b.pid));
  const d=document.createElement('div');d.className='freqSummary',b=Number(S.freqBand||0),matches=b?rows.filter(x=>freqBand(x.p)===b).length:rows.length;
  const detail=rows.length<=6?`<br>${rows.map(x=>`P${esc(x.pid)}: ${freq365(x.p).toLocaleString()} (${freqBandLabel(x.p)})`).join(' · ')}`:'';
  d.innerHTML=`<b>Past-year incident reports:</b> ${b?`${matches} of ${rows.length} selected precinct${rows.length===1?'':'s'} match the active ${freqBandRange(b)}-report filter`:'no frequency filter active'}${detail}<br><span style="color:#667085">Raw mapped report counts; not a safety score.</span>`;
  const sd=box.querySelector('.summarydistrict'),head=box.querySelector('.summaryhead');if(sd)sd.insertAdjacentElement('afterend',d);else if(head)head.insertAdjacentElement('afterend',d);else box.prepend(d);
};
const _initFrequency=init;init=function(){_initFrequency();renderDistricts();renderIncidentFrequency()};
'''

    html = html.replace(init_call, js + init_call, 1)

    manifest["precinct_incident_frequency"] = {
        "dataset_id": DATASET_ID,
        "source_url": "https://data.sf.gov/d/wg3w-h783",
        "window_days": 365,
        "count_semantics": "raw count of unique deduplicated initial incident reports at public privacy-mapped points covered by exactly one current election precinct; no severity weighting or exposure normalization",
        "assignment_rule": "exactly one covering precinct required; unassigned and multi-precinct public points are omitted rather than duplicated or guessed",
        "assigned_report_count": assigned_total,
        "source_mapped_report_count": source_total,
        "unassigned_report_count": unassigned_reports,
        "ambiguous_report_count": ambiguous_reports,
        "unassigned_point_count": unassigned_points,
        "ambiguous_point_count": ambiguous_points,
        "band_rule": "five raw-count quintile bands using nearest-rank 20/40/60/80 percent cut points across current precincts",
        "band_cutpoints": cuts,
        "band_precinct_counts": band_counts,
        "presentation_mode": "single-band precinct highlight filter",
        "default_filter": "all precincts (no frequency highlight)",
        "district_composition_rule": "Supervisor District identity is shown as a thick colored boundary outline; incident frequency highlights matching precinct interiors only",
        "source_rows_updated_at": hist_meta.get("source_rows_updated_at"),
        "interpretation": "reported-incident frequency context only; not a crime rate, severity score, or canvasser/neighborhood safety prediction",
        "legacy_history_ui": "retired/hidden; recent law-enforcement dispatch activity remains available",
    }

    if manifest.get("supervisor_districts"):
        manifest["supervisor_districts"]["visual_interpretation"] = "thick categorical colored boundary outlines only; no district fill; colors do not encode rank, score, party, safety, access, or turf quality"

    SITE.write_text(html, encoding="utf-8")
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        "precinct frequency overlay added: "
        f"precincts={len(counts)}; assigned365={assigned_total}; source365={source_total}; "
        f"unassigned365={unassigned_reports}; ambiguous365={ambiguous_reports}; "
        f"cuts={cuts}; band_counts={band_counts}"
    )


if __name__ == "__main__":
    main()
