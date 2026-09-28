# SF Field Conditions Map

A traceable, static San Francisco field-conditions map built from reliable public data.

The browser does **not** call DataSF at runtime. GitHub Actions retrieves official source datasets during the build, validates and filters them, and embeds the resulting GeoJSON directly into the deployed HTML. A normal page load therefore does not depend on DataSF/CORS availability.

## Current checkpoint

The map currently includes:

- active, physical/context SF Public Works street centerlines with street names and CNN segment identifiers;
- San Francisco election precinct boundaries as a neutral reference layer;
- parcel-level high-unit residential properties from SF Planning;
- 20+/50+/100+/200+ residential-unit thresholds;
- hover and click explanations;
- an in-product methodology key, source counts, exclusions, and build timestamp;
- dependency-free SVG pan/zoom rendering.

The street layer intentionally excludes Public Works source layers that are mapped-but-not-real or non-street geometry (`PAPER`, `PAPER_FWYS`, `PAPER_WATER`, `PSEUDO`, and `PRIVATE_PARKING`). “Active” in the source means “not retired”; it does **not** by itself mean publicly accessible or walkable. Private streets, pedestrian-only streets, park roads, and unpaved rights-of-way can remain as labeled context.

The residential layer is a proxy for places where many doors may be concentrated on one parcel. It does **not** establish whether a building or lobby is accessible.

## Architecture

```text
Official SF/DataSF datasets
          ↓
GitHub Actions build
          ↓
validation + documented filtering
          ↓
GeoJSON embedded into _site/index.html
          ↓
GitHub Pages
```

A failed source refresh does not replace the previously successful deployment.

## Build locally

```bash
python scripts/build_site.py
python -m http.server 8000 --directory _site
```

Then open `http://localhost:8000`.

## Deployment

The live site is deployed with `.github/workflows/pages.yml` from `main`. GitHub Pages is configured to use **GitHub Actions**. The workflow also performs a weekly refresh of the bundled public-data snapshots.

## Sources and audit trail

See [`SOURCES.md`](SOURCES.md) for dataset IDs, source semantics, filters, and caveats; [`DECISIONS.md`](DECISIONS.md) for consequential methodology choices; and `validation/` for review checkpoints. Each successful build also writes `_site/data-manifest.json` with retrieval time, source URLs, displayed/source counts, exclusions, threshold counts, and detected duplicate-source anomalies.

## Scope guardrails

This project uses public geographic and built-environment information. It does not include voter files, person-level political targeting, private canvasser observations, or proprietary campaign data.
