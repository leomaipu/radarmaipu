"""Evaluación zona × giro según la matriz de config/prc. Sin red: todo entra por parámetros.

Estados: PERMITIDO, PERMITIDO_CON_CONDICION, NO_PERMITIDO, NO_CONCLUYENTE.
Orden (documento MVP, sección 5): sin zona -> zona fuera de matriz -> prohibido -> alcohol ->
escala -> vía. Una condición de vía solo se cumple con un frente confirmado (declarado por el
usuario sobre una vía de la capa 0). La proximidad al eje no basta, y la ausencia de datos nunca
convierte una condición en NO.
"""
from __future__ import annotations

PERMITIDO = "PERMITIDO"
CON_CONDICION = "PERMITIDO_CON_CONDICION"
NO_PERMITIDO = "NO_PERMITIDO"
NO_CONCLUYENTE = "NO_CONCLUYENTE"

ESCALAS = ("basico", "menor", "mediano", "mayor")
NOMBRE_ESCALA = {"basico": "básico", "menor": "menor", "mediano": "mediano", "mayor": "mayor"}
TEXTO_CONDICION = {
    "vialidad_estructurante": "solo frente a vialidad estructurante del PRC",
    "colectora_o_mayor": "solo frente a vía colectora o de mayor jerarquía",
    "via_20m": "solo frente a vías de 20 o más metros",
    "texto": "con una condición especial (ver advertencias)",
}
AVISO_VIA = {
    "vialidad_estructurante": "Verificar si el frente del predio da a una vía estructurante del PRC.",
    "colectora_o_mayor": "Verificar si el frente del predio da a una vía colectora, troncal o expresa.",
    "via_20m": "Verificar si el predio enfrenta una vía de 20 o más metros entre líneas oficiales.",
}
_ORDEN = {"NO": 0, "CONDICION": 1, "SI": 2}


def _resultado(estado: str, motivo: str, articulo: str | None = None, **extra) -> dict:
    return {"estado": estado, "motivo": motivo, "articulo": articulo, **extra}


def _cumple(cond: str, vialidad: dict | None, cfg: dict) -> bool | None:
    """True si hay un dato que confirma la condición; None si no se puede confirmar."""
    if cond == "texto" or not vialidad or vialidad.get("estado") != "OK":
        return None
    vcfg = cfg["vialidad"]
    frente = [v for v in vialidad.get("frente") or [] if v.get("confirmado")]
    if cond == "vialidad_estructurante":
        validas = {j.lower() for j in vcfg["jerarquias_estructurantes"]}
        ok = any((v.get("jerarquia") or "").lower() in validas for v in frente)
    elif cond == "colectora_o_mayor":
        validas = {j.lower() for j in vcfg["jerarquias_colectora_o_mayor"]}
        ok = any((v.get("jerarquia") or "").lower() in validas for v in frente)
    elif cond == "via_20m":
        ok = any(v.get("ancho_m") is not None and v["ancho_m"] >= 20 for v in frente)
    else:
        raise ValueError(f"condición desconocida: {cond}")
    return True if ok else None


def _estado_condicion(cond: str | None, vialidad, cfg) -> str:
    if cond is None:
        return "SI"
    return "SI" if _cumple(cond, vialidad, cfg) else "CONDICION"


def _clase_bloque(zona_cfg: dict, clase: str) -> tuple[str, dict | None]:
    if clase == "2.2":
        return "Comercio", zona_cfg.get("comercio")
    if clase == "2.10":
        return "Servicios artesanales", zona_cfg.get("servicios_artesanales")
    if clase == "1.2":
        return "Hospedaje", zona_cfg.get("hospedaje")
    raise ValueError(f"clase sin regla: {clase}")


def _textos(bloque: dict, giro: str) -> list[str]:
    ct = bloque.get("condiciones_texto") or {}
    return [t for k, t in ct.items() if k in ("_todos", giro)]


