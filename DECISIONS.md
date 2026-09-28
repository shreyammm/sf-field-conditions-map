# Decision log

This file records consequential product and methodology choices so the map does not silently drift.

## D001 — Precincts are reference geography
**Status:** approved

Precinct boundaries stay visually neutral. Apartment, hill, incident, closure, and construction conditions should be shown at their natural geography rather than forced into precinct-level scores.

## D002 — Public data only
**Status:** approved

Use reliable public data, preferring official City and County of San Francisco / DataSF sources. No voter file, canvasser-entered access status, or private campaign data is required for the public-data map.

## D003 — No single canvassing-difficulty score
**Status:** approved

Keep apartment concentration, terrain, reported incidents, and temporary disruptions as separate interpretable layers.

## D004 — Large residential parcels are an access-friction proxy
**Status:** approved

Residential unit count is used as a proxy for places where many doors may be concentrated behind a shared entrance. The map must not claim that a building is inaccessible.

## D005 — Exclude broad Planning geographies from the apartment route layer
**Date:** 2026-09-27
**Status:** approved after visual review

The first build filled every SF Planning 20+ unit geometry. The source contained `parcel`, `multiple_parcels`, and `analytical` geography types. Large analytical areas in the Presidio and elsewhere looked like dense apartment properties even though the geometry represented a broad planning area.

For the route-planning apartment layer, display only records where:

`resunits >= selected threshold` AND `geography_type = parcel`

`analytical` records are excluded. `multiple_parcels` records are also withheld until we validate a representation that does not imply one giant building or property lot.

**Reason:** for canvassing routes, spatial precision is more useful than completeness. A false large footprint is more misleading than temporarily omitting an unusual multi-parcel complex.

## D006 — Explain parcel meaning in the UI
**Date:** 2026-09-27
**Status:** approved

The interface explicitly says that a colored shape is one property parcel with the reported number of residential units. It is not precinct/neighborhood density and the parcel boundary is not necessarily the building footprint.

Hover and click text should explain both the source fact and the possible shared-entry interpretation without overstating accessibility.

## D007 — Production refreshes use official SF sources only
**Date:** 2026-09-27
**Status:** approved during sanity audit

Production refreshes do not silently switch to third-party source snapshots. If an official SF/DataSF production source fails, the workflow fails and GitHub Pages keeps serving the prior successful deployment.

## D008 — Exact duplicate parcel records are resolved and logged
**Date:** 2026-09-27
**Status:** revised by D011

Exact duplicate parcel IDs are only auto-resolved when geometry is also identical. The first implementation kept the larger unit count when duplicate unit values conflicted. D011 tightens this to surface the observed range and fail if a conflict crosses a displayed threshold.

## D009 — Methodology belongs inside the product
**Date:** 2026-09-27
**Status:** approved

The map includes an in-product methodology key. Each legend category explains what it means, provenance is stated, “parcel” is defined, unit-count thresholds are documented, exclusions are explained, and current source/build counts are surfaced.

## D010 — SF Public Works centerlines are the street backbone
**Date:** 2026-09-27
**Status:** revised by D011

Use SF Public Works / DataSF `Streets – Active and Retired` (`3psu-pn9h`) as the source for the visual street network and canonical street-segment geography for later street-based layers. Preserve CNN, name/endpoints, class code, source layer, jurisdiction, and geometry. Street class codes are for visual hierarchy only, not a canvassing score.

Future hill grade, temporary closure, and construction information should attach to the same displayed street segments where the public source permits a reliable CNN or validated spatial join.

## D011 — Sanity-audited street backbone and source ambiguity handling
**Date:** 2026-09-28
**Status:** approved after source audit

“Active” in the Public Works street source means “not retired”; it does not mean that every active source feature is a real/publicly traversable street. The production street backbone therefore starts with `active = true` and excludes source layers `PAPER`, `PAPER_FWYS`, `PAPER_WATER`, `PSEUDO`, and `PRIVATE_PARKING`. Private streets, pedestrian-only streets, park/NPS roads, unpaved rights-of-way, freeways, and ramps can remain as contextual centerlines but must not be described as necessarily publicly accessible.

