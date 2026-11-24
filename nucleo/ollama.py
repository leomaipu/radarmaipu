"""Adaptador de embeddings para Ollama (servidor local de modelos, open source, licencia MIT).

Usa POST /api/embed. Si Ollama falla, deja de intentarlo durante `pausa_tras_falla_s` segundos para que cada
tecla del vecino no espere un timeout: el buscador sigue en modo léxico mientras tanto.
"""
from __future__ import annotations

import logging
import numbers
import threading
import time
from typing import Callable, Sequence

import httpx

from .buscador_giros import EmbeddingsNoDisponibles

log = logging.getLogger(__name__)


class OllamaEmbebedor:
    def __init__(self, url: str, modelo: str, timeout_s: float, pausa_tras_falla_s: float,
                 timeout_indexacion_s: float | None = None, cliente: httpx.Client | None = None,
                 reloj: Callable[[], float] = time.monotonic):
        self.url = url.rstrip("/")
        self.modelo = modelo
        self.timeout_s = timeout_s
        self.timeout_indexacion_s = timeout_indexacion_s or timeout_s
        self.pausa = pausa_tras_falla_s
        # Un cliente por proceso (reutiliza conexiones) y sin proxies del entorno: Ollama es local.
        self._cliente = cliente or httpx.Client(trust_env=False)
        self._reloj = reloj
        self._caido_hasta = 0.0
        self._candado = threading.Lock()

    def disponible(self) -> bool:
        return self._reloj() >= self._caido_hasta

    def _marcar_caido(self, motivo: str) -> None:
        with self._candado:
            self._caido_hasta = self._reloj() + self.pausa
        log.warning("Ollama no disponible (%s): modo léxico por %ss", motivo, self.pausa)

    def embeber(self, textos: Sequence[str], *, indexacion: bool = False) -> list[list[float]]:
        if not self.disponible():
            raise EmbeddingsNoDisponibles("En pausa tras una falla reciente")
        try:
            r = self._cliente.post(f"{self.url}/api/embed", json={"model": self.modelo, "input": list(textos)},
                                   timeout=self.timeout_indexacion_s if indexacion else self.timeout_s)
            r.raise_for_status()
            vectores = r.json()["embeddings"]
        except (httpx.HTTPError, httpx.InvalidURL, ValueError, KeyError, TypeError) as e:
            self._marcar_caido(type(e).__name__)
            raise EmbeddingsNoDisponibles(type(e).__name__) from e
        if (not isinstance(vectores, list) or len(vectores) != len(textos)
                or not all(isinstance(v, list) and v and all(isinstance(x, numbers.Real) for x in v) for v in vectores)
                or len({len(v) for v in vectores}) > 1):
            self._marcar_caido("respuesta inválida")
            raise EmbeddingsNoDisponibles("Respuesta inválida de Ollama")
        return vectores
