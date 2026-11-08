"""Comercio cercano: patentes vigentes en un radio, separando las de rubro similar al giro consultado."""
from __future__ import annotations

from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D

from nucleo.busqueda import normalizar
from nucleo.dominios import cargar as dominios
from territorio.models import Patente


def patentes_cerca(lon: float, lat: float, radio_m: float):
    pt = Point(lon, lat, srid=4326)
    ocultos = dominios()["estados_ocultos"]
    return (Patente.objects.filter(geom__dwithin=(pt, D(m=radio_m)))
            .exclude(estado_pat__in=ocultos)
            .annotate(dist=Distance("geom", pt)).order_by("dist"))


def es_similar(actividad: str | None, palabras: list[str]) -> bool:
    """Prefijo de palabra ('FARMAC' calza con 'FARMACIA'); si la clave termina en espacio, palabra completa."""
    texto = f" {normalizar(actividad)} "
    for p in palabras:
        clave = normalizar(p)
        if clave and (f" {clave} " in texto if p.endswith(" ") else f" {clave}" in texto):
            return True
    return False


def resumen(lon: float, lat: float, giro: dict, radio_m: float, maximo: int = 12, max_puntos: int = 600) -> dict:
    palabras = giro.get("palabras_actividad") or []
    total, similares, puntos = 0, [], []
    for p in patentes_cerca(lon, lat, radio_m):
        total += 1
        similar = bool(palabras) and es_similar(p.actividad, palabras)
        if similar:
            similares.append(p)
        if len(puntos) < max_puntos:
            puntos.append({"lon": round(p.geom.x, 6), "lat": round(p.geom.y, 6), "s": similar,
                           "a": (p.actividad or "Sin actividad registrada")[:80], "d": p.direccion or ""})
    return {
        "radio_m": radio_m,
        "total": total,
        "similares": len(similares) if palabras else None,
        "criterio_similar": palabras or None,
        "ejemplos_similares": [{"actividad": p.actividad, "direccion": p.direccion,
                                "distancia_m": round(p.dist.m, 1), "lon": p.geom.x, "lat": p.geom.y}
                               for p in similares[:maximo]],
        "puntos": puntos,
        "puntos_total": total,
        "nota": "Patentes vigentes del catastro municipal 2026. La actividad es texto libre: la similitud es aproximada.",
    }
