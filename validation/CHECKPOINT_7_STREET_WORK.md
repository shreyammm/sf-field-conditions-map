# Checkpoint 7 — Street-work / right-of-way permit layer

**Date:** 2026-09-28

## Production source

- SF Public Works / DataSF **Active and upcoming street surface permits** (`bpc9-7sus`)
- Official point geometry
- Daily refresh
- Source scope: currently active permits plus permits starting within the near-term upcoming window
- Source combines Street-Use Permit and Street Vending Permit records, so production must filter by permit purpose/type rather than displaying every source row as construction

## Source audit

The 2026-09-28 source download contained **4,843 rows**:

- geometry: 4,839 Points; 4 missing geometry
- status: 3,710 `APPROVED`; 1,133 `ACTIVE`

Source permit types included both construction/ROW work and non-construction street uses:

- Excavation: 3,825
- TempOccup: 358
- FoodFac: 143
- StreetVending - Referral: 133
- StrtImprov: 103
- blank: 82
- StreetVending - merchandise: 64
- ExcStreet: 50
- NightNoise: 31
- AddlStSpac: 24
- Parklet: 14
- StorCont: 11
- StreetVending - Merchandise: 2
- MinorEnc: 2
- StreetSpace: 1

This audit is why the production layer does **not** simply display all 4,843 source records as “construction.”

## Production filter

Keep only these types:

- `Excavation`
- `TempOccup`
- `StrtImprov`
- `ExcStreet`
- `AddlStSpac`
- `StorCont`
- `MinorEnc`
- `StreetSpace`

Exclude vending, food-facility, parklet, NightNoise, and blank/unclassified types. Those are legitimate permits but are not a clean signal of physical street/sidewalk work or ROW occupation for route planning.

Rows must also:

1. have status `ACTIVE` or `APPROVED`;
2. have valid SF Point geometry;
3. have a valid permit start/end date window;
4. survive exact duplicate collapsing by permit number, type, point, start, and end.

## Audited embedded result

The successful production build embedded **4,231 unique route-relevant permit points** from 4,843 source rows.

Embedded type counts:

- Excavation: 3,692
- TempOccup: 358
- StrtImprov: 100
- ExcStreet: 48
- AddlStSpac: 20
- StorCont: 11
- MinorEnc: 1
- StreetSpace: 1

Omitted during production filtering:

- 469 non-work/unclassified permit types
- 141 exact duplicate rows
- 2 invalid/missing date windows

All 4,231 embedded geometries are Points. No exact duplicates remain under the production dedupe key.

The embedded properties intentionally exclude DBA/applicant/contact information and raw latitude/longitude duplicates. Retained properties are limited to operational permit metadata such as permit number/type/description/status, permit dates, street/cross street, neighborhood/district, row-level `data_as_of`, and the official point geometry.

## Date filtering and completeness

The layer shares the map's **Field date/time (San Francisco)** control with the closure layer, but permit filtering uses only the selected SF **calendar date** because many permit windows are day-level rather than exact operational hours.

A permit marker is eligible when:

`permit_start_date <= selected SF date <= permit_end_date`

This means the **authorization window overlaps the selected date**. It does not mean crews are necessarily physically working at that moment.

The current/upcoming source is not a historical archive. The source documentation defines it as current permits plus permits starting in the near-term upcoming window, so completeness is anchored to the **actual San Francisco retrieval date**, not to a row-level `data_as_of` value. Row-level `data_as_of` varies by permit and therefore is retained only as record metadata/diagnostic information.

The audited build retrieved the source at **2026-09-27 23:12 SF time** and therefore treats **2026-09-27 through 2026-10-11** as the supported current/upcoming snapshot window. The map suppresses this layer outside that range instead of silently showing incomplete historical or far-future results.

On 2026-09-27, **3,921** embedded permit windows overlap the date. Because this is visually dense, the layer is **off by default** and must be explicitly toggled on.

## Interpretation safeguards

- Teal circles are official permit **point locations**, not work-zone polygons.
- Production does not expand a point into a whole street block or parcel.
- A permit is authorization for street/sidewalk use; it does not prove the space is currently obstructed.
- A permit is not a confirmed street closure.
- A permit does not establish pedestrian inaccessibility.
- Exact work timing may be narrower than the permitted date window.
- Construction/ROW permits stay visually separate from SFMTA closure lines.

## Artifact audit

The successful generated artifact was inspected after build:

- 4,231 embedded work/ROW permit points
- statuses in embedded layer: 3,267 APPROVED; 964 ACTIVE after type/date/geometry/dedupe filtering
- only the eight approved production permit types are present
- all embedded work geometries are Points
- zero exact duplicate production keys remain
- no duplicate HTML IDs
- one each of `wToggle`, `ws`, `wl`, shared `cTime`, and `cNow`
- no runtime `fetch()` calls
- no external JavaScript or stylesheet dependencies
- both generated JavaScript blocks pass `node --check`
- no applicant, phone, email, DBA, or similar unnecessary fields are embedded in the work-permit properties

## Review gate

The data/source methodology and generated artifact passed the build audit. Visual review should focus on whether teal permit points are legible when intentionally enabled and whether the amount of detail in hover/click is useful. Because the layer can contain thousands of overlapping permit windows, it remains opt-in by default rather than competing with streets, closures, parcels, and hills on initial load.
