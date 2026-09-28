# Deployment

## GitHub Pages

The repository includes `.github/workflows/pages.yml`. GitHub Pages is configured to use **GitHub Actions**. The workflow builds a self-contained site and deploys `_site`.

The workflow runs on pushes to `main`, can be run manually, and also refreshes the public-data snapshots weekly. If an official upstream source is unavailable or a validation rule fails, the build fails and the previously successful Pages deployment remains in place.

## Local build

```bash
python scripts/build_site.py
python -m http.server 8000 --directory _site
```

The generated `_site/index.html` contains the production GeoJSON inline. It has no runtime `fetch()` dependency on DataSF.

## Data refresh behavior

Each successful build:

1. downloads the official SF Elections precincts, SF Public Works streets, and SF Planning land-use GeoJSON distributions;
2. validates source structure, identifier uniqueness, expected record-count ranges, geometry types, and broad San Francisco coordinate bounds;
3. keeps only physical/context active street centerlines appropriate for the map, excluding known paper/pseudo/parking layers;
4. keeps only 20+ unit parcel-level land-use records, resolves safe exact duplicates, and fails on ambiguous threshold-crossing conflicts;
5. trims properties to fields used by the UI and future joins;
6. embeds all production FeatureCollections into `_site/index.html`;
7. writes `_site/data-manifest.json` with provenance, counts, exclusions, threshold bins, source freshness metadata, and anomaly handling;
8. uploads and deploys the Pages artifact.

Production refreshes do not silently substitute third-party datasets. If an official source fails, the previous successful site remains live.
