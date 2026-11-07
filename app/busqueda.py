"""Búsqueda de calles por palabras: sin tildes, sin orden y sin números.

La capa de calles no tiene numeración. Si la consulta trae un número (p. ej.
"Pajaritos 1200"), se separa y se avisa al usuario en lugar de devolver vacío.
"""
from __future__ import annotations

import re
import unicodedata

NUMERO = re.compile(r"\b\d+[\w-]*\b")


def normalizar(texto: str | None) -> str:
    if not texto:
        return ""
    descompuesto = unicodedata.normalize("NFKD", str(texto))
    sin_tildes = "".join(c for c in descompuesto if not unicodedata.combining(c))
    limpio = re.sub(r"[^A-Za-z0-9]+", " ", sin_tildes)
    return " ".join(limpio.upper().split())


def separar_numero(consulta: str) -> tuple[str, str | None]:
    numeros = NUMERO.findall(consulta or "")
    sin_numeros = NUMERO.sub(" ", consulta or "")
    return " ".join(sin_numeros.split()), (numeros[0] if numeros else None)


def buscar_calles(calles: list[dict], consulta: str, limite: int = 20) -> dict:
    texto, numero = separar_numero(consulta)
    palabras = normalizar(texto).split()
    if not palabras:
        return {"resultados": [], "aviso": None}
    resultados = []
    for c in calles:
        campo = normalizar(" ".join(str(c.get(k) or "") for k in ("NOMBRE", "SUF_DIREC", "CLASE")))
        if all(p in campo.split() or p in campo for p in palabras):
            resultados.append({k: v for k, v in c.items() if k != "path"})
            if len(resultados) >= limite:
                break
    aviso = None
    if numero is not None:
        aviso = ("Las calles no tienen numeración en esta capa. "
                 f"Se buscó solo el nombre (se ignoró «{numero}»).")
    return {"resultados": resultados, "aviso": aviso}
