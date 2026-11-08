"""Convierte el informe (dict del motor) en lo que necesita la plantilla. Sin lógica normativa aquí."""
from __future__ import annotations

import re

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


def presentar(inf: dict, vcfg: dict | None = None) -> dict:
    estado = inf["resultado"]["estado"]
    adv = sorted(inf["advertencias"], key=lambda a: ORDEN_TIPOS.index(a["tipo"]) if a["tipo"] in ORDEN_TIPOS else 99)
    adv = [_para_vecino(a) for a in adv if a["tipo"] != "vialidad" or estado == "PERMITIDO_CON_CONDICION"]
    advertencias = [{"texto": a["texto"], "etiqueta": TIPOS.get(a["tipo"], (a["tipo"], "dato"))[0],
                     "icono": TIPOS.get(a["tipo"], (a["tipo"], "dato"))[1]} for a in adv]
    vialidad = inf.get("vialidad") or {}
    confirmado = next((v for v in vialidad.get("frente", []) if v.get("confirmado")), None)
    if vcfg is None:
        from nucleo.prc_config import cargar
        vcfg = cargar()["vialidad"]
    ed = inf.get("edificacion") or {}
    alturas = [{"condicion": k.replace("_", " ").capitalize(), "valor": v} for k, v in (ed.get("altura_maxima") or {}).items()]
    zona = inf["zona"]
    return {
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
