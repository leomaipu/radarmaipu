"""Normalización de features de ArcGIS a registros propios. Solo usa la lista blanca."""
from __future__ import annotations

from .privacy import CALLE_PUBLIC_FIELDS, PATENTE_PUBLIC_FIELDS, filter_attributes


def normalize_calle(feature: dict) -> dict | None:
    geom = feature.get("geometry") or {}
    paths = geom.get("paths") or []
    if not paths:
        return None
    coords = [(x, y) for x, y in paths[0]]  # ya en 4326 (outSR=4326)
    return {**filter_attributes(feature.get("attributes", {}), CALLE_PUBLIC_FIELDS), "path": coords}


def normalize_patente(feature: dict, layer: str) -> dict | None:
    geom = feature.get("geometry") or {}
    if "x" not in geom or "y" not in geom:
        return None
    attrs = filter_attributes(feature.get("attributes", {}), PATENTE_PUBLIC_FIELDS)
    attrs["Año"] = str(attrs["Año"]) if "Año" in attrs and attrs["Año"] is not None else None
    return {**attrs, "capa": layer, "lon": geom["x"], "lat": geom["y"]}
