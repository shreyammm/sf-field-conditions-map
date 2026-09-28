# Deployment

## GitHub Pages

The repository includes `.github/workflows/pages.yml`. The workflow builds a self-contained site and deploys the `_site` directory as a GitHub Pages artifact.

### One-time GitHub setting

Open the repository and go to:

**Settings → Pages → Build and deployment → Source → GitHub Actions**

After that, push to `main` or run **Actions → Build and deploy map → Run workflow**.

The workflow also refreshes the bundled public-data snapshot weekly. If a refresh build fails because an upstream API is unavailable, the previously successful Pages deployment is not replaced.

### Private-repository note

GitHub Pages availability for private repositories depends on the GitHub plan. If GitHub does not offer Pages for this private repository, either make the repository public or deploy the generated `_site` directory to another static host.

## Local build

```bash
python scripts/build_site.py
python -m http.server 8000 --directory _site
```

The generated `_site/index.html` contains the precinct and multifamily GeoJSON inline, so it has no runtime dependency on DataSF.

## Data refresh behavior

Each build:

1. requests the official precinct and SF Planning land-use sources;
2. validates basic shape/count assumptions;
3. trims properties to the fields used by the UI;
4. embeds both FeatureCollections into the generated HTML;
5. writes `data-manifest.json` with source provenance and counts;
6. uploads the generated site as the Pages artifact.

The precinct layer has a documented versioned public fallback snapshot. The current multifamily layer intentionally fails the build rather than silently substituting an older land-use dataset.
