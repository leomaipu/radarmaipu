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


def _sin_rubros_excluidos(rubros: list[str]) -> Especificacion:
    """Para ítems genéricos que otro ítem más específico ya cubre en esos rubros."""
    return lambda item: not set(item.get("excepto_rubros", [])) & set(rubros)


def _cumple(item: dict, specs: list[Especificacion]) -> bool:
    return all(s(item) for s in specs)


def _legible(fuente: str, nombres: dict) -> str:
    """Cambia los códigos de las listas de Rentas (MAIPU_02_A) por su nombre, para el vecino."""
    for codigo in sorted((c for c in nombres if not c.startswith("_")), key=len, reverse=True):
        fuente = fuente.replace(codigo, nombres[codigo])
    return fuente


def _publico(item: dict, nombres: dict) -> dict:
    salida = {k: item[k] for k in CAMPOS_ITEM if item.get(k)}
    salida["fuente"] = _legible(item["fuente"], nombres)
    return salida


def disponible(reg: dict, codigo_giro: str) -> bool:
    return codigo_giro not in reg.get("no_disponible", {}).get("giros", [])


def _regimen(codigo: str, reg: dict, rubros: list[str], cfg_ck: dict, codigo_giro: str) -> dict:
    specs = [_de_regimen(codigo), _de_rubros(rubros), _sin_rubros_excluidos(rubros)]
    aplican = [i for i in cfg_ck["items"] if _cumple(i, specs)]
    nombres = cfg_ck.get("fuentes_lista", {})
    pub = lambda i: _publico(i, nombres)  # noqa: E731
    casos: dict[str, list[dict]] = {}
    for i in aplican:
        if i["tipo"] == "documento" and i.get("caso"):
            casos.setdefault(i["caso"], []).append(pub(i))
    orden_casos = [c for c in cfg_ck["casos"] if c in casos]
    enlaces = cfg_ck.get("enlaces", {})
    ok = disponible(reg, codigo_giro)
    avisos = reg.get("avisos_por_rubro", {})
    return {
        "codigo": codigo,
        "nombre": reg["nombre"],
        "corto": reg["corto"],
        "bajada": reg["bajada"],
        "disponible": ok,
        "motivo_no_disponible": "" if ok else reg["no_disponible"]["motivo"],
        "requisitos_titulo": reg.get("requisitos_titulo", ""),
        "requisitos": list(reg.get("requisitos", [])),
        "zonificacion": reg.get("zonificacion", ""),
        "avisos": [avisos[r] for r in rubros if r in avisos],
        "aviso": reg.get("aviso", ""),
        "fuente": _legible(reg.get("fuente", ""), nombres),
        "pasos": [{"texto": p["texto"], **({"enlace": enlaces[p["enlace"]]} if p.get("enlace") else {})}
                  for p in reg.get("pasos", [])],
        "documentos": [pub(i) for i in aplican if i["tipo"] == "documento" and not i.get("caso")],
        "si_te_aplica": [{"caso": cfg_ck["casos"][c], "items": casos[c]} for c in orden_casos],
        "condiciones": [pub(i) for i in aplican if i["tipo"] == "condicion"],
    }


def armar(codigo: str, giro: dict, cfg_ck: dict) -> dict:
    """Checklist para un giro, con un bloque por régimen. El régimen elegido por defecto va marcado."""
    rubros = rubros_del_giro(codigo, giro, cfg_ck)
    regimenes = [_regimen(c, r, rubros, cfg_ck, codigo) for c, r in cfg_ck["regimenes"].items()]
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
    if not any(not r.get("no_disponible", {}).get("giros") for r in cfg_ck["regimenes"].values()):
        errores.append("debe haber al menos un régimen disponible para todos los giros")
    for nombre_reg, r in cfg_ck["regimenes"].items():
        for g in r.get("no_disponible", {}).get("giros", []):
            if g not in giros:
                errores.append(f"{nombre_reg}.no_disponible: giro desconocido {g}")
        if {k for k in r.get("avisos_por_rubro", {}) if not k.startswith("_")} - rubros:
            errores.append(f"{nombre_reg}.avisos_por_rubro: rubro desconocido")
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
        if (set(i.get("rubros", [])) | set(i.get("excepto_rubros", []))) - rubros:
            errores.append(f"{ident}: rubro desconocido")
        if i.get("caso") and i["caso"] not in casos:
            errores.append(f"{ident}: caso desconocido")
        if i.get("caso") and i.get("tipo") != "documento":
            errores.append(f"{ident}: solo los documentos pueden depender de un caso")
    return errores
