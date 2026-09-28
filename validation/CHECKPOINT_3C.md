# Checkpoint 3C — Apartment layer route-clarity correction

**Date:** 2026-09-27

## Problem found in review

The first multifamily visualization filled all SF Planning records with 20+ residential units. The source includes multiple geography types, not only individual property parcels. Broad `analytical` records produced visually large filled areas in places such as the Presidio, which could be mistaken for apartment density.

## Correction

The displayed apartment/access-friction layer now retains only:

- `geography_type = parcel`
- residential units at or above the selected 20 / 50 / 100 / 200 threshold

The build records counts of excluded `analytical` and `multiple_parcels` records in the data manifest and exposes those counts in the UI.

## UI changes

- Layer renamed to **Large residential parcels**.
- Threshold labeled **Minimum units on one parcel**.
- A plain-language explanation defines a parcel as the colored property lot and explicitly says the layer is not neighborhood density.
- Hover identifies unit count, parcel ID, and why the parcel appears.
- Click gives source-supported descriptive fields when available and states the canvassing interpretation/caveat.
- Broad non-parcel geographies are explicitly described as excluded.

## Acceptance checks

The build must fail if a retained 20+ unit record is not `geography_type = parcel`.

The generated manifest must include:

- displayed parcel feature count;
- source 20+ unit counts by geography type;
- excluded analytical and multi-parcel counts;
- build timestamp and source freshness metadata.

## Open question

Large residential complexes represented as `multiple_parcels` may still matter for canvassing. They are intentionally omitted for now. Before reintroducing them, test a separate symbol/outline representation that does not make the whole complex look like one building footprint.
