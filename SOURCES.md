# Source manifest

Production layers use official City and County of San Francisco / DataSF sources. A source becomes a production layer only after its schema/geography is inspected, identifiers and duplicate behavior are understood, real-world examples are spot-checked, and material limitations are represented in the product.

## S001 — Election Precincts — Current, Defined 2022

- **Agency:** San Francisco Department of Elections / DataSF
- **Dataset ID:** `d6x4-hefw`
- **Use:** neutral precinct reference boundaries
- **Official GeoJSON:** `https://data.sf.gov/api/v3/views/d6x4-hefw/query.geojson?accessType=DOWNLOAD`
- **Source meaning:** Department of Elections voting precincts, redefined in 2022 from Census 2020 geography with exceptions.
- **Retained fields:** precinct ID and neighborhood labels when present, plus geometry.
- **Build validation:** 400–800 features, non-empty unique precinct IDs, plausible SF coordinates.
- **Production behavior:** official source only. An upstream failure stops the refresh rather than changing provenance.
- **Interpretation:** reference geography only; operational conditions are not forced into precinct scores.

## S002 — San Francisco Land Use

- **Agency:** San Francisco Planning / DataSF
- **Dataset ID:** `c5ge-t6pj`
- **Use:** high-unit residential parcel / possible shared-entry-friction proxy
- **Official GeoJSON:** `https://data.sf.gov/api/v3/views/c5ge-t6pj/query.geojson?accessType=DOWNLOAD`
- **Source cadence:** Planning describes this as a current land-use snapshot updated at the end of each quarter.
- **Display filter:** `resunits >= 20 AND geography_type = parcel`
- **Retained fields:** `ludb_id`, `mapblklot`, `resunits`, `resunits_s`, `geography_type`, `data_as_of`, available descriptive address/land-use fields, and geometry.
- **Build validation:** every displayed record is parcel geography with a valid 20+ unit count; parcel IDs are unique after controlled deduplication; coordinates must be plausible for SF.
- **Interpretation:** a colored feature is a parcel-level property lot with the reported residential-unit count. It is not necessarily a building footprint, and unit count does not establish entrance accessibility.

### Why non-parcel records are excluded

Planning explicitly notes that some land-use rows represent groups of parcels. Filling broad `multiple_parcels` or `analytical` geometry can make a large planning/project area look like one giant apartment property. For route use, those records remain excluded until a separate representation is validated.

In the 2026-09-28 source snapshot among records with 20+ units:

- `parcel`: 2,249 source rows
- `multiple_parcels`: 33 — excluded from the parcel fill layer
- `analytical`: 25 — excluded from the parcel fill layer

One exact duplicate parcel row is present in that snapshot. After deduplication there are 2,248 unique 20+ unit parcels, with current threshold counts of 2,248 at 20+, 811 at 50+, 384 at 100+, and 120 at 200+.

### Duplicate handling

Parcel `6311016` appears twice in the current source with identical parcel ID/geometry and unit counts 170 and 174. Both counts fall in the same 100–199 display bucket. The build keeps one geometry but annotates the feature/source manifest with the observed 170–174 range so the UI does not imply false exactness. If a future identical-parcel conflict crosses one of the displayed thresholds (20/50/100/200), the build fails for manual review. A repeated parcel ID with different geometry also fails.

## S003 — Streets – Active and Retired

- **Agency:** San Francisco Public Works / DataSF
- **Dataset ID:** `3psu-pn9h`
- **Use:** visual street network and canonical street-segment geography for future hill, closure, and construction layers
- **Official GeoJSON:** `https://data.sf.gov/api/v3/views/3psu-pn9h/query.geojson?accessType=DOWNLOAD`
- **Source meaning:** Public Works street centerlines. `cnn` is the unique Centerline Network Number for a segment in the dataset. `active = true` means the segment is not retired; it does not guarantee public access or even that every source-layer line is a physical street.
- **Class codes:** 1 freeway; 2 major street/highway; 3 arterial; 4 collector; 5 residential; 6 freeway ramp; 0 other.
- **Retained fields:** `cnn`, official street name/type/full name, endpoint streets/nodes, class code, source layer, jurisdiction, active/accepted/one-way fields when present, analysis neighborhood, `data_as_of`, and geometry.

### Street display filter

The current source has 16,372 active records. Public Works documents several `layer` values that are not physical streets. The route-context layer therefore starts with `active = true` and excludes:

- `PAPER` — mapped but not an actual street;
- `PAPER_FWYS` — mapped but not actual street, under/near freeway;
- `PAPER_WATER` — mapped but not actual street, under Bay water;
- `PSEUDO` — addressing-only segment;
- `PRIVATE_PARKING` — parking-lot centerline rather than a street.

