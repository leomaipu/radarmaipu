"""Sitio del vecino: un solo documento con mapa y panel; los paneles llegan por HTMX."""
from __future__ import annotations

import hashlib
import json
from collections import OrderedDict

import httpx
from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import render
from django.urls import reverse
from django.templatetags.static import static
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET

from api.views import construir_informe
from nucleo import geocode, prc_config
from nucleo import informe as informe_mod

from .presentacion import lenguaje, presentar

ESCALAS = [("", "No lo sé"), ("basico", "Básico"), ("menor", "Menor"), ("mediano", "Mediano"), ("mayor", "Mayor")]
POPULARES = ["abarrotes", "bazar", "peluqueria", "restaurante", "farmacia", "taller_mecanico", "vestuario_calzado",
             "panaderia_venta"]


def _giros_agrupados(cfg: dict) -> list[dict]:
    clases = cfg["giros"]["clases"]
    grupos: "OrderedDict[str, list]" = OrderedDict((c, []) for c in ("2.2", "2.10", "1.2"))
    for codigo, g in cfg["giros"]["giros"].items():
        buscar = " ".join([g["nombre"], *g.get("sinonimos", []), *g.get("palabras_actividad", [])]).lower()
        grupos[g["clase"]].append({"codigo": codigo, "nombre": g["nombre"], "alcohol": g["alcohol"], "buscar": buscar})
    nombres = {"2.2": "Comercio", "2.10": "Servicios y talleres", "1.2": "Hospedaje"}
    return [{"clase": c, "nombre": nombres[c], "titulo": clases[c],
             "giros": sorted(gs, key=lambda x: x["nombre"])} for c, gs in grupos.items()]


@require_GET
def inicio(request):
    cfg = prc_config.cargar()
    giros = cfg["giros"]["giros"]
    contexto = {
        "grupos": _giros_agrupados(cfg),
        "populares": [{"codigo": c, "nombre": giros[c]["nombre"]} for c in POPULARES if c in giros],
        "escalas": ESCALAS,
        "config_js": {
            "tiles": settings.RADAR["TILES_URL"], "atribucion": settings.RADAR["TILES_ATTRIBUTION"],
            "tiles_ref": settings.RADAR["TILES_REFERENCIA_URL"], "tiles_max": settings.RADAR["TILES_MAX_NATIVO"],
            "base_municipal": settings.RADAR["BASE_MUNICIPAL"],
            "prc": settings.RADAR["PRC_MAPSERVER"], "centro": settings.RADAR["CENTRO"],
            "radio": settings.RADAR["RADIO_COMERCIO_M"],
            "urls": {"informe": reverse("web:panel_informe"), "leyenda": reverse("web:leyenda"),
                     "direccion": "/api/direccion"},
            "giros": {c: g["nombre"] for c, g in giros.items()},
            "debug": settings.DEBUG,
        },
    }
    return render(request, "web/inicio.html", contexto)


def _float(request, nombre):
    try:
        return float(request.GET[nombre])
    except (KeyError, ValueError):
        return None


@require_GET
def panel_informe(request):
    lat, lon = _float(request, "lat"), _float(request, "lon")
    giro = (request.GET.get("giro") or "").strip().lower()
    escala = request.GET.get("escala") or None
    frente = request.GET.get("frente_via") or None
    cfg = prc_config.cargar()
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return HttpResponseBadRequest("Punto inválido")
    if giro not in cfg["giros"]["giros"] or escala not in (None, "basico", "menor", "mediano", "mayor"):
        return HttpResponseBadRequest("Giro o escala inválidos")
    if frente is not None and (len(frente) > 20 or not frente.replace("-", "").replace(".", "").replace("_", "").isalnum()):
        return HttpResponseBadRequest("Vía inválida")
    inf = construir_informe(lat, lon, giro, escala, frente)
    puntos = inf.get("comercio_cercano", {}).get("puntos", [])
    otros = informe_mod.evaluar_otros(inf, cfg, lenguaje()["giros_referencia"], escala)
    return render(request, "web/parciales/informe.html", {
        "inf": inf, "vm": presentar(inf, otros=otros, cfg=cfg), "escala": escala or "",
        "puntos": puntos,
        "consulta": {"lat": lat, "lon": lon, "giro": giro, "escala": escala or ""},
    })


