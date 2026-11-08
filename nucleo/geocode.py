"""Cliente del geocodificador municipal (SITMA). La URL viene de config/servicios.json."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

import httpx

RUTA_SERVICIOS = Path(__file__).resolve().parent.parent / "config" / "servicios.json"


class GeocodeError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def base_url() -> str:
    env = os.environ.get("RM_GEOCODER_URL")
    if env:
        return env.rstrip("/")
    return json.loads(RUTA_SERVICIOS.read_text(encoding="utf-8"))["geocodificador"]["base"].rstrip("/")


def _check(data: dict) -> None:
    if "error" in data:
        raise GeocodeError(f"geocodificador: {data['error'].get('message')}")


def reverse(client: httpx.Client, lon: float, lat: float, distance_m: float = 100) -> dict | None:
    """Punto a dirección. Devuelve None si no hay dirección en el punto."""
    location = json.dumps({"x": lon, "y": lat, "spatialReference": {"wkid": 4326}})
    r = client.get(f"{base_url()}/reverseGeocode",
                   params={"location": location, "distance": distance_m, "outSR": 4326, "f": "json"},
                   timeout=15)
    r.raise_for_status()
    data = r.json()
    _check(data)
    addr = data.get("address") or {}
    if not addr.get("Match_addr"):
        return None
    loc = data.get("location") or {}
    return {
        "direccion": addr.get("Match_addr"),
        "etiqueta_corta": addr.get("ShortLabel"),
        "barrio": addr.get("Neighborhood") or None,
        "ciudad": addr.get("City") or None,
        "tipo": addr.get("Addr_type"),
        "lon": loc.get("x"),
        "lat": loc.get("y"),
    }


def forward(client: httpx.Client, texto: str, max_resultados: int = 5) -> list[dict]:
    """Dirección a punto. Devuelve candidatos ordenados como los entrega el servicio."""
    r = client.get(f"{base_url()}/findAddressCandidates",
                   params={"SingleLine": texto, "outSR": 4326, "maxLocations": max_resultados,
                           "outFields": "*", "f": "json"},
                   timeout=15)
    r.raise_for_status()
    data = r.json()
    _check(data)
    return [
        {
            "direccion": c.get("address"),
            "score": c.get("score"),
            "lon": (c.get("location") or {}).get("x"),
            "lat": (c.get("location") or {}).get("y"),
        }
        for c in data.get("candidates", [])
    ]
