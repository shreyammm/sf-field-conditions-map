# Checkpoint 5 — Hill steepness layer

**Date:** 2026-09-28

## Production source

- SF DataSF **Elevation Contours** (`rnbg-2qxw`)
- 5-foot contour interval
- San Francisco mainland plus Treasure Island/Yerba Island
- Based on the San Francisco Elevation Datum
- Street geometry remains SF Public Works `3psu-pn9h`

## Method selected

The production hill layer uses **direct street–contour crossings** rather than interpolating a continuous elevation surface.

For every displayed street centerline, the build:

1. intersects the street geometry with the official 5-foot contour lines;
2. orders crossings by distance along the street;
3. computes rise/run between consecutive crossings of different known elevations;
4. rejects tiny/degenerate and >45% crossing artifacts instead of clipping them;
5. combines the remaining supported intervals by distance;
6. assigns a high / medium / low confidence level based on the number of usable intervals, distinct contour elevations, and directly supported street length.

Streets without enough direct contour information remain **unavailable** rather than receiving a guessed grade.

The displayed value is an analytical estimate for route-planning context, **not an official engineering street-grade survey**.

## Rejected prototype

The first prototype inverse-distance interpolated elevation from nearby contour samples. The build guardrail caught implausible 60%+ results on ordinary street segments. A regression smoothing variant still produced the same failure because the underlying interpolated elevations were wrong. Neither version was deployed.

This failure is intentionally documented because it changed the methodology: the production version only uses direct contour evidence.

## Current build distribution

Successful direct-crossing build before the final visual-confidence patch:

- 15,901 displayed street segments total
- 9,062 with a derived grade
- 6,839 unavailable because direct contour evidence was insufficient
- confidence among classified streets: 4,745 high; 1,882 medium; 2,435 low
- grade buckets: 2,917 under 5%; 3,409 at 5–9.9%; 1,646 at 10–14.9%; 653 at 15–19.9%; 437 at 20%+
- classified-grade distribution: median 7.0%; 75th percentile 11.0%; 90th 16.0%; 95th 19.8%; 99th 27.9%; maximum 37.4%

The classified subset is not a random sample of all streets: contour-crossing coverage is naturally better on sloped streets. Do not interpret those percentiles as the citywide street-grade distribution.

## Visual treatment

- `<5%`: neutral gray
- `5–9.9%`: light amber
- `10–14.9%`: orange
- `15–19.9%`: red-orange
- `20%+`: dark red
- insufficient contour crossings: gray dashed / unclassified
- low-confidence estimates: faded + dashed in their grade color

Freeways and ramps remain contextual street geometry and are not emphasized as canvassing hill streets.

## Acceptance checks

- official contour source only;
- contour feature count must remain in a broad expected range;
- at least 1,500 displayed street segments must receive direct-crossing estimates;
- no accepted interval exceeds 45% grade;
- no more than 12% of classified segments may land in the 20%+ bucket without manual review;
- unavailable streets are explicitly represented as unavailable, not zero-percent grade;
- methodology and confidence are visible in the map UI;
- the hill layer can be toggled independently;
- failed hill builds do not replace the last successful GitHub Pages deployment.

## Review gate

The computation is now production-safe enough for visual review. Before using it as a routing decision layer, visually inspect several known steep and flat areas and decide whether the bucket colors / low-confidence treatment are intuitive enough in combination with parcels and precincts.
