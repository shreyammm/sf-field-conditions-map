#!/usr/bin/env python3
"""Audit final real-time law-enforcement dispatch data and UI semantics."""
from __future__ import annotations

import collections
import json
import math
import pathlib
import re
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = ROOT / "_site" / "index.html"
MANIFEST = ROOT / "_site" / "data-manifest.json"
html = SITE.read_text(encoding="utf-8")
manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
issues: list[str] = []


def check(ok, message):
    if not ok:
        issues.append(message)


match = re.search(r"window\.SF_FIELD_DATA=(\{.*?\});\s*</script>", html, re.S)
check(bool(match), "embedded payload missing")
data = json.loads(match.group(1)) if match else {}
meta = data.get("meta") or {}
features = ((data.get("live_calls") or {}).get("features") or [])

check(meta.get("live_calls_dataset_id") == "gnap-fj3t", "wrong live-calls dataset ID")
check(50 <= len(features) <= 5000, f"live-call fallback count implausible: {len(features)}")
check(len(features) == int(meta.get("live_calls_mapped_feature_count", -1)), "live-call count/meta mismatch")
check((manifest.get("live_calls") or {}).get("dataset_id") == "gnap-fj3t", "live-call manifest missing/wrong dataset")
check(int(meta.get("live_calls_runtime_refresh_minutes") or -1) == 10, "runtime refresh metadata is not 10 minutes")
check(int(meta.get("live_calls_upstream_delay_minutes") or -1) == 10, "upstream delay metadata is not 10 minutes")
check("privacy-masked" in str(meta.get("live_calls_location_note") or "").lower(), "location privacy note missing")
check("not confirmed" in str(meta.get("live_calls_interpretation") or "").lower(), "dispatch-vs-crime interpretation missing")

