"""Carga del GIS a PostGIS. Reutiliza el cargador de nucleo/loader.py (lista blanca de campos)."""
from __future__ import annotations

import logging
import time

import httpx
from django.contrib.gis.geos import LineString, Point
from django.db import transaction
from django.utils import timezone

from nucleo import geocode
from nucleo.loader import barrios_url_from_env, config_from_env, load_all
from nucleo.regeocode import config as config_regeo

from .models import Barrio, CargaGIS, Calle, Patente

log = logging.getLogger(__name__)


def _patente(rec: dict) -> Patente:
    geom = Point(rec["lon"], rec["lat"], srid=4326) if rec.get("lon") is not None else None
    return Patente(
        capa=rec["capa"], direccion=rec.get("DIRECCION"), estado_pat=rec.get("estado_pat"),
        estado_normalizado=rec.get("estado_normalizado"), tipo_paten=rec.get("tipo_paten"),
        subtipo_pa=rec.get("subtipo_pa"), actividad=rec.get("actividad"), anio=rec.get("Año"),
        semestre=rec.get("semestre"), status=rec.get("Status"), status_desc=rec.get("Status_DESC"),
        score=rec.get("Score"), match_type=rec.get("Match_type"), geom=geom)


def _calle(rec: dict) -> Calle | None:
    path = rec.get("path") or []
    if len(path) < 2:
        return None
    return Calle(nombre=rec.get("NOMBRE"), clase=rec.get("CLASE"), clase_desc=rec.get("CLASE_DESC"),
                 suf_direc=rec.get("SUF_DIREC"), geom=LineString(path, srid=4326))


def cargar(client: httpx.Client) -> dict:
    """Descarga todo y reemplaza las tablas en una sola transacción: si algo falla, quedan los datos anteriores."""
    recs: dict[str, list[dict]] = {"calle": [], "patente": [], "barrio": []}
    calles_url, patentes = config_from_env()
    conteos = load_all(client, calles_url, patentes, lambda k, r: recs[k].append(r), barrios_url=barrios_url_from_env())

    # Puntos re-geocodificados de cargas anteriores: se conservan por dirección y capa.
    previos = {(p.capa, p.direccion): p for p in Patente.objects.filter(coords_origen="re-geocodificado")}
    nuevas = []
    for rec in recs["patente"]:
        p = _patente(rec)
        prev = previos.get((p.capa, p.direccion))
        if prev is not None and (p.geom is None or rec.get("Status") == "U"):
            p.geom, p.coords_origen, p.score_geocodificacion = prev.geom, prev.coords_origen, prev.score_geocodificacion
        nuevas.append(p)
    calles = [c for c in (_calle(r) for r in recs["calle"]) if c is not None]
    with transaction.atomic():
        Patente.objects.all().delete()
        Calle.objects.all().delete()
        Barrio.objects.all().delete()
        Patente.objects.bulk_create(nuevas, batch_size=2000)
        Calle.objects.bulk_create(calles, batch_size=2000)
        Barrio.objects.bulk_create([Barrio(id_barrio=r["ID_BARRIO"], nombre=r["BARRIO"]) for r in recs["barrio"]])
    conteos["conservadas_regeocodificadas"] = sum(1 for p in nuevas if p.coords_origen)
    return conteos


def regeocodificar(client: httpx.Client, limite: int | None = None) -> dict:
    """Asigna punto a patentes con Status U o sin punto. Guarda cada una al momento: se puede interrumpir."""
    cfg = config_regeo()
    pendientes = (Patente.objects.filter(coords_origen__isnull=True)
                  .filter(models_q_pendiente(cfg["status"])).exclude(direccion__isnull=True))
    resumen = {"candidatas": 0, "actualizadas": 0, "bajo_umbral": 0, "sin_resultado": 0}
    for p in pendientes.iterator():
        if limite is not None and resumen["candidatas"] >= limite:
            break
        resumen["candidatas"] += 1
        try:
            cands = geocode.forward(client, p.direccion, max_resultados=1)
        except (httpx.HTTPError, geocode.GeocodeError):
            resumen["sin_resultado"] += 1
            continue
        if not cands or cands[0]["lon"] is None:
            resumen["sin_resultado"] += 1
            continue
        if (cands[0]["score"] or 0) < cfg["umbral_score"]:
            resumen["bajo_umbral"] += 1
            continue
        p.geom = Point(cands[0]["lon"], cands[0]["lat"], srid=4326)
        p.coords_origen, p.score_geocodificacion = "re-geocodificado", cands[0]["score"]
        p.save(update_fields=["geom", "coords_origen", "score_geocodificacion"])
        resumen["actualizadas"] += 1
    return resumen


def models_q_pendiente(status: list[str]):
    from django.db.models import Q
    return Q(status__in=status) | Q(geom__isnull=True)


def ejecutar(regeo: bool, limite: int | None = None, reintentos: int = 1, espera_s: float = 30) -> CargaGIS:
    bitacora = CargaGIS.objects.create(fase="cargando")
    try:
        with httpx.Client() as client:
            for intento in range(1, reintentos + 1):
                try:
                    bitacora.conteos = cargar(client)
                    break
                except Exception:
                    log.exception("Carga del GIS falló (intento %d de %d)", intento, reintentos)
                    if intento == reintentos:
                        raise
                    time.sleep(espera_s)
            bitacora.fase = "regeocodificando" if regeo else "lista_sin_regeocodificar"
            bitacora.save()
            if regeo:
                bitacora.conteos["regeocodificacion"] = regeocodificar(client, limite)
                bitacora.fase = "lista"
    except Exception as e:  # queda registrado en la bitácora y en el log
        log.exception("Carga del GIS falló")
        bitacora.fase, bitacora.error = "error", f"{type(e).__name__}: {e}"
    bitacora.fin = timezone.now()
    bitacora.save()
    return bitacora
