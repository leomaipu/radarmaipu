"""Mide el buscador de giros con frases etiquetadas (tests/datos/frases_giros.json)."""
from __future__ import annotations

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
                        "p95": round(sorted(tiempos)[max(0, int(len(tiempos) * 0.95) - 1)], 1) if tiempos else None},
        "fallos": [d for d in detalle if not d["top3"]],
    }


def calibrar(buscador: BuscadorGiros, frases: list[dict], umbrales: list[float], conjunto: str = "desarrollo") -> list[dict]:
    """Aciertos por umbral. `buscador` debe estar configurado con umbral 0 para ver todos los puntajes."""
    filas = [f for f in frases if f["conjunto"] == conjunto]
    resultados = [(f, buscador.buscar(f["frase"])) for f in filas]
    salida = []
    for u in umbrales:
        con, sin = [], []
        for f, res in resultados:
            filtrado = Resultado(modo=res.modo, sugerencias=[s for s in res.sugerencias if s.puntaje >= u])
            (con if f["esperado"] else sin).append((filtrado, f["esperado"]))
        pct = lambda xs, n: round(100 * sum(_acierta(r, e, n) for r, e in xs) / len(xs), 1) if xs else None  # noqa: E731
        salida.append({"umbral": u, "top1_pct": pct(con, 1), "top3_pct": pct(con, 3), "sin_giro_rechazadas_pct": pct(sin, 1)})
    return salida
