# SF Field Conditions Map

A traceable, static San Francisco field-conditions map built from reliable public data.

The browser does **not** call DataSF at runtime. GitHub Actions retrieves the public source datasets during the build, validates them, and embeds the resulting GeoJSON directly into the deployed HTML. That means a normal page load is not dependent on DataSF/CORS availability.

## Current checkpoint

The map currently includes:

- San Francisco election precinct boundaries as a neutral reference layer;
- large multifamily properties from SF Planning, using public residential-unit counts;
- 20+/50+/100+/200+ unit thresholds;
- hover and click explanations;
- source counts and build timestamp;
- dependency-free SVG pan/zoom rendering.

Large multifamily is shown only as a proxy for possible access friction. A large building is **not** treated as confirmed inaccessible.

## Architecture

```text
Official SF/DataSF datasets
          ↓
GitHub Actions build
          ↓
validation + field trimming
          ↓
GeoJSON embedded into _site/index.html
          ↓
GitHub Pages / other static host
```

The deployed app contains no runtime `fetch()` calls for the core layers.

## Build locally

```bash
python scripts/build_site.py
python -m http.server 8000 --directory _site
```

Then open `http://localhost:8000`.

## Deployment

A Pages workflow is included at `.github/workflows/pages.yml`. In GitHub, open **Settings → Pages** and set **Build and deployment → Source** to **GitHub Actions**. If GitHub does not allow Pages for this private repository on your plan, either make the repository public or deploy the generated `_site` directory on another static host.

## Sources

See [`SOURCES.md`](SOURCES.md) for dataset IDs, fields, and transformations. The build also writes `_site/data-manifest.json` with retrieval time, source URLs, record counts, and any source-update timestamps returned by the upstream metadata APIs.

## Scope guardrails

This project uses public geographic and built-environment information. It does not include voter files, person-level political targeting, private canvasser observations, or proprietary campaign data.
