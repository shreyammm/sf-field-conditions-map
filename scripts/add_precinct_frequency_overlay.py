#!/usr/bin/env python3
"""Replace the visible historical-point UI with a 365-day precinct frequency overlay.

The source remains SFPD/DataSF wg3w-h783 and the already-audited build-time
historical snapshot. Each incident_id was deduplicated upstream before counts
were aggregated at privacy-mapped public points. This pass sums only points
covered by exactly one current election precinct, then places precincts into
five raw-count quintile bands. It does not weight severity and does not
normalize for population, area, street miles, or foot traffic.

Supervisor District shading remains visible underneath the frequency overlay.
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
/* 365-day precinct reported-incident frequency overlay */
.legacyHistoryHidden{display:none!important}
.freqfill{fill:#101828;stroke:none;pointer-events:none;vector-effect:non-scaling-stroke;mix-blend-mode:multiply}
.freqband1{fill-opacity:.012}.freqband2{fill-opacity:.038}.freqband3{fill-opacity:.075}.freqband4{fill-opacity:.12}.freqband5{fill-opacity:.18}
.freqbox{margin:5px 0 9px;padding:7px 8px;border:1px solid #e4e7ec;border-radius:7px;background:#fcfcfd;font-size:9.8px;line-height:1.35;color:#667085}
.freqkey{display:flex;gap:5px;align-items:center;flex-wrap:wrap;margin:5px 0 3px}.freqkey span{display:inline-flex;gap:3px;align-items:center;white-space:nowrap}.freqkey i{width:13px;height:11px;border-radius:2px;border:1px solid #d0d5dd;background:#fff}.freqkey .f1{background:rgba(16,24,40,.012)}.freqkey .f2{background:rgba(16,24,40,.038)}.freqkey .f3{background:rgba(16,24,40,.075)}.freqkey .f4{background:rgba(16,24,40,.12)}.freqkey .f5{background:rgba(16,24,40,.18)}
.freqSummary{margin:0 0 8px;padding:7px 8px;border:1px solid #e4e7ec;border-radius:7px;background:#f9fafb;font-size:10.5px;line-height:1.4;color:#344054}.freqSummary b{color:#344054}
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
<div class="row"><div><div class="label">Reported incident frequency</div><div class="muted">Raw unique mapped SFPD incident reports · rolling 365 days · {update_text}</div></div><label class="switch"><input id="freqToggle" type="checkbox" checked><span></span></label></div>
<div id="freqBox" class="freqbox"><strong>Precinct frequency · last 365 days</strong><div class="freqkey"><span><i class="f1"></i>{ranges[0]}</span><span><i class="f2"></i>{ranges[1]}</span><span><i class="f3"></i>{ranges[2]}</span><span><i class="f4"></i>{ranges[3]}</span><span><i class="f5"></i>{ranges[4]}</span></div><div>Lighter → fewer mapped reports; darker → more. The five bands are citywide quintiles, so each contains roughly one-fifth of SF precincts. <strong>Raw counts only:</strong> not adjusted for precinct size, population, street miles, or foot traffic, and not a safety score. Supervisor District color remains underneath.</div></div>'''
    html = html[:mini_end] + frequency_ui + html[mini_end:]

    details_start = html.find('<summary>How this map is computed</summary>')
    if details_start < 0:
        raise ValueError("Methodology details start not found")
    details_end = html.find("</details>", details_start)
    if details_end < 0:
        raise ValueError("Methodology details end not found")
    frequency_method = f'''<div class="methoditem"><strong>Precinct reported-incident frequency</strong><br>Uses SFPD/DataSF dataset <span class="code">wg3w-h783</span> <a class="src-link" href="https://data.sf.gov/d/wg3w-h783" target="_blank" rel="noopener noreferrer">official source ↗</a>. The upstream build keeps initial report types and counts each <span class="code">incident_id</span> once, so multiple incident-code rows do not multiply an incident. This layer sums the rolling 365-day count for each privacy-mapped public point covered by exactly one current election precinct. Points outside precinct geometry or covered by more than one precinct are omitted rather than duplicated or guessed. The five neutral-darkness bands are citywide raw-count quintiles using this build's cut points: {c1}, {c2}, {c3}, and {c4} reports. The Supervisor District categorical color remains visible underneath. This view does not weight severity and is not normalized for precinct area, population, street mileage, or foot traffic; it is reported-incident frequency context, not a crime rate or canvasser/neighborhood safety score.</div>'''
    html = html[:details_end] + frequency_method + html[details_end:]

    init_call = "init();loadFocusFromUrl();"
    if init_call not in html:
        raise ValueError("Final init call not found")
    js = r'''
// ----- simple 365-day precinct reported-incident frequency overlay -----
const ifl=$('ifl');S.sif=true;
function freq365(p){return Number((p||{}).incident_frequency_365||0)}
function freqBand(p){return Math.max(1,Math.min(5,Number((p||{}).incident_frequency_band||1)))}
function freqRank(p){return Number((p||{}).incident_frequency_rank||0)}
function freqBandLabel(p){const b=freqBand(p);return b===1?'lowest fifth':b===2?'second fifth':b===3?'middle fifth':b===4?'fourth fifth':'highest fifth'}
function renderIncidentFrequency(){
  ifl.replaceChildren();const box=$('freqBox');
  if(!S.sif){ifl.style.display='none';if(box)box.style.display='none';return}
  ifl.style.display='';if(box)box.style.display='';
  for(const f of(DATA.precincts?.features||[])){
    const p=f.properties||{},d=polyPath(f.geometry);if(!d)continue;
    const e=document.createElementNS('http://www.w3.org/2000/svg','path');
    e.setAttribute('d',d);e.setAttribute('class','freqfill freqband'+freqBand(p));e.setAttribute('aria-hidden','true');ifl.appendChild(e);
  }
}
$('freqToggle').onchange=e=>{S.sif=e.target.checked;renderIncidentFrequency()};

S.shi=false;
updateIncidentIndexSummary=function(){document.querySelector('.incidentIndexSummary')?.remove()};
const _renderHistoryRetired=renderHistory;
renderHistory=function(){S.shi=false;hil.replaceChildren();hil.style.display='none';updateHistorySummary()};

const _hoverBeforeFrequency=hover;
hover=function(e){
  const base=_hoverBeforeFrequency(e);if(e.dataset.k!=='p'||!S.sif)return base;
  const p=e.f?.properties||{},n=freq365(p),r=freqRank(p);
  return `${base}<br><strong>${n.toLocaleString()} reported incidents · past 365 days</strong>${r?` · raw-count rank #${r}`:''}<br><span style="opacity:.82">${freqBandLabel(p)} of SF precincts by raw mapped report count. Not adjusted for precinct size/population/foot traffic; not a safety score.</span>`;
};
const _clickedBeforeFrequency=clicked;
clicked=function(e){
  const base=_clickedBeforeFrequency(e);if(e.dataset.k!=='p'||!S.sif)return base;
  const p=e.f?.properties||{},n=freq365(p),r=freqRank(p);
  return `${base}<br><br><strong>Reported incident frequency · last 365 days</strong><br>${n.toLocaleString()} unique mapped SFPD incident report${n===1?'':'s'} · ${freqBandLabel(p)}${r?` · raw-count rank #${r} of ${(DATA.precincts?.features||[]).length}`:''}<br><span class="muted">Frequency only. Raw counts are not adjusted for precinct size, resident population, street mileage, or foot traffic. Public locations are privacy-mapped, and a report does not by itself establish that a crime occurred.</span>`;
};

const _renderFocusSummaryFrequency=renderFocusSummary;
renderFocusSummary=function(){
  _renderFocusSummaryFrequency();const box=$('focusSummary');box?.querySelector('.freqSummary')?.remove();box?.querySelector('.incidentIndexSummary')?.remove();box?.querySelector('.histFocus')?.remove();
  if(!box||!PFOCUS.size)return;
  const rows=selectedPrecinctFeatures().map(f=>({pid:String((f.properties||{}).focus_precinct||pid(f.properties||{})),p:f.properties||{}})).sort((a,b)=>freqRank(a.p)-freqRank(b.p)||a.pid.localeCompare(b.pid));
  const total=rows.reduce((s,x)=>s+freq365(x.p),0),d=document.createElement('div');d.className='freqSummary';
  const detail=rows.length<=6?`<br>${rows.map(x=>`P${esc(x.pid)}: ${freq365(x.p).toLocaleString()} (${freqBandLabel(x.p)})`).join(' · ')}`:'';
  d.innerHTML=`<b>Reported incident frequency · last 365 days:</b> ${total.toLocaleString()} unique mapped reports across ${rows.length} selected precinct${rows.length===1?'':'s'}${detail}<br><span style="color:#667085">Raw counts; not adjusted for precinct size/population/foot traffic and not a safety score.</span>`;
  const sd=box.querySelector('.summarydistrict'),head=box.querySelector('.summaryhead');if(sd)sd.insertAdjacentElement('afterend',d);else if(head)head.insertAdjacentElement('afterend',d);else box.prepend(d);
};
const _initFrequency=init;init=function(){_initFrequency();renderIncidentFrequency()};
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
        "district_composition_rule": "frequency is a neutral darkness overlay above Supervisor District categorical fill; district color remains simultaneously visible",
        "source_rows_updated_at": hist_meta.get("source_rows_updated_at"),
        "interpretation": "reported-incident frequency context only; not a crime rate, severity score, or canvasser/neighborhood safety prediction",
        "legacy_history_ui": "retired/hidden; recent law-enforcement dispatch activity remains available",
    }

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
