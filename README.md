# SF Field Conditions Map

A traceable San Francisco field-conditions map built from official public data, with explicit limits on what each layer means.

Stable map layers are fetched and validated by GitHub Actions, then embedded directly into the deployed HTML. The only intentional runtime data request is the **optional real-time law-enforcement dispatch layer**: when a user turns that layer on, the page requests the official DataSF feed and refreshes it at most every 10 minutes. An audited recent fallback snapshot is embedded in the page, so failure of that live request does not break the map.

## Current production layers

The map currently includes:

- active SF Public Works street centerlines used as physical/context route geometry, with street names and CNN segment identifiers;
- San Francisco election precinct boundaries as a **reference-only** layer;
- parcel-level high-unit residential properties from SF Planning with 20+/50+/100+/200+ thresholds;
- contour-supported street steepness estimates derived from official 5-foot elevation contours, with high/medium/low confidence and unavailable segments shown explicitly;
- an **optional planning date** that reveals SFMTA-permitted temporary street closures whose official intervals overlap any part of that San Francisco calendar day;
- exact closure start/end hours retained in details even though visibility is day-level;
- SF Public Works current/upcoming street-work / right-of-way permit points, filtered by the same selected calendar date and shown only within the source snapshot's supported current/upcoming window;
- an **optional live law-enforcement dispatch layer** using DataSF's real-time Calls for Service feed, with 1/3/6/12/24/48-hour received-time filters, Police-only/all-agency filtering, and an open-calls-only option;
- hover/click explanations, linked official sources, source freshness/status information, and methodology notes;
- dependency-free SVG pan/zoom rendering in the browser.

## Interpretation guardrails

### Streets

The map starts from `active = true` in DataSF's Streets – Active and Retired dataset, then excludes source-layer categories `PAPER`, `PAPER_FWYS`, `PAPER_WATER`, `PSEUDO`, and `PRIVATE_PARKING` as a product rule for physical route context. “Active” means not retired; it does **not** establish public access or walkability. Private streets, pedestrian-only streets, park roads, and unpaved rights-of-way can remain as labeled context.

### Residential parcels

The high-unit layer uses SF Planning parcel geometry and `resunits`. A parcel is **not necessarily a building footprint** and may include yards, parking, or multiple structures. Unit count is a proxy for residential concentration, not proof that a lobby or building is accessible.

### Hills

Hill values are a derived analytical estimate, not an official engineering street-grade survey. The build intersects non-freeway street centerlines with official 5-foot contours and uses accepted consecutive contour intervals. Same-elevation spans contribute zero net rise; non-5-foot jumps and implausible short-span artifacts are rejected. Confidence reflects evidence and supported segment coverage. Streets without enough evidence stay unavailable; freeway/ramp context is not assigned a canvassing hill grade.

### Temporary closures

The closure layer contains only rows with `status = Permitted` from the official SFMTA Temporary Street Closures feed. It is hidden until a planning date is chosen. A line appears when its official local start/end interval overlaps any portion of the selected day. The line is a street/vehicle-disruption indicator, **not proof that pedestrians cannot pass**, and SFMTA notes that the feed does not include every closure managed by other City departments. Source freshness is displayed; time-sensitive planning should verify the official source if its `data_as_of` timestamp is old.

For Special Traffic Permit rows, the detail panel may show nearby Public Works permit context only when street name, date overlap, and a <=120 m spatial condition all match. Those records are explicitly labeled as **related context, not a causal join**.

### Street-work / ROW permits

This layer shows official Public Works permit **points**, not exact work footprints. A permit window means authorization exists during that period; it does not prove crews are physically present, that a street is closed, or that pedestrians cannot pass. Multiple source rows with the same permit/type/exact point/window are aggregated into one marker while preserving distinct source location and description text. The layer is off by default and is suppressed outside the source's documented current/+14-day support window.

### Live law-enforcement dispatches

The live layer uses DataSF dataset `gnap-fj3t`, Law Enforcement Dispatched Calls for Service: Real-Time. DataSF documents the upstream table as calls closed in the last 48 hours plus calls that remain open; rare older open/reopened records can therefore exist upstream. The map itself filters by **received time** to the selected 1–48 hour window.

The build-time fallback queries only the preceding 49 SF-local hours, validates one unique documented `cad_number` per source row, fails if the query reaches its safety cap, and rejects a feed that is more than 180 minutes stale. At runtime the same checks are applied before replacing the audited fallback. The page does not request this live feed until the optional layer is enabled.

These are **dispatched calls, not confirmed crimes**. A caller can be mistaken, not every dispatch results in a crime or incident report, and not every crime produces a dispatch. Public locations are privacy-mapped to intersections; sensitive call types can have location fields suppressed. The map does not compute a neighborhood or precinct safety/risk score.

## Architecture

```text
Official SF/DataSF datasets
          ↓
GitHub Actions build
          ↓
validation + documented filtering / derivation
          ↓
core artifact audits
          ↓
final planning-date + optional live-layer UI passes
          ↓
final semantic accuracy pass
          ↓
deep end-to-end production audit
          ↓
GitHub Pages
```

A failed source refresh or failed audit does **not** replace the previously successful deployment.

## Build locally

```bash
python -m pip install shapely==2.1.2
python scripts/build_site.py
python scripts/direct_contour_hills.py
python scripts/add_closures.py
python scripts/add_surface_permits.py
python scripts/add_live_calls.py
python scripts/enrich_closure_context.py
python scripts/patch_hill_ui.py
python scripts/fix_hill_text.py
python scripts/flag_low_confidence_hills.py
python scripts/patch_closure_ui.py
python scripts/prepare_surface_banner.py
python scripts/patch_surface_permit_ui.py
python scripts/refine_surface_permit_ui.py
python scripts/finalize_audit_ui.py
python scripts/finalize_permit_aggregation_ui.py
python scripts/refine_closure_context_ui.py
python scripts/audit_closure_context.py
python scripts/audit_build.py
python scripts/optional_planning_date_ui.py
python scripts/patch_live_calls_ui.py
python scripts/finalize_source_links_and_safety_color.py
python scripts/final_accuracy_pass.py
python scripts/audit_planning_date.py
python scripts/deep_accuracy_audit.py
python -m http.server 8000 --directory _site
```

Then open `http://localhost:8000`.

## Deployment and audit trail

The live site is deployed from `main` by `.github/workflows/pages.yml`. Bundled dynamic sources are refreshed daily; the optional dispatch overlay can refresh from DataSF while enabled.

Each successful build writes `_site/data-manifest.json` with source identifiers/URLs, retrieval and source timestamps, source/display counts, exclusions, parcel duplicate handling, hill confidence/support, closure validation, permit aggregation/support-window metadata, live-feed freshness/query guardrails, and final interpretation rules.

See [`SOURCES.md`](SOURCES.md) for source contracts and caveats, [`DECISIONS.md`](DECISIONS.md) for methodology decisions, and [`ACCURACY_AUDIT.md`](ACCURACY_AUDIT.md) for the production accuracy checklist and known limitations.

## Scope guardrails

This project uses public geographic, infrastructure, permitting, and operational dispatch information. It does not include voter files, person-level political targeting, private canvasser observations, or proprietary campaign data. Precincts are displayed only as reference geography; the project does not calculate a political targeting score, neighborhood safety score, or precinct ranking.
