"""Checklist de Rentas: qué documentos presenta el vecino según el régimen de su patente y el rubro de su giro.

Las reglas viven en config/prc/checklist_rentas.json. Este módulo solo las aplica: no conoce documentos ni giros
concretos. Cada ítem se filtra con especificaciones simples (régimen, rubro) y se ubica por el caso del vecino
que Radar Maipú no puede saber (si arrienda, si es sociedad, etc.).
"""
from __future__ import annotations

from typing import Callable

TIPOS = ("documento", "condicion")
CAMPOS_ITEM = ("id", "documento", "detalle", "donde", "fuente")

Especificacion = Callable[[dict], bool]


class ChecklistInvalido(ValueError):
    """La configuración de la checklist tiene referencias rotas."""


def rubros_del_giro(codigo: str, giro: dict, cfg_ck: dict) -> list[str]:
    """Rubros a los que pertenece un giro, en el orden de la configuración."""
    salida = []
    for nombre, r in cfg_ck["rubros"].items():
        if nombre.startswith("_"):
            continue
        if codigo in r.get("giros", []) or (r.get("atributo") and giro.get(r["atributo"])):
            salida.append(nombre)
    return salida


def _de_regimen(regimen: str) -> Especificacion:
    return lambda item: regimen in item["regimenes"]


def _de_rubros(rubros: list[str]) -> Especificacion:
    return lambda item: not item.get("rubros") or bool(set(item["rubros"]) & set(rubros))


def _cumple(item: dict, specs: list[Especificacion]) -> bool:
    return all(s(item) for s in specs)


def _publico(item: dict) -> dict:
    return {k: item[k] for k in CAMPOS_ITEM if item.get(k)}


def _regimen(codigo: str, reg: dict, items: list[dict], rubros: list[str], cfg_ck: dict, disponible: bool) -> dict:
    specs = [_de_regimen(codigo), _de_rubros(rubros)]
    aplican = [i for i in items if _cumple(i, specs)]
    casos: dict[str, list[dict]] = {}
    for i in aplican:
        if i["tipo"] == "documento" and i.get("caso"):
            casos.setdefault(i["caso"], []).append(_publico(i))
    orden_casos = [c for c in cfg_ck["casos"] if c in casos]
    enlaces = cfg_ck.get("enlaces", {})
    return {
        "codigo": codigo,
        "nombre": reg["nombre"],
        "corto": reg["corto"],
        "bajada": reg["bajada"],
        "disponible": disponible,
        "motivo_no_disponible": "" if disponible else cfg_ck["giros_sin_mef"]["motivo"],
        "requisitos_titulo": reg.get("requisitos_titulo", ""),
        "requisitos": list(reg.get("requisitos", [])),
        "zonificacion": reg.get("zonificacion", ""),
        "aviso": reg.get("aviso", ""),
        "fuente": reg.get("fuente", ""),
        "pasos": [{"texto": p["texto"], **({"enlace": enlaces[p["enlace"]]} if p.get("enlace") else {})}
                  for p in reg.get("pasos", [])],
        "documentos": [_publico(i) for i in aplican if i["tipo"] == "documento" and not i.get("caso")],
        "si_te_aplica": [{"caso": cfg_ck["casos"][c], "items": casos[c]} for c in orden_casos],
        "condiciones": [_publico(i) for i in aplican if i["tipo"] == "condicion"],
    }


def armar(codigo: str, giro: dict, cfg_ck: dict) -> dict:
    """Checklist para un giro, con un bloque por régimen. El régimen elegido por defecto va marcado."""
    rubros = rubros_del_giro(codigo, giro, cfg_ck)
    sin_mef = codigo in cfg_ck["giros_sin_mef"]["giros"]
    regimenes = [_regimen(c, r, cfg_ck["items"], rubros, cfg_ck, disponible=not (c == "mef" and sin_mef))
                 for c, r in cfg_ck["regimenes"].items()]
    defecto = cfg_ck["regimen_por_defecto"]
    if not any(r["codigo"] == defecto and r["disponible"] for r in regimenes):
        defecto = next(r["codigo"] for r in regimenes if r["disponible"])
    return {
        "estado": cfg_ck["estado"],
        "version": cfg_ck.get("version"),
        "rubros": [{"codigo": r, "nombre": cfg_ck["rubros"][r]["nombre"]} for r in rubros],
        "regimen_sugerido": defecto,
        "regimenes": regimenes,
        "fuentes_lista": cfg_ck.get("fuentes_lista", {}),
        "adicionales": [],
    }


def validar(cfg_ck: dict, giros: dict) -> list[str]:
    """Errores de referencia de la configuración (vacío si está bien). Lo usan las pruebas y el arranque."""
    errores = []
    regimenes, casos = set(cfg_ck["regimenes"]), {c for c in cfg_ck["casos"] if not c.startswith("_")}
    rubros = {r for r in cfg_ck["rubros"] if not r.startswith("_")}
    if cfg_ck.get("regimen_por_defecto") not in regimenes:
        errores.append("regimen_por_defecto no existe")
    for nombre in rubros:
        for g in cfg_ck["rubros"][nombre].get("giros", []):
            if g not in giros:
                errores.append(f"rubro {nombre}: giro desconocido {g}")
    for g in cfg_ck["giros_sin_mef"]["giros"]:
        if g not in giros:
            errores.append(f"giros_sin_mef: giro desconocido {g}")
    for r in cfg_ck["regimenes"].values():
        for p in r.get("pasos", []):
            if p.get("enlace") and p["enlace"] not in cfg_ck.get("enlaces", {}):
                errores.append(f"paso con enlace desconocido {p['enlace']}")
    vistos = set()
    for i in cfg_ck["items"]:
        ident = i.get("id", "?")
        if ident in vistos:
            errores.append(f"id repetido {ident}")
        vistos.add(ident)
        if i.get("tipo") not in TIPOS:
            errores.append(f"{ident}: tipo inválido")
        if not i.get("documento") or not i.get("fuente"):
            errores.append(f"{ident}: falta documento o fuente")
        if not i.get("regimenes") or set(i["regimenes"]) - regimenes:
            errores.append(f"{ident}: régimen desconocido")
        if set(i.get("rubros", [])) - rubros:
            errores.append(f"{ident}: rubro desconocido")
        if i.get("caso") and i["caso"] not in casos:
            errores.append(f"{ident}: caso desconocido")
        if i.get("caso") and i.get("tipo") != "documento":
            errores.append(f"{ident}: solo los documentos pueden depender de un caso")
    return errores
