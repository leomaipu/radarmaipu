"""Arma el informe orientativo (JSON y texto) a partir del resultado del GIS y de la matriz."""
from __future__ import annotations

import re
from datetime import datetime

from . import usos
from .prc_config import normalizar_zona
from .prc_gis import NO_DISPONIBLE, OK

VERSION = "0.1"
AVISO = ("Informe orientativo. No reemplaza el Certificado de Informaciones Previas ni la resolución "
         "de la DOM o de Rentas.")


def _ahora() -> str:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/Santiago")).isoformat(timespec="seconds")
    except Exception:  # sin base de zonas horarias (p. ej. Windows sin tzdata)
        return datetime.now().astimezone().isoformat(timespec="seconds")


def _zona_segun_descripcion(descripcion: str | None) -> str | None:
    """'Zona Habitacional 9: El Porvenir' -> 'ZH-9'. Sirve para detectar registros inconsistentes."""
    m = re.match(r"\s*Zona Habitacional (\d+)\b", descripcion or "")
    return f"ZH-{m.group(1)}" if m else None


def _edificacion(zona: str | None, cfg: dict) -> dict | None:
    base = cfg["alturas"]["zonas"].get(zona or "")
    if base is None:
        return None
    alturas = dict(base["alturas"])
    mod4 = cfg["modificaciones"]["MOD_4"]
    if zona in mod4["zonas"]:
        if mod4["vigente"]:
            alturas.update(mod4["alturas"].get(zona, {}))
            estado_mod4 = "aplicada"
        else:
            estado_mod4 = "no_vigente"
    else:
        estado_mod4 = "no_aplica"
    return {"altura_maxima": alturas, "modificacion_4": estado_mod4,
            "fuente": f"Ordenanza PRC 2004, art. 34, {zona}, p. {base['pagina']}"
                      + (" y Modificación N°4" if estado_mod4 == "aplicada" else "")}


def _advertencias_mod4(zona: str | None, cfg: dict) -> list[dict]:
    mod4 = cfg["modificaciones"]["MOD_4"]
    if zona not in mod4["zonas"]:
        return []
    if not mod4["vigente"]:
        return [{"tipo": "normativa", "texto": f"La zona {zona} está afecta a la Modificación N°4 (alturas y apart "
                 "hotel): modificación aprobada, vigencia por confirmar. Se informan las alturas base del PRC 2004."}]
    partes = [f"Zona {zona} afecta a la Modificación N°4 (D.A. {mod4['decreto']}, Diario Oficial "
              f"{mod4['publicacion_do']}): alturas reemplazadas según el texto aprobatorio"]
    if zona in mod4["apart_hotel_prohibido"]:
        partes.append("apart hotel prohibido")
    if zona in mod4["incentivos_zonas"]:
        partes.append("hasta 2 pisos adicionales por incentivos normativos")
    return [{"tipo": "normativa", "texto": "; ".join(partes) + "."}]


def _advertencias_vialidad(vialidad: dict, hay_condicion_via: bool) -> list[dict]:
    if vialidad.get("estado") != OK:
        return [{"tipo": "vialidad", "texto": "Capa de vialidad estructurante no disponible: no se pudo estimar el "
                 "frente del predio."}]
    out = []
    for v in vialidad.get("frente", []):
        ancho = f", ancho existente ~{v['ancho_m']:g} m" if v.get("ancho_m") else ""
        if v.get("confirmado"):
            out.append({"tipo": "vialidad", "texto": f"Frente a {v['via']} ({v['jerarquia']}{ancho}) declarado por "
                        "el usuario: se verifica en el CIP."})
            if (v.get("jerarquia") or "").lower() in ("servicio", "local"):
                out.append({"tipo": "vialidad", "texto": "Tratar las vías de servicio y locales como 'vialidad "
                            "estructurante del PRC' es una interpretación pendiente de confirmar con la DOM."})
        else:
            out.append({"tipo": "vialidad", "texto": f"Frente probable a {v['via']} ({v['jerarquia']}{ancho}, "
                        f"código {v['codigo']}), estimado por proximidad al eje ({v['distancia_eje_m']:g} m). "
                        "No se da por cumplido: si el predio enfrenta esa vía, repetir la consulta con "
                        f"frente_via={v['codigo']}."})
    excluidas = [v for v in vialidad.get("cercanas", []) if v.get("excluida")]
    for v in excluidas:
        out.append({"tipo": "vialidad", "texto": f"{v['via']} ({v['codigo']}) aparece cerca pero no se considera "
                    f"frente: {v['excluida']}."})
    if not vialidad.get("frente") and hay_condicion_via:
        out.append({"tipo": "vialidad", "texto": "La capa de vialidad estructurante no muestra vías a menos de "
                    f"{vialidad.get('radio_m')} m del punto, así que no se pudo confirmar la condición de vía. "
                    "Si el predio no la cumple, esa escala no está permitida."})
    return out