CNN is described as the source/City segment identifier, not as permanently immutable. Endpoint fields are described as “between” streets rather than a travel direction.

Street labels are cached and may repeat spatially as zoom increases so long streets remain identifiable at neighborhood scale. Major street classes are rendered above lower-priority local context.

For exact duplicate parcel rows with identical geometry, conflicting unit values may be auto-resolved only if all observed values fall in the same displayed threshold bucket; the UI shows the observed range. A conflict that crosses a 20/50/100/200 threshold, or a repeated parcel ID with different geometry, fails the build for manual review.

## D012 — Hill steepness uses direct official contour crossings
**Date:** 2026-09-28
**Status:** audited production methodology

The hill layer derives a street-level steepness estimate from DataSF Elevation Contours (`rnbg-2qxw`), which publishes 5-foot contour lines. The production method directly intersects each non-freeway displayed Public Works street centerline with those contours.

Two prototype approaches were rejected before deployment: nearby-contour interpolation and a smoothed interpolation variant. Both produced implausible 60%+ values on ordinary streets. The later direct-crossing method removed that failure mode, but a second audit found a subtler upward-bias risk: it counted only intervals between different contour elevations and therefore could silently omit directly supported same-elevation spans.

The revised production method treats consecutive same-elevation crossings as zero net rise across that supported span. Nonzero consecutive crossings must differ by approximately the documented 5-foot contour interval; non-5-foot jumps and implausible >45% short-span intervals are rejected instead of clipped. Accepted intervals are combined by directly supported along-street distance. Confidence also incorporates what fraction of the whole street segment is supported by accepted contour intervals.

Freeway mainlines and ramps are marked `not_applicable` rather than receiving a canvassing hill classification. Streets without enough direct contour evidence remain `unavailable`. Low-confidence estimates are visually faded/dashed.

The displayed value is labeled a **contour-supported grade estimate** because it describes the supported portions of the segment and is not an official engineering street-grade survey or guaranteed full-segment average. Display buckets remain `<5%`, `5–9.9%`, `10–14.9%`, `15–19.9%`, and `20%+`.

## D013 — Temporary closures use official SFMTA line geometry and SF-local time
**Date:** 2026-09-28
**Status:** audited production methodology; revised by D016

Use SFMTA / DataSF Temporary Street Closures (`8x25-yybr`) as the temporary-closure layer. Render the official closure line geometry directly rather than replacing it with an inferred precinct or full-street highlight.

Although DataSF documentation describes the published dataset as permitted closures, the 2026-09-28 download also contains rows in application/workflow statuses. Production therefore explicitly keeps only `status = Permitted`. Rows must also have line geometry and a valid `start_dt <= end_dt` window.

The original implementation filtered by an exact selected San Francisco local time. D016 replaces that interaction with an optional calendar-date planner while retaining the source start/end times for details.

CNN is retained and checked against the street backbone as a validation signal, but source closure geometry remains authoritative for rendering. A missing/unmatched CNN does not cause a valid official closure line to be discarded.

The layer is described as an SFMTA-permitted street/vehicle disruption indicator. It must not claim that pedestrian passage is necessarily blocked, and it must state that SFMTA's feed does not include every closure managed by Public Works, SFPD, or other departments.

Because the current closure rows do not expose a usable `data_as_of` value, the UI reports when the snapshot was **retrieved** rather than inventing a source date. The automated production build refreshes daily; a failed refresh leaves the prior successful Pages deployment in place.

## D014 — Street-work / ROW permits are point-level authorization context, not closures
**Date:** 2026-09-28
**Status:** revised by D015 and D016

Use SF Public Works / DataSF `Active and upcoming street surface permits` (`bpc9-7sus`) for the construction/right-of-way context layer rather than treating the much larger historical Street-Use Permits table as if every historical record were currently relevant.

