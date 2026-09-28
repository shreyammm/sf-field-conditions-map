#!/usr/bin/env python3
"""Final UI pass: forest-green live safety markers + clickable source provenance."""
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "_site" / "index.html"
s = p.read_text(encoding="utf-8")


def rep(old: str, new: str, label: str, count: int = 1):
    global s
    if old not in s:
        raise SystemExit(f"final source/color patch anchor missing: {label}")
    s = s.replace(old, new, count)


# Make the live public-safety layer a dark forest green so it does not blend with
# the purple/blue high-unit parcel palette or the blue closure layer. Keep the
# Public Works work-permit teal unchanged so the two operational point layers
# still remain distinguishable.
palette = {
    "#f97316": "#166534",  # open calls / aggregate fill
    "#c2410c": "#14532d",  # aggregate outline
    "#fff7ed": "#f0fdf4",  # closed-call fill
    "#ea580c": "#166534",  # closed outline / checkbox accent / legend outline
    "#fdba74": "#86efac",  # mixed open/closed cluster
    "#7c2d12": "#052e16",  # hover outline
}
for old, new in palette.items():
    if old not in s:
        raise SystemExit(f"expected live-call palette color missing: {old}")
    s = s.replace(old, new)

s = s.replace(
    "Solid orange markers are still-open calls; hollow orange markers are closed calls;",
    "Solid forest-green markers are still-open calls; hollow forest-green markers are closed calls;",
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
print("finalized forest-green safety styling and official source links")
