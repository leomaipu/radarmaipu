"""Carga de datos del GIS al almacén en memoria, compartida por la API y cargar.py."""
from __future__ import annotations

import logging
import time
from typing import Callable

import httpx

from .loader import barrios_url_from_env, config_from_env, load_all
from .regeocode import regeocodificar
from .store import Store

log = logging.getLogger(__name__)


def cargar_en_store(store: Store, client: httpx.Client) -> dict:
    """Descarga las capas y las publica juntas: si algo falla, el almacén queda como estaba."""
    publicados: dict[str, list[dict]] = {"calle": [], "patente": [], "barrio": []}

    def sink(kind: str, rec: dict) -> None:
        publicados[kind].append(rec)

    calles_url, patente_layers = config_from_env()
    counts = load_all(client, calles_url, patente_layers, sink, barrios_url=barrios_url_from_env())
    store.calles = publicados["calle"]
    store.patentes = publicados["patente"]
    store.barrios = publicados["barrio"]
    return counts


def carga_inicial(store: Store, estado: dict, intentos: int = 3, espera_s: float = 30,
                  crear_cliente: Callable[[], httpx.Client] = httpx.Client) -> None:
    """Corre en segundo plano al iniciar la API e informa su avance en estado["fase"].

    La re-geocodificación puede tardar más de una hora, así que los datos se publican antes
    de empezarla; las patentes sin punto no aparecen en búsquedas por ubicación hasta recibirlo.
    """
    with crear_cliente() as client:
        for intento in range(1, intentos + 1):
            estado["fase"] = "cargando"
            try:
                counts = cargar_en_store(store, client)
                break
            except Exception:  # hilo de fondo: cualquier fallo debe quedar en el estado
                log.exception("Carga del GIS falló (intento %d de %d)", intento, intentos)
                if intento == intentos:
                    estado["fase"] = "error"
                    return
                time.sleep(espera_s)
        log.info("Carga completa: %s", counts)

        estado["fase"] = "regeocodificando"
        try:
            log.info("Re-geocodificación: %s", regeocodificar(store.patentes, client))
        except Exception:
            log.exception("Re-geocodificación interrumpida; se mantienen los puntos originales")
            estado["fase"] = "lista_sin_regeocodificar"
            return
    estado["fase"] = "lista"
