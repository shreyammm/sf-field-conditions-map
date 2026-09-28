# Checkpoint 9 — Optional planning date and day-level closures

**Date:** 2026-09-28

## Product behavior

The map now opens with **no planning date selected**. Stable layers remain available immediately, but date-dependent overlays do not appear until the user chooses a date.

The date control is a San Francisco calendar date with:

- a normal date picker;
- **Today**, computed in `America/Los_Angeles`;
- **Clear**, which removes the selected date and both date-dependent overlays.

## Temporary closure rule

The SFMTA closure layer remains enabled by default, but with no selected date it draws zero closure lines. Once a date is selected, a closure is shown whenever its official local interval overlaps any portion of that calendar day.

Production test:

`closure_start < next_day_00:00 AND closure_end >= selected_day_00:00`

This is intentionally different from the previous exact-time filter. For example, a closure scheduled from 6 PM to 10 PM on October 3 is visible whenever October 3 is selected, even if the user is planning the route in the morning.

Exact SFMTA start/end hours are still retained and shown in hover/click details.

## ROW permit behavior

Public Works street-work / ROW permits use the same selected calendar date. The layer remains **off by default** because thousands of permit windows can overlap one day.

A permit marker is eligible only when:

1. a planning date has been selected;
2. the selected date lies inside that permit's authorization window; and
3. the selected date lies inside the current snapshot's documented supported range.

Clearing the planning date removes permit markers even if the permit toggle is enabled.

## Final audit

The final build passed both audit stages:

- the existing general layer/data artifact audit before the date-control mutation;
- a dedicated post-mutation planning-date audit on the actual HTML shipped to Pages.

The final audit verifies:

- `type=date`, not `datetime-local`;
- no planning date initialized on page load;
- closure layer ready to show automatically after a date is selected;
- ROW permit layer still opt-in;
- Today and Clear controls;
- day-overlap closure predicate;
- exact closure-hour details retained;
- no stale exact-time methodology text;
- no duplicate HTML IDs;
- no runtime `fetch()` calls or external JS/CSS dependencies;
- inline JavaScript syntax passes `node --check`.

A failed planning-date audit prevents deployment, preserving the prior successful GitHub Pages version.
