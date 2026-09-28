# Production source manifest

Production layers use official City and County of San Francisco / DataSF sources. The map does not substitute third-party summaries for production data. The exact source identifiers are also linked inside the map's methodology panel.

Current record counts and timestamps are intentionally **not hard-coded in this document** because several sources refresh daily or more often. The authoritative per-build counts, exclusions, source timestamps, and anomalies are written to `_site/data-manifest.json` and checked by `scripts/deep_accuracy_audit.py` before deployment.

## S001 — Election Precincts — Current, Defined 2022

- **Agency:** San Francisco Department of Elections / DataSF
- **Dataset ID:** `d6x4-hefw`
- **Official source:** https://data.sf.gov/d/d6x4-hefw
- **Production use:** neutral reference boundaries only.
- **Source meaning:** current voting precinct geography defined in 2022, based on Census 2020 geography with exceptions.
- **Validation:** expected polygon/MultiPolygon geometry, non-empty unique precinct IDs, plausible SF geometry, broad count guardrail.
- **Interpretation:** the map does not calculate a precinct score, political ranking, safety score, or aggregation of the operational layers into precincts.

## S002 — Current San Francisco Land Use

- **Agency:** San Francisco Planning / DataSF
- **Dataset ID:** `c5ge-t6pj`
- **Official source:** https://data.sf.gov/d/c5ge-t6pj
- **Production use:** high-unit residential **parcel** concentration.
- **Display filter:** `resunits >= 20 AND geography_type = parcel`.
- **Validation:** every displayed feature must be parcel geography, have a valid 20+ residential-unit count and stable parcel ID, and use plausible SF polygon geometry.
- **Duplicate policy:** repeated identical parcel geometry is resolved only when the observed unit counts remain in the same displayed threshold bucket. The observed range is retained. A repeated parcel with conflicting geometry or a unit-count conflict that crosses a 20/50/100/200 threshold fails the build for manual review.
- **Interpretation:** a parcel is a property-lot geometry, **not necessarily a building footprint**. Unit count is a residential-concentration proxy, not evidence of lobby/entrance accessibility.
- **Source limitation:** SF Planning itself cautions that, given the volume of parcel data, accuracy is not guaranteed for every record. The map therefore links the source and retains the source timestamp rather than treating the unit counts as infallible ground truth.

`multiple_parcels` and `analytical` rows are excluded from the colored parcel layer because broad planning/project geometry can otherwise look like one large apartment property.

## S003 — Streets – Active and Retired

- **Agency:** San Francisco Public Works / DataSF
- **Dataset ID:** `3psu-pn9h`
- **Official source:** https://data.sf.gov/d/3psu-pn9h
- **Production use:** street-centerline route/context backbone and canonical segment geometry for derived hills.
- **Base filter:** `active = true`.
- **Product exclusion rule:** source-layer categories `PAPER`, `PAPER_FWYS`, `PAPER_WATER`, `PSEUDO`, and `PRIVATE_PARKING` are excluded from the physical route-context backbone. This is a product policy based on those source-layer categories; it is **not** an official Public Works determination that every retained line is publicly walkable.
- **Class codes used for styling only:** 1 freeway; 2 major street/highway; 3 arterial; 4 collector; 5 residential; 6 freeway ramp; 0 other.
- **Validation:** unique/non-empty CNN, line geometry, no excluded-layer leakage, active records only, plausible SF geometry and broad count guardrails.
- **Interpretation:** `active` means not retired. Private streets, pedestrian-only streets, park/NPS roads, unpaved rights-of-way, freeways and ramps can remain as labeled context. The map does not claim they are accessible canvassing routes.

## S004 — Elevation Contours

