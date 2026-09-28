#!/usr/bin/env python3
"""Final UI pass: high-contrast forest-green live safety markers + clickable source provenance."""
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "_site" / "index.html"
s = p.read_text(encoding="utf-8")


def rep(old: str, new: str, label: str, count: int = 1):
    global s
    if old not in s:
        raise SystemExit(f"final source/color patch anchor missing: {label}")
    s = s.replace(old, new, count)


# Use a very dark forest green for live public-safety activity. The live-call
# layer needs to remain legible on top of orange/red hill streets, teal parcel
# outlines, purple/blue apartment fills, and blue closure lines. Open calls are
# darkest; closed calls remain filled (rather than nearly white/hollow) so they
# do not disappear into the parcel/street texture.
palette = {
    "#f97316": "#064e3b",  # open calls / aggregate fill
    "#c2410c": "#022c22",  # aggregate outline
    "#fff7ed": "#34d399",  # closed-call fill
    "#ea580c": "#065f46",  # closed outline / checkbox accent / legend outline
    "#fdba74": "#10b981",  # mixed open/closed cluster
    "#7c2d12": "#022c22",  # hover outline
}
for old, new in palette.items():
    if old not in s:
        raise SystemExit(f"expected live-call palette color missing: {old}")
    s = s.replace(old, new)

# Strengthen contrast beyond hue alone. Low-zoom aggregates get substantially
# more fill opacity and a dark border. Point markers get thicker outlines and a
# subtle halo so they remain visually separable from parcel polygons and street
# lines underneath.
rep(
    ".lcg{fill:#064e3b;fill-opacity:.20;stroke:#022c22;stroke-opacity:.72;stroke-width:1.5;vector-effect:non-scaling-stroke;cursor:pointer;pointer-events:all}",
    ".lcg{fill:#064e3b;fill-opacity:.46;stroke:#022c22;stroke-opacity:.96;stroke-width:1.8;vector-effect:non-scaling-stroke;cursor:pointer;pointer-events:all;filter:drop-shadow(0 0 1.2px rgba(255,255,255,.95))}",
    "aggregate safety contrast",
)
rep(
    ".lcg:hover{fill-opacity:.33;stroke-opacity:1;stroke-width:2.2}",
    ".lcg:hover{fill-opacity:.64;stroke-opacity:1;stroke-width:2.5}",
    "aggregate safety hover",
)
rep(
    ".lcp{fill:#064e3b;fill-opacity:.90;stroke:#fff;stroke-width:1.5;vector-effect:non-scaling-stroke;cursor:pointer;pointer-events:all}",
    ".lcp{fill:#064e3b;fill-opacity:.98;stroke:#fff;stroke-width:2;vector-effect:non-scaling-stroke;cursor:pointer;pointer-events:all;filter:drop-shadow(0 0 1.2px rgba(2,44,34,.42))}",
    "open-call safety contrast",
)
rep(
    ".lcp.closed{fill:#34d399;fill-opacity:.96;stroke:#065f46;stroke-width:1.8}",
    ".lcp.closed{fill:#34d399;fill-opacity:.78;stroke:#064e3b;stroke-width:2.2}",
    "closed-call safety contrast",
)
rep(
    ".lcp.mixed{fill:#10b981;fill-opacity:.94;stroke:#fff;stroke-width:1.5}",
    ".lcp.mixed{fill:#10b981;fill-opacity:.92;stroke:#fff;stroke-width:2}",
    "mixed-call safety contrast",
)
rep(
    ".lcp:hover{stroke:#022c22;stroke-width:2.2}",
    ".lcp:hover{stroke:#022c22;stroke-width:2.7;fill-opacity:1}",
    "point safety hover",
)

s = s.replace(
    "Solid orange markers are still-open calls; hollow orange markers are closed calls;",
    "Dark forest-green markers are still-open calls; lighter filled green markers with a dark outline are closed calls;",
    1,
)

# Small, unobtrusive provenance links that work both in the source directory and
# inline inside the methodology items.
rep(
    ".refreshbtn:hover{background:#f9fafb}",
    ".refreshbtn:hover{background:#f9fafb}"
    ".src-link{font-size:11px;font-weight:650;color:#175cd3;text-decoration:none;white-space:nowrap}"
    ".src-link:hover{text-decoration:underline}"
    ".sourcebox{margin:4px 0 10px;padding:9px 10px;border:1px solid #eaecf0;border-radius:8px;background:#f9fafb}"
    ".sourcebox strong{color:#344054}"
    ".sourcegrid{display:flex;flex-wrap:wrap;gap:6px 10px;margin-top:6px}"
    ".sourcegrid a{font-size:11px;font-weight:650;color:#175cd3;text-decoration:none}"
    ".sourcegrid a:hover{text-decoration:underline}",
    "source link CSS",
)

sources = [
    ("Street centerlines", "3psu-pn9h"),
    ("Elevation contours", "rnbg-2qxw"),
    ("Election precincts", "d6x4-hefw"),
    ("Residential parcels", "c5ge-t6pj"),
    ("Temporary closures", "8x25-yybr"),
    ("Street / ROW permits", "bpc9-7sus"),
    ("Live dispatch calls", "gnap-fj3t"),
]
source_grid = '<div class="sourcebox"><strong>Official data sources</strong><div class="muted">Open the exact City/DataSF datasets used by the map to manually verify the source records and field definitions.</div><div class="sourcegrid">' + ''.join(
    f'<a href="https://data.sf.gov/d/{dataset_id}" target="_blank" rel="noopener noreferrer">{label} ↗</a>'
    for label, dataset_id in sources
) + '</div></div>'
rep(
    '<summary>How this map is computed</summary>',
    '<summary>How this map is computed</summary>' + source_grid,
    "methodology source directory",
)

# Put a direct source link beside the dataset ID in every source-backed
# methodology section. This is deliberately redundant with the directory above:
# someone reading one specific key item can verify it without scrolling.
for dataset_id in [
    "3psu-pn9h",
    "rnbg-2qxw",
    "d6x4-hefw",
    "c5ge-t6pj",
    "8x25-yybr",
    "bpc9-7sus",
    "gnap-fj3t",
]:
    old = f'<span class="code">{dataset_id}</span>'
    new = (
        old
        + f' <a class="src-link" href="https://data.sf.gov/d/{dataset_id}" '
        + 'target="_blank" rel="noopener noreferrer">official source ↗</a>'
    )
    rep(old, new, f"inline source link {dataset_id}")

p.write_text(s, encoding="utf-8")
print("finalized high-contrast forest-green safety styling and official source links")
