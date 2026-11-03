"""Acceso a los dominios de datos. Los valores viven en config/dominios.json."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

RUTA_DEFAULT = Path(__file__).resolve().parent.parent / "config" / "dominios.json"


@lru_cache(maxsize=1)
def cargar(ruta: str | None = None) -> dict:
    return json.loads(Path(ruta or RUTA_DEFAULT).read_text(encoding="utf-8"))


def descripcion_clase(codigo: str | None) -> str | None:
    if codigo is None:
        return None
    return cargar()["calles_clase"].get(codigo, codigo)


def descripcion_status(codigo: str | None) -> str | None:
    if codigo is None:
        return None
    return cargar()["patente_status"].get(codigo, codigo)


def estado_normalizado(valor: str | None) -> str | None:
    if valor is None:
        return None
    return cargar()["patente_estado"].get(valor, valor)


def estado_oculto(valor: str | None) -> bool:
    """Compara el valor tal como viene del dato (antes de normalizar)."""
    return valor is not None and valor in set(cargar()["estados_ocultos"])