The source mixes construction/occupancy permits with vending and amenity uses. For route context, production keeps only the permit types `Excavation`, `TempOccup`, `StrtImprov`, `ExcStreet`, `AddlStSpac`, `StorCont`, `MinorEnc`, and `StreetSpace`. Vending, food-facility, parklet, blank-type, and NightNoise rows are excluded from this layer because they are not a clean physical-work/ROW-occupancy signal.

Render the official source **point** geometry. Do not stretch a point into a street segment, parcel, or work-zone polygon unless a future official source provides that extent. An overlapping permit window means the City has authorized street/sidewalk use during that period; it does **not** prove crews are physically working at the selected moment, that the street is closed, or that pedestrians cannot pass.

Permit rows are filtered by the selected San Francisco **calendar date**, inclusive of the permit start/end dates, because many source windows are day-level rather than precise operational hours. The source is a current/upcoming snapshot (current permits plus starts in the near-term window), so the map suppresses the permit layer outside the documented snapshot support range rather than implying historical or far-future completeness.

The layer is opt-in/off by default because several thousand permit authorization windows can overlap one date and would otherwise obscure the core street/parcel/closure map. The original implementation described same-point rows as “exact duplicates”; D015 corrects that interpretation.

## D015 — Full-layer audit: preserve co-located permit rows and audit the final artifact
**Date:** 2026-09-28
**Status:** production audit correction

A source-level audit found that the original ROW-permit collapse key grouped **141 additional source rows into 50 marker keys**, but **46 of those marker groups contained different street/cross-street descriptors**. They were therefore not safely describable as exact duplicates. Several Public Works permits publish multiple textual street locations at the same official point.

Production now aggregates rows only when they share the same permit number, permit type, **exact source point**, and permit start/end window. One point marker is still appropriate because the source geometry is identical, but the marker preserves every distinct source street/cross-street pair, description, status, neighborhood, district, and relevant row timestamp rather than arbitrarily keeping one row's text. Hover/click explicitly explains when multiple source rows or locations share one official point. This does not make the point an exact work footprint.

The audit also found two UI/engineering issues. The shared date/time control had a closure-only accessibility label even though both closures and permits use it; it is now labeled as the field date/time. And the opt-in permit layer previously created thousands of SVG circles on page load and merely hid them; it now creates permit markers only when the layer is enabled and clears them when disabled.

Closure filtering was tightened to require an explicit `Permitted` status; a blank status can no longer slip through as implicitly acceptable.

A separate final-artifact audit now runs on every build **before GitHub Pages deployment**. It re-checks layer counts, geometry types, IDs, street exclusions, parcel geography/thresholds, hill fields and distributions, closure status/time/CNN behavior, permit aggregation and privacy fields, provenance IDs, UI defaults, external dependencies/runtime fetches, duplicate HTML IDs, and inline JavaScript syntax. If any invariant fails, deployment is skipped and the previous successful Pages version remains live.

## D016 — Planning date is optional; closures are shown for any overlap with that day
**Date:** 2026-09-28
**Status:** approved by user and deployed

Do not initialize the map to “now.” The map opens with **no planning date selected**, so temporary closure lines and date-dependent permit markers are absent until the user explicitly chooses a date.

The control is a San Francisco **calendar date**, not a timestamp. A closure is displayed when its official local interval overlaps any portion of the selected day:

`closure_start < next_day_00:00 AND closure_end >= selected_day_00:00`

This means a closure scheduled only for 6–10 PM still appears when planning that date in the morning. The closure's exact official start/end hours remain visible in hover/click details.

The closure toggle remains on by default so selecting a date immediately reveals closures for that day. The dense Public Works ROW-permit layer remains off by default; if enabled, it uses the same selected calendar date and continues to respect the permit snapshot's supported current/upcoming window.

The date control includes **Today** (computed in `America/Los_Angeles`) and **Clear**. Clearing the date removes both date-dependent overlays without changing the stable street, hill, precinct, or high-unit residential layers.

A dedicated post-mutation audit verifies that the final deployed HTML uses a date input, has no default date, applies day-overlap closure logic, retains exact closure-time detail, keeps ROW permits opt-in, and introduces no duplicate IDs, runtime fetches, external dependencies, or JavaScript syntax errors.
