# Source manifest

Official City and County of San Francisco / DataSF sources are preferred. Each production layer should have an understood schema, geography, transformation, and limitation before it appears in the map.

## S001 — Election Precincts — Current, Defined 2022

- **Agency:** San Francisco Department of Elections / DataSF
- **Dataset ID:** `d6x4-hefw`
- **Use:** neutral precinct reference boundaries
- **Official GeoJSON distribution:** `https://data.sf.gov/api/v3/views/d6x4-hefw/query.geojson?accessType=DOWNLOAD`
- **Useful fields:** `prec_2022`; neighborhood labels when exposed by the source
- **Build validation:** feature count must remain within a broad 400–800 sanity range
- **Production behavior:** official source only. If the official download fails, the build fails and the previously deployed site remains live.
- **Interpretation:** precincts are reference geography only; other conditions should not be forced into precinct-level aggregates

## S002 — San Francisco Land Use

- **Agency:** San Francisco Planning / DataSF
- **Dataset ID:** `c5ge-t6pj`
- **Use:** large residential parcel / apartment-access-friction proxy layer
- **Official GeoJSON distribution:** `https://data.sf.gov/api/v3/views/c5ge-t6pj/query.geojson?accessType=DOWNLOAD`
- **Build filter:** the full official snapshot is downloaded, then the displayed layer retains only records where `resunits >= 20` and `geography_type = parcel`
- **Fields retained when present:** `ludb_id`, `mapblklot`, `resunits`, `resunits_s`, `geography_type`, `data_as_of`, descriptive address/land-use fields, and geometry
- **Build validation:** at least 100 retained records; every displayed record must have a valid 20+ residential-unit count and `geography_type = parcel`; duplicate parcel IDs cannot remain after deduplication
- **Interpretation:** a colored feature is one property parcel with the reported residential-unit count. A parcel boundary is not necessarily the building footprint, and unit count does not establish lobby/door accessibility.

### Why non-parcel records are excluded from the displayed layer

The current SF Planning source also contains `multiple_parcels` and `analytical` geographies. Filling those geometries made broad places such as parts of the Presidio look like giant apartment properties. That is misleading for canvassing-route use.

Observed in the 2026-09-28 source snapshot among records with 20+ units:

- `parcel`: 2,249 source records
- `multiple_parcels`: 33 records — excluded pending a better visual treatment
- `analytical`: 25 records — excluded

After resolving one exact duplicate parcel record, the displayed parcel set contains 2,248 unique 20+ unit parcels. Current threshold counts are:

- 20+ units: 2,248 unique parcels
- 50+ units: 811 unique parcels
- 100+ units: 384 unique parcels
- 200+ units: 120 unique parcels

### Duplicate handling

The current snapshot contains parcel `6311016` twice with identical geometry but reported unit counts of 170 and 174. The build retains one copy with 174 units and records the conflict in `_site/data-manifest.json`. Exact duplicates are only auto-resolved when both the parcel ID and geometry match. A duplicate parcel ID with different geometry causes the build to fail for manual review.

## S003 — Streets – Active and Retired

- **Agency:** San Francisco Public Works / DataSF
- **Dataset ID:** `3psu-pn9h`
- **Use:** visual street network and canonical street-segment geography for future hill, closure, and construction layers
- **Official GeoJSON distribution:** `https://data.sf.gov/api/v3/views/3psu-pn9h/query.geojson?accessType=DOWNLOAD`
- **Build filter:** retain only records where `active = true`
- **Fields retained:** `cnn`, `street`, `st_type`, `f_st`, `t_st`, `f_node_cnn`, `t_node_cnn`, `classcode`, `jurisdiction`, `layer`, `active`, geometry, and analysis neighborhood when present
- **Build validation:** 10,000–25,000 active line features; every retained feature must be a LineString/MultiLineString and have a unique CNN
- **Current active count:** 16,372 segments in the 2026-09-28 build
- **Current class counts:** 10,906 residential; 2,376 collector; 1,530 arterial; 202 major/highway; 110 freeway; 109 freeway ramp; 1,139 other
- **Interpretation:** CNN is the stable City street-centerline identifier. Class codes are used for visual hierarchy only, not as a canvassing score.

The map derives a readable street label from the source `street` + `st_type` fields and shows progressively more local labels as the user zooms. Street centerlines are bundled into the static site so opening the map does not trigger a DataSF request.

## Build-time provenance

Every successful build writes `_site/data-manifest.json` containing:

- retrieval timestamp;
- source URL and dataset ID for each production layer;
- displayed feature counts;
- active street-segment count and class-code counts;
- the apartment-layer display filter and threshold counts;
- source 20+ unit counts by geography type;
- counts of excluded analytical and multi-parcel records;
- duplicate parcel records resolved and the rule used;
- `data_as_of` for the land-use dataset when available;
- upstream row-update timestamps when the Socrata metadata endpoint exposes them.

The data are then embedded into `_site/index.html`. End users do not make DataSF requests when they open the deployed map.

## Candidate future sources

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