def evaluar(zona: str | None, giro: str, cfg: dict, vialidad: dict | None = None,
            escala: str | None = None) -> dict:
    """Devuelve {estado, motivo, articulo, detalle_escalas, advertencias}."""
    giros = cfg["giros"]["giros"]
    if giro not in giros:
        raise ValueError(f"giro no soportado: {giro}")
    if escala is not None and escala not in ESCALAS:
        raise ValueError(f"escala no válida: {escala}")
    g = giros[giro]
    advertencias: list[dict] = []
    if g.get("nota"):
        advertencias.append({"tipo": "giro", "texto": g["nota"]})

    # 1-2. Zona
    if zona is None:
        return _resultado(NO_CONCLUYENTE, "Fuera de zona normativa: el punto no cae en ninguna zona del PRC "
                          "(puede estar en la vía pública o fuera del límite urbano).", advertencias=advertencias)
    zcfg = cfg["zonas"]
    if zona in zcfg["zonas_excluidas_mvp"]:
        return _resultado(NO_CONCLUYENTE, f"Zona {zona} fuera del alcance del MVP. {zcfg['motivo_exclusion']}",
                          "Art. 34, ZI", advertencias=advertencias)
    especiales = zcfg["zonas_especiales"]["descripcion"]
    if zona in especiales:
        return _resultado(NO_CONCLUYENTE, f"Zona de uso especial {zona}: {especiales[zona]} "
                          "Sus usos se revisan caso a caso con la DOM.", "Art. 41", advertencias=advertencias)
    matriz = cfg["usos_comercio"]["zonas"]
    if zona not in matriz:
        return _resultado(NO_CONCLUYENTE, f"Zona {zona} sin matriz de usos cargada.", advertencias=advertencias)

    zona_cfg = matriz[zona]
    articulo = f"Art. 34, {zona}"
    nombre_clase, bloque = _clase_bloque(zona_cfg, g["clase"])
    if bloque is None:
        return _resultado(NO_CONCLUYENTE, f"Sin regla cargada para {nombre_clase.lower()} en {zona}.", articulo,
                          advertencias=advertencias)

    if g["clase"] == "1.2":
        return _evaluar_hospedaje(zona, giro, g, bloque, articulo, cfg, advertencias)

    # 3. Prohibiciones de la zona
    if giro in (bloque.get("prohibido") or []):
        return _resultado(NO_PERMITIDO, f"{g['nombre']}: prohibido en {zona} ({nombre_clase.lower()}).", articulo,
                          advertencias=advertencias)
    solo = bloque.get("solo_giros")
    if solo is not None and giro not in solo:
        nombres = ", ".join(giros[s]["nombre"].lower() for s in solo)
        return _resultado(NO_PERMITIDO, f"En {zona} solo se permiten estos servicios artesanales: {nombres}.",
                          articulo, advertencias=advertencias)

    # 4. Alcohol
    if g["alcohol"]:
        advertencias.append({"tipo": "normativa", "texto": "Art. 28: los distanciamientos de locales con expendio "
                             "de alcohol a equipamientos se rigen por la Ley 19.925 y la ordenanza municipal."})
        return _resultado(NO_CONCLUYENTE, "Requiere ordenanza municipal de alcoholes y Ley 19.925 (no cargadas).",
                          articulo, advertencias=advertencias)

    # 5-6. Escalas y condiciones de vía
    escalas_eval = [escala] if escala else list(cfg["usos_comercio"]["escalas_sin_declarar"])
    cond_escala = bloque.get("condicion_escala") or {}
    cond_giro = (bloque.get("condicion_giro") or {}).get(giro)
    if cond_giro is None and g.get("taller") and bloque.get("condicion_talleres"):
        cond_giro = bloque["condicion_talleres"]

    detalle: dict[str, dict] = {}
    pendientes: set[str] = set()
    for e in escalas_eval:
        valor = bloque["escalas"][e]
        cond = cond_escala.get(e) if valor == "CONDICION" else None
        estado_e = valor if valor != "CONDICION" else _estado_condicion(cond, vialidad, cfg)
        if estado_e != "NO" and cond_giro:
            estado_g = _estado_condicion(cond_giro, vialidad, cfg)
            if _ORDEN[estado_g] < _ORDEN[estado_e]:
                estado_e, cond = estado_g, cond_giro
        detalle[e] = {"estado": estado_e, **({"condicion": cond} if estado_e == "CONDICION" else {})}
        if estado_e == "CONDICION" and cond:
            pendientes.add(cond)

    estados = {d["estado"] for d in detalle.values()}
    partes = []
    for e, d in detalle.items():
        if d["estado"] == "SI":
            partes.append(f"escala {NOMBRE_ESCALA[e]} permitida")
        elif d["estado"] == "NO":
            partes.append(f"escala {NOMBRE_ESCALA[e]} no permitida")
        else:
            partes.append(f"escala {NOMBRE_ESCALA[e]} {TEXTO_CONDICION[d['condicion']]}")
    motivo = f"{g['nombre']} ({nombre_clase.lower()}) en {zona}: " + "; ".join(partes) + "."
    if estados == {"SI"}:
        estado = PERMITIDO
    elif estados == {"NO"}:
        estado = NO_PERMITIDO
    else:
        estado = CON_CONDICION

    textos = _textos(bloque, giro) + ([g["condicion_general"]] if g.get("condicion_general") else [])
    for t in textos:
        advertencias.append({"tipo": "condicion", "texto": t})
        if estado == PERMITIDO:
            estado = CON_CONDICION
    for cond in sorted(pendientes):
        if cond in AVISO_VIA:
            advertencias.append({"tipo": "vialidad", "texto": AVISO_VIA[cond]})
    advertencias.append({"tipo": "normativa", "texto": "Escala por definir: art. 2.1.36 OGUC no cargado. "
                         + ("Se evaluó la escala declarada." if escala else
                            "Sin escala declarada se evaluaron: "
                            + ", ".join(NOMBRE_ESCALA[e] for e in escalas_eval) + ".")})
    return _resultado(estado, motivo, articulo, detalle_escalas=detalle, advertencias=advertencias)


