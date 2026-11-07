"""Consultas espaciales al servicio MAIPU/PRCMaipu. Si una capa falla, su sección queda NO_DISPONIBLE."""
from __future__ import annotations

import logging
import os
import re
import threading
from datetime import datetime, timezone

import httpx

from .geo import point_to_segment_m

log = logging.getLogger(__name__)

OK, NO_DISPONIBLE = "OK", "NO_DISPONIBLE"
ANCHO_MAX_M = 100

# Último resultado por capa, para /api/health. Se escribe desde varios hilos de la API.
_estado_capas: dict[str, dict] = {}
_lock = threading.Lock()


class CapaNoDisponible(Exception):
    pass


def estado_capas() -> dict:
    with _lock:
        return {k: dict(v) for k, v in _estado_capas.items()}


def _registrar(capa: str, ok: bool, detalle: str | None = None) -> None:
    with _lock:
        _estado_capas[capa] = {"estado": OK if ok else NO_DISPONIBLE,
                               "consultada": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                               **({"detalle": detalle} if detalle else {})}


def base_url(cfg: dict) -> str:
    return os.environ.get("RM_PRC_URL", cfg["zonas"]["capas"]["base"])


def consultar_capa(client: httpx.Client, cfg: dict, layer_id: int, out_fields: str, lon: float, lat: float,
                   distancia_m: float | None = None, geometria: bool = False) -> list[dict]:
    params = {
        "geometry": f"{lon},{lat}", "geometryType": "esriGeometryPoint", "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects", "outFields": out_fields,
        "returnGeometry": "true" if geometria else "false", "f": "json",
    }
    if geometria:
        params["outSR"] = 4326
    if distancia_m is not None:
        params.update(distance=distancia_m, units="esriSRUnit_Meter")
    nombre = f"capa_{layer_id}"
    try:
        r = client.get(f"{base_url(cfg)}/{layer_id}/query", params=params,
                       timeout=cfg["zonas"]["capas"]["timeout_s"])
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        _registrar(nombre, False, type(e).__name__)
        raise CapaNoDisponible(nombre) from e
    if not isinstance(data, dict) or "error" in data:
        err = data.get("error") if isinstance(data, dict) else None
        _registrar(nombre, False, f"ArcGIS {err.get('code') if isinstance(err, dict) else err}")
        raise CapaNoDisponible(nombre)
    feats = data.get("features")
    if not isinstance(feats, list):
        _registrar(nombre, False, "features no es lista")
        raise CapaNoDisponible(nombre)
    _registrar(nombre, True)
    return [f for f in feats if isinstance(f, dict)]


def _attrs(feature: dict) -> dict:
    a = feature.get("attributes")
    return a if isinstance(a, dict) else {}


def _texto(valor) -> str | None:
    """Atributo como texto limpio; None si viene vacío o nulo."""
    if valor is None:
        return None
    t = str(valor).strip()
    return t or None


def _numero(valor) -> float | None:
    try:
        return float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        return None


def ancho_existente(ancho_exis) -> float | None:
    """Menor ancho existente ('18-25' -> 18, '10 var' -> 10). Vacío o 0 -> None (vía no abierta)."""
    if ancho_exis is None or isinstance(ancho_exis, bool):
        return None
    valores = [float(n.replace(",", ".")) for n in re.findall(r"\d+(?:[.,]\d+)?", str(ancho_exis))]
    valores = [v for v in valores if 0 < v <= ANCHO_MAX_M]  # descarta datos implausibles (p. ej. "140")
    return min(valores) if valores else None


def tramo_excluido(a: dict, vcfg: dict) -> str | None:
    """Motivo para no considerar un tramo como frente: proyectado, eliminado, sin jerarquía o fuera del límite."""
    jer = _texto(a.get("JERARQUIA"))
    if jer is None:
        return "sin jerarquía"
    if jer.lower() in {j.lower() for j in vcfg["excluir_jerarquias"]}:
        return jer
    for campo in vcfg["campos_estado"]:
        valor = (_texto(a.get(campo)) or "").upper()
        for token in vcfg["excluir_si_contiene"]:
            if token.upper() in valor:
                return valor.lower()
    return None


def _distancia_a_polilinea(lon, lat, geometry: dict | None) -> float | None:
    if not geometry:
        return None
    best = None
    paths = geometry.get("paths") if isinstance(geometry, dict) else None
    for path in paths or []:
        try:
            pares = [(float(p[0]), float(p[1])) for p in path]
        except (TypeError, ValueError, IndexError):
            continue
        for a, b in zip(pares, pares[1:]):
            d = point_to_segment_m(lon, lat, a, b)
            best = d if best is None or d < best else best
    return best


