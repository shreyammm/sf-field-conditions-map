#!/usr/bin/env python3
"""Deployment-blocking audit for the precinct reported-incident context index."""
from __future__ import annotations

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


def check(ok, msg):
    if not ok:
        issues.append(msg)


m = re.search(r"window\.SF_FIELD_DATA=(\{.*?\});\s*</script>", html, re.S)
check(bool(m), "embedded payload missing")
data = json.loads(m.group(1)) if m else {}
precincts = ((data.get("precincts") or {}).get("features") or [])
prec_ids = {
    str((f.get("properties") or {}).get("prec_2022") or (f.get("properties") or {}).get("precinct") or (f.get("properties") or {}).get("id") or "").strip()
    for f in precincts
}
check(bool(prec_ids) and "" not in prec_ids, "official precinct ids missing")
idx = data.get("precinct_incident_index") or {}
rows = idx.get("precincts") or []
row_ids = [str(r.get("precinct") or "") for r in rows]
check(set(row_ids) == prec_ids, "incident-index precinct id set does not exactly match official precinct geometry")
check(len(row_ids) == len(set(row_ids)), "duplicate precinct row in incident index")
check(idx.get("source_dataset_id") == "wg3w-h783", "incident-index embedded source id drift")

WINDOWS = (30, 90, 180, 365)
assigned365 = 0.0
for r in rows:
    pid = str(r.get("precinct") or "")
    ws = r.get("windows") or {}
    check(set(ws.keys()) == {str(x) for x in WINDOWS}, f"precinct {pid} missing requested windows")
    prev_reports = prev_weighted = -1.0
    for days in WINDOWS:
        w = ws.get(str(days)) or {}
        try:
            reports = float(w.get("reports"))
            weighted = float(w.get("weighted"))
            reports30 = float(w.get("reports_per30"))
            weighted30 = float(w.get("weighted_per30"))
            index = float(w.get("index"))
            rank = int(w.get("rank"))
        except Exception:
            issues.append(f"precinct {pid}/{days} contains malformed numeric values")
            continue
        check(math.isfinite(reports) and reports >= 0, f"precinct {pid}/{days} reports invalid")
        check(math.isfinite(weighted) and weighted >= 0, f"precinct {pid}/{days} weighted invalid")
        check(reports + 1e-6 >= prev_reports, f"precinct {pid} reports are not monotonic by window")
        check(weighted + 1e-6 >= prev_weighted, f"precinct {pid} weighted load is not monotonic by window")
        prev_reports, prev_weighted = reports, weighted
        check(abs(reports30 - round(reports * 30.0 / days, 2)) <= 0.011, f"precinct {pid}/{days} reports_per30 formula mismatch")
        check(abs(weighted30 - round(weighted * 30.0 / days, 2)) <= 0.011, f"precinct {pid}/{days} weighted_per30 formula mismatch")
        check(0 <= index <= 100, f"precinct {pid}/{days} index outside 0-100")
        check(1 <= rank <= len(rows), f"precinct {pid}/{days} rank outside precinct count")
        tiers = w.get("tiers") or {}
        vals = []
        for t in (1, 2, 3, 4):
            try:
                x = float(tiers.get(str(t), 0))
            except Exception:
                x = -1
            check(x >= 0 and math.isfinite(x), f"precinct {pid}/{days} tier {t} invalid")
            vals.append(max(0, x))
        check(abs(sum(vals) - reports) <= 0.006, f"precinct {pid}/{days} tier counts do not sum to reports")
        check(abs(sum((i + 1) * x for i, x in enumerate(vals)) - weighted) <= 0.006, f"precinct {pid}/{days} tier weights do not reproduce weighted load")
        if days == 365:
            assigned365 += reports

