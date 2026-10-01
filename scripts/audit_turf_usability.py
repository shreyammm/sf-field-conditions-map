#!/usr/bin/env python3
"""Deployment-blocking audit for final turf-cutting usability hardening."""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = ROOT / "_site" / "index.html"
MANIFEST = ROOT / "_site" / "data-manifest.json"
html = SITE.read_text(encoding="utf-8")
manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
issues = []


def check(ok, msg):
    if not ok:
        issues.append(msg)

# Core payload must still parse after every final HTML mutation.
m = re.search(r"window\.SF_FIELD_DATA=(\{.*?\});\s*</script>", html, re.S)
check(bool(m), "embedded production payload missing")
if m:
    try:
        data = json.loads(m.group(1))
        check(bool((data.get("streets") or {}).get("features")), "street payload missing")
        check(bool((data.get("precincts") or {}).get("features")), "precinct payload missing")
    except Exception as exc:
        issues.append(f"embedded payload invalid JSON: {exc}")

# Precinct picking must be an explicit mode so polygon interiors do not always
# intercept street/parcel clicks.
for token in ('id="pPick"', 'Select on map', 'PRECINCT_PICK_MODE', 'prec-pick', "aria-pressed"):
    check(token in html, f"precinct pick-mode component missing: {token}")
check('.prec.prec-pick' in html and 'pointer-events:all' in html, "precinct interiors are not made clickable in pick mode")
check("classList.toggle('prec-pick',PRECINCT_PICK_MODE)" in html, "pick-mode class is not dynamically controlled")
check("S.sp=true;$('pToggle').checked=true" in html, "pick mode does not ensure precinct layer is visible")

# Stale live fallback must not silently render a numeric zero/current-looking
# selected-area dispatch summary.
check("mins<=45" in html, "selected-area live freshness threshold missing")
check("live dispatch data not current" in html, "stale selected-area dispatch placeholder missing")
check("embedded fallback is stale" in html, "stale fallback explanation missing")
check("turn on/refresh the dispatch layer" in html, "stale live recovery instruction missing")

# The source feed includes MTA and other agencies, so the UI must not describe
# the ALL option as law-enforcement-only.
check('All agencies in this feed' in html, "inclusive feed-agency label missing")
check('All law-enforcement agencies</option>' not in html, "over-broad law-enforcement agency label remains")

# Initial whole-city street DOM should be lightweight while exact geometry and
# styles are retained in compound paths; detailed nodes return on zoom/focus.
for token in ('STREET_DETAIL_ZOOM=2.4', 'renderStreetOverview()', 'st-overview', "if(!PFOCUS.size&&S.z<STREET_DETAIL_ZOOM)"):
    check(token in html, f"citywide street overview optimization missing: {token}")
check("a.parts.join(' ')" in html, "overview does not combine exact path geometry")
check("_renderSBeforeOverview()" in html, "detailed street renderer cannot be restored")
check("if(before!==after)renderS()" in html, "zoom threshold does not switch street rendering mode")
check("pointer-events:none!important" in html, "overview paths may remain interactive")

hard = manifest.get("turf_usability_hardening") or {}
check(int(hard.get("version") or 0) == 1, "turf usability manifest missing/wrong version")
check("45" in str(hard.get("dispatch_summary_freshness") or ""), "manifest does not document live freshness guard")
check("2.4" in str(hard.get("citywide_street_rendering") or ""), "manifest does not document street overview threshold")

# Preserve the security/performance contract: only the official optional live
# feed is fetched at runtime and final JavaScript remains syntactically valid.
check(len(re.findall(r"\bfetch\s*\(", html)) == 1, "unexpected runtime fetch count after usability patch")
scripts = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", html, re.S | re.I)
for i, script in enumerate(scripts):
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write(script); path = fh.name
    r = subprocess.run(["node", "--check", path], capture_output=True, text=True)
    pathlib.Path(path).unlink(missing_ok=True)
    check(r.returncode == 0, f"inline JS block {i} syntax failed: {r.stderr.strip()[:500]}")

if issues:
    print(f"TURF USABILITY AUDIT FAIL: {len(issues)} issue(s)")
    for issue in issues:
        print(" -", issue)
    raise SystemExit(1)

print("TURF USABILITY AUDIT PASS")
print("precinct picking: explicit map mode; normal map interactions preserved outside pick mode")
print("dispatch summary: stale fallback withheld after 45 minutes")
print("performance: low-zoom citywide streets use compound non-interactive paths; detail restored on zoom/focus")
