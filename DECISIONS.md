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

Hover and click text should explain both the source fact (residential-unit count on one parcel) and the canvassing interpretation (possible concentration of doors / shared-entry friction) without overstating accessibility.

## D007 — Production refreshes use official SF sources only
**Date:** 2026-09-27
**Status:** approved during sanity audit

The production build no longer silently falls back to a third-party precinct snapshot. If the official SF Elections / DataSF download fails, the workflow should fail and GitHub Pages should keep serving the last successful deployment.

**Reason:** preserving an older verified official build is preferable to silently changing provenance during an upstream outage.

## D008 — Exact duplicate parcel records are resolved and logged
**Date:** 2026-09-27
**Status:** approved during sanity audit

The sanity audit found one exact duplicate parcel ID and geometry in the current SF Planning snapshot with two reported residential-unit counts (170 and 174). The build now deduplicates only when the parcel ID and geometry are identical. If the counts conflict, the larger count is retained and the conflict is written to the build manifest. If the same parcel ID ever arrives with different geometry, the build fails for manual review.

## D009 — Methodology belongs inside the product
**Date:** 2026-09-27
**Status:** approved

The map includes an in-product methodology key. Each legend category explains what it means, precinct provenance is stated, “parcel” is defined, unit-count thresholds are documented, excluded geographies are explained, and the current threshold counts / land-use snapshot date are shown from the bundled data.