for days in WINDOWS:
    vals = [(str(r.get("precinct")), (r.get("windows") or {}).get(str(days)) or {}) for r in rows]
    ordered = sorted(vals, key=lambda x: (-float(x[1].get("weighted_per30") or 0), x[0]))
    n = max(1, len(ordered))
    for pos, (pid, w) in enumerate(ordered, 1):
        value = float(w.get("weighted_per30") or 0)
        actual_rank = int(w.get("rank") or 0)
        if pos > 1:
            prev_rank = int(ordered[pos - 2][1].get("rank") or 0)
            check(actual_rank >= prev_rank, f"{days}d rank ordering is not monotonic at precinct {pid}")
        expected_index = 0.0 if value <= 0 else (100.0 if n == 1 else 100.0 * (n - actual_rank) / (n - 1))
        check(abs(float(w.get("index") or 0) - round(expected_index, 1)) <= 0.11, f"{pid}/{days} index does not match documented rank transform")
    if ordered:
        check(int(ordered[0][1].get("rank") or 0) == 1, f"{days}d top weighted precinct is not rank 1")
        check(abs(float(ordered[0][1].get("index") or 0) - 100) <= 0.11, f"{days}d top rank index is not 100")

meta = manifest.get("precinct_incident_index") or {}
check(meta.get("dataset_id") == "wg3w-h783", "incident-index manifest source id drift")
check(meta.get("windows_days") == [30, 90, 180, 365], "incident-index manifest window set drift")
check("one record per incident_id" in str(meta.get("incident_dedupe_rule") or ""), "incident-index dedupe rule missing")
check("split equally" in str(meta.get("boundary_allocation_rule") or "").lower(), "incident-index boundary split rule missing")
check("weighted_per30" in str(meta.get("score_formula") or "") and "rank 1" in str(meta.get("score_formula") or "").lower(), "incident-index formula missing")
check("not an sfpd severity" in str(meta.get("severity_interpretation") or "").lower(), "product-defined severity caveat missing")
check("privacy" in str(meta.get("privacy_caveat") or "").lower(), "privacy-mapped precinct caveat missing")
check(abs(float(meta.get("assigned_scored_365d_total") or -1) - assigned365) <= 0.02, "365d assigned total disagrees with embedded index")
check(abs(float(meta.get("assigned_scored_365d_total") or -1) - float(meta.get("scored_mapped_365d_incidents") or -2)) <= 0.02, "boundary splitting did not preserve mapped scored 365d total")

# The product-defined severity-weighted index remains in the build only as an
# audited experimental data artifact. Its previous user-facing methodology and
# selected-area summary are intentionally retired in favor of the simpler raw
# 365-day frequency overlay requested for field use.
check("wg3w-h783" in html, "incident source provenance missing from final artifact")
check('<div class="methoditem"><strong>Precinct reported-incident context index</strong><br>' not in html, "retired weighted-index methodology is still visible")
check("updateIncidentIndexSummary=function(){document.querySelector('.incidentIndexSummary')?.remove()}" in html, "weighted selected-area summary is not explicitly retired")
check("crime risk score" not in html.lower(), "UI presents incident context as a crime-risk score")
check("not a safety score" in html.lower(), "raw-frequency non-safety-score caveat missing")
check(len(re.findall(r"\bfetch\s*\(", html)) == 1, "incident index introduced an additional runtime fetch")

scripts = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", html, re.S | re.I)
for i, script in enumerate(scripts):
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write(script)
        p = fh.name
    r = subprocess.run(["node", "--check", p], capture_output=True, text=True)
    pathlib.Path(p).unlink(missing_ok=True)
    check(r.returncode == 0, f"inline JS block {i} syntax failed: {r.stderr.strip()[:500]}")

if issues:
    print(f"PRECINCT INCIDENT INDEX AUDIT FAIL: {len(issues)} issue(s)")
    for x in issues:
        print(" -", x)
    raise SystemExit(1)
print("PRECINCT INCIDENT INDEX AUDIT PASS")
print(f"precincts={len(rows)}; assigned scored reports (365d)={assigned365:.3f}; boundary splits={meta.get('boundary_split_unique_incidents')}")
print("interpretation: relative severity-weighted reported-incident context; not an SFPD severity or safety/risk probability")