def consultar_zona(client, lon, lat, cfg) -> dict:
    """Busca la zona en las capas 1 a 4. Las capas no se superponen (verificado en muestra)."""
    hits, fallidas = [], []
    for capa in cfg["zonas"]["capas"]["zonas"]:
        try:
            for f in consultar_capa(client, cfg, capa["id"], capa["outFields"], lon, lat):
                a = _attrs(f)
                codigo = _texto(a.get("ZONA"))
                if not codigo:
                    # Un polígono sin código: el punto está en alguna zona, pero no se sabe cuál.
                    raise CapaNoDisponible(f"capa_{capa['id']}: polígono sin ZONA")
                hits.append({"capa": capa["id"], "gis": codigo.upper(), "descripcion": _texto(a.get("DESCRIPCION"))})
        except CapaNoDisponible:
            fallidas.append(capa["id"])
    if fallidas:
        # Con una capa caída no se puede afirmar "fuera de zona" ni descartar una zona superpuesta
        # (hay al menos un polígono ZE-8 sobre ZH-6).
        return {"estado": NO_DISPONIBLE, "hits": hits, "capas_fallidas": fallidas}
    if hits:
        return {"estado": OK, "hits": hits, "capas_fallidas": []}
    cercanas = set()
    try:
        for capa in cfg["zonas"]["capas"]["zonas"]:
            for f in consultar_capa(client, cfg, capa["id"], "ZONA", lon, lat,
                                    distancia_m=cfg["zonas"]["zonas_cercanas_m"]):
                cercanas.add((_texto(_attrs(f).get("ZONA")) or "").upper())
    except CapaNoDisponible:
        pass
    return {"estado": OK, "hits": [], "capas_fallidas": [], "cercanas": sorted(z for z in cercanas if z)}


def consultar_vialidad(client, lon, lat, cfg) -> dict:
    vcfg = cfg["vialidad"]
    capa = cfg["zonas"]["capas"]["vialidad"]
    try:
        feats = consultar_capa(client, cfg, capa["id"], capa["outFields"], lon, lat,
                               distancia_m=vcfg["radio_busqueda_m"], geometria=True)
    except CapaNoDisponible:
        return {"estado": NO_DISPONIBLE}
    cercanas = []
    for f in feats:
        a = _attrs(f)
        d = _distancia_a_polilinea(lon, lat, f.get("geometry"))
        ancho = ancho_existente(a.get("ANCHO_EXIS"))
        excluido = tramo_excluido(a, vcfg)
        via = {"via": _texto(a.get("VIA")), "codigo": _texto(a.get("CODIGO")), "jerarquia": _texto(a.get("JERARQUIA")),
               "ancho_m": ancho, "ancho_propuesto_m": _numero(a.get("ANCHO_PROP")),
               "distancia_eje_m": None if d is None else round(d, 1)}
        if excluido:
            via["excluida"] = excluido
        semiancho = (ancho or 0) / 2
        via["frente_probable"] = (not excluido and d is not None and d <= semiancho + vcfg["margen_frente_m"])
        via["confirmado"] = False
        cercanas.append(via)
    # Una vía puede venir en varios tramos: dejar el más cercano por código y jerarquía.
    unicas: dict[tuple, dict] = {}
    for v in sorted(cercanas, key=lambda v: v["distancia_eje_m"] if v["distancia_eje_m"] is not None else 1e9):
        unicas.setdefault((v["codigo"], v["via"], v["jerarquia"]), v)
    vias = list(unicas.values())
    return {"estado": OK, "radio_m": vcfg["radio_busqueda_m"], "cercanas": vias,
            "frente": [v for v in vias if v["frente_probable"]]}


def consultar_riesgos(client, lon, lat, cfg) -> dict:
    capas = cfg["zonas"]["capas"]
    out: dict = {"estado": OK, "areas": [], "bleve": None}
    try:
        for f in consultar_capa(client, cfg, capas["riesgo"]["id"], capas["riesgo"]["outFields"], lon, lat):
            a = _attrs(f)
            tipo = _texto(a.get("TIPO_DE_AR"))
            if tipo:
                out["areas"].append({"tipo": tipo, "descripcion": _texto(a.get("DESCRIPCIO")) or ""})
    except CapaNoDisponible:
        out["estado"] = NO_DISPONIBLE
    try:
        feats = consultar_capa(client, cfg, capas["bleve"]["id"], capas["bleve"]["outFields"], lon, lat)
        if feats:
            out["bleve"] = {"buff_dist_m": _numero(_attrs(feats[0]).get("BUFF_DIST"))}
    except CapaNoDisponible:
        out["bleve_estado"] = NO_DISPONIBLE
    return out


def consultar_punto(client: httpx.Client, lon: float, lat: float, cfg: dict) -> dict:
    return {
        "zona": consultar_zona(client, lon, lat, cfg),
        "vialidad": consultar_vialidad(client, lon, lat, cfg),
        "riesgos": consultar_riesgos(client, lon, lat, cfg),
    }
