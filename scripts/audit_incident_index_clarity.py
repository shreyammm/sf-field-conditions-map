#!/usr/bin/env python3
"""Audit final transparency copy for the precinct incident index."""
from __future__ import annotations
import json, pathlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
html=(ROOT/'_site'/'index.html').read_text(encoding='utf-8')
manifest=json.loads((ROOT/'_site'/'data-manifest.json').read_text(encoding='utf-8'))
meta=manifest.get('precinct_incident_index') or {}
clar=manifest.get('incident_index_clarity') or {}
coverage=meta.get('weighted_category_coverage_365d_pct')
issues=[]
def check(ok,msg):
    if not ok: issues.append(msg)
check(coverage is not None, 'weighted-category coverage missing')
check('Scored reports /30d' in html, 'ranking table does not distinguish scored reports from all reports')
check('Current one-year coverage:' in html, 'weighted-category coverage is not visible in ranking explanation')
if coverage is not None:
    check(f'{float(coverage):.1f}% of mapped initial reports' in html, 'visible coverage percentage disagrees with manifest')
check(clar.get('scored_report_column_explicit') is True, 'clarity manifest scored-report flag missing')
check(float(clar.get('weighted_category_coverage_365d_pct_visible') or -1)==float(coverage or -2), 'clarity manifest coverage mismatch')
if issues:
    print(f'INCIDENT INDEX CLARITY AUDIT FAIL: {len(issues)} issue(s)')
    for x in issues: print(' -',x)
    raise SystemExit(1)
print('INCIDENT INDEX CLARITY AUDIT PASS')
print(f'weighted category coverage (365d)={float(coverage):.1f}%')
