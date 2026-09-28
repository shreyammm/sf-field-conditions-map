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
