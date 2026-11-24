"""Arma el buscador de giros del proceso (composición): modo semántico si hay Ollama configurado, si no léxico."""
from __future__ import annotations

import threading

from django.conf import settings

from nucleo import prc_config
from nucleo.buscador_giros import BuscadorGiros
from nucleo.ollama import OllamaEmbebedor

_buscador: BuscadorGiros | None = None
_candado = threading.Lock()


def crear(cfg: dict | None = None, url: str | None = None, modelo: str | None = None) -> BuscadorGiros:
    cfg = cfg or prc_config.cargar()
    cb = cfg["buscador_giros"]
    url = settings.RADAR["OLLAMA_URL"] if url is None else url
    embebedor = None
    if url:
        cs = cb["semantico"]
        embebedor = OllamaEmbebedor(url, modelo or settings.RADAR["OLLAMA_MODELO"] or cs["modelo"],
                                    cs["timeout_s"], cs["pausa_tras_falla_s"], cs["timeout_indexacion_s"])
    return BuscadorGiros(cfg["giros"]["giros"], cb, embebedor)


def buscador() -> BuscadorGiros:
    """Uno por proceso: el índice de embeddings de los giros se calcula una vez."""
    global _buscador
    with _candado:
        if _buscador is None:
            _buscador = crear()
            _buscador.preparar()  # arma el índice semántico en segundo plano, si hay Ollama
        return _buscador


def reiniciar() -> None:
    """Para pruebas o tras cambiar la configuración."""
    global _buscador
    with _candado:
        _buscador = None
