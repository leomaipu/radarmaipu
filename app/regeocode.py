"""Re-geocodifica patentes sin match (Status U) usando DIRECCION, con umbral de score."""
from __future__ import annotations

import json
from pathlib import Path

import httpx

from . import geocode

RUTA = Path(__file__).resolve().parent.parent / "config" / "servicios.json"


def config() -> dict:
    return json.loads(RUTA.read_text(encoding="utf-8"))["regeocodificacion"]


def regeocodificar(patentes: list[dict], client: httpx.Client) -> dict:
    cfg = config()
    resumen = {"candidatas": 0, "actualizadas": 0, "bajo_umbral": 0, "sin_resultado": 0}
    for p in patentes:
        if p.get("Status") not in cfg["status"] or not p.get("DIRECCION"):
            continue
        resumen["candidatas"] += 1
        try:
            candidatos = geocode.forward(client, p["DIRECCION"], max_resultados=1)
        except (httpx.HTTPError, geocode.GeocodeError):
            resumen["sin_resultado"] += 1
            continue
        if not candidatos or candidatos[0]["lon"] is None:
            resumen["sin_resultado"] += 1
            continue
        mejor = candidatos[0]
        if (mejor["score"] or 0) < cfg["umbral_score"]:
            resumen["bajo_umbral"] += 1
            continue
        p["lon"], p["lat"] = mejor["lon"], mejor["lat"]
        p["coords_origen"] = "re-geocodificado"
        p["score_geocodificacion"] = mejor["score"]
        resumen["actualizadas"] += 1
    return resumen
