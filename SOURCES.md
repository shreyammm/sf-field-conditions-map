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
- **Use:** visual street network and canonical street-segment geography for hill, closure, and construction layers
- **Official GeoJSON:** `https://data.sf.gov/api/v3/views/3psu-pn9h/query.geojson?accessType=DOWNLOAD`
- **Source meaning:** Public Works street centerlines. `cnn` is the unique Centerline Network Number for a segment in the dataset. `active = true` means the segment is not retired; it does not guarantee public access or even that every source-layer line is a physical street.
- **Class codes:** 1 freeway; 2 major street/highway; 3 arterial; 4 collector; 5 residential; 6 freeway ramp; 0 other.
- **Retained fields:** `cnn`, official street name/type/full name, endpoint streets/nodes, class code, source layer, jurisdiction, active/accepted/one-way fields when present, analysis neighborhood, `data_as_of`, and geometry.

### Street display filter

The audited source has 16,372 active records. The route-context layer starts with `active = true` and excludes `PAPER`, `PAPER_FWYS`, `PAPER_WATER`, `PSEUDO`, and `PRIVATE_PARKING`, leaving **15,901 displayed street segments** in the 2026-09-28 build.

Real but nonstandard context can remain: private streets, unpaved rights-of-way, pedestrian-only streets, park/NPS roads, freeways and ramps. The UI identifies these categories rather than assuming they are publicly walkable or appropriate canvassing routes.

- **Build validation:** 9,000–25,000 displayed line features, unique/non-empty CNN, no excluded source layer leakage, plausible SF coordinates.
- **Join rule:** CNN is used when another public dataset exposes the same segment identifier. Do not assume a CNN is permanently immutable across all future street-network revisions; source changes are revalidated at build time.

## S004 — Elevation Contours

- **Agency:** City and County of San Francisco / DataSF
- **Dataset ID:** `rnbg-2qxw`
- **Use:** derive the hill-steepness overlay on the displayed Public Works street centerlines
- **Official GeoJSON:** `https://data.sf.gov/api/v3/views/rnbg-2qxw/query.geojson?accessType=DOWNLOAD`
- **Source meaning:** 5-foot elevation contours for San Francisco mainland and Treasure Island/Yerba Island, based on the San Francisco Elevation Datum.
- **Production method:** directly intersect each applicable street centerline with contour lines. Consecutive same-elevation crossings contribute zero net rise across their directly supported span. A nonzero consecutive crossing must differ by approximately 5 feet, matching the source contour interval. Accepted intervals are combined by directly supported along-street distance.
- **No interpolation fallback:** streets without enough direct contour evidence remain `unavailable`; freeway mainlines and ramps are `not_applicable` for the canvassing hill layer.
- **Confidence:** high/medium/low based on usable crossing intervals, distinct contour levels, supported street distance, and supported fraction of the full street segment. Low-confidence estimates are visually faded/dashed.
- **Guardrails:** reject ambiguous same-location/different-elevation crossings, non-5-foot elevation jumps, degenerate spans, and >45% short-span crossing artifacts. Fail for unexpectedly low coverage or an implausibly large share of 20%+ classifications.
- **Interpretation:** contour-supported route-planning estimate over directly supported portions of the street segment; not an official Public Works engineering street-grade survey.

Two interpolation prototypes were rejected before deployment after producing implausible 60%+ values. A later audit also found that an earlier direct-crossing version could bias values upward by silently omitting same-elevation supported spans. The current v2 method explicitly includes those spans as zero net rise and records segment coverage.

In the 2026-09-28 audited build, 15,682 non-freeway/ramp street segments were applicable; 9,375 received a grade estimate, 6,307 remained unavailable, and 219 freeway/ramp segments were marked not applicable. Confidence among classified segments was 4,688 high, 2,006 medium, and 2,681 low. See `validation/CHECKPOINT_5_HILLS.md`.

## S005 — Temporary Street Closures

- **Agency:** San Francisco Municipal Transportation Agency / DataSF
- **Dataset ID:** `8x25-yybr`
- **Use:** time-filtered temporary street/vehicle-disruption overlay
- **Official GeoJSON:** `https://data.sf.gov/api/v3/views/8x25-yybr/query.geojson?accessType=DOWNLOAD`
- **Documented scope:** upcoming/current temporary closures associated with Shared Spaces, certain special events, and some construction work. SFMTA documentation says the feed covers SFMTA-permitted closures and does not include every closure managed by Public Works, SFPD, or other departments.
- **Production filter:** `status = Permitted`, valid LineString/MultiLineString geometry, and valid `start_dt <= end_dt`.
- **Retained fields:** case number/name, closure type/status, `start_dt`, `end_dt`, location description, CNN, street/from/to, direction, vehicle impact, info, and official line geometry.
- **Time interpretation:** the UI treats `start_dt` and `end_dt` as San Francisco local wall times and shows a feature when `start_dt <= selected SF local time <= end_dt`. The date/time control initializes using the `America/Los_Angeles` time zone even for viewers elsewhere.
- **Geometry rule:** render SFMTA's official closure line geometry directly. CNN is retained and compared with the Public Works street backbone for validation but is not required to render a valid official closure line.
- **Interpretation:** street/vehicle disruption indicator only. A closure line does not prove that pedestrian passage is prohibited.
- **Freshness:** the source documentation describes the report as daily. Current rows did not expose a usable `data_as_of` field, so the product reports the build/retrieval date rather than inventing one. The production workflow refreshes daily.

### 2026-09-28 source audit

The official download contained 4,628 rows. Although the source documentation says the dataset contains permitted temporary closures, the download also contained workflow/application statuses. Production explicitly filtered them rather than relying on the documentation alone:

