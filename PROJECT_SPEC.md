# Project spec

## Purpose

Build a San Francisco field-conditions map for field logistics using reliable public data. Streets provide navigation and the canonical geography for street-based conditions; precincts provide neutral election-geography orientation; other phenomena stay at their natural geography whenever possible.

## Current production layers

### Street network
- SF Public Works / DataSF `Streets – Active and Retired` (`3psu-pn9h`).
- Start from `active = true`, then exclude `PAPER`, `PAPER_FWYS`, `PAPER_WATER`, `PSEUDO`, and `PRIVATE_PARKING` source layers because they are not physical street geometry suitable for route/grade use.
- Preserve CNN, name/endpoints, class code, source layer, jurisdiction, and geometry.
- Street class affects visual hierarchy only; it is not a route or canvassing score.
- “Active” means not retired, not necessarily publicly accessible. Private/unpaved/park/pedestrian segments that remain must be described accurately in click details.


### Hill / terrain-grade layer
- Derived from DataSF `Elevation Contours` (`rnbg-2qxw`) and attached to the displayed Public Works street centerline segment/CNN.
- The source provides five-foot contour lines. The build orders contour crossings along each street centerline.
- Primary metric: steepest monotonic contour-derived pitch over a horizontal window of at least 80 feet.
- Fallback when no such window exists: conservative whole-segment estimate using only the observed contour elevation range divided by segment length.
- User-selectable emphasis thresholds: 5%+, 10%+, 15%+, 20%+. Colors reflect absolute grade bins rather than a composite route score.
- Report magnitude only; do not infer uphill/downhill direction.
- Describe values as an estimated terrain-grade proxy, not a surveyed roadway/sidewalk engineering grade.
- Freeway/ramp context is not hill-emphasized. Private, pedestrian, park, and unpaved rights-of-way that remain in the street layer retain their source-category caveats.

### Precinct boundaries
- Thin, visually distinct neutral outlines.
- Hover/click shows precinct ID and neighborhood when available.
- Reference only; no operational layer is converted into a precinct score.

### High-unit residential parcels
- SF Planning `San Francisco Land Use` (`c5ge-t6pj`).
- Display only `geography_type = parcel` with `resunits >= 20`.
- Buckets: 20–49, 50–99, 100–199, 200+ reported residential units.
- Exclude `analytical` and `multiple_parcels` geography from this fill layer until a non-misleading representation is validated.
- Never label a property inaccessible from unit count alone.
- Exact duplicate parcel rows are resolved only when parcel ID and geometry match. Conflicting unit counts are surfaced as a range if they remain in the same threshold bucket; a conflict crossing a threshold must fail the build for review.

## Interaction requirements

- Toggle each layer independently.
- Hover for immediate explanation.
- Click for persistent detail.
- Pan and zoom.
- Show progressively more street labels as zoom increases.
- Keep source/build status visible.
- Use language that matches what the source actually establishes.

## Data and deployment requirements

- Public/reliable data only; official SF/DataSF sources for production layers.
- No voter files, person-level political targeting, private canvasser observations, or proprietary campaign data.
- Core map layers must not depend on cross-origin API calls at page-open time.
- The build validates source shape/counts, identifiers, geography type, coordinate bounds, and known exclusion rules before deployment.
- A failed refresh must not replace the previously successful deployment.
- Every derived/filtered layer must remain traceable to source dataset, fields, transformation, retrieval time, and validation checks.

## Candidate next layers

- temporary SFMTA street closures with date/time filters and reliable CNN/spatial matching;
- construction/right-of-way disruptions clearly distinguished from confirmed closures;
- reported incidents with explicit geocoding/privacy caveats and a user-selected time window.

No blended “field difficulty” score is planned for the current version.