In the audited 2026-09-28 snapshot those exclusions remove 471 active records (209 `PAPER_FWYS`, 136 `PAPER_WATER`, 115 `PAPER`, 9 `PRIVATE_PARKING`, 2 `PSEUDO`), leaving **15,901 displayed street segments**.

Real but nonstandard context can remain: private streets, unpaved rights-of-way, pedestrian-only streets, park/NPS roads, freeways and ramps. The UI identifies these categories rather than assuming they are publicly walkable or appropriate canvassing routes.

- **Build validation:** 9,000–25,000 displayed line features, unique/non-empty CNN, no excluded source layer leakage, plausible SF coordinates.
- **Join rule:** CNN is used when another public dataset exposes the same segment identifier. Do not assume a CNN is permanently immutable across all future street-network revisions; source changes are revalidated at build time.

## S004 — Elevation Contours

- **Agency:** City and County of San Francisco / DataSF
- **Dataset ID:** `rnbg-2qxw`
- **Use:** derive an estimated terrain-grade magnitude for the displayed Public Works street segments
- **Official GeoJSON:** `https://data.sf.gov/api/v3/views/rnbg-2qxw/query.geojson?accessType=DOWNLOAD`
- **Observed source structure:** 14,151 line features in the 2026-09-28 build; elevation is supplied in the `elevation` field on five-foot intervals.
- **Build validation:** 10,000–20,000 line features; every retained contour has numeric elevation on a five-foot interval; elevations and coordinates pass broad plausibility guards.

### Hill-grade derivation

For each displayed street centerline, the build spatially intersects the line with the official elevation contours and orders the contour crossings along the street geometry. Horizontal distance is approximated from WGS84 longitude/latitude at San Francisco's latitude and converted to feet so rise and run share the same unit.

The displayed hill value is:

1. the steepest monotonic contour-derived grade over a horizontal span of at least 80 feet, when such a span exists; otherwise
2. a conservative whole-segment fallback using only the observed contour elevation range divided by total segment length.

Grade is `vertical rise / horizontal run × 100`. The layer reports **magnitude only**; it does not say which direction is uphill. This is a terrain-derived proxy along the City centerline, not an engineering/surveyed street or sidewalk grade. Bridges, tunnels, grade-separated structures, stairways, and unusual rights-of-way can diverge from the underlying terrain. Freeway/ramp segments remain visible as context but are not hill-emphasized.

### Current validation and distribution

The current derivation reproduces several published steep-block reference values closely enough for a broad regression guardrail: Filbert between Hyde/Leavenworth (~31.8% derived vs. 31.5% reference), 22nd between Church/Vicksburg (~32.5% vs. 31.5%), Jones between Union/Filbert (~30.2% vs. 29%), and Duboce between Alpine/Buena Vista East (~25.7% vs. 27.9%). These are validation examples, not claims that the derived number is a surveyed legal grade.

Across all 15,901 displayed street-context segments in the current snapshot, the conservative derivation produces 9,622 at 0–4.9%, 2,978 at 5–9.9%, 1,686 at 10–14.9%, 875 at 15–19.9%, and 740 at 20%+. Excluding 219 freeway/ramp context segments from hill emphasis leaves 15,682 route-context segments, of which 3,223 are at least 10% by the derived metric. These counts are recalculated on every build.


## Build-time provenance

Every successful build writes `_site/data-manifest.json` containing retrieval time; source URL and dataset ID for each layer; source and displayed record counts; street exclusions and class counts; contour source counts and hill-grade bins/benchmark checks; housing threshold counts and excluded geography counts; duplicate parcel anomalies; `data_as_of` when available; and upstream row-update timestamps when exposed by Socrata metadata.

The production GeoJSON is embedded into `_site/index.html`, so end users do not make DataSF requests when opening the map.

## Candidate future sources

### Slopes of 20% or Greater
- **Agency:** San Francisco Planning / DataSF
- **Dataset ID:** `3vv2-nvev`
- **Candidate use:** independent cross-check of steep areas; not a substitute for street-segment grade.

### Temporary Street Closures
- **Agency:** SFMTA / DataSF
- **Dataset ID:** `8x25-yybr`
- **Candidate use:** date/time-filtered street overlay; prefer CNN joins where present and validate spatial matching otherwise.

### Street-Use Permits
- **Agency:** San Francisco Public Works / DataSF
- **Dataset ID:** `b6tj-gt35`
- **Candidate use:** construction/right-of-way disruptions.
- **Caveat:** a permit is not proof of a full street closure.

### Police Department Incident Reports: 2018 to Present
- **Agency:** San Francisco Police Department / DataSF
- **Dataset ID:** `wg3w-h783`
- **Candidate use:** recent reported-incident geography with an explicit time window.
- **Caveat:** SFPD location privacy/geocoding limitations must remain visible; reported incidents are not a definitive neighborhood-risk score.
