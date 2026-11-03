"""Normalización de features de ArcGIS a registros propios. Solo usa la lista blanca."""
from __future__ import annotations

from .dominios import descripcion_clase, descripcion_status, estado_normalizado
from .normalize import clean_text
from .privacy import CALLE_PUBLIC_FIELDS, PATENTE_PUBLIC_FIELDS, filter_attributes


def normalize_calle(feature: dict) -> dict | None:
    geom = feature.get("geometry") or {}
    paths = geom.get("paths") or []
    if not paths:
        return None
    coords = [(x, y) for x, y in paths[0]]  # ya en 4326 (outSR=4326)
    attrs = filter_attributes(feature.get("attributes", {}), CALLE_PUBLIC_FIELDS)
    attrs = {k: clean_text(v) for k, v in attrs.items()}
    attrs["CLASE_DESC"] = descripcion_clase(attrs.get("CLASE"))
    return {**attrs, "path": coords}


def normalize_patente(feature: dict, layer: str) -> dict | None:
    geom = feature.get("geometry") or {}
    if "x" not in geom or "y" not in geom:
        return None
    attrs = filter_attributes(feature.get("attributes", {}), PATENTE_PUBLIC_FIELDS)
    attrs = {k: clean_text(v) for k, v in attrs.items()}
    attrs["estado_normalizado"] = estado_normalizado(attrs.get("estado_pat"))
    attrs["Status_DESC"] = descripcion_status(attrs.get("Status"))
    # ArcGIS entrega x/y = "NaN" si la dirección no se geocodificó. Se conserva el registro
    # sin punto: la re-geocodificación puede asignárselo a partir de DIRECCION.
    con_punto = isinstance(geom["x"], (int, float)) and isinstance(geom["y"], (int, float))
    return {**attrs, "capa": layer,
            "lon": geom["x"] if con_punto else None,
            "lat": geom["y"] if con_punto else None}