def _advertencias_riesgo(riesgos: dict, cfg: dict) -> list[dict]:
    rcfg = cfg["riesgos"]
    out = []
    if riesgos.get("estado") != OK:
        out.append({"tipo": "riesgo", "texto": "Capa de zonas de riesgo no disponible."})
    for a in riesgos.get("areas", []):
        texto = rcfg["tipos"].get(a["tipo"], a["descripcion"])
        out.append({"tipo": "riesgo", "texto": f"Área de riesgo {a['tipo']} ({a['descripcion'].capitalize()}): {texto}"})
    if riesgos.get("bleve"):
        buff = riesgos["bleve"].get("buff_dist_m")
        out.append({"tipo": "riesgo", "texto": rcfg["bleve"]["texto"].format(
            buff=f"{buff:g}" if isinstance(buff, (int, float)) else "?")})
    return out


def _art32(zona: str | None, giro: str, resultado: dict, cfg: dict) -> list[dict]:
    """Art. 32: comercio pequeño en una vivienda, en cualquier zona, si la vivienda sigue siendo el destino principal."""
    g = cfg["giros"]["giros"][giro]
    zcfg = cfg["usos_comercio"]["zonas"].get(zona or "")
    if zcfg is None or zcfg.get("vivienda") != "SI" or g["clase"] not in ("2.2", "2.10") or g["alcohol"]:
        return []
    bloque = zcfg.get("comercio" if g["clase"] == "2.2" else "servicios_artesanales") or {}
    if giro in (bloque.get("prohibido") or []) or resultado["estado"] in (usos.PERMITIDO, usos.NO_CONCLUYENTE):
        return []
    return [{"tipo": "normativa", "texto": "Si el negocio funciona dentro de una vivienda, el art. 32 permite pequeños "
             "comercios e industrias artesanales en cualquier zona mientras la vivienda siga siendo el destino "
             "principal; si el uso no habitacional supera el 50 % de lo construido, rigen las normas de la zona."}]


def _fuentes(zona: str | None, cfg: dict, resultado: dict) -> list[dict]:
    fuentes = []
    zcfg = cfg["usos_comercio"]["zonas"].get(zona or "")
    if zcfg:
        fuentes.append({"titulo": "Ordenanza PRC 2004 (D.A. 6383/2004)", "articulo": resultado.get("articulo"),
                        "pagina": zcfg["pagina"], "detalle": zcfg["fuente"]})
    elif resultado.get("articulo") == "Art. 41":
        fuentes.append({"titulo": "Ordenanza PRC 2004 (D.A. 6383/2004)", "articulo": "Art. 41", "pagina": 35})
    mod4 = cfg["modificaciones"]["MOD_4"]
    fuentes.append({"titulo": "Modificación N°4", "vigente": mod4["vigente"], "decreto": mod4["decreto"],
                    "publicacion_do": mod4["publicacion_do"]})
    fuentes.append({"titulo": "GIS Municipalidad de Maipú, servicio MAIPU/PRCMaipu", "capas": [0, 1, 2, 3, 4, 5, 6]})
    return fuentes


