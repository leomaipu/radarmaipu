import copy
import itertools

import pytest

from app import prc_config, usos

CFG = prc_config.leer()
# Frentes confirmados (declarados por el usuario). Los probables no cumplen condiciones.
VIA_ESTRUCTURANTE = {"estado": "OK", "frente": [{"via": "Av. Pajaritos", "jerarquia": "Troncal", "ancho_m": 30.0,
                                                 "confirmado": True}]}
VIA_LOCAL_ANGOSTA = {"estado": "OK", "frente": [{"via": "Pje. Uno", "jerarquia": "local", "ancho_m": 12.0,
                                                 "confirmado": True}]}
VIA_SERVICIO = {"estado": "OK", "frente": [{"via": "Calle S", "jerarquia": "Servicio", "ancho_m": 15.0,
                                            "confirmado": True}]}
VIA_PROBABLE = {"estado": "OK", "frente": [{"via": "Av. Pajaritos", "jerarquia": "Troncal", "ancho_m": 30.0,
                                            "confirmado": False}]}
SIN_VIA = {"estado": "OK", "frente": []}


def tipos(res):
    return [a["tipo"] for a in res["advertencias"]]


# 1. Normalización de zonas
def test_normalizacion_de_zonas():
    assert prc_config.normalizar_zona("ZH1", CFG) == "ZH-1"
    assert prc_config.normalizar_zona("ZC4", CFG) == "ZC-4"
    assert prc_config.normalizar_zona("ZH10", CFG) == "ZH-10"
    assert prc_config.normalizar_zona(" zh6 ", CFG) == "ZH-6"
    assert prc_config.normalizar_zona("ZX9", CFG) is None
    assert prc_config.normalizar_zona(None, CFG) is None


# 2. ZC-1 + botillería: nunca PERMITIDO.
# El documento pide NO_CONCLUYENTE, pero su propio orden de evaluación (sección 5) pone la prohibición
# de zona antes que el alcohol, y ZC-1 prohíbe botillerías en forma expresa (art. 34, p. 17). Una
# ordenanza de alcoholes solo puede restringir más, nunca habilitar un uso que el PRC prohíbe.
def test_zc1_botilleria_no_es_permitido():
    res = usos.evaluar("ZC-1", "botilleria", CFG)
    assert res["estado"] == usos.NO_PERMITIDO
    assert res["articulo"] == "Art. 34, ZC-1"


def test_alcohol_no_prohibido_en_la_zona_es_no_concluyente():
    res = usos.evaluar("ZH-4", "bar", CFG, vialidad=VIA_ESTRUCTURANTE)
    assert res["estado"] == usos.NO_CONCLUYENTE
    assert "19.925" in res["motivo"]


def test_ningun_giro_con_alcohol_da_permitido_en_ninguna_combinacion():
    alcohol = [c for c, g in CFG["giros"]["giros"].items() if g["alcohol"]]
    zonas = list(CFG["usos_comercio"]["zonas"]) + ["ZI-1", "ZE-5", None]
    for zona, giro, via, escala in itertools.product(zonas, alcohol, [None, VIA_ESTRUCTURANTE, SIN_VIA],
                                                     [None, *usos.ESCALAS]):
        assert usos.evaluar(zona, giro, CFG, vialidad=via, escala=escala)["estado"] != usos.PERMITIDO


# 3. ZH-2 + discoteca
def test_zh2_discoteca_no_permitido():
    assert usos.evaluar("ZH-2", "discoteca", CFG)["estado"] == usos.NO_PERMITIDO


# 4. ZH-6 + bazar sin dato de vía
def test_zh6_bazar_sin_via_es_con_condicion():
    res = usos.evaluar("ZH-6", "bazar", CFG, vialidad=None)
    assert res["estado"] == usos.CON_CONDICION
    assert "vialidad" in tipos(res)
    assert res["detalle_escalas"]["basico"]["estado"] == "SI"
    assert res["detalle_escalas"]["menor"] == {"estado": "CONDICION", "condicion": "vialidad_estructurante"}


def test_zh6_bazar_sin_via_cercana_sigue_con_condicion_no_prohibido():
    # La ausencia de vías en el radio no basta para negar: el predio puede tener otro frente.
    assert usos.evaluar("ZH-6", "bazar", CFG, vialidad=SIN_VIA)["estado"] == usos.CON_CONDICION


# 5. ZH-6 + bazar con vía estructurante
def test_zh6_bazar_con_via_estructurante_es_permitido_con_escala_por_definir():
    res = usos.evaluar("ZH-6", "bazar", CFG, vialidad=VIA_ESTRUCTURANTE)
    assert res["estado"] == usos.PERMITIDO
    assert any("Escala por definir" in a["texto"] for a in res["advertencias"])
    assert "vialidad" not in tipos(res)


