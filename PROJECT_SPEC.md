# Project spec

## Purpose

Build a San Francisco field-conditions map for field logistics using reliable public data. Streets provide navigation/context geometry; precincts provide neutral election-geography orientation; other phenomena remain at their natural source geography whenever possible. The product must prefer omission/uncertainty over guessed precision.

## Current production layers

### Street network

- SF Public Works / DataSF `Streets – Active and Retired` (`3psu-pn9h`).
- Start from `active = true`.
- Exclude `PAPER`, `PAPER_FWYS`, `PAPER_WATER`, `PSEUDO`, and `PRIVATE_PARKING` as an explicit product rule for the physical route-context backbone.
- Preserve CNN, name/endpoints, class code, source layer, jurisdiction and geometry.
- Street class affects visual hierarchy only; it is not a route/canvassing score.
- “Active” means not retired, not necessarily publicly accessible. Private/unpaved/park/pedestrian segments that remain must be described accurately in details.

### Hill steepness

- DataSF `Elevation Contours` (`rnbg-2qxw`), official 5-foot contour lines.
- Derive a contour-supported estimate on non-freeway displayed street segments using direct accepted contour crossings.
- Same-elevation supported spans contribute zero net rise; non-zero consecutive crossings must differ by approximately five feet.
- Reject ambiguous intersections, non-five-foot jumps, degenerate spans and >45% short-span artifacts.
- Confidence must reflect direct evidence and segment coverage; low-confidence estimates are visually distinguished.
- If evidence is insufficient, leave the street unavailable rather than interpolate/guess.
- Freeways/ramps are not applicable to the canvassing hill overlay.
- Never describe these values as official engineering street grades.

### Precinct boundaries

- SF Department of Elections / DataSF `Election Precincts — Current, Defined 2022` (`d6x4-hefw`).
- Thin, neutral reference outlines.
- Hover/click shows precinct ID and neighborhood when available.
- Reference only: no operational, housing, hill or dispatch data is converted into a precinct score/ranking.

### High-unit residential parcels

- SF Planning `San Francisco Land Use` (`c5ge-t6pj`).
- Display only `geography_type = parcel` with `resunits >= 20`.
- Buckets: 20–49, 50–99, 100–199, 200+ reported residential units.
- Exclude `analytical` and `multiple_parcels` geography from this fill layer.
- A parcel is not necessarily a building footprint; never infer entrance/lobby accessibility from unit count.
- Repeated parcel geometry may be resolved only when parcel ID and geometry match. Conflicting unit counts are surfaced as an observed range if they remain in the same display bucket; threshold-crossing conflicts or geometry conflicts fail the build for review.

### Temporary street closures

- SFMTA / DataSF `Temporary Street Closures` (`8x25-yybr`).
- Keep only rows with `status = Permitted`, valid source line geometry, object ID and valid time window.
- No planning date on initial load; no closure lines until a date is selected.
- Date visibility uses overlap with the entire selected San Francisco calendar day, while exact source hours remain in details.
- Render official SFMTA lines directly; do not infer larger closure polygons.
- Describe as street/vehicle disruption context, not proof of pedestrian blockage or a complete inventory of every City-managed closure.
- Display source freshness; warn when the official `data_as_of` timestamp is materially behind the build date.

### Street-work / right-of-way permits

- Public Works / DataSF `Active and upcoming street surface permits` (`bpc9-7sus`).
- Production types: `Excavation`, `TempOccup`, `StrtImprov`, `ExcStreet`, `AddlStSpac`, `StorCont`, `MinorEnc`, `StreetSpace`.
- Status must be `ACTIVE` or `APPROVED`.
- Render the official permit point only; never infer work footprints/closure lines.
- Filter by the selected SF calendar date inside the permit authorization window.
- Restrict display to the build's current/+14-day source support window.
- Off by default because the layer is dense.
- Preserve distinct source locations/descriptions when co-located rows share one marker key.
- A permit is authorization context, not evidence of actual crew presence, closure or pedestrian inaccessibility.

### Related closure/permit context

- Only `Special Traffic Permit` closures can receive this contextual join.
- Require same normalized street, overlapping date windows and official permit point <=120 m from the official closure line.
- Label as related context only. Never claim the matched Public Works permit caused the SFMTA closure.

### Recent law-enforcement dispatch activity

- DataSF `Law Enforcement Dispatched Calls for Service: Real-Time` (`gnap-fj3t`).
- Optional/off by default.
- User windows are based on **received time**: 1, 3, 6, 12, 24 or 48 hours.
- Police-only is the default agency view; users can include all law-enforcement agencies and/or show only calls that remain open.
- Validate one unique documented `cad_number` per queried source row.
- Build fallback query uses a 49-hour received-time window, a 10,000-row safety cap and <=180-minute freshness guardrail.
- The browser requests the official live feed only after the user enables this optional layer; while enabled it can refresh at most every 10 minutes. If runtime data fails schema/uniqueness/freshness/cap checks, retain the audited embedded fallback.
- Public locations are privacy-mapped intersection points; sensitive call types can suppress location and therefore cannot be mapped.
- These are dispatch records, **not confirmed crimes**. Do not derive a neighborhood/precinct safety score or crime count.
- Low-zoom aggregation is display-only and must preserve all-open/all-closed/mixed status semantics rather than implying every aggregate is an open call.

## Interaction requirements

- Toggle each layer independently.
- Hover for immediate explanation; click for persistent details.
- Pan and zoom; show progressively more street labels as zoom increases.
- Keep source/build/freshness status visible.
- Link every production dataset to the official source.
- Use language that matches what the source actually establishes.
- Clearly distinguish source values from derived estimates and display-only aggregation.

## Data and deployment requirements

- Public/reliable data only; official SF/DataSF sources for production layers.
- No voter files, person-level political targeting, private canvasser observations or proprietary campaign data.
- Stable/core layers must not depend on runtime cross-origin requests.
- The sole runtime exception is the optional official DataSF real-time dispatch feed, requested only while that layer is enabled and backed by an embedded audited snapshot.
- Validate source shape/counts, identifiers, geography type, coordinate bounds, timestamps, known exclusion rules and final UI semantics before deployment.
- A failed source refresh or audit must not replace the previously successful deployment.
- Every derived/filtered layer must remain traceable to source dataset, fields, transformation and retrieval time.
- Final deployed HTML must pass JavaScript syntax, duplicate-ID, source-link, network-whitelist and end-to-end semantic audits.

## Explicit non-goals

- No blended “field difficulty” score.
- No precinct targeting/ranking score.
- No neighborhood safety/risk score.
- No inference that a permit means a closure or that a closure means pedestrian access is blocked.
- No conversion of privacy-mapped dispatch points into exact incident locations.