def confirmar_frente(vialidad: dict, frente_via: str | None) -> tuple[dict, list[dict]]:
    """Marca como confirmado el tramo cercano cuyo código declaró el usuario (sin modificar el original)."""
    if not frente_via or vialidad.get("estado") != OK:
        return vialidad, []
    codigo = frente_via.strip().upper()
    vias = [dict(v) for v in vialidad.get("cercanas", [])]
    elegidas = [v for v in vias if (v.get("codigo") or "").upper() == codigo and v.get("frente_probable")]
    if not elegidas:
        return vialidad, [{"tipo": "vialidad", "texto": f"La vía declarada ({frente_via}) no es un frente probable "
                           "del punto (vía construida, junto al punto): no se consideró."}]
    for v in elegidas:
        v["confirmado"] = True
        v["frente_probable"] = True
    nueva = dict(vialidad, cercanas=vias, frente=[v for v in vias if v.get("frente_probable")])
    return nueva, []


def generar(lat: float, lon: float, giro: str, cfg: dict, gis: dict, escala: str | None = None,
            ahora: str | None = None, frente_via: str | None = None) -> dict:
    g = cfg["giros"]["giros"][giro]
    vialidad, adv_frente = confirmar_frente(gis["vialidad"], frente_via)
    gis = dict(gis, vialidad=vialidad)
    zona_gis = gis["zona"]
    advertencias: list[dict] = []
    zona_out: dict = {"estado": zona_gis["estado"]}
    zona = None
    resultado: dict

    if zona_gis["estado"] == NO_DISPONIBLE:
        zona_out["capas_fallidas"] = zona_gis.get("capas_fallidas", [])
        resultado = {"estado": usos.NO_CONCLUYENTE, "articulo": None,
                     "motivo": "No respondieron todas las capas de zonas del GIS, así que no se puede determinar "
                               "la zona con seguridad. Intentar más tarde."}
    else:
        codigos = sorted({h["gis"] for h in zona_gis["hits"]})
        if len(codigos) > 1:
            zona_out.update(gis=codigos)
            resultado = {"estado": usos.NO_CONCLUYENTE, "articulo": None,
                         "motivo": f"El punto cae en más de una zona ({', '.join(codigos)}): revisar con la DOM."}
        elif codigos:
            hit = zona_gis["hits"][0]
            zona = normalizar_zona(hit["gis"], cfg)
            zona_out.update(gis=hit["gis"], ordenanza=zona, descripcion=hit["descripcion"])
            if zona is None:
                resultado = {"estado": usos.NO_CONCLUYENTE, "articulo": None,
                             "motivo": f"Código de zona del GIS no reconocido: {hit['gis']}."}
            else:
                resultado = usos.evaluar(zona, giro, cfg, vialidad=gis["vialidad"], escala=escala)
                alterna = _zona_segun_descripcion(hit["descripcion"])
                if alterna and alterna != zona:
                    advertencias.append({"tipo": "calidad_dato", "texto": f"El GIS registra la zona {zona} con la "
                                         f"descripción de {alterna} ('{hit['descripcion']}'). Registro por corregir."})
                    otro = usos.evaluar(alterna, giro, cfg, vialidad=gis["vialidad"], escala=escala)
                    if otro["estado"] != resultado["estado"]:
                        resultado = {"estado": usos.NO_CONCLUYENTE, "articulo": None,
                                     "motivo": f"Zona ambigua en el GIS ({zona} o {alterna}) y el resultado cambia "
                                               "según cuál sea: confirmar con la DOM."}
        else:
            zona_out["cercanas"] = [normalizar_zona(z, cfg) or z for z in zona_gis.get("cercanas", [])]
            resultado = usos.evaluar(None, giro, cfg)
            if zona_out["cercanas"]:
                advertencias.append({"tipo": "ubicacion", "texto": "Zonas a menos de "
                                     f"{cfg['zonas']['zonas_cercanas_m']} m: {', '.join(zona_out['cercanas'])}. "
                                     "Si el punto quedó sobre la calle, marcarlo dentro del predio."})
        if zona_gis.get("capas_fallidas"):
            advertencias.append({"tipo": "gis", "texto": "Capas de zonas sin respuesta: "
                                 f"{zona_gis['capas_fallidas']}. La zona se obtuvo de las demás capas."})

    advertencias += adv_frente
    adv_eval = resultado.pop("advertencias", [])
    detalle = resultado.pop("detalle_escalas", None)
    hay_cond_via = any(a["tipo"] == "vialidad" for a in adv_eval)
    advertencias = adv_eval + advertencias
    if zona in cfg["usos_comercio"]["zonas"]:
        advertencias += _advertencias_vialidad(gis["vialidad"], hay_cond_via)
    advertencias += _advertencias_riesgo(gis["riesgos"], cfg)
    advertencias += _advertencias_mod4(zona, cfg)
    advertencias += _art32(zona, giro, resultado, cfg)

    informe = {
        "version_informe": VERSION,
        "fecha_generacion": ahora or _ahora(),
        "punto": {"lat": lat, "lon": lon},
        "zona": zona_out,
        "giro": {"codigo": giro, "nombre": g["nombre"], "clase_ordenanza": cfg["giros"]["clases"][g["clase"]],
                 "escala": escala},
        "frente_declarado": frente_via,
        "resultado": {k: resultado.get(k) for k in ("estado", "motivo", "articulo")},
        "advertencias": advertencias,
        "edificacion": _edificacion(zona, cfg),
        "vialidad": gis["vialidad"],
        "riesgos": {"estado": gis["riesgos"]["estado"], "areas": gis["riesgos"].get("areas", []),
                    "bleve": gis["riesgos"].get("bleve")},
        "secciones": {"zona": zona_gis["estado"], "vialidad": gis["vialidad"]["estado"],
                      "riesgos": gis["riesgos"]["estado"]},
        "fuentes": _fuentes(zona, cfg, resultado),
        "checklist_rentas": {"estado": cfg["checklist_rentas"]["estado"], "items": cfg["checklist_rentas"]["items"]},
        "aviso": AVISO,
    }
    if detalle is not None:
        informe["resultado"]["detalle_escalas"] = detalle
    return informe


