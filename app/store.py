"""Almacén en memoria del MVP. En producción: PostGIS con las mismas consultas."""
from __future__ import annotations

from dataclasses import dataclass, field

from .dominios import estado_oculto
from .geo import nearest_street


@dataclass
class Store:
    calles: list[dict] = field(default_factory=list)
    patentes: list[dict] = field(default_factory=list)

    def search_calles(self, q: str, limit: int = 20) -> list[dict]:
        needle = q.strip().upper()
        if not needle:
            return []
        return [c for c in self.calles if needle in (c.get("NOMBRE") or "").upper()][:limit]

    def patentes_in_bbox(self, minlon, minlat, maxlon, maxlat, limit: int = 500) -> list[dict]:
        out = []
        for p in self.patentes:
            if estado_oculto(p.get("estado_pat")):
                continue
            if minlon <= p["lon"] <= maxlon and minlat <= p["lat"] <= maxlat:
                out.append(p)
                if len(out) >= limit:
                    break
        return out

    def calle_for_point(self, lon: float, lat: float) -> dict | None:
        street, dist = nearest_street(lon, lat, self.calles)
        if street is None:
            return None
        return {"NOMBRE": street.get("NOMBRE"), "CLASE": street.get("CLASE"), "distancia_m": round(dist, 1)}
