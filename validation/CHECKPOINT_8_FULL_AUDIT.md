# Checkpoint 8 — Full production-layer audit

**Date:** 2026-09-28  
**Scope:** finished deployed artifact, not just individual source/build scripts

## Result

The final production artifact passed the independent `scripts/audit_build.py` gate before GitHub Pages deployment.

Audited embedded layer counts:

- Election precincts: **514**
- Displayed Public Works street segments: **15,901**
- High-unit residential parcel markers/polygons: **2,248** at the 20+ threshold
- SFMTA permitted temporary-closure lines: **4,283**
- Public Works street-work / ROW permit markers: **4,231**

The final generated HTML also passed syntax/packaging checks: no duplicate HTML IDs, no runtime `fetch()` calls, no external JavaScript or stylesheet dependencies, and every inline JavaScript block passed `node --check`.

## 1. Precinct boundaries

Source: SF Department of Elections / DataSF `d6x4-hefw`.

Audit checks:

- 514 polygon/multipolygon features
- non-empty, unique precinct IDs
- used only as reference geography
- no operational condition is converted into a precinct score

No corrective change was required in this audit.

## 2. Public Works street backbone

Source: SF Public Works / DataSF `3psu-pn9h`.

The source had 16,372 active records. Production displays 15,901 after excluding mapped-but-not-real/non-route-context source layers:

- `PAPER`: 115 excluded
- `PAPER_FWYS`: 209 excluded
- `PAPER_WATER`: 136 excluded
- `PSEUDO`: 2 excluded
- `PRIVATE_PARKING`: 9 excluded

The final artifact contains no leakage from those excluded layers and every displayed segment has a unique CNN.

Private streets, pedestrian-only streets, park/NPS roads, unpaved rights-of-way, freeways, and ramps can remain as labeled geographic context; `active` is not interpreted as a promise of public walkability.

No corrective change was required in this audit.

## 3. High-unit residential parcels

Source: SF Planning / DataSF `c5ge-t6pj`.

Final artifact checks:

- all 2,248 displayed records are `geography_type = parcel`
- no `analytical` or `multiple_parcels` geography leaked into the apartment layer
- all displayed records have at least 20 residential units
- unique parcel identifiers after controlled duplicate handling
- threshold counts: 20+ = 2,248; 50+ = 811; 100+ = 384; 200+ = 120

The known repeated parcel `6311016` has identical geometry with observed unit counts 170 and 174; both are in the same 100–199 display bucket and the range is retained rather than pretending to exact precision.

The layer remains explicitly a unit-concentration/shared-entry proxy. A parcel is not necessarily a building footprint and unit count does not establish canvasser access.

No new corrective change was required in this audit.

## 4. Hill steepness

Source: DataSF Elevation Contours `rnbg-2qxw`, 5-foot contour interval.

The audited v2 method directly intersects applicable street centerlines with official contours. Same-elevation supported spans contribute zero net rise; non-zero consecutive crossings must be approximately one 5-foot contour interval apart; non-5-foot jumps and >45% short-span artifacts are rejected rather than clipped.

Final distribution:

- classified: **9,375**
- unavailable for insufficient direct contour evidence: **6,307**
- freeway/ramp not applicable: **219**
- `<5%`: 3,481
- `5–9.9%`: 3,329
- `10–14.9%`: 1,554
- `15–19.9%`: 603
- `20%+`: 408
- max retained estimate: 37.4%

Confidence among classified segments:

- high: 4,688
- medium: 2,006
- low: 2,681

Every classified final-artifact segment has a 0–45% estimate, an allowed confidence value, a positive support fraction no greater than 1, and method label `direct_5ft_contour_crossings_v2`. The 20%+ share remains below the build guardrail.

The limitation remains material: this is a contour-supported route-planning estimate over supported portions, not an official engineering maximum or guaranteed full-segment average. Unavailable streets remain visibly unavailable rather than being interpolated.

No new corrective change was required in this audit; prior hill audits had already corrected the interpolation and same-elevation issues.

## 5. Temporary street closures

Source: SFMTA / DataSF `8x25-yybr`.

Current source audit:

- source rows: 4,628
- `Permitted`: 4,283 embedded
- 345 workflow/application rows excluded
- all embedded rows have line geometry and valid time windows
- 4,281 of 4,283 closure CNN values match the displayed street backbone

