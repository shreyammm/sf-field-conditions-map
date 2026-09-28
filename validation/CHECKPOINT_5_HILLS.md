# Checkpoint 5 — Hill steepness layer

**Date:** 2026-09-28

## Production source

- SF DataSF **Elevation Contours** (`rnbg-2qxw`)
- 5-foot contour interval
- San Francisco mainland plus Treasure Island/Yerba Island
- Based on the San Francisco Elevation Datum
- Street geometry remains SF Public Works `3psu-pn9h`

## Production method — audited v2

The hill layer uses **direct street–contour crossings** rather than interpolating a continuous elevation surface.

For every applicable displayed street centerline, the build:

1. intersects the street geometry with the official 5-foot contour lines;
2. orders crossings by distance along the street;
3. collapses near-duplicate crossings at effectively the same along-street position;
4. rejects an ambiguous position if multiple materially different contour elevations collide there;
5. treats consecutive same-elevation crossings as **zero net rise** across that directly supported span;
6. requires a nonzero consecutive crossing to differ by approximately 5 feet, matching the documented contour interval;
7. rejects non-5-foot jumps, degenerate spans, and >45% short-span crossing artifacts instead of clipping them;
8. combines accepted intervals by directly supported along-street distance;
9. assigns high / medium / low confidence based on usable intervals, distinct contour elevations, supported distance, and the supported fraction of the full street segment.

Street class 1 freeway mainlines and class 6 freeway ramps are marked **not applicable** for the canvassing hill layer. Other streets without enough direct contour information remain **unavailable** rather than receiving a guessed grade.

The displayed value is a **contour-supported route-planning grade estimate over the directly supported portions of the segment**, not an official engineering street-grade survey or a guaranteed full-segment average.

## Why the method changed

### Rejected interpolation prototypes

The first prototype inverse-distance interpolated elevation from nearby contour samples. The build guardrail caught implausible 60%+ results on ordinary street segments. A smoothing variant still failed because the underlying interpolated elevations were unreliable. Neither version was deployed.

### Second audit of direct crossings

The first direct-crossing implementation removed the interpolation problem, but a deeper audit found a more subtle bias: it only kept intervals between **different** contour elevations. If a street crossed the same contour elevation again later, that directly supported flatter span could disappear from the weighted estimate, biasing the result upward.

The v2 method fixes this by retaining same-elevation consecutive crossings as zero net rise across that span, rejecting non-5-foot elevation jumps, and recording how much of the street is directly supported. Confidence is downgraded when coverage is low.

This methodological correction changed the classified median from 7.0% to 6.4% and reduced the 20%+ count from 437 to 408 while slightly increasing overall classified coverage.

## Current audited build

- 15,901 displayed street segments total
- 219 freeway/ramp segments marked not applicable
- 15,682 applicable non-freeway/ramp segments
- 9,375 with a contour-supported grade estimate
- 6,307 unavailable because direct contour evidence was insufficient
- confidence among classified streets: 4,688 high; 2,006 medium; 2,681 low
- grade buckets:
  - 3,481 under 5%
  - 3,329 at 5–9.9%
  - 1,554 at 10–14.9%
  - 603 at 15–19.9%
  - 408 at 20%+
- classified distribution: median 6.4%; 75th percentile 10.5%; 90th 15.4%; 95th 19.2%; 99th 27.2%; maximum 37.4%
- rejected during the audit build: 23 ambiguous crossing clusters; 11 non-5-foot jumps; 0 accepted intervals requiring the >45% rejection guard in this snapshot

The classified subset is not a random sample of all streets: contour-crossing coverage is naturally better on sloped streets. Do not interpret those percentiles as the citywide street-grade distribution.

## Visual treatment

- `<5%`: neutral gray
- `5–9.9%`: light amber
- `10–14.9%`: orange
- `15–19.9%`: red-orange
- `20%+`: dark red
- insufficient direct contour evidence: gray dashed / unavailable
- low-confidence estimate: faded + dashed in its grade color
- freeway/ramp context: no hill classification

Hover/click copy says “contour-supported grade estimate,” shows confidence, and click details include the directly supported segment coverage where available.

## Acceptance checks

- official contour source only;
- contour elevations must conform to the documented 5-foot grid;
- at least 1,500 applicable displayed street segments must receive direct-crossing estimates;
- no accepted interval exceeds 45% grade;
- no more than 12% of classified segments may land in the 20%+ bucket without manual review;
- non-5-foot elevation jumps are not silently interpreted as one enormous rise interval;
- unavailable streets are explicitly unavailable, not zero-percent grade;
- freeway/ramp context is explicitly not applicable;
- methodology, confidence, and coverage limitation are visible in the map UI;
- the hill layer can be toggled independently;
- failed hill builds do not replace the last successful GitHub Pages deployment.

## Review gate

The computation has now passed two methodological audits and automated deployment checks. It is still appropriate to visually compare known steep and flat streets before treating any individual estimate as route-critical, especially where confidence is low. Future work should prefer an official street-grade dataset if the City publishes a suitable one; the contour-derived layer is explicitly an analytical estimate.
