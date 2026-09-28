# Production accuracy audit

**Audit date:** 2026-09-28  
**Scope:** exact production build pipeline, source contracts, transformations, displayed geometry, user-visible semantics, runtime network behavior, and final deploy artifact.

This audit is designed to catch two different failure modes:

1. **data/engineering errors** — wrong source, duplicate identifiers, invalid geometry, stale data, truncated queries, broken joins, incorrect date filters, or UI code drift; and
2. **interpretation errors** — displaying a parcel as if it were a building footprint, a permit as if it were a closure, a dispatch call as if it were a confirmed crime, or a derived hill estimate as if it were an official engineering grade.

Passing the audit means the production artifact satisfies the explicit source and transformation contracts below. It does **not** mean the underlying City data are infallible; where the official source has uncertainty, latency, privacy masking, incomplete scope, or source-reported values, the map preserves that limitation rather than inventing precision.

## Executive findings

The full review found several real issues that were corrected before the audit was made deployment-blocking:

- the law-enforcement dispatch layer was visually forest green but some detail text still referred to orange markers;
- low-zoom dispatch aggregates used the open-call color even when all represented calls were closed or the group was mixed;
- the first live fallback query fetched the broader upstream real-time table with a fixed 5,000-row cap even though the product only needs a maximum 48-hour received-time view;
- the live layer previously requested DataSF on page open even though it is optional;
- the street methodology still contained an old sentence saying no hill score had been calculated;
- one hill-method description still described only different-elevation contour crossings and therefore did not accurately describe the production v2 treatment of same-elevation supported spans;
- the source manifest and README had fallen behind the current live-dispatch architecture;
- the SFMTA closure source can expose a `data_as_of` timestamp older than the build date, so a daily GitHub build is not sufficient evidence that the upstream closure data itself is fresh.

The production pipeline now addresses these directly: bounded received-time live queries, documented-CAD uniqueness validation, live-source freshness and truncation guardrails, conditional runtime refresh only while the optional layer is enabled, correct aggregate open/closed/mixed styling, source-age display/warnings for time-sensitive layers, and a final semantic pass plus deep end-to-end audit on the exact HTML that is deployed.

## Layer-by-layer audit contract

### 1. Street network

**Production source:** SF Public Works / DataSF `3psu-pn9h` — Streets – Active and Retired.

Checks:

- every displayed feature is line geometry;
- every displayed feature has a unique non-empty CNN;
- every displayed row is `active = true`;
- `PAPER`, `PAPER_FWYS`, `PAPER_WATER`, `PSEUDO`, and `PRIVATE_PARKING` do not leak into the displayed route-context backbone;
- geometry remains inside broad SF coordinate guardrails;
- source class code affects styling only and is not converted into a route/canvassing score.

Interpretation guardrail: the exclusion list is a **product map policy**, not a claim that Public Works officially certifies every retained line as publicly walkable. `active` means not retired, not public access.

### 2. Hill steepness

**Production source:** DataSF `rnbg-2qxw` — Elevation Contours.

Checks:

- source contour elevations conform to the documented five-foot interval;
- freeway/ramp classes receive `not_applicable`, not a canvassing hill grade;
- classified streets use only `direct_5ft_contour_crossings_v2`;
- same-elevation consecutive crossings contribute zero net rise over supported span;
- non-zero consecutive crossings must differ by approximately five feet;
- ambiguous crossings, non-five-foot jumps, degenerate spans, and >45% short-span artifacts are rejected;
- classified values must be between 0% and 45%;
- every classified value includes support fraction and high/medium/low confidence;
- low-confidence estimates are visibly dashed/faded;
- streets without sufficient direct evidence remain unavailable rather than interpolated.

Interpretation guardrail: the displayed number is a **contour-supported route-planning estimate over directly supported portions**, not an official engineering street-grade survey or guaranteed whole-segment mean.

### 3. Precinct boundaries

**Production source:** SF Department of Elections / DataSF `d6x4-hefw` — Election Precincts — Current, Defined 2022.

Checks:

- official polygon/MultiPolygon geometry only;
- unique non-empty precinct identifier;
- plausible SF geometry and broad feature-count guardrail;
- no derived `score`, `risk`, or operational metric is stored on precinct features.

Interpretation guardrail: precincts are neutral reference geography. The map does not calculate a precinct targeting score, neighborhood safety score, or political ranking.

### 4. High-unit residential parcels

**Production source:** SF Planning / DataSF `c5ge-t6pj` — Current San Francisco Land Use.

Checks:

- `geography_type = parcel` only;
- `resunits >= 20` only;
- unique stable parcel ID after controlled duplicate handling;
- polygon/MultiPolygon geometry only;
- threshold totals are independently recomputed and must agree with embedded metadata;
- repeated parcel geometry with conflicting unit counts may only be retained when every observed count remains in the same 20/50/100/200 display bucket;
- a threshold-crossing conflict or repeated parcel ID with different geometry fails the build.

Interpretation guardrail: parcel geometry is a property lot, **not necessarily a building footprint**. Unit count does not prove a lobby is locked, shared, or accessible. The values remain source-reported Planning data rather than model-generated estimates.

