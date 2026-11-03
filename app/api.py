from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query

import httpx

from . import geocode
from .carga import carga_inicial
from .dominios import estado_oculto
from .geo import haversine_m
from .store import Store, tiene_punto

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)  # no registrar cada URL consultada

store = Store()
estado_carga = {"fase": "sin_iniciar"}
hilo_carga: threading.Thread | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    # En segundo plano: la carga puede tardar y el servidor debe responder mientras tanto.
    global hilo_carga
    hilo_carga = threading.Thread(target=carga_inicial, args=(store, estado_carga), daemon=True)
    hilo_carga.start()
    yield


app = FastAPI(title="Radar Maipú MVP", version="0.1.0", lifespan=lifespan)


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "carga": estado_carga["fase"],
        "calles": len(store.calles),
        "patentes": len(store.patentes),
        "patentes_sin_punto": sum(not tiene_punto(p) for p in store.patentes),
    }


@app.get("/api/calles")
def calles(q: str = Query(..., min_length=2, max_length=60)):
    return {"resultados": [{k: v for k, v in c.items() if k != "path"} for c in store.search_calles(q)]}


@app.get("/api/patentes")
def patentes(minlon: float, minlat: float, maxlon: float, maxlat: float):
    if minlon >= maxlon or minlat >= maxlat:
        raise HTTPException(400, "bbox inválido")
    return {"resultados": store.patentes_in_bbox(minlon, minlat, maxlon, maxlat)}


@app.get("/api/punto")
def punto(lon: float, lat: float, radio_m: float = Query(150, gt=0, le=1000)):
    cercanas = []
    for p in store.patentes:
        if estado_oculto(p.get("estado_pat")) or not tiene_punto(p):
            continue
        d = haversine_m(lon, lat, p["lon"], p["lat"])
        if d <= radio_m:
            cercanas.append({**p, "distancia_m": round(d, 1)})
    return {
        "calle_cercana": store.calle_for_point(lon, lat),
        "patentes_cercanas": sorted(cercanas, key=lambda x: x["distancia_m"]),
        "radio_m": radio_m,
    }


@app.get("/api/direccion")
def direccion(lon: float, lat: float):
    try:
        with httpx.Client() as client:
            dir_ = geocode.reverse(client, lon, lat)
    except (httpx.HTTPError, geocode.GeocodeError) as e:
        raise HTTPException(502, f"Geocodificador no disponible: {e}")
    return {"direccion": dir_}


@app.get("/api/buscar-direccion")
def buscar_direccion(q: str = Query(..., min_length=3, max_length=150)):
    try:
        with httpx.Client() as client:
            candidatos = geocode.forward(client, q)
    except (httpx.HTTPError, geocode.GeocodeError) as e:
        raise HTTPException(502, f"Geocodificador no disponible: {e}")
    return {"resultados": candidatos}
