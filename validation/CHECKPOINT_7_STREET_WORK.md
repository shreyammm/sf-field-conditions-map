# Checkpoint 7 — Street-work / right-of-way permit layer

**Date:** 2026-09-28  
**Status:** revised by the full-layer audit; this file reflects the corrected methodology.

## Production source

- SF Public Works / DataSF **Active and upcoming street surface permits** (`bpc9-7sus`)
- Official point geometry
- Daily refresh
- Source scope: currently active permits plus permits starting within the near-term upcoming window
- Source combines Street-Use Permit and Street Vending Permit records, so production filters permit type instead of calling every source row construction

## Source audit

The audited source download contained **4,843 rows**:

- geometry: 4,839 Points; 4 missing geometry
- status: 3,710 `APPROVED`; 1,133 `ACTIVE`

Source permit types included both work/ROW uses and unrelated street uses. Production keeps only:

- `Excavation`
- `TempOccup`
- `StrtImprov`
- `ExcStreet`
- `AddlStSpac`
- `StorCont`
- `MinorEnc`
- `StreetSpace`

Vending, food-facility, parklet, NightNoise, and blank/unclassified types are excluded because they are not a clean signal of construction or physical ROW occupation for this route-context layer.

Eligible rows must also have status `ACTIVE` or `APPROVED`, a permit number, valid SF Point geometry, and a valid permit start/end window.

## Important audit correction: same point does not mean exact duplicate

The initial implementation treated rows sharing permit number/type/point/date window as exact duplicates. A deeper source audit proved that description was wrong.

There were **141 additional source rows across 50 repeated marker keys**, and **46 of those marker groups had different street/cross-street descriptors**. Examples included one excavation permit whose rows named several different streets while using the same official source point.

The corrected production rule is:

`same permit_number + permit_type + exact source point + permit start/end window -> one map marker`

But the marker preserves **all distinct source rows' operational text**: street/cross-street pairs, descriptions, statuses, neighborhoods, districts, approval dates, and relevant row timestamps. The source rows are aggregated for display because their geometry is identical; they are not discarded as duplicates.

This distinction matters. One marker can represent several source street-location rows, and the official point is not necessarily the exact extent of every named work location.

## Corrected embedded representation

The audited snapshot contains **4,372 eligible work/ROW source rows represented by 4,231 point markers**. The 141-row difference is retained inside the 50 aggregated marker records rather than silently dropped.

Marker type counts remain:

- Excavation: 3,692
- TempOccup: 358
- StrtImprov: 100
- ExcStreet: 48
- AddlStSpac: 20
- StorCont: 11
- MinorEnc: 1
- StreetSpace: 1

The route-type filter excludes 469 non-work/unclassified source rows; two audited rows had invalid/missing date windows.

The embedded properties intentionally exclude DBA/applicant/contact information and raw latitude/longitude duplicates. Only operational permit metadata and official point geometry are retained.

## Date filtering and completeness

The layer shares the map's **Field date/time (San Francisco)** control with closures, but permit filtering uses the selected SF **calendar date** because many permit windows are day-level rather than exact work hours.

A marker is eligible when:

`permit_start_date <= selected SF date <= permit_end_date`

This means the authorization window overlaps the selected date. It does **not** mean crews are necessarily physically working then.

The source is a current/upcoming view, not a historical archive. Production anchors completeness to the actual San Francisco retrieval date and suppresses the permit layer outside that date through 14 days later. Row-level `data_as_of` remains diagnostic metadata only.

On the initial 2026-09-27 snapshot, **3,921** marker authorization windows overlapped the date. The layer is therefore **off by default**.

## UI/performance correction from full audit

The first opt-in implementation still created thousands of permit SVG circles on initial page load and hid the group. The corrected implementation does not create permit circles until the user enables the layer; disabling it clears them again.

The shared date/time input also previously retained a closure-only accessibility label. It is now labeled **Field date and time in San Francisco** because both the closure and permit layers use it.

## Interpretation safeguards

- Teal circles are official permit **point locations**, not work-zone polygons.
- Multiple source street locations can share one point.
- Production does not expand a point into a whole street block or parcel.
- A permit is authorization for street/sidewalk use; it does not prove physical work is occurring at that moment.
- A permit is not a confirmed street closure.
- A permit does not establish pedestrian inaccessibility.
- Exact work timing may be narrower than the permit window.
- ROW permits remain visually separate from SFMTA closure lines.

## Permanent build audit

The full artifact now fails deployment unless the final embedded permit layer has valid points/windows/types/status lists, unique aggregation keys, preserved aggregation counts, no unnecessary applicant/contact fields, a 14-day support window tied to SF retrieval date, and the expected opt-in rendering behavior. These checks run alongside invariant checks for all earlier map layers.
