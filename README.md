# SF Field Conditions Map

A traceable, static San Francisco field-conditions map built from reliable public data.

The browser does **not** call DataSF at runtime. GitHub Actions retrieves official source datasets during the build, validates and filters them, and embeds the resulting data directly into the deployed HTML. A normal page load therefore does not depend on DataSF/CORS availability.

## Current checkpoint

The map currently includes:

- active, physical/context SF Public Works street centerlines with street names and CNN segment identifiers;
- San Francisco election precinct boundaries as a neutral reference layer;
- parcel-level high-unit residential properties from SF Planning with 20+/50+/100+/200+ thresholds;
- a contour-supported street hill/steepness layer derived from official 5-foot SF elevation contours, with high/medium/low confidence and unavailable segments shown explicitly;
- SFMTA-permitted temporary street-closure lines filtered by a selectable San Francisco date/time;
- SF Public Works current/upcoming street-work / right-of-way permit points filtered by the selected San Francisco calendar date and shown only within the snapshot's supported current/upcoming window;
- hover and click explanations;
- an in-product methodology key, source counts, exclusions, and build/retrieval status;
- dependency-free SVG pan/zoom rendering in the browser.

The street layer intentionally excludes Public Works source layers that are mapped-but-not-real or non-street geometry (`PAPER`, `PAPER_FWYS`, `PAPER_WATER`, `PSEUDO`, and `PRIVATE_PARKING`). “Active” in the source means “not retired”; it does **not** by itself mean publicly accessible or walkable. Private streets, pedestrian-only streets, park roads, and unpaved rights-of-way can remain as labeled context.

The residential layer is a proxy for places where many doors may be concentrated on one parcel. It does **not** establish whether a building or lobby is accessible.

The hill layer is an analytical contour-supported estimate, not an official engineering street-grade survey. Streets without enough direct contour evidence remain unavailable; freeway/ramp context is not assigned a canvassing hill grade.

The closure layer is an SFMTA street/vehicle-disruption indicator. It does not imply that pedestrian passage is blocked, and the SFMTA feed does not include every closure managed by other City departments.

The street-work / ROW layer shows official Public Works permit **points**, not exact work footprints. A permit window means the City has authorized street/sidewalk use during that period; it does not prove crews are physically working at the selected moment, that the street is closed, or that pedestrians cannot pass. Some permits publish multiple street-location rows at one official point; those rows are represented by one marker while all distinct source location text is retained in its details. Because thousands of permit windows can overlap a date, this layer is off by default and its SVG markers are not created until the layer is enabled.

## Architecture

```text
Official SF/DataSF datasets
          ↓
GitHub Actions build
          ↓
validation + documented filtering/derivation
          ↓
final-artifact invariant audit
          ↓
self-contained data embedded into _site/index.html
          ↓
GitHub Pages
```

A failed source refresh **or failed final-artifact audit** does not replace the previously successful deployment.

## Build locally

```bash
python -m pip install shapely==2.1.2
python scripts/build_site.py
python scripts/direct_contour_hills.py
python scripts/add_closures.py
python scripts/add_surface_permits.py
python scripts/patch_hill_ui.py
python scripts/fix_hill_text.py
python scripts/flag_low_confidence_hills.py
python scripts/patch_closure_ui.py
python scripts/prepare_surface_banner.py
python scripts/patch_surface_permit_ui.py
python scripts/refine_surface_permit_ui.py
python scripts/finalize_audit_ui.py
python scripts/finalize_permit_aggregation_ui.py
python scripts/audit_build.py
python -m http.server 8000 --directory _site
```

Then open `http://localhost:8000`.

## Deployment

The live site is deployed with `.github/workflows/pages.yml` from `main`. GitHub Pages is configured to use **GitHub Actions**. The temporary-closure and current/upcoming street-surface permit sources are daily feeds, so the workflow refreshes the bundled public-data snapshot daily.

Deployment only proceeds after the independent final-artifact audit passes. That audit checks the finished embedded data and UI rather than assuming each intermediate script produced the intended result.

## Sources and audit trail

See [`SOURCES.md`](SOURCES.md) for dataset IDs, source semantics, filters, and caveats; [`DECISIONS.md`](DECISIONS.md) for consequential methodology choices; and `validation/` for review checkpoints. Each successful build also writes `_site/data-manifest.json` with retrieval time, source URLs, displayed/source counts, exclusions, hill coverage/confidence, closure status/type validation, surface-permit aggregation/support-window metadata, threshold counts, and detected source anomalies.

## Scope guardrails

This project uses public geographic and built-environment information. It does not include voter files, person-level political targeting, private canvasser observations, or proprietary campaign data.