- **Agency:** City and County of San Francisco / DataSF
- **Dataset ID:** `rnbg-2qxw`
- **Official source:** https://data.sf.gov/d/rnbg-2qxw
- **Production use:** derived street steepness overlay.
- **Source meaning:** elevation contours at five-foot intervals for San Francisco mainland and Treasure Island/Yerba Island, based on the San Francisco Elevation Datum. DataSF marks this as historical/not regularly updated.
- **Method:** directly intersect each applicable non-freeway street centerline with the contour lines. Consecutive same-elevation crossings contribute zero net rise across that supported span. Non-zero consecutive crossings must differ by approximately five feet. Non-five-foot jumps, ambiguous coincident crossings, degenerate intervals, and >45% short-span artifacts are rejected instead of forced into a grade.
- **Confidence:** high/medium/low based on accepted crossing intervals, distinct contour levels, supported along-street distance, and supported fraction of the segment. Low-confidence estimates are visually dashed/faded.
- **No interpolation fallback:** streets without enough direct evidence remain `unavailable`; freeway/ramp context is `not_applicable`.
- **Interpretation:** a **contour-supported route-planning estimate over directly supported portions**, not an official engineering street-grade survey or full routing score.

Earlier interpolation prototypes and an earlier direct-crossing variant were rejected during validation after producing implausible values or upward bias. The production method is `direct_5ft_contour_crossings_v2` and the build records its coverage/confidence distribution.

## S005 — Temporary Street Closures

- **Agency:** San Francisco Municipal Transportation Agency / DataSF
- **Dataset ID:** `8x25-yybr`
- **Official source:** https://data.sf.gov/d/8x25-yybr
- **Production use:** date-optional street/vehicle-disruption overlay.
- **Documented scope:** SFMTA-permitted temporary closures associated with Shared Spaces, certain special events, and some construction work. SFMTA documents that other departments' closures are not comprehensively represented.
- **Production filter:** `status = Permitted` plus non-empty object ID, valid line geometry, and valid start/end window. The filter is applied even if source documentation says the table is permitted-only; source contents are independently checked at build time.
- **Date rule:** a closure is visible when its official local interval overlaps any portion of the selected San Francisco calendar date: `start < next_day_00:00 AND end >= selected_day_00:00`.
- **Geometry:** render the official SFMTA line directly; do not expand it into a guessed closure area.
- **Freshness:** `data_as_of` is retained when provided. Because this is a time-sensitive source that SFMTA describes as daily, the UI displays its source date and warns when it is more than two days behind the build date. The deep audit fails if that gap exceeds 14 days.
- **Interpretation:** a closure line indicates a permitted street/vehicle disruption. It does **not** establish that pedestrian access is blocked.

### Related Public Works permit context

Only `Special Traffic Permit` closure rows are eligible for contextual matching. A Public Works permit is shown as related context only when:

1. normalized street name matches;
2. permit and closure date windows overlap; and
3. the official Public Works point lies within 120 m of the official SFMTA closure line.

This is explicitly a **context match, not a causal join**. The UI never states that the Public Works permit caused the SFMTA closure.

## S006 — Active and upcoming street surface permits

- **Agency:** San Francisco Public Works / DataSF
- **Dataset ID:** `bpc9-7sus`
- **Official source:** https://data.sf.gov/d/bpc9-7sus
- **Production use:** date-filtered street-work / right-of-way authorization context.
- **Documented source scope:** active permits plus permits whose start date is within the next 14 days; refreshed daily; union of Street Use and Street Vending permit data.
- **Production types:** `Excavation`, `TempOccup`, `StrtImprov`, `ExcStreet`, `AddlStSpac`, `StorCont`, `MinorEnc`, `StreetSpace`.
- **Excluded from this product layer:** vending categories, `FoodFac`, `Parklet`, `NightNoise`, blank/unclassified and other source types that are not a clean construction/physical-occupancy signal for the intended route context.
- **Status rule:** `ACTIVE` or `APPROVED` only.
- **Geometry:** official point only. The map never turns a point into a guessed work-zone polygon or closure line.
- **Date rule:** selected SF calendar date falls inclusively inside the permit authorization window, and the date must be inside the current build's supported current/+14-day snapshot window.
- **Co-located source rows:** rows are merged to one marker only when permit number, type, exact source point, and start/end window all match. Distinct source street/cross-street descriptions, permit descriptions, statuses, neighborhoods and relevant timestamps are preserved on the marker.
- **Interpretation:** authorization context only. A permit does not establish that crews are present, a street is closed, an exact footprint is occupied, or pedestrians cannot pass.

