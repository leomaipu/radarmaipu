"""Mide el buscador de giros con frases etiquetadas (tests/datos/frases_giros.json)."""
from __future__ import annotations

import math
import statistics
import time
from typing import Callable

from .buscador_giros import BuscadorGiros, Resultado


def _acierta(res: Resultado, esperado: list[str], n: int) -> bool:
    codigos = [s.codigo for s in res.sugerencias[:n]]
    return not codigos if not esperado else any(c in esperado for c in codigos)


def evaluar(buscador: BuscadorGiros, frases: list[dict], conjunto: str | None = None,
            reloj: Callable[[], float] = time.perf_counter) -> dict:
    """Aciertos en la 1.ª sugerencia y entre las 3 primeras, frases sin giro bien rechazadas, latencias y fallos."""
    filas = [f for f in frases if conjunto in (None, f["conjunto"])]
    detalle, tiempos, modos = [], [], set()
    for f in filas:
        t0 = reloj()
        res = buscador.buscar(f["frase"])
        tiempos.append((reloj() - t0) * 1000)
        modos.add(res.modo)
        detalle.append({"frase": f["frase"], "esperado": f["esperado"], "conjunto": f["conjunto"],
                        "obtenido": [(s.codigo, s.puntaje) for s in res.sugerencias],
                        "top1": _acierta(res, f["esperado"], 1), "top3": _acierta(res, f["esperado"], 3)})
    con_giro = [d for d in detalle if d["esperado"]]
    sin_giro = [d for d in detalle if not d["esperado"]]
    pct = lambda xs, k: round(100 * sum(d[k] for d in xs) / len(xs), 1) if xs else None  # noqa: E731
    return {
        "frases": len(detalle), "modos": sorted(modos),
        "top1_pct": pct(con_giro, "top1"), "top3_pct": pct(con_giro, "top3"),
        "sin_giro_rechazadas_pct": pct(sin_giro, "top1"),
        "latencia_ms": {"p50": round(statistics.median(tiempos), 1) if tiempos else None,
                        "p95": round(sorted(tiempos)[max(0, math.ceil(len(tiempos) * 0.95) - 1)], 1) if tiempos else None},
        "fallos": [d for d in detalle if not d["top3"]],
    }


def calibrar(buscador: BuscadorGiros, frases: list[dict], umbrales: list[float], pesos: list[float],
             conjunto: str = "desarrollo", excluir: set[str] = frozenset()) -> list[dict]:
    """Aciertos por peso semántico y umbral, sin volver a consultar el modelo: recombina los puntajes léxico y
    semántico de cada giro. `buscador` debe estar configurado con umbral 0 y sin límite de sugerencias.
    `excluir`: frases copiadas como ejemplos (darían similitud 1 y sesgarían la calibración)."""
    filas = [f for f in frases if f["conjunto"] == conjunto and f["frase"] not in excluir]
    resultados = [(f, buscador.buscar(f["frase"])) for f in filas]
    semantico = any(r.modo == "semantico" for _, r in resultados)
    salida = []
    for w in (pesos if semantico else [0.0]):
        for u in umbrales:
            con, sin = [], []
            for f, res in resultados:
                puntuadas = [((w * s.semantico + (1 - w) * s.lexico) if s.semantico is not None else s.lexico, s)
                             for s in res.sugerencias]
                elegidas = [s for p, s in sorted(puntuadas, key=lambda x: (-x[0], x[1].nombre)) if p >= u]
                (con if f["esperado"] else sin).append((Resultado(modo=res.modo, sugerencias=elegidas), f["esperado"]))
            pct = lambda xs, n: round(100 * sum(_acierta(r, e, n) for r, e in xs) / len(xs), 1) if xs else None  # noqa: E731
            salida.append({"peso_semantico": w if semantico else None, "umbral": u, "frases": len(filas),
                           "top1_pct": pct(con, 1), "top3_pct": pct(con, 3), "sin_giro_rechazadas_pct": pct(sin, 1)})
    return salida