ids = []
agencies = collections.Counter()
open_count = 0
for feature in features:
    props = feature.get("properties") or {}
    geom = feature.get("geometry") or {}
    check(geom.get("type") == "Point", "live-call feature has non-point geometry")
    coords = geom.get("coordinates") or []
    point_ok = False
    if isinstance(coords, list) and len(coords) >= 2:
        try:
            lon, lat = float(coords[0]), float(coords[1])
            point_ok = (
                math.isfinite(lon)
                and math.isfinite(lat)
                and -122.60 <= lon <= -122.25
                and 37.65 <= lat <= 37.90
            )
        except (TypeError, ValueError):
            pass
    check(point_ok, f"live-call point outside SF guardrail: {coords}")

    iid = str(props.get("id") or "")
    if iid:
        ids.append(iid)
    received = str(props.get("received_datetime") or "")
    check(bool(re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", received)), f"bad live-call received time: {received}")
    agency = str(props.get("agency") or "Unknown")
    agencies[agency] += 1
    check(isinstance(props.get("open"), bool), "live-call open flag is not boolean")
    if props.get("open") is True:
        open_count += 1

    # Do not embed free-text notes or raw CAD numbers; they are unnecessary for
    # route context and can add avoidable detail/noise.
    for forbidden in (
        "cad_number",
        "call_type_original_notes",
        "call_type_final_notes",
    ):
        check(forbidden not in props, f"unnecessary live-call field embedded: {forbidden}")

check(len(ids) == len(set(ids)), "duplicate public live-call IDs in fallback snapshot")
check(open_count <= int(meta.get("live_calls_open_source_count") or 0), "mapped open count exceeds source open count")
check(bool(agencies), "live-call agency set is empty")

# Product semantics: orange instead of purple; short rolling windows; Police is
# default; optional open-only filter; runtime refresh with embedded fallback.
check('<input id="iToggle" type="checkbox">' in html, "live-call layer is not opt-in")
for hours in (1, 3, 6, 12, 24, 48):
    check(f'data-hours="{hours}"' in html, f"missing {hours}-hour live-call preset")
check('data-hours="6">6 hr</button>' in html and 'pill active" data-hours="6"' in html, "6-hour window is not the default")
check('<option value="Police">Police only</option>' in html, "Police-only default agency option missing")
check('id="iOpenOnly"' in html, "open-only control missing")
check('id="iRefresh"' in html, "manual live refresh control missing")
check('#f97316' in html and '#ea580c' in html, "orange live-call palette missing")
check('#7c3aed' not in re.search(r"\.lcg\{.*?\.incidentctl", html, re.S).group(0) if re.search(r"\.lcg\{.*?\.incidentctl", html, re.S) else False, "live-call marker styling still uses purple")
check('rolling 48-hour' in html.lower() or 'rolling 48 hour' in html.lower(), "48-hour real-time source semantics missing")
check('not confirmed crimes' in html.lower() or 'not a crime count' in html.lower(), "dispatch-vs-crime caveat missing from UI")
check('privacy-mapped' in html.lower(), "privacy-mapped wording missing")
check('setInterval(refreshLiveCalls,600000)' in html, "10-minute browser refresh loop missing")
check('fetch(LIVE_CALLS_URL' in html, "live API refresh fetch missing")
check('https://data.sf.gov/resource/gnap-fj3t.json' in html, "runtime API is not official DataSF real-time calls")
check("S.ihours:6" not in html, "malformed live-call state syntax")
check("ihours:6" in html and "iagency:'Police'" in html, "live-call defaults missing from state")
check("liveFreshness" in html and "mins<=45" in html, "feed freshness/staleness check missing")
check("LIVE.source='live API'" in html and "embedded fallback" in html, "runtime/fallback source distinction missing")
check("low_zoom_aggregate" in html and "privacy_mapped_point" in html, "zoom-dependent live-call rendering missing")
check("DATA?.live_calls" in html and "renderI()" in html, "live-call payload not wired to UI")
check("$('iToggle').onchange" in html and "$('iPills').onclick" in html, "live-call controls not wired")
check("live dispatch marker" in html, "selected-feature prompt does not mention live dispatch markers")
check("sourceLink(liveSourceUrl()" in html, "live-call details lack official source link")

render_match = re.search(r"function renderI\(\).*?function renderW\(\)", html, re.S)
check(bool(render_match), "live-call render function missing")
if render_match:
    render_text = render_match.group(0).lower()
    check("precinct" not in render_text and "risk score" not in render_text, "live-call rendering appears to create precinct/risk scoring")

# Only the official DataSF live feed may be fetched at runtime.
fetch_count = len(re.findall(r"\bfetch\s*\(", html))
check(fetch_count == 1, f"unexpected runtime fetch count: {fetch_count}")

# Packaging/syntax integrity.
ids_html = re.findall(r"\bid=[\"']([^\"']+)", html)
dups = [key for key, n in collections.Counter(ids_html).items() if n > 1]
check(not dups, f"duplicate HTML ids after live-call patch: {dups[:10]}")
check(not re.search(r"<script[^>]+src=", html, re.I), "external JS dependency introduced")
check(not re.search(r"<link[^>]+rel=[\"']?stylesheet", html, re.I), "external stylesheet introduced")

scripts = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", html, re.S | re.I)
for i, script in enumerate(scripts):
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as tmp:
        tmp.write(script)
        filename = tmp.name
    result = subprocess.run(["node", "--check", filename], capture_output=True, text=True)
    pathlib.Path(filename).unlink(missing_ok=True)
    check(result.returncode == 0, f"inline JS block {i} syntax error: {result.stderr.strip()}")

if issues:
    print(f"LIVE CALL AUDIT FAIL: {len(issues)} issue(s)")
    for issue in issues:
        print(" -", issue)
    raise SystemExit(1)

print("LIVE CALL AUDIT PASS")
print(f"fallback mapped calls: {len(features):,}; agencies: {dict(agencies)}")
print(f"mapped calls currently open in fallback: {open_count:,}")
print(f"fallback data_as_of: {meta.get('live_calls_data_as_of')}")
print("UI: orange solid=open / hollow=closed; 1/3/6/12/24/48h; Police default; open-only option")
print("runtime: official DataSF refresh every 10 minutes with embedded fallback")
print("interpretation: dispatch activity only; no crime/risk/precinct score")
