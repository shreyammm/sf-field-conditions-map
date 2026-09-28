# Checkpoint 5 — Hill / terrain-grade layer

**Date:** 2026-09-28

## Goal

Add a street-level hill layer useful for route orientation without presenting a generic land-slope polygon as though it were a measured road grade. Hill values stay attached to the same Public Works street segments/CNNs already used by the map.

## Sources

- Street geometry: SF Public Works / DataSF `Streets – Active and Retired` (`3psu-pn9h`), using the audited displayed-street filter.
- Elevation: DataSF `Elevation Contours` (`rnbg-2qxw`), 14,151 line features in the current source snapshot with elevations on five-foot intervals.
- Published steep-block values are used only as broad regression examples; they are not substituted for the City contour data.

## Derivation

For every displayed street segment, the build intersects the centerline with the five-foot contours and orders crossings along the line. It calculates:

- **peak terrain-grade estimate:** steepest monotonic rise/run over a span of at least 80 horizontal feet;
- **whole-segment fallback:** observed contour elevation range / total segment length when no 80-foot monotonic window exists;
- **display grade:** peak estimate when available, otherwise the conservative fallback.

The calculation reports grade magnitude only. Horizontal distance is approximated locally from WGS84 geometry and converted to feet. The UI calls this a terrain-grade proxy/estimate, not a surveyed roadway grade.

## Current sanity checks

Broad reference checks on the current snapshot:

- Filbert St, Hyde–Leavenworth: ~31.8% derived vs. 31.5% published reference.
- 22nd St, Church–Vicksburg: ~32.5% vs. 31.5%.
- Jones St, Union–Filbert: ~30.2% vs. 29%.
- Duboce Ave, Alpine–Buena Vista Ave East: ~25.7% vs. 27.9%.

Flat/context checks also show the expected pattern: nearly all Embarcadero and Great Highway segments fall below 5% in the current derivation.

## Current distribution

All 15,901 displayed street-context segments:

- 0–4.9%: 9,622
- 5–9.9%: 2,978
- 10–14.9%: 1,686
- 15–19.9%: 875
- 20%+: 740

The hill visualization does not emphasize 219 freeway/ramp context segments. Among the remaining 15,682 route-context segments, 3,223 are at least 10% by the derived metric. Counts are build outputs, not hard-coded source facts.

## UI

- Separate Hill grade coloring toggle.
- User-selectable 5% / 10% / 15% / 20% minimum emphasis threshold; default 10%+.
- Absolute grade-bin colors so threshold selection does not change the meaning of a color.
- Hover shows the approximate grade and whether it came from the ≥80-ft peak method or fallback.
- Click shows peak-window estimate, whole-segment fallback, contour-crossing count, source street category, and the terrain/survey caveat.
- Freeways/ramps remain visible but do not receive hill coloring.

## Limitations

This is terrain inference along a mapped centerline, not a legal or engineering grade. It can diverge from the traveled surface on bridges, tunnels, grade-separated structures, stairs, unusual rights-of-way, or where centerline geometry differs from the actual walking path. Very local micro-slopes shorter than the contour spacing/window are not guaranteed to be captured.

## Acceptance checks before main deployment

- contour schema/interval validation passes;
- every displayed street receives a finite hill metric or an explicit unavailable state;
- steep-block regression guardrails pass;
- no hill color is applied to freeway/ramp context;
- JS syntax and generated HTML sanity checks pass;
- production build succeeds using official sources only;
- Pages deployment succeeds;
- source/methodology documentation and manifest are updated.
