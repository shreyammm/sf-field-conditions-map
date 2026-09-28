#!/usr/bin/env python3
"""Audit the final optional planning-date behavior after the general build audit."""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = ROOT / "_site" / "index.html"
html = SITE.read_text(encoding="utf-8")
issues: list[str] = []


def check(ok, message):
    if not ok:
        issues.append(message)


# Parse embedded data so this audit also confirms the final patch did not damage
# the self-contained payload.
m = re.search(r"window\.SF_FIELD_DATA=(\{.*?\});\s*</script>", html, re.S)
check(bool(m), "embedded data payload missing after planning-date patch")
data = json.loads(m.group(1)) if m else {}
check(len((data.get("closures") or {}).get("features") or []) > 0, "closure payload missing")
check(len((data.get("surface_permits") or {}).get("features") or []) > 0, "permit payload missing")

# Controls and defaults.
check('<input id="cTime" type="date" aria-label="Planning date in San Francisco">' in html, "planning control is not an optional date input")
check('id="cClear"' in html and '>Clear</button>' in html, "clear-date control missing")
check('id="cNow"' in html and '>Today</button>' in html, "Today shortcut missing")
check('type="datetime-local"' not in html, "old date/time input remains")
check('Plan for a date' in html and '(optional)' in html, "optional-date label missing")
check('<input id="cToggle" type="checkbox" checked>' in html, "closure layer is not ready to appear after date selection")
check('<input id="wToggle" type="checkbox">' in html, "dense ROW-permit layer is not off by default")
# Other independent layers may initialize after the planning date is cleared.
# What matters is that S.ct and the input are empty before date-dependent layers
# render.
check(
    bool(re.search(
        r"S\.ct='';\$\('cTime'\)\.value='';(?:initIncidentControls\(\);)?renderS\(\);renderP\(\);renderM\(\);renderW\(\);renderC\(\);",
        html,
    )),
    "map initializes with a planning date instead of no date",
)
check("$('cClear').onclick=()=>{S.ct='';$('cTime').value='';renderC();renderW()}" in html, "Clear does not remove date-dependent layers")
check("$('cNow').onclick=()=>{S.ct=sfNowLocal().slice(0,10);$('cTime').value=S.ct;renderC();renderW()}" in html, "Today shortcut does not use SF calendar date")

# Closure semantics: any overlap with the selected SF day, not exact selected hour.
check("a<nextStart&&b>=dayStart" in html, "closure predicate is not day-overlap based")
check("nextStart=nx+'T00:00:00'" in html, "closure day boundary calculation missing")
check("Choose a planning date to display temporary closures" in html, "no-date closure status missing")
check("scheduled" in html and "fmtDateOnly(q)" in html, "selected-day closure status missing")
check("closureTimeText" in html and "fmtSFLocal" in html, "exact closure hours are no longer available in details")
check("scheduled on selected date" in html, "closure legend still implies exact-time filtering")
check("selected <em>San Francisco local wall time</em>" not in html, "old exact-time methodology wording remains")

# Permit semantics: same optional date, but still opt-in and support-window bounded.
check("if(S.swk)addMarker" in html, "ROW permits create SVG markers while layer is off")
check("wl.style.display=S.swk&&!!q?'':'none'" in html, "ROW permits are visible without both date and toggle")
check("Choose a planning date to filter permit windows" in html, "no-date permit status missing")

# General packaging integrity after the last UI mutation. The one intentional
# runtime request is the official DataSF real-time calls feed; all other layers
# remain embedded/static.
ids = re.findall(r"\bid=[\"']([^\"']+)", html)
seen = set()
dup = []
for x in ids:
    if x in seen:
        dup.append(x)
    seen.add(x)
check(not dup, f"duplicate HTML ids after planning-date patch: {dup[:10]}")
fetch_count = len(re.findall(r"\bfetch\s*\(", html))
if fetch_count:
    check(fetch_count == 1, f"unexpected number of runtime fetch calls: {fetch_count}")
    check("fetch(LIVE_CALLS_URL" in html, "runtime fetch is not the whitelisted live-calls request")
    check("https://data.sf.gov/resource/gnap-fj3t.json" in html, "live-calls request is not pointed at official DataSF")
check(not re.search(r"<script[^>]+src=", html, re.I), "external JS dependency introduced")
check(not re.search(r"<link[^>]+rel=[\"']?stylesheet", html, re.I), "external stylesheet introduced")

scripts = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", html, re.S | re.I)
for i, script in enumerate(scripts):
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as tmp:
        tmp.write(script)
        name = tmp.name
    result = subprocess.run(["node", "--check", name], capture_output=True, text=True)
    pathlib.Path(name).unlink(missing_ok=True)
    check(result.returncode == 0, f"inline JS block {i} syntax error after planning-date patch: {result.stderr.strip()}")

if issues:
    print(f"PLANNING DATE AUDIT FAIL: {len(issues)} issue(s)")
    for issue in issues:
        print(" -", issue)
    raise SystemExit(1)

print("PLANNING DATE AUDIT PASS")
print("default: no planning date; closures hidden until date selection")
print("closure rule: show when official local interval overlaps any portion of selected SF calendar day")
print("permit rule: same selected calendar date, still opt-in and support-window bounded")
print("runtime exception: one whitelisted official DataSF live-calls refresh")
