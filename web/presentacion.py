"""Convierte el informe (dict del motor) en lo que necesita la plantilla. Sin lógica normativa aquí.

La ficha del lugar (opción C) traduce el resultado técnico a lenguaje vecinal con los textos de
config/prc/lenguaje_vecinal.json. Toda frase sale de un dato del informe o de la matriz: si falta el
dato, se dice que falta; nunca se completa con una suposición.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

RUTA_LENGUAJE = Path(__file__).resolve().parent.parent / "config" / "prc" / "lenguaje_vecinal.json"
ORDEN_ESCALAS = ("basico", "menor", "mediano", "mayor")


@lru_cache(maxsize=1)
def lenguaje() -> dict:
    return json.loads(RUTA_LENGUAJE.read_text(encoding="utf-8"))

ESTADOS = {
    "PERMITIDO": {
        "clase": "ok", "titulo": "Compatible",
        "bajada": "Según el Plan Regulador, este giro se puede instalar en este punto.",
    },
    "PERMITIDO_CON_CONDICION": {
        "clase": "cond", "titulo": "Compatible con condiciones",
        "bajada": "Se puede instalar si cumples las condiciones que se indican abajo.",
    },
    "NO_PERMITIDO": {
        "clase": "no", "titulo": "No compatible",
        "bajada": "El Plan Regulador no permite este giro en este punto.",
    },
    "NO_CONCLUYENTE": {
        "clase": "rev", "titulo": "Requiere revisión",
        "bajada": "Con la información disponible no podemos orientarte. Consulta en la municipalidad.",
    },
}

TIPOS = {
    "condicion": ("Condición", "cond"),
    "vialidad": ("Vía y frente del local", "via"),
    "normativa": ("Norma", "norma"),
    "riesgo": ("Área de riesgo", "riesgo"),
    "ubicacion": ("Ubicación", "ubic"),
    "calidad_dato": ("Dato por revisar", "dato"),
    "giro": ("Sobre el giro", "giro"),
    "gis": ("Servicio GIS", "dato"),
}
ORDEN_TIPOS = ["condicion", "vialidad", "riesgo", "ubicacion", "normativa", "giro", "calidad_dato", "gis"]


NOMBRE_ESCALA = {"basico": "básica", "menor": "menor", "mediano": "mediana", "mayor": "mayor"}
CONDICION_VIA = {
    "vialidad_estructurante": "una vía estructurante del Plan Regulador",
    "colectora_o_mayor": "una vía colectora, troncal o expresa",
    "via_20m": "una vía de 20 m o más de ancho",
}


def _cumple(via: dict, condicion: str, vcfg: dict) -> bool:
    jer = (via.get("jerarquia") or "").lower()
    if condicion == "vialidad_estructurante":
        return jer in {j.lower() for j in vcfg["jerarquias_estructurantes"]}
    if condicion == "colectora_o_mayor":
        return jer in {j.lower() for j in vcfg["jerarquias_colectora_o_mayor"]}
    if condicion == "via_20m":
        return (via.get("ancho_m") or 0) >= 20
    return False


def frentes_utiles(inf: dict, vcfg: dict) -> list[dict]:
    """Vías probables que, si el vecino confirma el frente, sí cumplirían alguna condición pendiente."""
    pendientes = {d.get("condicion") for d in (inf["resultado"].get("detalle_escalas") or {}).values()
                  if d.get("estado") == "CONDICION"} & set(CONDICION_VIA)
    out = []
    for v in (inf.get("vialidad") or {}).get("frente", []):
        if v.get("confirmado"):
            continue
        cumple = [c for c in sorted(pendientes) if _cumple(v, c, vcfg)]
        if cumple:
            out.append({**v, "cumple": CONDICION_VIA[cumple[0]]})
    return out


_JERGA_FRENTE = re.compile(r"No se da por cumplido: .*$")


def _para_vecino(a: dict) -> dict:
    """Quita instrucciones pensadas para quien usa la API (p. ej. 'repetir la consulta con frente_via=…')."""
    if a["tipo"] == "vialidad" and "frente_via=" in a["texto"]:
        return {**a, "texto": _JERGA_FRENTE.sub("No la damos por cumplida hasta que confirmes que tu local la enfrenta.",
                                                a["texto"])}
    return a


# ——— Lenguaje vecinal (ficha del lugar) ———

def _lista(items: list[str], y: str = "y") -> str:
    """['a'] -> 'a'; ['a', 'b'] -> 'a y b'; ['a', 'b', 'c'] -> 'a, b y c'. En negativo, y='ni'."""
    items = [i for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + f" {y} " + items[-1]


def _mayuscula(s: str) -> str:
    return s[:1].upper() + s[1:]


def _locales(escalas: list[str], leng: dict, y: str = "y") -> str:
    return "locales " + _lista([leng["tamanos_plural"][e] for e in escalas], y)


def _agrupar(detalle: dict) -> tuple[list[str], dict[str, list[str]], list[str]]:
    """Separa las escalas evaluadas en permitidas, con condición (agrupadas por condición) y no permitidas."""
    si, cond, no = [], {}, []
    for e in ORDEN_ESCALAS:
        d = detalle.get(e)
        if not d:
            continue
        if d["estado"] == "SI":
            si.append(e)
        elif d["estado"] == "NO":
            no.append(e)
        else:
            cond.setdefault(d.get("condicion") or "texto", []).append(e)
    return si, cond, no


def _texto_condicion(cond: str, leng: dict) -> str:
    return leng["condiciones"].get(cond, leng["condiciones"]["texto"])


def linea_giro(estado: str, detalle: dict | None, leng: dict, *, alcohol: bool = False, ambigua: bool = False,
               condicion_texto: bool = False, escala: str | None = None) -> str:
    """Una frase corta que dice si el giro se puede y con qué condición, sin términos técnicos."""
    lin = leng["lineas"]
    if ambigua:
        return lin["ambigua"]
    if estado == "NO_CONCLUYENTE":
        return lin["alcohol"] if alcohol else lin["revisar"]
    if estado == "PERMITIDO":
        return lin["permitido"]
    if estado == "NO_PERMITIDO":
        return lin["no_tamano"] if (detalle and escala) else lin["prohibido"]
    # PERMITIDO_CON_CONDICION
    if not detalle:
        return lin["permitido_texto"]
    si, cond, no = _agrupar(detalle)
    # La condición escrita ya se nombra si alguna escala depende de ella: no repetirla.
    extra = f" {lin['y_texto']}" if condicion_texto and "texto" not in cond else ""
    if escala and escala in detalle:
        d = detalle[escala]
        if d["estado"] == "SI":
            return lin["permitido_texto"]
        return lin["tamano_condicion"].format(cond=_texto_condicion(d.get("condicion") or "texto", leng)) + extra
    if not cond:
        return (lin["salvo"].format(no=_locales(no, leng)) + extra) if no else lin["permitido_texto"]
    if len(cond) == 1:
        (c, escalas_c), = cond.items()
        texto_c = _texto_condicion(c, leng)
        if not si and not no:
            return lin["solo_si"].format(cond=texto_c) + extra
        if si == ["basico"] and not no:
            return lin["barrio_y_condicion"].format(tam=leng["tamanos"]["basico"], cond=texto_c) + extra
    partes = []
    if si:
        partes.append(lin["detalle_si"].format(lista=_locales(si, leng)))
    for c, escalas_c in cond.items():
        partes.append(lin["detalle_condicion"].format(lista=_mayuscula(_locales(escalas_c, leng)),
                                                      cond=_texto_condicion(c, leng)))
    if no:
        partes.append(lin["detalle_no"].format(lista=_locales(no, leng, "ni")))
    return " ".join(partes) + extra


def _nombre_lugar(nombre_matriz: str) -> str:
    """'Habitacional 6 (Maipú Norte - Sector Villas Pehuén)' -> 'Maipú Norte - Sector Villas Pehuén'."""
    m = re.search(r"\(([^()]+)\)\s*$", nombre_matriz)
    return (m.group(1) if m else nombre_matriz).strip()


def describir_zona(inf: dict, cfg: dict, leng: dict) -> dict:
    """Título y descripción de la zona del punto, en lenguaje vecinal, desde la matriz de usos."""
    lz = leng["zona"]
    z = inf.get("zona") or {}
    if z.get("estado") == "NO_DISPONIBLE":
        return {"titulo": lz["titulo_sin_gis"], "texto": lz["sin_gis"], "codigo": None}
    if isinstance(z.get("gis"), list):
        return {"titulo": lz["titulo_varias"], "texto": lz["varias"], "codigo": None}
    codigo = z.get("ordenanza")
    if not codigo:
        return {"titulo": lz["titulo_sin_zona"], "texto": lz["sin_zona"], "codigo": None}
    zm = cfg["usos_comercio"]["zonas"].get(codigo)
    if zm is None:
        nombre = (z.get("descripcion") or "").split(":", 1)[-1].strip() or codigo
        return {"titulo": nombre, "texto": lz["sin_matriz"], "codigo": codigo}
    prefijo = codigo.split("-", 1)[0]
    tipo = lz["tipo"].get(prefijo, "")
    if prefijo in lz["vivienda_en"] and zm.get("vivienda") in lz["vivienda"]:
        tipo = f"{tipo} {lz['vivienda'][zm['vivienda']]}"
    frases = [f"{tipo}."] if tipo else []
    escalas = (zm.get("comercio") or {}).get("escalas") or {}
    cond_escala = (zm.get("comercio") or {}).get("condicion_escala") or {}
    # Se describen las mismas escalas que el motor evalúa cuando el vecino no declara el tamaño.
    evaluadas = cfg["usos_comercio"]["escalas_sin_declarar"]
    detalle = {e: {"estado": v, **({"condicion": cond_escala.get(e)} if v == "CONDICION" else {})}
               for e, v in escalas.items() if e in evaluadas}
    si, cond, no = _agrupar(detalle)
    if si:
        frases.append(lz["comercio_si"].format(lista=_locales(si, leng)))
    for c, escalas_c in cond.items():
        frases.append(lz["comercio_condicion"].format(lista=_mayuscula(_locales(escalas_c, leng)),
                                                      cond=_texto_condicion(c, leng)))
    if no:
        frases.append(lz["comercio_no"].format(lista=_locales(no, leng, "ni")))
    return {"titulo": _nombre_lugar(zm["nombre"]), "texto": " ".join(frases), "codigo": codigo}


def chips_lugar(inf: dict, leng: dict, frente_confirmado: dict | None) -> list[dict]:
    """Datos del entorno en una línea: frente a vía (si importa) y riesgos. tono: ok | alerta | neutro."""
    chips = []
    if frente_confirmado:
        chips.append({"texto": f"Tu local da a {frente_confirmado['via']}", "tono": "ok"})
    else:
        pendientes = {d.get("condicion") for d in (inf["resultado"].get("detalle_escalas") or {}).values()
                      if d.get("estado") == "CONDICION"} & set(leng["condiciones_chip"]) - {"_nota"}
        for c in sorted(pendientes):
            chips.append({"texto": f"{leng['condiciones_chip'][c]}: por confirmar", "tono": "neutro"})
    if any(a["tipo"] == "calidad_dato" for a in inf.get("advertencias", [])):
        chips.append({"texto": leng["zona"]["dato_por_corregir"], "tono": "alerta"})
    rc = leng["riesgos_chip"]
    r = inf.get("riesgos") or {}
    if r.get("estado") != "OK":
        chips.append({"texto": rc["sin_dato"], "tono": "neutro"})
    else:
        tipos = []
        for a in r.get("areas") or []:
            t = rc.get(a.get("tipo"), rc["otro"])
            if t not in tipos:
                tipos.append(t)
        if r.get("bleve"):
            tipos.append(rc["bleve"])
        chips += [{"texto": t, "tono": "alerta"} for t in tipos] or [{"texto": rc["ninguno"], "tono": "ok"}]
    return chips


def _fila(codigo: str, nombre: str, estado: str, linea: str, leng: dict, principal: bool = False) -> dict:
    corto = leng["estados"][estado]["corto"]
    if principal and linea == leng["lineas"]["permitido"]:
        linea = leng["lineas"]["permitido_principal"]  # el título ya dice "Se puede": no repetirlo
    return {"codigo": codigo, "nombre": nombre, "estado": estado, "clase": ESTADOS[estado]["clase"],
            "titulo": leng["estados"][estado]["titulo"], "corto": corto,
            # Para lector de pantalla: el estado solo si la frase visible no empieza diciéndolo.
            "sr": "" if linea.startswith(corto) else f"{corto}.",
            "linea": linea, "principal": principal}


def ficha(inf: dict, cfg: dict, otros: list[dict] | None, frente_confirmado: dict | None,
          leng: dict | None = None) -> dict:
    leng = leng or lenguaje()
    giro = inf.get("giro") or {}
    g = cfg["giros"]["giros"].get(giro.get("codigo") or "", {})
    escala = giro.get("escala")
    r = inf["resultado"]
    ambigua = r["estado"] == "NO_CONCLUYENTE" and "Zona ambigua" in (r.get("motivo") or "")
    linea = linea_giro(r["estado"], r.get("detalle_escalas"), leng, alcohol=g.get("alcohol", False), ambigua=ambigua,
                       condicion_texto=any(a["tipo"] == "condicion" for a in inf.get("advertencias", [])),
                       escala=escala)
    nombre = (giro.get("nombre") or g.get("nombre") or "") + (f" · local {leng['tamanos'][escala]}" if escala else "")
    principal = _fila(giro.get("codigo") or "", nombre, r["estado"], linea, leng, principal=True)
    filas = [_fila(o["codigo"], o["nombre"], o["estado"],
                   linea_giro(o["estado"], o.get("detalle_escalas"), leng, alcohol=o["alcohol"],
                              ambigua=o.get("ambigua", False), condicion_texto=o.get("condicion_texto", False),
                              escala=escala), leng)
             for o in (otros or [])[:leng["max_otros"]]]
    usados = {f["estado"] for f in [principal, *filas]}
    leyenda = [{"clase": ESTADOS[e]["clase"], "texto": leng["estados"][e]["corto"]}
               for e in ESTADOS if e in usados]
    return {"lugar": describir_zona(inf, cfg, leng), "chips": chips_lugar(inf, leng, frente_confirmado),
            "principal": principal, "otros": filas, "leyenda": leyenda}


def presentar(inf: dict, vcfg: dict | None = None, otros: list[dict] | None = None, cfg: dict | None = None) -> dict:
    estado = inf["resultado"]["estado"]
    adv = sorted(inf["advertencias"], key=lambda a: ORDEN_TIPOS.index(a["tipo"]) if a["tipo"] in ORDEN_TIPOS else 99)
    adv = [_para_vecino(a) for a in adv if a["tipo"] != "vialidad" or estado == "PERMITIDO_CON_CONDICION"]
    advertencias = [{"texto": a["texto"], "etiqueta": TIPOS.get(a["tipo"], (a["tipo"], "dato"))[0],
                     "icono": TIPOS.get(a["tipo"], (a["tipo"], "dato"))[1]} for a in adv]
    vialidad = inf.get("vialidad") or {}
    confirmado = next((v for v in vialidad.get("frente", []) if v.get("confirmado")), None)
    if cfg is None:
        from nucleo.prc_config import cargar
        cfg = cargar()
    if vcfg is None:
        vcfg = cfg["vialidad"]
    ed = inf.get("edificacion") or {}
    alturas = [{"condicion": k.replace("_", " ").capitalize(), "valor": v} for k, v in (ed.get("altura_maxima") or {}).items()]
    zona = inf["zona"]
    return {
        "ficha": ficha(inf, cfg, otros, confirmado),
        # El riesgo ya se ve en la cabecera: el detalle técnico se abre solo si el punto o el dato están en duda.
        "abrir_detalle": any(a["tipo"] in ("ubicacion", "calidad_dato") for a in inf.get("advertencias", [])),
        "estado": ESTADOS[estado],
        "codigo_estado": estado,
        "advertencias": advertencias,
        "frentes_sugeridos": frentes_utiles(inf, vcfg) if estado == "PERMITIDO_CON_CONDICION" else [],
        "escala_nombre": NOMBRE_ESCALA.get(inf["giro"].get("escala") or ""),
        "frente_confirmado": confirmado,
        "alturas": alturas,
        "mod4": ed.get("modificacion_4"),
        "zona_codigo": zona.get("ordenanza"),
        "zona_nombre": (zona.get("descripcion") or "").split(":", 1)[-1].strip() or None,
        "detalle_escalas": [
            {"escala": {"basico": "Básico", "menor": "Menor", "mediano": "Mediano", "mayor": "Mayor"}[k],
             "estado": v["estado"]}
            for k, v in (inf["resultado"].get("detalle_escalas") or {}).items()],
    }
