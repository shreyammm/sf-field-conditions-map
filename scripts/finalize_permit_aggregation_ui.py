#!/usr/bin/env python3
"""Teach the final permit UI about aggregated co-located source rows."""
from pathlib import Path
import re

p = Path(__file__).resolve().parents[1] / "_site" / "index.html"
s = p.read_text(encoding="utf-8")

old_helper = "const workWhere=p=>[String(p.street_name||'').trim(),String(p.cross_street||'').trim()?`near ${String(p.cross_street).trim()}`:''].filter(Boolean).join(' ');"
new_helper = '''const workLocations=p=>{const xs=Array.isArray(p.source_locations)?p.source_locations:[];if(xs.length)return xs.map(x=>[String(x.street||'').trim(),String(x.cross_street||'').trim()?`near ${String(x.cross_street).trim()}`:''].filter(Boolean).join(' ')).filter(Boolean);const one=[String(p.street_name||'').trim(),String(p.cross_street||'').trim()?`near ${String(p.cross_street).trim()}`:''].filter(Boolean).join(' ');return one?[one]:[]};
const workDescriptions=p=>Array.isArray(p.source_descriptions)?p.source_descriptions.filter(Boolean):(p.permit_description?[String(p.permit_description)]:[]);
const workStatuses=p=>Array.isArray(p.source_statuses)?p.source_statuses.filter(Boolean):(p.status?[String(p.status)]:[]);
const workNeighborhoods=p=>Array.isArray(p.source_neighborhoods)?p.source_neighborhoods.filter(Boolean):(p.analysis_neighborhood?[String(p.analysis_neighborhood)]:[]);'''
if old_helper not in s:
    raise SystemExit("permit aggregation UI anchor missing: helper")
s = s.replace(old_helper, new_helper, 1)

hover_pattern = re.compile(r"if\(e\.dataset\.k==='w'\)\{.*?\}if\(e\.dataset\.k==='c'\)\{", re.S)
hover_matches = list(hover_pattern.finditer(s))
if len(hover_matches) < 2:
    raise SystemExit(f"permit aggregation UI expected hover/click branches, found {len(hover_matches)}")

hover_replacement = '''if(e.dataset.k==='w'){const locs=workLocations(p),descs=workDescriptions(p),rows=Number(p.source_row_count||1),locText=locs.length>1?`${locs.length} source street-location rows at this official point`:locs[0]||'',desc=descs[0]||'';return`<strong>${esc(workLabel(p))}</strong>${locText?esc(locText)+'<br>':''}${esc(workWindow(p))}${desc?'<br>'+esc(desc):''}${rows>1?`<br>${rows} source rows represented by this marker`:''}<br><span style="opacity:.82">Public Works permit authorization point; the date window does not prove crews are working then, and this is not a confirmed closure or exact work footprint.</span>`}if(e.dataset.k==='c'){'''
first = hover_matches[0]
s = s[:first.start()] + hover_replacement + s[first.end():]

# Find the click branch after replacing hover; it is now the first remaining
# branch with the original work implementation.
click_pattern = re.compile(r"if\(e\.dataset\.k==='w'\)\{const where=workWhere\(p\).*?\}if\(e\.dataset\.k==='c'\)\{", re.S)
m = click_pattern.search(s)
if not m:
    raise SystemExit("permit aggregation UI anchor missing: click branch")
click_replacement = '''if(e.dataset.k==='w'){const locs=workLocations(p),descs=workDescriptions(p),statuses=workStatuses(p),hoods=workNeighborhoods(p),rows=Number(p.source_row_count||1),num=p.permit_number?`<br>Permit: ${esc(p.permit_number)}`:'',locHtml=locs.length?`<br>Source location${locs.length===1?'':'s'}:<br>${locs.map(x=>'• '+esc(x)).join('<br>')}`:'',descHtml=descs.length?`<br>Source description${descs.length===1?'':'s'}:<br>${descs.map(x=>'• '+esc(x)).join('<br>')}`:'',hoodHtml=hoods.length?`<br>Neighborhood${hoods.length===1?'':'s'}: ${esc(hoods.join(', '))}`:'',statusText=statuses.length?statuses.join(' / '):'—',rowNote=rows>1?`<br>${rows} source rows share this permit/type/date window and official point; their distinct location text is preserved above.`:'';return`<strong>${esc(workLabel(p))}</strong><br>Status: ${esc(statusText)}<br>Permit window: ${esc(workWindow(p))}${num}${locHtml}${hoodHtml}${descHtml}${rowNote}<br><span class="muted">A permit authorizes street/sidewalk use during a permitted window; it does not prove crews are physically working on the selected date or that the space is obstructed, closed, or impassable to pedestrians. The marker is the source point, not the work footprint; multiple source street locations can share one point.</span>`}if(e.dataset.k==='c'){'''
s = s[:m.start()] + click_replacement + s[m.end():]

p.write_text(s, encoding="utf-8")
print("finalized permit aggregation UI")