ETIQUETA = {usos.PERMITIDO: "Permitido", usos.CON_CONDICION: "Permitido con condición",
            usos.NO_PERMITIDO: "No permitido", usos.NO_CONCLUYENTE: "No concluyente"}


def texto(informe: dict) -> str:
    """Versión para la app: aviso visible, luego zona, resultado del giro y advertencias."""
    z, r, g = informe["zona"], informe["resultado"], informe["giro"]
    if z.get("ordenanza"):
        zona_txt = f"Zona {z['ordenanza']}" + (f": {z['descripcion']}" if z.get("descripcion") else "")
    elif z["estado"] == NO_DISPONIBLE:
        zona_txt = "Zona no disponible (GIS sin respuesta)."
    else:
        zona_txt = "Sin zona normativa en este punto."
    lineas = [f"AVISO: {informe['aviso']}", "", "1. ZONA", zona_txt]
    ed = informe.get("edificacion")
    if ed:
        alturas = "; ".join(f"{k.replace('_', ' ')}: {v}" for k, v in ed["altura_maxima"].items())
        lineas.append(f"Altura máxima: {alturas}.")
    lineas += ["", "2. RESULTADO DEL GIRO", f"{g['nombre']} ({g['clase_ordenanza']}): {ETIQUETA[r['estado']]}.",
               r["motivo"]]
    if r.get("articulo"):
        lineas.append(f"Referencia: {r['articulo']}.")
    lineas += ["", "3. ADVERTENCIAS"]
    lineas += [f"- {a['texto']}" for a in informe["advertencias"]] or ["- Sin advertencias."]
    fuentes = [f["titulo"] + (f", p. {f['pagina']}" if f.get("pagina") else "") for f in informe["fuentes"]]
    lineas += ["", "Fuentes: " + "; ".join(fuentes) + ".", "", f"AVISO: {informe['aviso']}"]
    return "\n".join(lineas)
