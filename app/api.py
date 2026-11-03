from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query

from .dominios import estado_oculto
from .geo import haversine_m
from .store import Store

app = FastAPI(title="Radar Maipú MVP", version="0.1.0")
store = Store()


@app.get("/api/health")
def health():
    return {"ok": True, "calles": len(store.calles), "patentes": len(store.patentes)}


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
        if estado_oculto(p.get("estado_pat")):
            continue
        d = haversine_m(lon, lat, p["lon"], p["lat"])
        if d <= radio_m:
            cercanas.append({**p, "distancia_m": round(d, 1)})
    return {
        "calle_cercana": store.calle_for_point(lon, lat),
        "patentes_cercanas": sorted(cercanas, key=lambda x: x["distancia_m"]),
        "radio_m": radio_m,
    }
