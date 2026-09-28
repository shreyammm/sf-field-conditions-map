# Checkpoint 4 — Street-layer sanity audit

**Date:** 2026-09-27/28

## What was audited

The street addition was checked against SF Public Works/DataSF source documentation, the generated build artifact, and build-time counts. The audit also rechecked precinct IDs, parcel IDs/unit thresholds, source provenance, runtime dependencies, and documentation consistency.

## Confirmed

- Official production sources are being used for precincts (`d6x4-hefw`), land use (`c5ge-t6pj`), and streets (`3psu-pn9h`).
- Current precinct build has 514 unique precinct IDs.
- Current land-use build has 2,248 unique displayed 20+ unit parcels after one exact duplicate-source row is resolved.
- The current street source has 17,170 total rows and 16,372 active rows, matching the official DataSF active-street view.
- Every displayed street has a unique CNN and line geometry.
- No core layer makes a runtime network request; the deployed HTML is self-contained.
- Latest Pages build/deploy completed successfully before this audit correction.

## Problems found and corrections

### 1. `active = true` was too broad for a route backbone
Public Works defines “active” as not retired. It also contains active `PAPER`, `PAPER_FWYS`, and `PAPER_WATER` lines that are explicitly not actual streets, plus pseudo-addressing and private-parking centerlines.

**Correction:** exclude `PAPER`, `PAPER_FWYS`, `PAPER_WATER`, `PSEUDO`, and `PRIVATE_PARKING` from the displayed/analytical street backbone. In the audited snapshot this removes 471 active records and leaves 15,901 displayed segments.

### 2. Endpoint arrows could imply travel direction
The UI showed `from → to`, but `f_st` and `t_st` are segment endpoints, not a travel-direction instruction.

**Correction:** display “Between X and Y.”

### 3. CNN wording was too strong
The UI called CNN “stable.” Public Works documents CNN as the unique segment identifier in the dataset, but street-network revisions/change logs mean permanent immutability should not be assumed.

**Correction:** call it the City/source segment identifier and use it for joins when another dataset exposes the same CNN.

### 4. Street labels were globally deduplicated by name
At neighborhood zoom, a long street could have only one label elsewhere on the map.

**Correction:** cache label candidates for performance and allow multiple spatially separated labels per street name as zoom increases, while retaining collision suppression.

### 5. Major streets could be visually overdrawn by local streets
SVG draw order previously followed numeric class code, allowing later local classes to cross over earlier arterials.

**Correction:** draw low-priority/local context first and major/freeway context later.

### 6. Exact duplicate parcel unit conflict showed false precision
The known duplicate parcel source reports 170 and 174 units. Keeping only 174 is deterministic but overstates precision.

**Correction:** show the observed 170–174 range because both values fall in the same threshold bucket. A future duplicate conflict crossing a threshold fails the build.

### 7. Repository documentation had drifted
README/project/deployment documentation still described the pre-street build and an obsolete precinct fallback.

**Correction:** update all production documentation to match the current official-source-only, street-enabled architecture.

## Remaining limitation before hills

The current SVG approach is appropriate for the prototype but embeds ~16k street segments plus parcel/precinct geometry in one static page. Performance should be watched on mobile as more street-based layers are added. Before adding several additional line overlays, consider moving base-street rendering to Canvas/WebGL while retaining inspectable feature metadata.