### 5. Temporary street closures

**Production source:** SFMTA / DataSF `8x25-yybr` — Temporary Street Closures.

Checks:

- only `status = Permitted` rows are embedded;
- non-empty unique object ID;
- official LineString/MultiLineString geometry is rendered directly;
- valid source start/end window;
- map opens with no planning date and therefore no closure lines;
- a selected SF calendar date uses full-day interval overlap, not a hidden exact-time filter;
- exact source hours remain available in hover/click details;
- related Public Works context is attached only to `Special Traffic Permit` rows and only when street, date overlap, and <=120 m spatial criteria pass;
- related Public Works records are labeled context, not proof of causation;
- closure `data_as_of` freshness is surfaced. More than two days behind the build requires a UI warning; more than fourteen days fails the deep production audit.

Interpretation guardrail: the official line indicates SFMTA-permitted street/vehicle disruption. It does not prove pedestrian access is blocked and is not a complete inventory of every closure managed by every City department.

### 6. Public Works street-work / ROW permits

**Production source:** Public Works / DataSF `bpc9-7sus` — Active and upcoming street surface permits.

Checks:

- allowed product types only: `Excavation`, `TempOccup`, `StrtImprov`, `ExcStreet`, `AddlStSpac`, `StorCont`, `MinorEnc`, `StreetSpace`;
- `ACTIVE` or `APPROVED` source status only;
- valid official source point and permit number;
- valid start/end authorization window;
- selected calendar date is inclusive inside the permit window;
- display is suppressed outside the build's current/+14-day support window;
- layer is off by default and does not pre-create thousands of hidden SVG markers;
- aggregation key is permit number + type + exact source point + exact permit window;
- all distinct source locations/descriptions/statuses preserved when source rows share that marker key;
- no point is expanded into a guessed work polygon or street segment.

Interpretation guardrail: a permit establishes authorization, not that crews are present, a closure exists, or pedestrians cannot pass.

### 7. Recent law-enforcement dispatch activity

**Production source:** DataSF `gnap-fj3t` — Law Enforcement Dispatched Calls for Service: Real-Time.

Checks:

- optional layer, off by default;
- user windows are based on `received_datetime`: 1, 3, 6, 12, 24, or 48 hours;
- Police-only is the default agency filter;
- optional all-agency and open-only controls are explicit;
- build fallback requests only the preceding 49 SF-local wall-clock hours;
- source query cap is 10,000 and a response reaching the cap is rejected rather than silently treated as complete;
- every queried source row must contain a unique documented `cad_number`;
- `cad_number` is used for validation but is not embedded in user-facing feature properties;
- source `data_as_of` and newest-call time must each be no more than 180 minutes stale at build time;
- all embedded mapped features must fall within the 49-hour fallback buffer;
- public geometry must be a valid privacy-mapped SF point;
- absent `close_datetime` means open; populated close time means closed;
- runtime response receives the same cap, CAD uniqueness, freshness, recency and minimum-mapped-row checks before it can replace the audited fallback;
- no live request is made merely by opening the map; enabling the optional layer triggers the official DataSF request and the layer may refresh at most every 10 minutes while enabled;
- low-zoom aggregates are display-only and distinguish all-open, all-closed, and mixed represented calls rather than using one status color for every aggregate;
- the aggregate center is not described as an incident location.

Interpretation guardrail: dispatched calls are **not confirmed crimes** and cannot be used as a definitive crime count. Public locations are privacy-mapped to intersections and sensitive call types can suppress location. The map does not calculate a neighborhood or precinct safety/risk score.

## Final artifact checks

Immediately before deployment, `scripts/deep_accuracy_audit.py` reads the exact generated `_site/index.html` and `_site/data-manifest.json` and verifies:

- all seven production dataset IDs and official DataSF links;
- layer geometry types, identifiers, broad count guardrails and critical filters;
- derived hill method/support/confidence consistency;
- parcel threshold totals and duplicate-conflict handling;
- closure/permit time semantics and no guessed geometry;
- live query cap, CAD uniqueness, freshness and received-time behavior;
- no stale user-visible text that contradicts the current implementation;
- no duplicate HTML IDs;
- no external JavaScript or stylesheet dependencies;
- exactly one allowed runtime `fetch()` path, the optional official DataSF real-time dispatch feed;
- inline JavaScript syntax using `node --check`.

If any invariant fails, GitHub Pages deployment is skipped and the prior successful site remains live.

## What this audit cannot guarantee

- It cannot make official source data more accurate than the agencies that publish it.
- It cannot know whether a permit-authorized obstruction is physically present at a particular moment without an official real-time source saying so.
- It cannot infer pedestrian access from a vehicle closure.
- It cannot infer exact incident addresses from intentionally privacy-mapped dispatch data.
- It cannot turn contour-derived grades into official engineering measurements.
- It cannot guarantee every Planning parcel's `resunits` value is correct; the product reports the source value and links to the official dataset for manual verification.
- It cannot treat absence from a source as proof that a condition does not exist when the source itself is incomplete in scope.

Those are product-level limitations, not hidden assumptions: the UI and documentation are expected to state them explicitly.
