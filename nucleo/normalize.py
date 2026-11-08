"""Limpieza de valores tal como vienen del GIS. No inventa significados.

Solo corrige ruido verificado en la medición real (2026-11-02):
espacios sobrantes y marcadores de nulo. Los códigos abreviados
(PBN, PSN, PTE, CARRE) y los estados (BLOQUEDADA, Status M/T/U) se
conservan tal cual hasta confirmarlos con la municipalidad.
"""
from __future__ import annotations

NULL_MARKERS = {"", "<Nulo>", "None", "NULL", "null"}


def clean_text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return None if text in NULL_MARKERS else text
