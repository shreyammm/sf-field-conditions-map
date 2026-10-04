#!/usr/bin/env python3
"""Add optional current Supervisor District background shading.

Uses DataSF's official current Supervisor District geometry trimmed for mapping
of the contiguous/populated city territory. District color is purely categorical
reference context; it is not a score and never changes feature counts.
"""
from __future__ import annotations

import json
import pathlib
import re
import time
import urllib.request

from shapely.geometry import shape
from shapely.strtree import STRtree

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = ROOT / "_site" / "index.html"
MANIFEST = ROOT / "_site" / "data-manifest.json"

DISTRICT_ID = "hcgx-vtsb"
DISTRICT_PAGE = "https://data.sf.gov/d/hcgx-vtsb"
DISTRICT_URL = "https://data.sf.gov/api/v3/views/hcgx-vtsb/query.geojson?accessType=DOWNLOAD"
HEADERS = {
    "User-Agent": "sf-field-conditions-map/1.0 (+https://github.com/shreyammm/sf-field-conditions-map)",
    "Accept": "application/geo+json,application/json;q=0.9,*/*;q=0.1",
}


def get_json(url: str, attempts: int = 3, timeout: int = 90):
    last = None
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except Exception as exc:
            last = exc
            if attempt < attempts:
                time.sleep(attempt * 2)
    raise RuntimeError(f"Failed after {attempts} attempts: {url}\n{last}") from last


def payload_match(html: str):
    m = re.search(r"window\.SF_FIELD_DATA=(\{.*?\});\s*</script>", html, re.S)
    if not m:
        raise ValueError("Embedded payload not found")
    return m, json.loads(m.group(1))


def district_number(p):
    for key in ("sup_dist_num", "sup_dist", "supervisor_district", "district", "district_num"):
        v = p.get(key)
        if v in (None, ""):
            continue
        try:
            n = int(float(str(v).strip()))
        except (TypeError, ValueError):
            continue
        if 1 <= n <= 11:
            return n
    # Last-resort schema-tolerant check: only fields explicitly named as a
    # district are eligible; do not infer from arbitrary numeric attributes.
    for key, v in p.items():
        lk = str(key).lower()
        if "dist" not in lk or v in (None, ""):
            continue
        try:
            n = int(float(str(v).strip()))
        except (TypeError, ValueError):
            continue
        if 1 <= n <= 11:
            return n
    return None


def latest_text(values):
    xs = sorted(str(v).strip() for v in values if v not in (None, ""))
    return xs[-1] if xs else None


def build_districts(payload):
    raw = get_json(DISTRICT_URL)
    if raw.get("type") != "FeatureCollection":
        raise ValueError("Supervisor District source is not GeoJSON")
    src = raw.get("features") or []
    if not 10 <= len(src) <= 15:
        raise ValueError(f"Unexpected Supervisor District source feature count: {len(src)}")

    features = []
    seen = set()
    source_as_of = []
    source_loaded = []
    for f in src:
        p = f.get("properties") or {}
        g = f.get("geometry") or {}
        n = district_number(p)
        if n is None:
            raise ValueError(f"Could not identify Supervisor District number from properties: {sorted(p)}")
        if n in seen:
            raise ValueError(f"Duplicate Supervisor District number in source: {n}")
        if g.get("type") not in {"Polygon", "MultiPolygon"}:
            raise ValueError(f"Supervisor District {n} has non-polygon geometry: {g.get('type')}")
        geom = shape(g)
        if geom.is_empty or not geom.is_valid:
            raise ValueError(f"Supervisor District {n} has invalid/empty geometry")
        seen.add(n)
        source_as_of.append(p.get("data_as_of"))
        source_loaded.append(p.get("data_loaded_at"))
        features.append({
            "type": "Feature",
            "geometry": g,
            "properties": {"district": n},
        })

    if seen != set(range(1, 12)):
        raise ValueError(f"Supervisor District numbers are not exactly 1-11: {sorted(seen)}")
    features.sort(key=lambda f: f["properties"]["district"])

    # Add district membership to precinct records using actual polygon overlap.
    # Keep all material overlaps rather than silently forcing a precinct into a
    # district. These fields are reference metadata only; no counts depend on it.
    district_geoms = [shape(f["geometry"]) for f in features]
    district_nums = [int(f["properties"]["district"]) for f in features]
    tree = STRtree(district_geoms)
    unassigned = 0
    cross_district = 0
    min_dominant_share = 1.0
    for pf in (payload.get("precincts") or {}).get("features") or []:
        pp = pf.setdefault("properties", {})
        pg = shape(pf.get("geometry"))
        if pg.is_empty or pg.area <= 0:
            pp["supervisor_districts"] = []
            unassigned += 1
            continue
        overlaps = []
        for idx in tree.query(pg):
            i = int(idx)
            inter = pg.intersection(district_geoms[i])
            if inter.is_empty:
                continue
            share = float(inter.area / pg.area)
            if share > 1e-6:
                overlaps.append((district_nums[i], share))
        overlaps.sort(key=lambda x: (-x[1], x[0]))
        material = [n for n, share in overlaps if share >= 0.001]
        pp["supervisor_districts"] = sorted(material)
        if not material:
            unassigned += 1
        elif len(material) > 1:
            cross_district += 1
        if overlaps:
            min_dominant_share = min(min_dominant_share, overlaps[0][1])

    return {"type": "FeatureCollection", "features": features}, {
        "dataset_id": DISTRICT_ID,
        "source_url": DISTRICT_URL,
        "source_page": DISTRICT_PAGE,
        "source_feature_count": len(src),
        "embedded_feature_count": len(features),
        "district_numbers": list(range(1, 12)),
        "source_data_as_of": latest_text(source_as_of),
        "source_data_loaded_at": latest_text(source_loaded),
        "precinct_unassigned_count": unassigned,
        "precinct_cross_district_count": cross_district,
        "minimum_precinct_dominant_overlap_share": round(min_dominant_share, 6),
        "geometry_interpretation": "official current Supervisor District boundaries trimmed by DataSF to remove water/non-populated City territories for mapping",
        "visual_interpretation": "low-opacity categorical background colors only; colors do not encode rank, score, party, safety, or turf quality",
    }