- `Permitted`: 4,283 — embedded
- `Application In Review`: 216 — excluded
- `Submitted`: 92 — excluded
- `Pending Payment`: 29 — excluded
- `Pending Additional Information`: 7 — excluded
- `On Hold`: 1 — excluded

All 4,283 embedded features had line geometry, valid time windows, and unique object IDs. Of 4,283 embedded rows with a CNN, 4,281 matched a displayed Public Works street CNN; the two unmatched rows remain renderable because the official SFMTA line geometry is the displayed geometry. Embedded closure types were 3,139 Roadway Shared Spaces, 885 Special Events, and 259 Special Traffic Permits.

## S006 — Active and upcoming street surface permits

- **Agency:** San Francisco Public Works / DataSF
- **Dataset ID:** `bpc9-7sus`
- **Use:** date-filtered street-work / right-of-way authorization context
- **Official GeoJSON:** `https://data.sf.gov/api/v3/views/bpc9-7sus/query.geojson?accessType=DOWNLOAD`
- **Documented scope:** active street-surface permits plus permits beginning within the near-term upcoming window; the source is refreshed daily and combines Street-Use Permit and Street Vending Permit records.
- **Source geometry:** point locations. Production renders those points directly and does not infer a work-zone polygon or closure line.
- **Production permit types:** `Excavation`, `TempOccup`, `StrtImprov`, `ExcStreet`, `AddlStSpac`, `StorCont`, `MinorEnc`, and `StreetSpace`.
- **Excluded source types:** vending categories, `FoodFac`, `Parklet`, `NightNoise`, and blank/unclassified permit types. Those may be legitimate street uses but are not a clean construction/physical-ROW-occupancy signal for this route layer.
- **Status rule:** embedded records must be `ACTIVE` or `APPROVED` and have valid SF point geometry plus a valid permit start/end window.
- **Date interpretation:** a point is eligible for display when the selected San Francisco calendar date falls inclusively within the permit start/end dates. This describes the **authorization window**, not proof that crews are working on that exact date.
- **Completeness window:** the current/upcoming source is not treated as a historical archive or far-future schedule. Production anchors the supported range to the actual San Francisco retrieval date and suppresses the layer outside the current/upcoming window. Row-level `data_as_of` varies by record and is not used as the snapshot date.
- **Interpretation:** potential street/sidewalk work or occupancy context only. A permit is not proof of a closure, obstruction, exact work footprint, or pedestrian inaccessibility.
- **Presentation:** opt-in/off by default because thousands of permit points may overlap one date and would otherwise obscure the route map.
- **Freshness:** refreshed daily with the rest of the dynamic public-data layers.

### 2026-09-28 source audit

The official current/upcoming download contained 4,843 rows: 3,710 with status `APPROVED` and 1,133 `ACTIVE`. The source mixes work permits with vending/amenity uses. After applying the route-relevant type filter, validating date windows/point geometry, and collapsing exact duplicate permit-location/date/type rows, **4,231 unique permit points** were embedded.

Embedded type counts were:

- Excavation: 3,692
- Temporary occupancy (`TempOccup`): 358
- Street improvement (`StrtImprov`): 100
- Street excavation/work (`ExcStreet`): 48
- Additional street space (`AddlStSpac`): 20
- Storage container (`StorCont`): 11
- Minor encroachment (`MinorEnc`): 1
- Street space (`StreetSpace`): 1

The build omitted 469 source rows whose permit type was outside the construction/ROW filter, 141 exact duplicate rows, and 2 rows with invalid/missing permit date windows. The latest retained row-level `data_as_of` value was `2026-09-25T03:27:20.780`, but that field varies by record and is **not** used as the snapshot date. The audited build retrieved the source at `2026-09-27T23:12:23-07:00`, so the product treats **2026-09-27 through 2026-10-11** as that snapshot's supported current/upcoming window. On 2026-09-27, 3,921 embedded permit windows overlapped the date, which is why this dense layer is off by default.

## Build-time provenance

Every successful build writes `_site/data-manifest.json` containing retrieval time; source URL and dataset ID for each layer; source and displayed record counts; street exclusions and class counts; hill source/method, coverage, confidence and grade-bucket counts; closure status/type/CNN-validation counts and time range; surface-permit source/display type counts, duplicate/exclusion counts, SF retrieval time and supported date range; housing threshold counts and excluded geography counts; duplicate parcel anomalies; and upstream row-update timestamps when exposed by Socrata metadata.

The production geometry and derived attributes are embedded into `_site/index.html`, so end users do not make DataSF requests when opening the map.

## Related / candidate sources

### Slopes of 20% or Greater
- **Agency:** San Francisco Planning / DataSF
- **Dataset ID:** `3vv2-nvev`
- **Candidate use:** independent historical cross-check of steep areas; not a substitute for street-segment grade.

### Street-Use Permits (full historical table)
- **Agency:** San Francisco Public Works / DataSF
- **Dataset ID:** `b6tj-gt35`
- **Relationship:** broader historical Street-Use Permit source. Production uses the smaller current/upcoming street-surface view `bpc9-7sus` for route relevance.
- **Caveat:** a permit is not proof of a full street closure or of work occurring at a particular moment.

### Police Department Incident Reports: 2018 to Present
- **Agency:** San Francisco Police Department / DataSF
- **Dataset ID:** `wg3w-h783`
- **Candidate use:** recent reported-incident geography with an explicit time window.
- **Caveat:** SFPD location privacy/geocoding limitations must remain visible; reported incidents are not a definitive neighborhood-risk score.