## S007 — Law Enforcement Dispatched Calls for Service: Real-Time

- **Agency:** San Francisco Department of Emergency Management / DataSF
- **Dataset ID:** `gnap-fj3t`
- **Official source:** https://data.sf.gov/d/gnap-fj3t
- **Official explainer:** https://sfdigitalservices.gitbook.io/dataset-explainers/law-enforcement-dispatched-calls-for-service
- **Production use:** optional recent law-enforcement dispatch activity overlay.
- **Upstream scope:** DataSF describes the real-time table as calls closed in the last 48 hours plus any calls that remain open; older open/reopened exceptions can therefore appear upstream. The feed normally updates every 10 minutes with about a 10-minute additional delay.
- **Product time rule:** users select calls **received within** the last 1, 3, 6, 12, 24 or 48 SF-local hours. Older upstream open/reopened rows are not displayed by these controls.
- **Fallback build query:** only rows received in the preceding 49 SF-local hours are requested, providing a one-hour buffer beyond the maximum user view.
- **Counting/uniqueness:** DataSF documents `cad_number` as the unique dispatched-incident identifier. The build requires a non-empty, unique `cad_number` for each queried source row. `cad_number` is used for validation but is not embedded in the user-facing feature properties because the UI does not need it.
- **Truncation protection:** build and runtime queries have a 10,000-row cap and are rejected rather than used if the response reaches the cap.
- **Freshness protection:** fallback and runtime data must pass a <=180-minute `data_as_of` freshness check; otherwise the runtime response is rejected and the audited fallback remains.
- **Runtime behavior:** the browser does **not** query DataSF merely because the map opens. The official feed is requested when this optional layer is enabled and can refresh at most every 10 minutes while enabled.
- **Open/closed meaning:** `close_datetime` absent => still open; a populated close time => closed, following the source's operational lifecycle.
- **Privacy:** public locations are anonymized/mapped to intersection-level locations. Sensitive call types can have public location fields suppressed, and those rows are therefore not mappable here.
- **Interpretation:** these are operational dispatch records, **not confirmed crimes** and not a crime count. The map does not create a neighborhood or precinct safety/risk score.

At low zoom, nearby privacy-mapped source points are combined into display-only circles. Zooming in separates them into clusters at the public source coordinates. Aggregate marker status distinguishes all-open, all-closed, and mixed represented calls; the aggregate center itself is not an incident location.

## Build/deployment audit contract

Every successful build writes `_site/data-manifest.json` containing the exact production source IDs/URLs, retrieval/source timestamps, record counts, exclusions, duplicate handling, hill method/support/confidence, closure/permit date semantics, closure-context match counts, and live-feed query/freshness guardrails.

The workflow runs layer-specific validation, a general artifact audit, the final UI mutations, a final semantic-accuracy pass, and `scripts/deep_accuracy_audit.py` against the exact HTML that will be deployed. Any failed source fetch, schema guardrail, semantic check, JavaScript syntax check, freshness guardrail, or final audit prevents a new Pages deployment and leaves the previously successful site live.

All stable layers are embedded. The sole whitelisted runtime network request is the optional official DataSF real-time dispatch feed while that layer is enabled.

## Related validation-only source

### Slopes of 20% or Greater

- **Agency:** San Francisco Planning / DataSF
- **Dataset ID:** `3vv2-nvev`
- **Use:** possible independent historical cross-check of known steep areas.
- **Not used as a production grade source:** it should not be treated as an official segment-by-segment grade replacement for the contour computation.
