"""API pública de Radar Maipú (Django Ninja). Mismas rutas y respuestas que la versión FastAPI."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

import httpx
from django.conf import settings
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point, Polygon
from django.contrib.gis.measure import D
from django.http import HttpResponse
from ninja import NinjaAPI, Query
from ninja.errors import HttpError

from nucleo import geocode, informe as informe_mod, prc_config, prc_gis
from nucleo.busqueda import buscar_calles
from nucleo.dominios import cargar as dominios
from territorio.models import Barrio, CargaGIS, Calle, Patente
from tramites.models import checklist_para

from . import comercio

api = NinjaAPI(title="Radar Maipú", version="0.3.0", urls_namespace="api",
               docs_url="/docs" if settings.DEBUG or settings.RADAR["API_DOCS_PUBLICA"] else None,
               description="Informe orientativo de factibilidad y datos territoriales de Maipú.")


def cliente_gis() -> httpx.Client:
    """Punto de inyección: las pruebas lo reemplazan por un cliente con MockTransport."""
    return httpx.Client()


def _estado_prc() -> dict:
    try:
        cfg = prc_config.cargar()
    except Exception as e:  # JSON mal formado o archivo faltante
        return {"config": "error", "detalle": type(e).__name__}
    return {"config": "ok", "giros": len(cfg["giros"]["giros"]), "zonas_matriz": len(cfg["usos_comercio"]["zonas"]),
            "mod4_vigente": cfg["modificaciones"]["MOD_4"]["vigente"], "capas": prc_gis.estado_capas()}


@api.get("/salud", include_in_schema=False)
def salud(request):
    """Liviana, para el chequeo de HAProxy: la app responde y la base acepta consultas."""
    from django.db import connection
    with connection.cursor() as c:
        c.execute("SELECT 1")
    return {"ok": True}


@api.get("/health")
def health(request):
    ultima = CargaGIS.objects.first()
    return {
        "ok": True,
        "carga": ultima.fase if ultima else "sin_cargas",
        "ultima_carga": ultima.fin.isoformat() if ultima and ultima.fin else None,
        "calles": Calle.objects.count(),
        "barrios": Barrio.objects.count(),
        "patentes": Patente.objects.count(),
        "patentes_sin_punto": Patente.objects.filter(geom__isnull=True).count(),
        "prc": _estado_prc(),
    }


@lru_cache(maxsize=2)
def _calles_en_memoria(version: tuple) -> list[dict]:
    """Nombres de calles para la búsqueda por palabras; se recarga cuando hay una carga nueva."""
    return [c.a_dict() for c in Calle.objects.only("nombre", "clase", "suf_direc", "clase_desc").order_by("nombre")]


@api.get("/calles")
def calles(request, q: str = Query(..., min_length=2, max_length=60)):
    from django.db.models import Count, Max
    tabla = Calle.objects.aggregate(n=Count("id"), maximo=Max("id"))
    version = (tuple(CargaGIS.objects.filter(fin__isnull=False).values_list("id", "fin").first() or ()),
               tabla["n"], tabla["maximo"])
    return buscar_calles(_calles_en_memoria(version), q, 20)


@api.get("/barrios")
def barrios(request, q: str | None = Query(None, min_length=2, max_length=60)):
    from nucleo.busqueda import normalizar
    todos = sorted((b.a_dict() for b in Barrio.objects.all()), key=lambda b: normalizar(b["BARRIO"]))
    if q is None:
        return {"resultados": todos}
    aguja = normalizar(q)
    return {"resultados": [b for b in todos if aguja in normalizar(b["BARRIO"])][:21]}


@api.get("/patentes")
def patentes(request, minlon: float, minlat: float, maxlon: float, maxlat: float):
    if minlon >= maxlon or minlat >= maxlat:
        raise HttpError(400, "bbox inválido")
    caja = Polygon.from_bbox((minlon, minlat, maxlon, maxlat))
    caja.srid = 4326
    qs = (Patente.objects.filter(geom__intersects=caja).exclude(estado_pat__in=dominios()["estados_ocultos"])
          .order_by("id")[:500])
    return {"resultados": [p.a_dict() for p in qs]}


def _calle_cercana(lon: float, lat: float) -> dict | None:
    pt = Point(lon, lat, srid=4326)
    c = (Calle.objects.filter(geom__dwithin=(pt, D(m=2000))).annotate(d=Distance("geom", pt)).order_by("d").first())
    if c is None:
        return None
    return {"NOMBRE": c.nombre, "CLASE": c.clase, "distancia_m": round(c.d.m, 1)}


@api.get("/punto")
def punto(request, lon: float, lat: float, radio_m: float = Query(150, gt=0, le=1000)):
    cercanas = [{**p.a_dict(), "distancia_m": round(p.dist.m, 1)} for p in comercio.patentes_cerca(lon, lat, radio_m)]
    return {"calle_cercana": _calle_cercana(lon, lat), "patentes_cercanas": cercanas, "radio_m": radio_m}


@api.get("/direccion")
def direccion(request, lon: float, lat: float):
    try:
        with httpx.Client() as client:
            dir_ = geocode.reverse(client, lon, lat)
    except (httpx.HTTPError, geocode.GeocodeError) as e:
        raise HttpError(502, f"Geocodificador no disponible: {e}")
    return {"direccion": dir_}


@api.get("/buscar-direccion")
def buscar_direccion(request, q: str = Query(..., min_length=3, max_length=150)):
    try:
        with httpx.Client() as client:
            candidatos = geocode.forward(client, q)
    except (httpx.HTTPError, geocode.GeocodeError) as e:
        raise HttpError(502, f"Geocodificador no disponible: {e}")
    return {"resultados": candidatos}


@api.get("/giros")
def giros(request):
    return {"resultados": prc_config.giros_publicos(prc_config.cargar())}


def construir_informe(lat: float, lon: float, giro: str, escala: str | None, frente_via: str | None) -> dict:
    """Informe completo: motor de nucleo + checklist de la base + comercio cercano."""
    cfg = prc_config.cargar()
    with cliente_gis() as client:
        gis = prc_gis.consultar_punto(client, lon, lat, cfg)
    inf = informe_mod.generar(lat, lon, giro, cfg, gis, escala=escala, frente_via=frente_via)
    g = cfg["giros"]["giros"][giro]
    items = checklist_para(giro, g["clase"], g["alcohol"])
    if items:
        inf["checklist_rentas"] = {"estado": "lista_oficial", "items": items}
    try:
        inf["comercio_cercano"] = comercio.resumen(lon, lat, g, settings.RADAR["RADIO_COMERCIO_M"])
    except Exception:  # la base puede no estar cargada aún: el informe se entrega igual
        inf["comercio_cercano"] = {"estado": "NO_DISPONIBLE"}
    return inf


@api.get("/informe")
def informe(
    request,
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    giro: str = Query(..., min_length=2, max_length=40),
    escala: Literal["basico", "menor", "mediano", "mayor"] | None = None,
    formato: Literal["json", "texto"] = "json",
    frente_via: str | None = Query(None, min_length=1, max_length=20, pattern=r"^[A-Za-z0-9._-]+$"),
):
    """Informe orientativo de factibilidad para un punto y un giro. No reemplaza el CIP."""
    codigo = giro.strip().lower()
    if codigo not in prc_config.cargar()["giros"]["giros"]:
        raise HttpError(422, "Giro no soportado. Ver /api/giros para la lista de códigos.")
    inf = construir_informe(lat, lon, codigo, escala, frente_via)
    if formato == "texto":
        return HttpResponse(informe_mod.texto(inf), content_type="text/plain; charset=utf-8")
    return inf