Corrective change from this audit: the builder now requires `status.upper() == "PERMITTED"` exactly. The earlier implementation would also have accepted a blank status if one appeared in a future source refresh. The final artifact audit independently rejects anything other than explicit `Permitted`, so that ambiguity is now closed at both stages.

The source line geometry remains authoritative even for the two current CNNs that do not match the street backbone. A closure is still described as a street/vehicle disruption, not proof that pedestrians cannot pass, and the SFMTA feed is not represented as a complete inventory of closures controlled by other City departments.

## 6. Street-work / ROW permits

Source: SF Public Works / DataSF `bpc9-7sus`.

This was the layer where the full audit found a substantive source-handling problem.

### Problem found

The first version collapsed rows sharing permit number/type/point/date window and called the removed rows “exact duplicates.” The deeper source audit found:

- **4,372 eligible work/ROW source rows**
- **4,231 display marker keys**
- **50 marker keys** contain more than one source row
- **141 additional source rows** share those markers
- **46 of the 50 groups** have multiple distinct street/cross-street descriptors
- 0 groups have multiple permit descriptions
- 0 groups have multiple statuses
- one marker represents as many as **14 source rows**

So the 141 rows were not safely discardable as exact duplicates.

### Correction

Production now aggregates rows to one point only when they share:

`permit_number + permit_type + exact source point + permit start/end window`

The marker preserves every distinct source street/cross-street pair, description, status, neighborhood, district, approval date, and relevant row timestamp. The click panel exposes the source locations and explains when multiple rows share one official point.

This preserves the source information while avoiding dozens of indistinguishable overlapping SVG circles. It does **not** convert the point into an exact work footprint.

Final marker type counts:

- Excavation: 3,692
- TempOccup: 358
- StrtImprov: 100
- ExcStreet: 48
- AddlStSpac: 20
- StorCont: 11
- MinorEnc: 1
- StreetSpace: 1

All embedded source-status lists are either `APPROVED` or `ACTIVE`; 3,267 markers currently represent APPROVED rows and 964 represent ACTIVE rows. Applicant/contact/DBA/phone/email fields are not embedded.

### UI/performance corrections

The full audit also found two non-data issues:

1. The shared field date/time input still had an accessibility label saying it was only the closure date/time. It now says **Field date and time in San Francisco**.
2. The permit layer was visually off by default but still constructed thousands of hidden SVG circles on initial load. It now creates permit circles only when explicitly enabled and clears them when disabled.

The permit snapshot is current/upcoming only. The audited build uses the actual SF retrieval date through 14 days later as its completeness window and suppresses this layer outside that range. Permit-window overlap does not prove crews are physically working at the selected moment.

## 7. Cross-layer / packaging checks

The permanent final-artifact audit now runs after all source transformations and UI patch scripts and before Pages upload. It checks:

- expected official dataset IDs in the manifest
- broad layer-count guardrails
- geometry types and canonical IDs
- street exclusion leakage
- parcel geography and threshold counts
- hill category/confidence/meta consistency
- closure status, time windows, object IDs, and CNN match rate
- permit type/status/location aggregation, privacy-field exclusions, and snapshot window
- layer defaults and shared date/time accessibility label
- lazy rendering of the opt-in permit layer
- duplicate HTML IDs
- runtime network calls / external dependencies
- inline JavaScript syntax

Any failed invariant stops the build before deployment, leaving the prior successful GitHub Pages version live.

## Remaining limitations after audit

The audit confirms that the implementation matches the documented methodology; it does not turn source proxies into facts the sources do not contain.

- Parcels are property-lot geography, not confirmed building entrances or accessibility.
- 6,307 applicable non-freeway street segments still lack enough direct contour evidence for a hill estimate.
- Hill values are contour-supported estimates, not engineering street-grade surveys or maximum-slope measurements.
- SFMTA's closure feed is not a complete inventory of every City-managed closure and does not establish pedestrian blockage.
- Public Works permit points are authorization locations, not exact work extents or proof of active crews.
- The permit source is a current/upcoming snapshot, not a historical archive.
- Some real street-centerline context may be private, pedestrian-only, unpaved, or otherwise unsuitable for ordinary walking; the UI labels rather than silently removes all such context.

The planned recent-reported-incident layer is not part of this checkpoint and must receive its own source/privacy/geocoding audit before production.
