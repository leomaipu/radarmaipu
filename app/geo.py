"""Utilidades geométricas livianas (sin PostGIS) para el MVP."""
from __future__ import annotations

import math

EARTH_M = 6_371_000.0


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_M * math.asin(math.sqrt(a))


def point_to_segment_m(lon, lat, a, b) -> float:
    """Distancia aproximada (metros) de un punto a un segmento lon/lat."""
    # Proyección local equirectangular: suficiente a escala comunal.
    k = math.cos(math.radians(lat))
    px, py = (lon - a[0]) * k, lat - a[1]
    bx, by = (b[0] - a[0]) * k, b[1] - a[1]
    seg2 = bx * bx + by * by
    t = 0.0 if seg2 == 0 else max(0.0, min(1.0, (px * bx + py * by) / seg2))
    cx, cy = bx * t, by * t
    return math.hypot(px - cx, py - cy) * (math.pi / 180) * EARTH_M


def nearest_street(lon, lat, streets: list[dict]) -> tuple[dict | None, float | None]:
    best, best_d = None, None
    for s in streets:
        coords = s["path"]
        for a, b in zip(coords, coords[1:]):
            d = point_to_segment_m(lon, lat, a, b)
            if best_d is None or d < best_d:
                best, best_d = s, d
    return best, best_d
