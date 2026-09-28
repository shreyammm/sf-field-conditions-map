#!/usr/bin/env python3
"""Make closure popups location-first and expose source/reason context links."""
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "_site" / "index.html"
s = p.read_text(encoding="utf-8")


def repl(old: str, new: str, label: str):
    global s
    if old not in s:
        raise SystemExit(f"closure-context UI patch anchor missing: {label}")
    s = s.replace(old, new, 1)


old_helpers = """const closureName=p=>String(p.case_name||p.loc_desc||p.street||'Temporary street closure').trim();
const closureWhere=p=>{const st=String(p.street||'').trim(),a=String(p.from_st||'').trim(),b=String(p.to_st||'').trim();return st+(a||b?` between ${a||'segment start'} and ${b||'segment end'}`:'')};
const closureTimeText=p=>`${fmtSFLocal(p.start_local||p.start_dt)} to ${fmtSFLocal(p.end_local||p.end_dt)}`;"""
new_helpers = """const closureTitle=p=>{const st=String(p.street||'').trim(),a=String(p.from_st||'').trim(),b=String(p.to_st||'').trim(),loc=String(p.loc_desc||'').trim();if(st&&(a||b))return`${st} — ${a||'segment start'} to ${b||'segment end'}`;return loc||st||'Temporary street closure'};
const closureTimeText=p=>`${fmtSFLocal(p.start_local||p.start_dt)} to ${fmtSFLocal(p.end_local||p.end_dt)}`;
const closureRelated=p=>Array.isArray(p.related_work_permits)?p.related_work_permits:[];
const relatedDescriptions=r=>Array.isArray(r?.source_descriptions)?r.source_descriptions.filter(Boolean).map(String):[];
const relatedLocations=r=>Array.isArray(r?.source_locations)?r.source_locations.filter(Boolean):[];
const shortText=(v,n=150)=>{const x=String(v||'').trim();return x.length>n?x.slice(0,n-1)+'…':x};
const closureSourceUrl=p=>p.objectid?`https://data.sfgov.org/resource/8x25-yybr.json?objectid=${encodeURIComponent(String(p.objectid))}`:'https://data.sfgov.org/d/8x25-yybr';
const permitSourceUrl=r=>r?.permit_number?`https://data.sfgov.org/resource/bpc9-7sus.json?permit_number=${encodeURIComponent(String(r.permit_number))}`:'https://data.sfgov.org/d/bpc9-7sus';
const sourceLink=(url,label)=>`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)} ↗</a>`;
const relatedPermitLabel=r=>String(r?.permit_type_label||r?.permit_type||'Public Works permit');
const relatedPermitReason=r=>{const ds=relatedDescriptions(r);return ds[0]||relatedPermitLabel(r)};
const closureHoverReason=p=>{const info=String(p.info||'').trim();if(info)return`SFMTA note: ${shortText(info)}`;const rs=closureRelated(p);return rs.length?`Related Public Works permit: ${shortText(relatedPermitReason(rs[0]))}`:''};"""
repl(old_helpers, new_helpers, "closure helpers")

old_hover = """if(e.dataset.k==='c'){const where=closureWhere(p),typ=p.type||'Temporary closure';return`<strong>${esc(closureName(p))}</strong>${where?esc(where)+'<br>':''}${esc(typ)} · ${esc(closureTimeText(p))}<br><span style="opacity:.82">SFMTA-permitted closure/disruption. Check details; this does not automatically mean pedestrian access is blocked.</span>`}if(e.dataset.k==='s'){"""
new_hover = """if(e.dataset.k==='c'){const typ=p.type||'Temporary closure',caseName=String(p.case_name||'').trim(),reason=closureHoverReason(p),related=closureRelated(p);return`<strong>${esc(closureTitle(p))}</strong><br>${esc(typ)} · ${esc(closureTimeText(p))}${caseName?`<br>SFMTA case: ${esc(caseName)}`:''}${reason?`<br>${esc(reason)}`:''}${related.length>1?`<br>${related.length} related Public Works permit records matched`:''}<br><span style="opacity:.82">SFMTA-permitted street/vehicle disruption. Click for source links and match details; pedestrian access may still be possible.</span>`}if(e.dataset.k==='s'){"""
repl(old_hover, new_hover, "closure hover")

