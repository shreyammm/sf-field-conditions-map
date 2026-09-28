#!/usr/bin/env python3
"""Audit live dispatch semantics, high-contrast forest styling, and clickable provenance."""
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
    check(
        bool(re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", received)),
        f"bad live-call received time: {received}",
    )
    agency = str(props.get("agency") or "Unknown")
    agencies[agency] += 1
    check(isinstance(props.get("open"), bool), "live-call open flag is not boolean")
    if props.get("open") is True:
        open_count += 1

    for forbidden in (
        "cad_number",
        "call_type_original_notes",
        "call_type_final_notes",
    ):
        check(forbidden not in props, f"unnecessary live-call field embedded: {forbidden}")

check(len(ids) == len(set(ids)), "duplicate public live-call IDs in fallback snapshot")
check(open_count <= int(meta.get("live_calls_open_source_count") or 0), "mapped open count exceeds source open count")
check(bool(agencies), "live-call agency set is empty")

# Product semantics: very dark forest green, short rolling windows, Police
# default, optional open-only filter, runtime refresh with embedded fallback.
check('<input id="iToggle" type="checkbox">' in html, "live-call layer is not opt-in")
for hours in (1, 3, 6, 12, 24, 48):
    check(f'data-hours="{hours}"' in html, f"missing {hours}-hour live-call preset")
check('pill active" data-hours="6"' in html, "6-hour window is not the default")
check('<option value="Police">Police only</option>' in html, "Police-only default agency option missing")
check('id="iOpenOnly"' in html, "open-only control missing")
check('id="iRefresh"' in html, "manual live refresh control missing")
check('#064e3b' in html and '#022c22' in html and '#34d399' in html, "high-contrast forest-green live-call palette missing")
live_css = re.search(r"\.lcg\{.*?\.incidentctl", html, re.S)
check(bool(live_css), "live-call CSS block missing")
if live_css:
    css = live_css.group(0).lower()
    check('#f97316' not in css and '#ea580c' not in css and '#7c3aed' not in css, "old orange/purple color remains in live-call CSS")
    check('fill-opacity:.46' in css, "low-zoom safety aggregates are still too faint")
    check('stroke-width:2.2' in css, "closed-call outline was not strengthened")
    check('drop-shadow' in css, "safety markers lack contrast halo")
check("Dark forest-green markers" in html, "methodology does not describe dark forest-green live markers")
check('rolling 48-hour' in html.lower() or 'rolling 48 hour' in html.lower(), "48-hour real-time source semantics missing")
check('not confirmed crimes' in html.lower() or 'not a crime count' in html.lower(), "dispatch-vs-crime caveat missing from UI")
check('privacy-mapped' in html.lower(), "privacy-mapped wording missing")
check('setInterval(refreshLiveCalls,600000)' in html, "10-minute browser refresh loop missing")
check('fetch(LIVE_CALLS_URL' in html, "live API refresh fetch missing")
check('https://data.sf.gov/resource/gnap-fj3t.json' in html, "runtime API is not official DataSF real-time calls")
check("ihours:6" in html and "iagency:'Police'" in html, "live-call defaults missing from state")
check("liveFreshness" in html and "mins<=45" in html, "feed freshness/staleness check missing")
check("LIVE.source='live API'" in html and "embedded fallback" in html, "runtime/fallback source distinction missing")
check("low_zoom_aggregate" in html and "privacy_mapped_point" in html, "zoom-dependent live-call rendering missing")
check("DATA?.live_calls" in html and "renderI()" in html, "live-call payload not wired to UI")
check("$('iToggle').onchange" in html and "$('iPills').onclick" in html, "live-call controls not wired")
check("live dispatch marker" in html, "selected-feature prompt does not mention live dispatch markers")
check("sourceLink(liveSourceUrl()" in html, "live-call details lack official source link")

# Every production source represented in the methodology key has a direct
# official DataSF link. These are stable dataset-ID links rather than search
# results or third-party summaries.
source_ids = (
    "3psu-pn9h",
    "rnbg-2qxw",
    "d6x4-hefw",
    "c5ge-t6pj",
    "8x25-yybr",
    "bpc9-7sus",
    "gnap-fj3t",
)
check('Official data sources' in html, "official source directory missing from methodology key")
for dataset_id in source_ids:
    href = f'href="https://data.sf.gov/d/{dataset_id}"'
    check(html.count(href) >= 2, f"{dataset_id} does not have both directory and inline methodology links")
check(html.count('class="src-link"') >= len(source_ids), "inline source-link styling is not applied to all production sources")
check('target="_blank" rel="noopener noreferrer"' in html, "source links do not use safe external-link attributes")

# Only the official DataSF live feed may be fetched at runtime.
fetch_count = len(re.findall(r"\bfetch\s*\(", html))
check(fetch_count == 1, f"unexpected runtime fetch count: {fetch_count}")

# Packaging/syntax integrity.
ids_html = re.findall(r"\bid=[\"']([^\"']+)", html)
dups = [key for key, n in collections.Counter(ids_html).items() if n > 1]
check(not dups, f"duplicate HTML ids after final UI patch: {dups[:10]}")
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
    print(f"LIVE/SOURCE AUDIT FAIL: {len(issues)} issue(s)")
    for issue in issues:
        print(" -", issue)
    raise SystemExit(1)

print("LIVE/SOURCE AUDIT PASS")
print(f"fallback mapped calls: {len(features):,}; agencies: {dict(agencies)}")
print(f"mapped calls currently open in fallback: {open_count:,}")
print(f"fallback data_as_of: {meta.get('live_calls_data_as_of')}")
print("UI: high-contrast forest-green solid=open / medium-green filled=closed; stronger low-zoom fill + halo")
print("provenance: all seven production source datasets linked in methodology directory and inline")
print("runtime: official DataSF refresh every 10 minutes with embedded fallback")
