#!/usr/bin/env python3
"""Guarantee a visible warning when the official closure snapshot is stale.

This runs after all UI mutation passes and before the deployment-blocking audits.
It intentionally fails closed if the final artifact cannot be patched reliably.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = ROOT / "_site" / "index.html"
MANIFEST = ROOT / "_site" / "data-manifest.json"

html = SITE.read_text(encoding="utf-8")
manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

closure = manifest.get("closures") or {}
asof_raw = str(closure.get("data_as_of") or "").strip()
retrieved_raw = str(manifest.get("retrieved_at") or "").strip()


def parse_date(value: str):
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return dt.date.fromisoformat(value[:10])
        except ValueError:
            return None


asof = parse_date(asof_raw)
build = parse_date(retrieved_raw) or dt.datetime.now(dt.timezone.utc).date()
age = (build - asof).days if asof else None

warning_phrase = "verify source if planning is time-sensitive"

# Remove any prior build-generated banner so the operation is idempotent.
html = re.sub(
    r'<div id="closureFreshnessWarning"[^>]*>.*?</div>',
    "",
    html,
    flags=re.S,
)

if age is not None and age > 2:
    date_text = asof.isoformat()
    warning = (
        '<div id="closureFreshnessWarning" class="warn" '
        'style="margin:6px 0 10px;padding:7px 8px;border:1px solid #f5c2c7;'
        'border-radius:7px;background:#fff7ed;font-size:11px;line-height:1.35">'
        f'<strong>Closure-source freshness:</strong> official source data is dated {date_text} '
        f'({age} days before this build). Please {warning_phrase}.</div>'
    )
    # Place the warning immediately under the planning-date explanation, where
    # a user is most likely to rely on closure data operationally.
    anchor = (
        '<div class="muted" style="margin-top:5px">Choose a date to show temporary '
        'closures scheduled at any point that day. Closure details still show the '
        'official start/end hours. Street-work permits use the same date when that '
        'layer is enabled.</div>'
    )
    if anchor not in html:
        raise SystemExit("freshness warning anchor missing from final artifact")
    html = html.replace(anchor, anchor + warning, 1)

SITE.write_text(html, encoding="utf-8")
print(
    "closure freshness guard:",
    f"data_as_of={asof_raw or 'unknown'}",
    f"age_days={age if age is not None else 'unknown'}",
    "warning=" + ("shown" if age is not None and age > 2 else "not needed"),
)
