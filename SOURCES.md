# Production source manifest

Production layers use official City and County of San Francisco / DataSF sources. The map does not substitute third-party summaries for production data. The exact source identifiers are also linked inside the map's methodology panel.

Current record counts and timestamps are intentionally **not hard-coded here** because several sources refresh daily or more often. Every build writes the actual counts, exclusions, source timestamps, derived-method metadata, and anomalies to `_site/data-manifest.json`. Deployment-blocking audits inspect the exact final HTML and manifest before GitHub Pages is updated.

## S001 — Election Precincts — Current, Defined 2022

- **Agency:** San Francisco Department of Elections / DataSF
- **Dataset ID:** `d6x4-hefw`
- **Official source:** https://data.sf.gov/d/d6x4-hefw
- **Production use:** reference boundaries and user-selected geographic focus.
- **Source meaning:** current voting precinct geography defined in 2022, based on Census 2020 geography with exceptions.
- **Validation:** Polygon/MultiPolygon geometry, non-empty unique precinct IDs, plausible SF extent, and broad count guardrails.
- **Focus behavior:** users may search/paste precinct IDs or click precinct polygons. Selecting precincts filters the operational map to those areas and produces descriptive summaries of the same public-data layers already displayed.
- **Interpretation:** precinct focus is an operational display/aggregation tool. The product does **not** calculate a political score, turnout score, persuasion score, safety score, or recommendation about which precincts to canvass.

## S002 — Current San Francisco Land Use

- **Agency:** San Francisco Planning / DataSF
- **Dataset ID:** `c5ge-t6pj`
- **Official source:** https://data.sf.gov/d/c5ge-t6pj
- **Production use:** high-unit residential **parcel** concentration.
- **Display filter:** `resunits >= 20 AND geography_type = parcel`.
- **Validation:** every displayed feature must be parcel geography, have a usable 20+ residential-unit count and stable parcel ID, and use plausible SF polygon geometry.
- **Duplicate policy:** repeated identical parcel geometry is resolved only when observed unit counts remain in the same displayed threshold bucket. The observed range is retained. A repeated parcel with conflicting geometry, or a unit-count conflict that crosses a 20/50/100/200 threshold, fails the build for manual review.
- **Precinct summary assignment:** each displayed parcel is assigned to exactly one precinct using a representative point guaranteed to lie inside its polygon. This prevents a parcel touching/crossing a precinct boundary from being double-counted when several precincts are selected.
- **Interpretation:** a parcel is a property-lot geometry, **not necessarily a building footprint**. Unit count is a residential-concentration proxy, not evidence of lobby/entrance accessibility. Selected-area unit totals are the sum of units on the currently displayed high-unit parcels, not all housing units in those precincts.
- **Source limitation:** SF Planning cautions that parcel-scale records can contain errors. The map retains source dates, preserves known same-bucket conflicts, and links to the official dataset for manual verification.

`multiple_parcels` and `analytical` rows are excluded from the colored parcel layer because broad planning/project geometry can otherwise look like one large apartment property.

## S003 — Streets – Active and Retired

- **Agency:** San Francisco Public Works / DataSF
- **Dataset ID:** `3psu-pn9h`
- **Official source:** https://data.sf.gov/d/3psu-pn9h
- **Production use:** street-centerline route/context backbone and canonical segment geometry for the derived hill layer.
- **Base filter:** `active = true`.
- **Product exclusion rule:** source-layer categories `PAPER`, `PAPER_FWYS`, `PAPER_WATER`, `PSEUDO`, and `PRIVATE_PARKING` are excluded from the physical route-context backbone. This is a product policy based on those source-layer categories; it is **not** an official Public Works determination that every retained line is publicly walkable.
- **Class codes used for styling only:** 1 freeway; 2 major street/highway; 3 arterial; 4 collector; 5 residential; 6 freeway ramp; 0 other.
- **Validation:** unique/non-empty CNN, line geometry, no excluded-layer leakage, active records only, plausible SF geometry and broad count guardrails.
- **Precinct focus:** street and closure line membership is computed by non-zero-length intersection with official precinct polygons. In focused mode, selected-area streets remain individually interactive while out-of-area streets are collapsed into a few faint, non-interactive SVG context paths for performance.
- **Interpretation:** `active` means not retired. Private streets, pedestrian-only streets, park/NPS roads, unpaved rights-of-way, freeways and ramps can remain as labeled context. The map does not claim they are accessible canvassing routes.

## S004 — Elevation Contours

