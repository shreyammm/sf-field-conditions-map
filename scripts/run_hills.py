#!/usr/bin/env python3
"""Run the hill derivation with a smoothed longitudinal-grade estimator.

The contour surface estimate can be locally noisy. Fitting one elevation trend
across the five street samples is more appropriate for a block-level running
street grade than summing every small estimated elevation wiggle.
"""
import add_hills as h


def regression_part_grade(grid, part):
    length_m = h.polyline_length_xy(part)
    if length_m < 8:
        return None
    samples = []
    for i in range(h.STREET_SAMPLES):
        f = i / (h.STREET_SAMPLES - 1)
        pt = h.point_along(part, f)
        z, nearest_m, levels = h.estimate_elevation(grid, pt)
        if z is None:
            return None
        samples.append((f * length_m, z, nearest_m, levels))

    # Least-squares longitudinal trend: elevation(feet) = a + b * distance(m).
    xs = [s[0] for s in samples]
    zs = [s[1] for s in samples]
    xbar = sum(xs) / len(xs)
    zbar = sum(zs) / len(zs)
    denom = sum((x - xbar) ** 2 for x in xs)
    if denom <= 0:
        return None
    slope_ft_per_m = sum((x - xbar) * (z - zbar) for x, z in zip(xs, zs)) / denom
    grade = abs(slope_ft_per_m) / h.FT_PER_M * 100.0
    nearest = max(s[2] for s in samples)
    min_levels = min(s[3] for s in samples)
    return grade, length_m, nearest, min_levels


h.estimate_part_grade = regression_part_grade
h.main()
