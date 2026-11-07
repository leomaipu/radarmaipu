from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse

import httpx

from . import geocode, informe as informe_mod, prc_config, prc_gis
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
        "barrios": len(store.barrios),
        "patentes": len(store.patentes),
        "patentes_sin_punto": sum(not tiene_punto(p) for p in store.patentes),
        "prc": _estado_prc(),
    }


def _estado_prc() -> dict:
    """Las capas PRC se consultan en vivo por cada informe: se informa la última respuesta de cada una."""
    try:
        cfg = prc_config.cargar()
    except Exception as e:  # JSON mal formado o archivo faltante
        return {"config": "error", "detalle": type(e).__name__}
    return {"config": "ok", "giros": len(cfg["giros"]["giros"]), "zonas_matriz": len(cfg["usos_comercio"]["zonas"]),
            "mod4_vigente": cfg["modificaciones"]["MOD_4"]["vigente"], "capas": prc_gis.estado_capas()}


@app.get("/api/calles")
def calles(q: str = Query(..., min_length=2, max_length=60)):
    return store.search_calles(q)


@app.get("/api/barrios")
def barrios(q: str | None = Query(None, min_length=2, max_length=60)):
    """Sin `q` devuelve los 21 barrios ordenados. Con `q` busca por subcadena, sin tildes."""
    if q is None:
        return {"resultados": store.list_barrios()}
    return {"resultados": store.search_barrios(q)}


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


def cliente_gis() -> httpx.Client:
    """Punto de inyección: las pruebas lo reemplazan por un cliente con MockTransport."""
    return httpx.Client()


@app.get("/api/giros")
def giros():
    return {"resultados": prc_config.giros_publicos(prc_config.cargar())}


@app.get("/api/informe")
def informe(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    giro: str = Query(..., min_length=2, max_length=40),
    escala: Literal["basico", "menor", "mediano", "mayor"] | None = None,
    formato: Literal["json", "texto"] = "json",
    frente_via: str | None = Query(None, min_length=1, max_length=20, pattern=r"^[A-Za-z0-9._-]+$",
                                   description="Código de la vía que el predio enfrenta (de vialidad.cercanas)."),
):
    """Informe orientativo de factibilidad para un punto y un giro. No reemplaza el CIP."""
    cfg = prc_config.cargar()
    codigo = giro.strip().lower()
    if codigo not in cfg["giros"]["giros"]:
        raise HTTPException(422, "Giro no soportado. Ver /api/giros para la lista de códigos.")
    with cliente_gis() as client:
        gis = prc_gis.consultar_punto(client, lon, lat, cfg)
    inf = informe_mod.generar(lat, lon, codigo, cfg, gis, escala=escala, frente_via=frente_via)
    if formato == "texto":
        return PlainTextResponse(informe_mod.texto(inf))
    return inf
