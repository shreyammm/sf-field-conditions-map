# Project spec

## Purpose

Build a San Francisco field-conditions map for field logistics using reliable public data. Precincts provide orientation; other phenomena remain at their natural geography whenever possible.

## Current production layers

### Precinct boundaries
- Thin neutral outlines.
- Hover/click shows precinct ID and neighborhood when available.
- Visually subordinate to operational layers.

### Large multifamily
- Parcel/property or official grouped-parcel geometry.
- Buckets: 20–49, 50–99, 100–199, 200+ residential units.
- Hover/click shows unit count, property/parcel identifier, and the access-friction caveat.
- Never label a property “inaccessible” solely from unit count.

## Interaction requirements

- Toggle each layer independently.
- Hover for immediate explanation.
- Click for persistent detail.
- Pan and zoom.
- Keep source/load status visible.
- Use language that matches what the source actually establishes.

## Data and deployment requirements

- Public/reliable data only; official SF/DataSF sources first.
- No voter files, person-level political targeting, private canvasser observations, or proprietary campaign data.
- Core map layers must not depend on cross-origin API calls at page-open time.
- The build validates and embeds the current public-data snapshot into a static site artifact.
- A failed refresh must not replace the previously successful deployment.
- Every derived/filtered layer must remain traceable to source dataset, fields, transformation, and retrieval time.

## Candidate next layers

- street grade / hills at street-segment geography;
- temporary SFMTA street closures with date/time filters;
- reported incidents with clear privacy and approximation caveats;
- construction/right-of-way disruptions that distinguish permits from confirmed closures.

No blended “field difficulty” score is planned for the current version.