- **Agency:** City and County of San Francisco / DataSF
- **Dataset ID:** `rnbg-2qxw`
- **Official source:** https://data.sf.gov/d/rnbg-2qxw
- **Production use:** derived street steepness overlay.
- **Source meaning:** five-foot elevation contours for San Francisco mainland and Treasure Island/Yerba Buena Island, based on the San Francisco Elevation Datum. The source is historical rather than a frequently refreshed operational feed.
- **Method:** directly intersect each applicable non-freeway street centerline with contour lines. Consecutive same-elevation crossings contribute zero net rise across that supported span. Non-zero consecutive crossings must differ by approximately five feet. Non-five-foot jumps, ambiguous coincident crossings, degenerate intervals, and >45% short-span artifacts are rejected instead of forced into a grade.
- **Confidence:** high/medium/low based on accepted intervals, distinct contour levels, supported along-street distance, and supported fraction of the segment. Low-confidence estimates are visually dashed/faded.
- **No interpolation fallback:** streets without enough direct evidence remain `unavailable`; freeway/ramp context is `not_applicable`.
- **Interpretation:** a **contour-supported route-planning estimate over directly supported portions**, not an official engineering street-grade survey. Selected-area summaries count classified source street segments, not roadway mileage.

The production method is `direct_5ft_contour_crossings_v2`. Earlier interpolation/direct prototypes were rejected after validation showed implausible or biased results.

## S005 — Temporary Street Closures

- **Agency:** San Francisco Municipal Transportation Agency / DataSF
- **Dataset ID:** `8x25-yybr`
- **Official source:** https://data.sf.gov/d/8x25-yybr
- **Production use:** date-optional street/vehicle-disruption overlay.
- **Documented scope:** SFMTA-permitted temporary closures associated with Shared Spaces, certain special events, and some construction work. Closures managed by other departments are not comprehensively represented.
- **Production filter:** `status = Permitted`, non-empty object ID, valid line geometry, and valid start/end window.
- **Date rule:** a closure is visible when its official local interval overlaps any portion of the selected San Francisco calendar date: `start < next_day_00:00 AND end >= selected_day_00:00`.
- **Geometry:** render the official SFMTA line directly; never expand it into a guessed closure area.
- **Freshness:** `data_as_of` is retained when provided. The UI warns when a daily source is more than two days behind the build date; the deep audit blocks deployment if the gap exceeds 14 days.
- **Interpretation:** a closure line indicates a permitted street/vehicle disruption. It does **not** establish that pedestrian access is blocked.

### Related Public Works permit context

Only `Special Traffic Permit` closure rows are eligible for contextual matching. A Public Works permit is shown as related context only when normalized street name matches, permit/closure date windows overlap, and the official Public Works point lies within 120 m of the official SFMTA closure line. This is explicitly a **context match, not a causal join**.

## S006 — Active and upcoming street surface permits

- **Agency:** San Francisco Public Works / DataSF
- **Dataset ID:** `bpc9-7sus`
- **Official source:** https://data.sf.gov/d/bpc9-7sus
- **Production use:** date-filtered street-work/right-of-way authorization context.
- **Documented source scope:** active permits plus permits whose start date is within the next 14 days; refreshed daily; union of Street Use and Street Vending permit data.
- **Production types:** `Excavation`, `TempOccup`, `StrtImprov`, `ExcStreet`, `AddlStSpac`, `StorCont`, `MinorEnc`, `StreetSpace`.
- **Excluded from this product layer:** vending categories, `FoodFac`, `Parklet`, `NightNoise`, blank/unclassified, and other source types that are not a clean construction/physical-occupancy signal for the intended route context.
- **Status rule:** `ACTIVE` or `APPROVED` only.
- **Geometry:** official point only. The map never turns a point into a guessed work-zone polygon or closure line.
- **Date rule:** selected SF calendar date falls inclusively inside the permit authorization window and must be inside the current build's current/+14-day source support window.
- **Co-located source rows:** rows are merged to one marker only when permit number, type, exact source point, and start/end window all match. Distinct source locations/descriptions/statuses are preserved.
- **Interpretation:** authorization context only. A permit does not establish that crews are present, a street is closed, an exact footprint is occupied, or pedestrians cannot pass.

## S007 — Law Enforcement Dispatched Calls for Service: Real-Time

