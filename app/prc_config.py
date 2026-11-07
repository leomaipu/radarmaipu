"""Configuración del PRC (config/prc/*.json). Las reglas viven en los JSON, no en el código."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DIR_DEFAULT = Path(__file__).resolve().parent.parent / "config" / "prc"
ARCHIVOS = ("zonas", "usos_comercio", "giros", "modificaciones", "alturas", "vialidad", "riesgos",
            "checklist_rentas")


def leer(directorio: str | Path | None = None) -> dict:
    base = Path(directorio or DIR_DEFAULT)
    return {nombre: json.loads((base / f"{nombre}.json").read_text(encoding="utf-8")) for nombre in ARCHIVOS}


@lru_cache(maxsize=1)
def cargar() -> dict:
    """Configuración por defecto, leída una vez. Las pruebas pasan su propio dict a las funciones."""
    return leer()


def normalizar_zona(codigo_gis: str | None, cfg: dict) -> str | None:
    """'ZH1' -> 'ZH-1'. Devuelve None si el código no está en la tabla de normalización."""
    if codigo_gis is None:
        return None
    return cfg["zonas"]["normalizacion"].get(codigo_gis.strip().upper())


def giros_publicos(cfg: dict) -> list[dict]:
    clases = cfg["giros"]["clases"]
    return [
        {"codigo": codigo, "nombre": g["nombre"], "clase_ordenanza": clases[g["clase"]],
         "requiere_ordenanza_alcoholes": g["alcohol"], **({"nota": g["nota"]} if "nota" in g else {})}
        for codigo, g in cfg["giros"]["giros"].items()
    ]