@require_GET
def panel_buscar(request):
    q = (request.GET.get("q") or "").strip()
    if len(q) < 3:
        return render(request, "web/parciales/buscar.html", {"resultados": [], "q": q})
    try:
        with httpx.Client() as client:
            cands = geocode.forward(client, q if "maip" in q.lower() else f"{q}, Maipú", max_resultados=6)
        error = None
    except (httpx.HTTPError, geocode.GeocodeError):
        cands, error = [], "El buscador de direcciones no responde. Puedes tocar el mapa."
    vistos, resultados = set(), []
    for c in cands:
        if c["lon"] is None or c["direccion"] in vistos:
            continue
        vistos.add(c["direccion"])
        resultados.append(c)
    return render(request, "web/parciales/buscar.html", {"resultados": resultados, "q": q, "error": error})


@cache_control(max_age=3600)
def manifest(request):
    datos = {
        "name": "Radar Maipú · Simulador de negocio",
        "short_name": "Radar Maipú",
        "description": "Revisa si tu negocio es compatible con el Plan Regulador de Maipú antes de iniciar el trámite.",
        "lang": "es-CL",
        "start_url": "/?origen=pwa",
        "scope": "/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#ffffff",
        "categories": ["government", "business", "utilities"],
        "icons": [
            {"src": static("web/img/icon-192.png"), "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": static("web/img/icon-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": static("web/img/icon-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
    }
    return HttpResponse(json.dumps(datos, ensure_ascii=False), content_type="application/manifest+json")


ARCHIVOS_SW = ["web/css/app.css", "web/js/app.js", "web/vendor/leaflet/leaflet.js", "web/vendor/leaflet/leaflet.css",
               "web/vendor/esri-leaflet.js", "web/vendor/markercluster/leaflet.markercluster.js",
               "web/vendor/markercluster/MarkerCluster.css", "web/vendor/htmx.min.js",
               "web/img/logo-maipu.svg", "web/img/escudo-maipu.svg", "web/img/icon-192.png",
               "web/fonts/rubik-latin-400-normal.woff2", "web/fonts/rubik-latin-500-normal.woff2",
               "web/fonts/rubik-latin-700-normal.woff2", "web/fonts/rubik-latin-800-normal.woff2"]


def service_worker(request):
    """Se sirve desde la raíz para que su alcance sea todo el sitio. La versión cambia con los archivos."""
    archivos = [static(a) for a in ARCHIVOS_SW]
    version = hashlib.sha1("|".join(archivos).encode()).hexdigest()[:10]
    cuerpo = render(request, "web/sw.js", {"archivos": json.dumps(["/offline/", *archivos]), "version": version}).content
    r = HttpResponse(cuerpo, content_type="application/javascript")
    r["Cache-Control"] = "no-cache"
    r["Service-Worker-Allowed"] = "/"
    return r


def offline(request):
    return render(request, "web/offline.html")


CAPAS_LEYENDA = (2, 3, 1, 4)  # orden de lectura: centrales, habitacionales, especiales, industriales


@require_GET
def leyenda(request):
    """Simbología oficial del PRC (capas 1 a 4), pedida al MapServer y guardada un día en caché."""
    from django.core.cache import cache
    datos = cache.get("leyenda_prc")
    if datos is None:
        try:
            with httpx.Client() as client:
                r = client.get(f"{settings.RADAR['PRC_MAPSERVER']}/legend", params={"f": "json"}, timeout=15)
                r.raise_for_status()
                capas = {c.get("layerId"): c for c in (r.json().get("layers") or []) if isinstance(c, dict)}
        except (httpx.HTTPError, ValueError):
            r = HttpResponse('{"capas": []}', content_type="application/json", status=503)
            r["Cache-Control"] = "no-store"
            return r
        datos = {"capas": [
            {"id": i, "nombre": capas[i].get("layerName"),
             "items": [{"etiqueta": x.get("label"), "img": f"data:{x.get('contentType')};base64,{x.get('imageData')}"}
                       for x in capas[i].get("legend", []) if x.get("imageData")]}
            for i in CAPAS_LEYENDA if i in capas]}
        cache.set("leyenda_prc", datos, 86400)
    r = HttpResponse(json.dumps(datos, ensure_ascii=False), content_type="application/json")
    r["Cache-Control"] = "public, max-age=86400"
    return r