# 6. ZI-1 + cualquier giro
@pytest.mark.parametrize("giro", list(CFG["giros"]["giros"]))
def test_zi_fuera_del_mvp(giro):
    for zona in ("ZI-1", "ZI-2", "ZI-3"):
        assert usos.evaluar(zona, giro, CFG)["estado"] == usos.NO_CONCLUYENTE


# 12. Punto sin zona
def test_sin_zona_es_no_concluyente():
    res = usos.evaluar(None, "bazar", CFG)
    assert res["estado"] == usos.NO_CONCLUYENTE
    assert "fuera de zona normativa" in res["motivo"].lower()


# Lecturas verificadas contra el Diario Oficial (difieren del borrador del documento MVP)
def test_zh1_no_admite_escala_basico():
    assert usos.evaluar("ZH-1", "bazar", CFG, escala="basico")["estado"] == usos.NO_PERMITIDO
    # Mediano permitido, pero no frente solo a vía de servicio (DO p. 6): queda con condición.
    mediano = usos.evaluar("ZH-1", "bazar", CFG, escala="mediano", vialidad=VIA_SERVICIO)
    assert mediano["estado"] == usos.CON_CONDICION
    assert any("vías de servicio" in a["texto"] for a in mediano["advertencias"])
    menor = usos.evaluar("ZH-1", "bazar", CFG, escala="menor", vialidad=VIA_ESTRUCTURANTE)
    assert menor["detalle_escalas"]["menor"]["estado"] == "SI"  # troncal = colectora o mayor jerarquía
    local = usos.evaluar("ZH-1", "bazar", CFG, escala="menor", vialidad=VIA_LOCAL_ANGOSTA)
    assert local["estado"] == usos.CON_CONDICION


def test_zh8_todas_las_escalas_y_taller_mecanico_permitido():
    assert usos.evaluar("ZH-8", "bazar", CFG, escala="mayor")["estado"] == usos.PERMITIDO
    assert usos.evaluar("ZH-8", "taller_mecanico", CFG)["estado"] == usos.PERMITIDO
    assert usos.evaluar("ZH-8", "vulcanizacion", CFG)["estado"] == usos.NO_PERMITIDO


def test_taller_en_zh5_depende_de_via_de_20_m():
    assert usos.evaluar("ZH-5", "taller_mecanico", CFG)["estado"] == usos.CON_CONDICION
    assert usos.evaluar("ZH-5", "taller_mecanico", CFG, vialidad=VIA_ESTRUCTURANTE)["estado"] == usos.PERMITIDO
    assert usos.evaluar("ZH-5", "taller_mecanico", CFG, vialidad=VIA_LOCAL_ANGOSTA)["estado"] == usos.CON_CONDICION
    assert usos.evaluar("ZH-5", "peluqueria", CFG)["estado"] == usos.PERMITIDO
    assert usos.evaluar("ZH-5", "taller_mecanico", CFG, vialidad=VIA_PROBABLE)["estado"] == usos.CON_CONDICION


def test_talleres_en_zh4_solo_en_vialidad_estructurante():
    assert usos.evaluar("ZH-4", "taller_bicicletas", CFG)["estado"] == usos.CON_CONDICION
    assert usos.evaluar("ZH-4", "taller_bicicletas", CFG, vialidad=VIA_LOCAL_ANGOSTA)["estado"] == usos.PERMITIDO
    assert usos.evaluar("ZH-4", "peluqueria", CFG)["estado"] == usos.PERMITIDO


def test_zc1_servicios_artesanales_solo_en_mercado_municipal():
    assert usos.evaluar("ZC-1", "peluqueria", CFG)["estado"] == usos.CON_CONDICION
    assert usos.evaluar("ZC-1", "taller_mecanico", CFG)["estado"] == usos.NO_PERMITIDO


def test_zh2_solo_escalas_basico_y_menor():
    # Sin escala declarada se evalúa también mediano, prohibido en ZH-2: no puede ser PERMITIDO simple.
    assert usos.evaluar("ZH-2", "bazar", CFG)["estado"] == usos.CON_CONDICION
    assert usos.evaluar("ZH-2", "bazar", CFG, escala="menor")["estado"] == usos.PERMITIDO
    assert usos.evaluar("ZH-2", "bazar", CFG, escala="mediano")["estado"] == usos.NO_PERMITIDO


def test_condicion_textual_impide_permitido_simple():
    res = usos.evaluar("ZH-1", "restaurante", CFG, escala="mediano")
    assert res["estado"] == usos.CON_CONDICION
    assert "condicion" in tipos(res)


def test_zona_de_uso_especial_es_no_concluyente():
    res = usos.evaluar("ZE-8", "bazar", CFG)
    assert res["estado"] == usos.NO_CONCLUYENTE and res["articulo"] == "Art. 41"


