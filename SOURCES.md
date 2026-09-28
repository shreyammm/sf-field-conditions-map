# Source manifest

Official City and County of San Francisco / DataSF sources are preferred. Each production layer should have an understood schema, geography, transformation, and limitation before it appears in the map.

## S001 — Election Precincts — Current, Defined 2022

- **Agency:** San Francisco Department of Elections / DataSF
- **Dataset ID:** `d6x4-hefw`
- **Use:** neutral precinct reference boundaries
- **Official GeoJSON distribution:** `https://data.sf.gov/api/v3/views/d6x4-hefw/query.geojson?accessType=DOWNLOAD`
- **Useful fields:** `prec_2022`; neighborhood labels when exposed by the source
- **Build validation:** feature count must remain within a broad 400–800 sanity range
- **Fallback:** a versioned public GeoJSON snapshot from `sfbay/datadiver`, itself derived from the SF Elections source
- **Interpretation:** precincts are reference geography only; other conditions should not be forced into precinct-level aggregates

## S002 — San Francisco Land Use

- **Agency:** San Francisco Planning / DataSF
- **Dataset ID:** `c5ge-t6pj`
- **Use:** large-multifamily property layer
- **Official GeoJSON distribution:** `https://data.sf.gov/api/v3/views/c5ge-t6pj/query.geojson?accessType=DOWNLOAD`
- **Build filter:** the full official snapshot is downloaded, then `resunits >= 20` is applied locally during the build
- **Fields retained:** `ludb_id`, `mapblklot`, `resunits`, `resunits_s`, `geography_type`, `data_as_of`, geometry
- **Build validation:** at least 100 records, and every retained record must have a valid residential-unit count of 20+
- **Interpretation:** rows can describe parcels, parcel groups, or analytical geography; unit count is a proxy for possible access friction and does not establish lobby/door accessibility

## Build-time provenance

Every successful build writes `_site/data-manifest.json` containing:

- retrieval timestamp;
- source URL and dataset ID for each layer;
- feature counts;
- whether the precinct source was official or the documented fallback snapshot;
- `data_as_of` for the multifamily dataset when available;
- upstream row-update timestamps when the Socrata metadata endpoint exposes them.

The data are then embedded into `_site/index.html`. End users do not make DataSF requests when they open the deployed map.

## Candidate future sources

### Streets — Active and Retired
- **Agency:** San Francisco Public Works / DataSF
- **Dataset ID:** `3psu-pn9h`
- **Candidate use:** base street geometry for street-grade derivation and joins by CNN

### Elevation Contours
- **Agency:** City and County of San Francisco / DataSF
- **Dataset ID:** `rnbg-2qxw`
- **Candidate use:** derive or validate street grade

### Slopes of 20% or Greater
- **Agency:** San Francisco Planning / DataSF
- **Dataset ID:** `3vv2-nvev`
- **Candidate use:** cross-check steep-street classifications

### Police Department Incident Reports: 2018 to Present
- **Agency:** San Francisco Police Department / DataSF
- **Dataset ID:** `wg3w-h783`
- **Candidate use:** recent reported-incident geography with an explicit user-selected time window
- **Caveat:** published location privacy/approximation rules must be preserved in the UI rather than implying exact-address precision

### Temporary Street Closures
- **Agency:** SFMTA / DataSF
- **Dataset ID:** `8x25-yybr`
- **Candidate use:** date/time-filtered street-line overlay
- **Potential fields:** case/project, type/status, start/end, street/cross streets, vehicle impact, line geometry

### Street-Use Permits
- **Agency:** San Francisco Public Works / DataSF
- **Dataset ID:** `b6tj-gt35`
- **Candidate use:** construction/right-of-way disruptions
- **Caveat:** a permit is not proof of a full street closure

## Source acceptance rule

A candidate source becomes a production layer only after its schema and geography are inspected, its relevant fields are verified, duplicate/one-to-many behavior is understood, several real-world examples are spot-checked, and material limitations are represented in the UI or documentation.