old_click = """if(e.dataset.k==='c'){const where=closureWhere(p),impact=p.veh_imp?`<br>Vehicle impact: ${esc(p.veh_imp)}`:'',dir=p.direction?`<br>Direction: ${esc(p.direction)}`:'',info=p.info?`<br>Info: ${esc(p.info)}`:'',caseNo=p.case_num?`<br>Case: ${esc(p.case_num)}`:'';return`<strong>${esc(closureName(p))}</strong>${where?'<br>'+esc(where):''}<br>Type: ${esc(p.type||'Temporary closure')}<br>Scheduled: ${esc(closureTimeText(p))}${impact}${dir}${caseNo}${info}<br><span class="muted">Official SFMTA permitted-closure geometry. This feed is not a complete inventory of closures managed by other City departments and a street closure does not necessarily prohibit pedestrian passage.</span>`}if(e.dataset.k==='s'){"""
new_click = """if(e.dataset.k==='c'){const impact=p.veh_imp?`<br>Vehicle impact: ${esc(p.veh_imp)}`:'',dir=p.direction?`<br>Direction: ${esc(p.direction)}`:'',info=p.info?`<br>SFMTA note: ${esc(p.info)}`:'',caseNo=p.case_num?`<br>SFMTA case number: ${esc(p.case_num)}`:'',caseName=p.case_name?`<br>SFMTA case: ${esc(p.case_name)}`:'',source=`<br>${sourceLink(closureSourceUrl(p),'Open SFMTA source record')}`,related=closureRelated(p),relatedTotal=Number(p.related_work_permit_count||related.length),relatedHtml=related.length?`<br><br><strong>Related Public Works permit context</strong><br>${related.map(r=>{const ds=relatedDescriptions(r),locs=relatedLocations(r),desc=ds.length?ds.join(' / '):relatedPermitLabel(r),where=locs.length?locs.map(x=>[String(x.street||'').trim(),String(x.cross_street||'').trim()?`near ${String(x.cross_street).trim()}`:''].filter(Boolean).join(' ')).filter(Boolean).join('; '):'',num=String(r.permit_number||'').trim(),dist=Number(r.distance_m),distance=Number.isFinite(dist)?` · source point ${dist.toFixed(0)} m from closure line`:'',window=(r.start_local||r.end_local)?` · ${fmtDateOnly(r.start_local)} – ${fmtDateOnly(r.end_local)}`:'';return`• <strong>${esc(desc)}</strong>${num?`<br>Permit ${esc(num)} · ${esc(relatedPermitLabel(r))}`:''}${window}${where?`<br>${esc(where)}`:''}${distance}<br>${sourceLink(permitSourceUrl(r),'Open Public Works/DataSF permit record')}`}).join('<br><br>')}${relatedTotal>related.length?`<br><br>${(relatedTotal-related.length).toLocaleString()} additional related permit record${relatedTotal-related.length===1?'':'s'} met the match rule but are not shown here.`:''}<br><span class="muted">These are contextual matches only: same normalized street, overlapping date windows, and an official Public Works permit point within ${Number(DATA.meta?.closure_context_match_distance_m||120).toFixed(0)} m of the official SFMTA closure line. A match does not prove that the Public Works permit caused the SFMTA closure or that pedestrian access is blocked.</span>`:(String(p.type||'').toUpperCase()==='SPECIAL TRAFFIC PERMIT'?`<br><br><strong>Related Public Works permit context</strong><br><span class="muted">No current/upcoming Public Works work-permit point met the conservative street/date/proximity match rule in this build. That does not mean no related work exists.</span>`:'');return`<strong>${esc(closureTitle(p))}</strong><br>Type: ${esc(p.type||'Temporary closure')}<br>Scheduled: ${esc(closureTimeText(p))}${impact}${dir}${caseName}${caseNo}${info}${source}${relatedHtml}<br><br><span class="muted">Official SFMTA permitted-closure geometry. The closure feed is not a complete inventory of closures managed by other City departments, and a street closure does not necessarily prohibit pedestrian passage.</span>`}if(e.dataset.k==='s'){"""
repl(old_click, new_click, "closure click")

method_anchor = "SFMTA explicitly notes that this feed does not include every closure managed by Public Works, SFPD, or other City departments.</div>"
method_new = "SFMTA explicitly notes that this feed does not include every closure managed by Public Works, SFPD, or other City departments. For <span class=\"code\">Special Traffic Permit</span> rows, the detail panel may also show separately sourced Public Works permit context when the street name matches, the date windows overlap, and the official permit point lies within 120 m of the official closure line. Those records are labeled as related context rather than as the cause of the closure.</div>"
repl(method_anchor, method_new, "closure methodology context")

p.write_text(s, encoding="utf-8")
print("refined closure context UI")
