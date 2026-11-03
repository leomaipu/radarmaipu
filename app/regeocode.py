"""Re-geocodifica patentes sin match (Status U) o sin punto usando DIRECCION, con umbral de score."""
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
        # Alcoholes no tiene campo Status: sus patentes sin punto se detectan por las coordenadas.
        pendiente = p.get("Status") in cfg["status"] or p.get("lon") is None
        if not pendiente or not p.get("DIRECCION"):
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
        # lat primero: la API lee esta patente en paralelo y usa lon para saber si tiene punto.
        p["lat"], p["lon"] = mejor["lat"], mejor["lon"]
        p["coords_origen"] = "re-geocodificado"
        p["score_geocodificacion"] = mejor["score"]
        resumen["actualizadas"] += 1
    return resumen
