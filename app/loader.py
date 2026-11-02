"""Carga paginada desde ArcGIS REST. Las URLs vienen de configuración (variables de entorno)."""
from __future__ import annotations

import os
from typing import Callable

import httpx

from .ingest import normalize_calle, normalize_patente
from .privacy import CALLE_PUBLIC_FIELDS

PAGE = 2000  # maxRecordCount publicado por el servidor de Maipú

# Campo de identificador por capa: no es el mismo en todas (ver metadatos verificados).
OID_BY_LAYER = {"Calles": "OBJECTID", "Alcoholes": "OBJECTID",
                "Industriales": "OBJECTID_12", "Comerciales": "OBJECTID_1"}

# Campos que existen en cada capa de patentes, intersectados con la lista blanca.
PATENTE_FIELDS_BY_LAYER = {
    "Alcoholes": ("estado_pat", "tipo_paten", "actividad", "Año", "semestre"),
    "Industriales": ("Status", "Score", "Match_type", "estado_pat", "tipo_paten", "subtipo_pa", "Año", "semestre"),
    "Comerciales": ("Status", "Score", "Match_type", "estado_pat", "tipo_paten", "subtipo_pa", "actividad", "Año", "semestre"),
}


def fetch_layer(client: httpx.Client, layer_url: str, out_fields: str, oid: str) -> list[dict]:
    feats, offset = [], 0
    while True:
        params = {
            "where": "1=1", "outFields": out_fields, "returnGeometry": "true",
            "outSR": 4326, "f": "json", "orderByFields": oid,
            "resultOffset": offset, "resultRecordCount": PAGE,
        }
        r = client.get(f"{layer_url}/query", params=params, timeout=60)
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            raise RuntimeError(f"ArcGIS error: {data['error']}")
        batch = data.get("features", [])
        feats.extend(batch)
        if not data.get("exceededTransferLimit") or not batch:
            return feats
        offset += len(batch)


def load_all(client: httpx.Client, calles_url: str, patente_layers: dict[str, str],
             sink: Callable[[str, dict], None]) -> dict:
    counts = {"calles": 0, "patentes": 0, "descartadas": 0}
    calle_fields = ",".join(CALLE_PUBLIC_FIELDS)
    for f in fetch_layer(client, calles_url, calle_fields, OID_BY_LAYER["Calles"]):
        rec = normalize_calle(f)
        if rec is None:
            counts["descartadas"] += 1
        else:
            sink("calle", rec); counts["calles"] += 1
    for name, url in patente_layers.items():
        fields = ",".join(PATENTE_FIELDS_BY_LAYER[name])
        for f in fetch_layer(client, url, fields, OID_BY_LAYER[name]):
            rec = normalize_patente(f, name)
            if rec is None:
                counts["descartadas"] += 1
            else:
                sink("patente", rec); counts["patentes"] += 1
    return counts


def config_from_env() -> tuple[str, dict[str, str]]:
    base = os.environ.get("RM_GIS_BASE", "https://gis.maipu.cl/server/rest/services")
    calles = os.environ.get("RM_CALLES_URL", f"{base}/DOM/DOM_CATASTRO_MUNICIPAL/FeatureServer/1")
    patentes = {
        "Alcoholes": f"{base}/DAF/PATENTES_2026_2/FeatureServer/0",
        "Industriales": f"{base}/DAF/PATENTES_2026_2/FeatureServer/1",
        "Comerciales": f"{base}/DAF/PATENTES_2026_2/FeatureServer/2",
    }
    return calles, patentes
