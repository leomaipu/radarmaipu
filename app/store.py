"""Almacén en memoria del MVP. En producción: PostGIS con las mismas consultas."""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

from .dominios import estado_oculto
from .geo import nearest_street


def tiene_punto(patente: dict) -> bool:
    return patente["lon"] is not None


def _sin_tildes(texto: str) -> str:
    """'Maipú' -> 'MAIPU'. Permite buscar sin tildes y sin distinguir mayúsculas."""
    descompuesto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in descompuesto if not unicodedata.combining(c)).upper()


@dataclass
class Store:
    calles: list[dict] = field(default_factory=list)
    patentes: list[dict] = field(default_factory=list)
    barrios: list[dict] = field(default_factory=list)

    def list_barrios(self) -> list[dict]:
        return sorted(self.barrios, key=lambda b: _sin_tildes(b["BARRIO"]))

    def search_barrios(self, q: str, limit: int = 21) -> list[dict]:
        needle = _sin_tildes(q.strip())
        if not needle:
            return []
        return [b for b in self.list_barrios() if needle in _sin_tildes(b["BARRIO"])][:limit]

    def search_calles(self, q: str, limit: int = 20) -> list[dict]:
        needle = q.strip().upper()
        if not needle:
            return []
        return [c for c in self.calles if needle in (c.get("NOMBRE") or "").upper()][:limit]

    def patentes_in_bbox(self, minlon, minlat, maxlon, maxlat, limit: int = 500) -> list[dict]:
        out = []
        for p in self.patentes:
            if estado_oculto(p.get("estado_pat")) or not tiene_punto(p):
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