- **Agency:** San Francisco Department of Emergency Management / DataSF
- **Dataset ID:** `gnap-fj3t`
- **Official source:** https://data.sf.gov/d/gnap-fj3t
- **Official explainer:** https://sfdigitalservices.gitbook.io/dataset-explainers/law-enforcement-dispatched-calls-for-service
- **Production use:** optional recent law-enforcement dispatch-activity context.
- **Upstream scope:** the real-time table normally contains calls closed in the last 48 hours plus calls that remain open. It normally refreshes every 10 minutes with about a 10-minute additional delay.
- **Product time rule:** users select calls **received within** the last 1, 3, 6, 12, 24 or 48 SF-local hours. Older upstream open/reopened rows are not displayed by these controls.
- **Fallback build query:** only rows received in the preceding 49 SF-local hours are requested, providing a one-hour buffer beyond the maximum user view.
- **Counting/uniqueness:** `cad_number` is used to validate one unique source row per dispatched incident in the bounded query. It is not embedded in user-facing feature properties.
- **Truncation protection:** build and runtime queries have a 10,000-row cap and are rejected rather than used if the response reaches the cap.
- **Freshness protection:** fallback and runtime data must pass a <=180-minute `data_as_of` freshness check; otherwise the runtime response is rejected and the audited fallback remains.
- **Runtime behavior:** the browser does **not** query DataSF merely because the map opens. The official feed is requested only when this optional layer is enabled and refreshes at most every 10 minutes while enabled.
- **Open/closed meaning:** `close_datetime` absent => still open; a populated close time => closed, following the source's operational lifecycle.
- **Priority visualization:** marker color uses the documented dispatch-priority field: `priority_final` when present, otherwise `priority_original`. A is highest official dispatch urgency, B intermediate, C lower/routine, and I information-only if present. Marker size is fixed and does not encode count or severity.
- **Privacy:** public locations are anonymized to intersection-level points and some sensitive calls suppress public location. DataSF specifically cautions that anonymization can move locations across small geographic boundaries. Therefore, dispatch totals inside a selected precinct are **approximate map context, not exact precinct incident statistics**.
- **Interpretation:** these are operational dispatch records, **not confirmed crimes** and not a crime count. The map does not create a neighborhood or precinct safety/risk score.

In the citywide view, nearby privacy-mapped points may be combined into display-only clusters for readability; cluster color uses the highest represented official priority and hover/click exposes the full priority breakdown. Cluster size remains fixed. **When precinct focus is active, dispatches are first filtered to the selected precincts and low-zoom spatial clustering is disabled**, preventing out-of-focus calls from leaking into a selected-area cluster. Multiple calls sharing the same public privacy-mapped point may still be represented together.

## Field-use and performance contract

The final production pass is optimized for the common field workflow of selecting a small group of precincts:

- pasted/searched precinct selections automatically fit the map;
- shareable `?precincts=` links open directly into the same focused view;
- focused mode instantiates only selected high-unit parcels and individually interactive selected-area streets, while keeping collapsed faint street context outside the selection;
- live API point-to-precinct assignment uses a bounding-box index plus boundary-inclusive point-in-polygon and caches the result on each runtime call;
- mobile uses a map-first split view with a scrollable control sheet and larger touch targets;
- redundant source properties that are no longer needed after all joins/derivations are removed from the final embedded payload without rounding or altering source geometry.

`field_ux_hardening` metadata in `_site/data-manifest.json` records the payload reduction and final runtime semantics for each successful build.

## Build/deployment audit contract

Every successful build writes `_site/data-manifest.json` containing exact production source IDs/URLs, retrieval/source timestamps, record counts, exclusions, duplicate handling, hill support/confidence, closure/permit date semantics, closure-context match counts, live-feed query/freshness guardrails, precinct-focus semantics, and field-performance metadata.

The workflow runs layer-specific validation, general artifact checks, final UI/semantic/freshness passes, the precinct-workspace audit, a dedicated field-UX/performance audit, and `scripts/deep_accuracy_audit.py` against the exact HTML that will be deployed. A failed source fetch, schema guardrail, semantic check, JavaScript syntax check, freshness guardrail, or final audit prevents a new Pages deployment and leaves the previous successful site live.

All stable layers are embedded. The sole whitelisted runtime network request is the optional official DataSF real-time dispatch feed while that layer is enabled.

## Related validation-only source

### Slopes of 20% or Greater

- **Agency:** San Francisco Planning / DataSF
- **Dataset ID:** `3vv2-nvev`
- **Use:** possible independent historical cross-check of known steep areas.
- **Not used as a production grade source:** it is not treated as an official segment-by-segment replacement for the contour computation.
