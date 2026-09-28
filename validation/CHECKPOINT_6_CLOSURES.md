# Checkpoint 6 — Temporary street closures

**Date:** 2026-09-28

## Production source

- SFMTA / DataSF **Temporary Street Closures** (`8x25-yybr`)
- Official SFMTA closure line geometry
- Documentation scope: Shared Spaces, certain special events, and some construction work permitted by SFMTA
- Source/report cadence: daily
- Explicit limitation: the feed does not include every closure managed by Public Works, SFPD, or other departments

## Production filter

The build downloads the official GeoJSON and embeds only rows that satisfy all of the following:

1. `status = Permitted` (case-insensitive);
2. geometry is `LineString` or `MultiLineString`;
3. `start_dt` and `end_dt` parse as local timestamps;
4. `end_dt >= start_dt`.

The source geometry is displayed directly. CNN is retained and cross-checked against the Public Works street backbone for validation, but an unmatched CNN does not suppress a valid official SFMTA geometry.

## Why status is filtered explicitly

DataSF documentation says the dataset contains permitted temporary closures. The 2026-09-28 download nevertheless contained 345 rows in non-permitted workflow/application states. The application therefore does not rely on that prose description alone; it explicitly filters `status = Permitted`.

Source status counts in the audited download:

- Permitted: 4,283 — embedded
- Application In Review: 216 — excluded
- Submitted: 92 — excluded
- Pending Payment: 29 — excluded
- Pending Additional Information: 7 — excluded
- On Hold: 1 — excluded

Total source rows: 4,628. Embedded permitted rows: **4,283**.

## Geometry / identifier validation

- all 4,283 embedded rows have line geometry;
- all 4,283 have valid start/end windows;
- all 4,283 embedded object IDs are unique;
- 4,283 embedded rows contain a CNN;
- 4,281 CNN values match a currently displayed Public Works street segment;
- two do not match the filtered street backbone, but retain official SFMTA closure geometry and therefore remain displayable;
- no browser-side DataSF request is required to render the closure layer.

Embedded closure types:

- Roadway Shared Spaces: 3,139
- Special Event: 885
- Special Traffic Permit: 259

The embedded source time range in this snapshot is 2026-04-13 00:00 through 2027-10-10 23:59, San Francisco local wall time.

## Time-filter logic

The map exposes a `datetime-local` control labeled **Closure time (San Francisco)** and a **Now** button.

- The `Now` value is calculated with the browser's `Intl.DateTimeFormat` using `America/Los_Angeles`, so a user viewing from another time zone still gets San Francisco wall time.
- A closure is shown when `start_local <= selected_local_time <= end_local`.
- Source timestamps are compared as normalized `YYYY-MM-DDTHH:MM:SS` local-wall-time strings, which is valid for these same-time-zone ISO-like values.
- The layer is recomputed immediately when the selected date/time changes.

At approximately 2026-09-27 22:20 San Francisco time, the audited artifact returned **126 active closure lines**: 71 Special Events, 50 Special Traffic Permits, and 5 Roadway Shared Spaces. This count is only a point-in-time validation, not a permanent expected value.

## Interpretation / UI safeguards

- Closure lines are blue and independently toggleable.
- Hover shows case/name/location, type, and scheduled local interval.
- Click shows available vehicle-impact, direction, case number, and source info.
- The UI describes the feature as a street/vehicle disruption indicator.
- It explicitly does **not** claim that pedestrian passage is blocked.
- It explicitly states that the SFMTA feed is not a complete inventory of Public Works/SFPD/other-agency closures.

## Freshness handling

The current rows did not provide a usable `data_as_of` value. The product therefore does not show “source date unknown” as though that were meaningful metadata. It falls back to the successful build/retrieval date and labels it **retrieved**.

Because the source report is daily, the GitHub Actions workflow now rebuilds the embedded snapshot daily. If an upstream source or validation fails, the deployment job does not replace the prior successful site.

## Artifact checks

The successful production artifact was inspected after build:

- 514 precincts
- 15,901 displayed street segments
- 2,248 unique 20+ residential parcels
- 4,283 permitted closure lines
- all embedded closure statuses are `Permitted`
- all embedded closure geometries are `LineString` in the current snapshot
- no duplicate HTML IDs
- no runtime `fetch()` call
- no external JavaScript or stylesheet dependency

## Known limitations

1. The source is SFMTA-only and therefore not a complete City closure feed.
2. `veh_imp` describes vehicle impact; the layer does not infer pedestrian passability.
3. Some Special Traffic Permit windows are long-lived; the map follows the official start/end window rather than inventing a daily sub-schedule.
4. A closure CNN can be absent from the filtered route-context street backbone due to network/source differences; official closure geometry remains the source of truth for rendering.
5. This layer is a daily embedded snapshot rather than a live per-page-load API call, trading a small freshness delay for reproducibility and a map that still opens when DataSF is unavailable.

## Review gate

The layer passed source-schema, status, geometry, timestamp, identifier, artifact, and deployment validation. Before adding construction/right-of-way permits, visually inspect several closure lines and exercise the time selector on the live map to confirm the amount of detail and blue styling are useful in combination with the hill and parcel layers.