def test_hospedaje():
    assert usos.evaluar("ZH-3", "hostal", CFG)["estado"] == usos.NO_PERMITIDO
    assert usos.evaluar("ZH-2", "hostal", CFG)["estado"] == usos.CON_CONDICION
    assert usos.evaluar("ZH-2", "hotel", CFG)["estado"] == usos.NO_PERMITIDO
    assert usos.evaluar("ZH-5", "motel", CFG)["estado"] == usos.NO_PERMITIDO
    assert usos.evaluar("ZH-9", "hotel", CFG)["estado"] == usos.PERMITIDO


def test_apart_hotel_segun_vigencia_mod4():
    vigente = copy.deepcopy(CFG)
    vigente["modificaciones"]["MOD_4"]["vigente"] = True
    res = usos.evaluar("ZH-8", "apart_hotel", vigente)
    assert res["estado"] == usos.NO_PERMITIDO and "Mod. N°4" in res["articulo"]
    no_vigente = copy.deepcopy(CFG)
    no_vigente["modificaciones"]["MOD_4"]["vigente"] = False
    res = usos.evaluar("ZH-8", "apart_hotel", no_vigente)
    assert res["estado"] == usos.PERMITIDO
    assert any("vigencia por confirmar" in a["texto"] for a in res["advertencias"])
    assert usos.evaluar("ZH-9", "apart_hotel", vigente)["estado"] == usos.PERMITIDO


def test_giro_o_escala_invalidos():
    with pytest.raises(ValueError):
        usos.evaluar("ZH-6", "kiosko_inventado", CFG)
    with pytest.raises(ValueError):
        usos.evaluar("ZH-6", "bazar", CFG, escala="gigante")


# Integridad de la configuración: errores de tipeo en los JSON no deben pasar en silencio.
def test_config_codigos_consistentes():
    giros = CFG["giros"]["giros"]
    condiciones = set(usos.TEXTO_CONDICION)
    for zona, z in CFG["usos_comercio"]["zonas"].items():
        assert zona in CFG["zonas"]["normalizacion"].values()
        assert zona in CFG["alturas"]["zonas"], zona
        for clave in ("comercio", "servicios_artesanales"):
            b = z[clave]
            assert set(b["escalas"]) == set(usos.ESCALAS), (zona, clave)
            for e, v in b["escalas"].items():
                assert v in ("SI", "NO", "CONDICION")
                if v == "CONDICION":
                    assert b["condicion_escala"][e] in condiciones, (zona, clave, e)
            for codigo in b.get("prohibido", []) + b.get("solo_giros", []) + list(b.get("condicion_giro", {})):
                assert codigo in giros, (zona, codigo)
            assert all(c in condiciones for c in b.get("condicion_giro", {}).values())
            assert set(b.get("condiciones_texto", {})) <= set(giros) | {"_todos"}
        for codigo in z["hospedaje"].get("prohibido", []) + z["hospedaje"].get("solo_giros", []):
            assert giros[codigo]["clase"] == "1.2"
    for g in giros.values():
        assert g["clase"] in CFG["giros"]["clases"]


def test_frente_probable_nunca_habilita():
    for zona in ("ZH-3", "ZH-6", "ZH-7"):
        assert usos.evaluar(zona, "bazar", CFG, vialidad=VIA_PROBABLE)["estado"] == usos.CON_CONDICION


def test_arts_30_y_31_condicionan_estaciones_y_gas():
    for giro in ("estacion_servicio", "revision_tecnica"):
        res = usos.evaluar("ZC-3", giro, CFG)
        assert res["estado"] == usos.CON_CONDICION
        assert any("Art. 31" in a["texto"] for a in res["advertencias"])
    assert any("Art. 30" in a["texto"] for a in usos.evaluar("ZH-4", "gas_licuado", CFG)["advertencias"])


def test_repuestos_en_zonas_que_prohiben_automoviles_queda_con_condicion():
    for zona in ("ZH-6", "ZH-7", "ZH-9", "ZH-10"):
        res = usos.evaluar(zona, "repuestos_automovil", CFG, escala="basico")
        assert res["estado"] == usos.CON_CONDICION, zona


def test_ningun_permitido_sin_escala_cuando_mediano_no_esta_permitido():
    for zona, z in CFG["usos_comercio"]["zonas"].items():
        if z["comercio"]["escalas"]["mediano"] == "NO":
            assert usos.evaluar(zona, "bazar", CFG, vialidad=VIA_ESTRUCTURANTE)["estado"] != usos.PERMITIDO


def test_giros_de_gran_escala_piden_declarar_escala():
    for giro in ("supermercado", "centro_comercial", "multitiendas"):
        assert usos.evaluar("ZH-5", giro, CFG)["estado"] != usos.PERMITIDO