def _evaluar_hospedaje(zona, giro, g, bloque, articulo, cfg, advertencias) -> dict:
    mod4 = cfg["modificaciones"]["MOD_4"]
    if bloque.get("permitido") == "NO":
        return _resultado(NO_PERMITIDO, f"Hospedaje no permitido en {zona}.", articulo, advertencias=advertencias)
    if giro == "apart_hotel" and zona in mod4["apart_hotel_prohibido"]:
        if mod4["vigente"]:
            return _resultado(NO_PERMITIDO, f"Apart hotel prohibido en {zona} por la Modificación N°4.",
                              f"{articulo} (Mod. N°4, D.A. {mod4['decreto']})", advertencias=advertencias)
        advertencias.append({"tipo": "normativa", "texto": "La Modificación N°4 prohíbe el apart hotel en esta "
                             "zona; modificación aprobada, vigencia por confirmar."})
    if giro in (bloque.get("prohibido") or []):
        return _resultado(NO_PERMITIDO, f"{g['nombre']}: prohibido en {zona}.", articulo, advertencias=advertencias)
    solo = bloque.get("solo_giros")
    if solo is not None and giro not in solo:
        return _resultado(NO_PERMITIDO, f"En {zona} el hospedaje se limita a residencial, hostal u hospedería.",
                          articulo, advertencias=advertencias)
    textos = _textos(bloque, giro)
    for t in textos:
        advertencias.append({"tipo": "condicion", "texto": t})
    estado = CON_CONDICION if textos else PERMITIDO
    return _resultado(estado, f"{g['nombre']} (hospedaje) en {zona}: permitido"
                      + (" con condición." if textos else "."), articulo, advertencias=advertencias)
