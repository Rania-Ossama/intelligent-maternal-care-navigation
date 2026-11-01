"""Approximate outline of Egypt (lon, lat) used to restrict where a pin may be dropped.

The outline is deliberately coarse (a few km of tolerance, slightly generous over
the sea). It is served to the browser through /api/config so the front end and
the back end always use exactly the same polygon.
"""
from __future__ import annotations

import math

EGYPT_POLYGON: list[tuple[float, float]] = [
    (25.15, 31.68), (25.00, 29.25), (25.00, 22.00), (36.90, 22.00),
    (36.70, 22.25), (36.10, 22.95), (35.70, 23.20), (35.90, 23.95),
    (35.45, 24.20), (35.10, 25.00), (34.45, 25.95), (34.05, 26.70),
    (33.85, 27.30), (33.50, 27.75), (33.15, 28.30), (32.75, 29.05),
    (32.45, 29.60), (32.55, 29.98),            # head of the Gulf of Suez
    (32.72, 29.62), (33.10, 29.05), (33.30, 28.70), (33.65, 28.25),
    (34.20, 27.72), (34.42, 27.95), (34.58, 28.55), (34.72, 29.10),
    (34.90, 29.50), (34.72, 30.00), (34.42, 30.87), (34.20, 31.38),
    (33.80, 31.40), (33.00, 31.45), (32.30, 31.50), (31.80, 31.65),
    (31.10, 31.85), (30.40, 31.75), (29.95, 31.55), (29.30, 31.15),
    (28.20, 31.45), (27.20, 31.65), (26.20, 31.75),
]

LON_MIN = min(p[0] for p in EGYPT_POLYGON)
LON_MAX = max(p[0] for p in EGYPT_POLYGON)
LAT_MIN = min(p[1] for p in EGYPT_POLYGON)
LAT_MAX = max(p[1] for p in EGYPT_POLYGON)


def point_in_egypt(lat: float, lon: float) -> bool:
    """Ray-casting point-in-polygon test. Returns False for NaN/inf."""
    if not (math.isfinite(lat) and math.isfinite(lon)):
        return False
    if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
        return False
    inside = False
    pts = EGYPT_POLYGON
    j = len(pts) - 1
    for i in range(len(pts)):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > lat) != (yj > lat):
            x_cross = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lon < x_cross:
                inside = not inside
        j = i
    return inside