def replace_one(s, old, new, label):
    if old not in s:
        raise ValueError(f"Supervisor District UI anchor missing: {label}")
    return s.replace(old, new, 1)


def patch_ui(html):
    css = r'''
/* Supervisor District categorical reference shading */
.distfill{stroke:#667085;stroke-opacity:.72;stroke-width:1.15;fill-opacity:.13;vector-effect:non-scaling-stroke;pointer-events:none}.distfill.focus-district{fill-opacity:.18;stroke-opacity:.9}.districtmini{display:flex;flex-wrap:wrap;gap:4px 8px;margin:6px 0 2px;font-size:9.5px;color:#667085}.districtmini span{display:inline-flex;align-items:center;gap:3px}.districtmini i{width:9px;height:9px;border-radius:2px;border:1px solid rgba(52,64,84,.22);display:inline-block}.districtLegendSwatch{width:32px;height:11px;border-radius:3px;border:1px solid #d0d5dd;background:linear-gradient(90deg,#8dd3c7 0 9%,#ffffb3 9% 18%,#bebada 18% 27%,#fb8072 27% 36%,#80b1d3 36% 45%,#fdb462 45% 54%,#b3de69 54% 63%,#fccde5 63% 72%,#d9d9d9 72% 81%,#bc80bd 81% 90%,#ccebc5 90%)}.summarydistrict{margin:-2px 0 8px;font-size:10.5px;color:#475467}.summarydistrict b{color:#344054}
'''
    html = replace_one(html, "</style>", css + "</style>", "style end")

    street_row = '<div class="row"><div><div class="label">Street network</div><div class="muted">SF Public Works · active physical/context centerlines</div></div><label class="switch"><input id="sToggle" type="checkbox" checked><span></span></label></div>'
    district_control = street_row + '''\n<div class="row"><div><div class="label">Supervisor district shading</div><div class="muted">Current Board of Supervisors districts · categorical reference only</div></div><label class="switch"><input id="dToggle" type="checkbox" checked><span></span></label></div>\n<div class="districtmini" id="districtMini" aria-label="Supervisor district color key"><span><i style="background:#8dd3c7"></i>D1</span><span><i style="background:#ffffb3"></i>D2</span><span><i style="background:#bebada"></i>D3</span><span><i style="background:#fb8072"></i>D4</span><span><i style="background:#80b1d3"></i>D5</span><span><i style="background:#fdb462"></i>D6</span><span><i style="background:#b3de69"></i>D7</span><span><i style="background:#fccde5"></i>D8</span><span><i style="background:#d9d9d9"></i>D9</span><span><i style="background:#bc80bd"></i>D10</span><span><i style="background:#ccebc5"></i>D11</span></div>'''
    html = replace_one(html, street_row, district_control, "layer control")

    html = replace_one(html, '<g id="view"><g id="tl"></g>', '<g id="view"><g id="dl"></g><g id="tl"></g>', "district SVG layer")

    prec_legend = '<div class="legend"><span class="ln prec-ln" style="border-top-style:dashed"></span><span class="legendtext">Election precinct boundary</span><span class="info" title="Official SF Department of Elections / DataSF precinct geometry. Reference boundary only.">ⓘ</span></div>'
    district_legend = '<div class="legend"><span class="districtLegendSwatch"></span><span class="legendtext">Supervisor district background · D1–D11</span><span class="info" title="Current official Supervisor District reference geography. Colors only distinguish districts; they do not encode a score or ranking.">ⓘ</span></div>\n' + prec_legend
    html = replace_one(html, prec_legend, district_legend, "legend")

    source_anchor = '<a href="https://data.sf.gov/d/d6x4-hefw" target="_blank" rel="noopener noreferrer">Election precincts ↗</a>'
    district_source = source_anchor + '<a href="https://data.sf.gov/d/hcgx-vtsb" target="_blank" rel="noopener noreferrer">Supervisor districts ↗</a>'
    html = replace_one(html, source_anchor, district_source, "source directory")

    precinct_method = '<div class="methoditem"><strong>Precinct boundaries</strong><br>Downloaded from the SF Department of Elections / DataSF dataset <span class="code">d6x4-hefw</span> <a class="src-link" href="https://data.sf.gov/d/d6x4-hefw" target="_blank" rel="noopener noreferrer">official source ↗</a>, “Election Precincts — Current, Defined 2022.” Precinct polygons are reference lines only; housing, hill, closure, permit, and dispatch layers are not averaged into precinct scores.</div>'
    district_method = precinct_method + '<div class="methoditem"><strong>Supervisor district shading</strong><br>Uses DataSF dataset <span class="code">hcgx-vtsb</span> <a class="src-link" href="https://data.sf.gov/d/hcgx-vtsb" target="_blank" rel="noopener noreferrer">official source ↗</a>, the current Supervisor District boundaries trimmed by DataSF to remove water and other non-populated City territories for mapping. The 11 background colors are arbitrary categorical identifiers only: color does not encode rank, political preference, safety, access, or turf quality.</div>'
    html = replace_one(html, precinct_method, district_method, "district methodology")

    js_anchor = 'init();loadFocusFromUrl();\n})();'
    js = r'''
// Current Supervisor District reference shading. This is a non-interactive
// background layer so it cannot intercept precinct/street/parcel interactions.
const dl=$('dl');
const DISTRICT_COLORS={1:'#8dd3c7',2:'#ffffb3',3:'#bebada',4:'#fb8072',5:'#80b1d3',6:'#fdb462',7:'#b3de69',8:'#fccde5',9:'#d9d9d9',10:'#bc80bd',11:'#ccebc5'};
S.sd=true;
function renderDistricts(){
  dl.replaceChildren();
  if(!S.sd){dl.style.display='none';$('districtMini').style.display='none';return}
  dl.style.display='';$('districtMini').style.display='';
  for(const f of(DATA.supervisor_districts?.features||[])){
    const p=f.properties||{},n=Number(p.district),d=polyPath(f.geometry);if(!d||!DISTRICT_COLORS[n])continue;
    const e=document.createElementNS('http://www.w3.org/2000/svg','path');
    e.setAttribute('d',d);e.setAttribute('class','distfill');e.setAttribute('fill',DISTRICT_COLORS[n]);
    e.dataset.district=String(n);dl.appendChild(e);
  }
  updateDistrictFocus();
}
function selectedSupervisorDistricts(){
  const out=new Set();
  for(const f of selectedPrecinctFeatures())for(const n of((f.properties||{}).supervisor_districts||[]))if(Number(n)>=1&&Number(n)<=11)out.add(Number(n));
  return [...out].sort((a,b)=>a-b);
}
function updateDistrictFocus(){
  if(!dl)return;const selected=new Set(selectedSupervisorDistricts().map(String));
  dl.querySelectorAll('.distfill').forEach(e=>e.classList.toggle('focus-district',!!PFOCUS.size&&selected.has(e.dataset.district)));
}
$('dToggle').onchange=e=>{S.sd=e.target.checked;renderDistricts()};
const _renderFocusSummaryDistrict=renderFocusSummary;
renderFocusSummary=function(){
  _renderFocusSummaryDistrict();
  const box=$('focusSummary');box?.querySelector('.summarydistrict')?.remove();
  if(!PFOCUS.size){updateDistrictFocus();return}
  const ds=selectedSupervisorDistricts(),d=document.createElement('div');d.className='summarydistrict';
  d.innerHTML=ds.length?`<b>Supervisor district${ds.length===1?'':'s'}:</b> ${ds.map(n=>'D'+n).join(', ')}`:'<b>Supervisor district:</b> not assigned from official overlap';
  const head=box?.querySelector('.summaryhead');if(head)head.insertAdjacentElement('afterend',d);else box?.prepend(d);updateDistrictFocus();
};
const _initDistrict=init;
init=function(){_initDistrict();renderDistricts()};
'''
    html = replace_one(html, js_anchor, js + '\n' + js_anchor, "district runtime")
    return html


def main():
    html = SITE.read_text(encoding="utf-8")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    m, payload = payload_match(html)
    districts, meta = build_districts(payload)
    payload["supervisor_districts"] = districts
    manifest["supervisor_districts"] = meta

    # Replace payload before any HTML-length-changing UI mutations so offsets
    # cannot go stale and corrupt the generated artifact.
    packed = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    html = html[: m.start(1)] + packed + html[m.end(1) :]
    html = patch_ui(html)

    SITE.write_text(html, encoding="utf-8")
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        "supervisor districts added: 11 current official districts; "
        f"precinct_unassigned={meta['precinct_unassigned_count']}; "
        f"cross_district_precincts={meta['precinct_cross_district_count']}"
    )


if __name__ == "__main__":
    main()
