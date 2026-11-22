"""Checklist de Rentas: régimen (microempresa familiar o patente comercial) y casuística por rubro."""
import copy
import re

import pytest

from nucleo import checklist, informe, prc_config

CFG = prc_config.cargar()
CK = CFG["checklist_rentas"]
GIROS = CFG["giros"]["giros"]


def armar(codigo):
    return checklist.armar(codigo, GIROS[codigo], CK)


def regimen(ck, codigo):
    return next(r for r in ck["regimenes"] if r["codigo"] == codigo)


def ids(reg):
    """Ids de todos los ítems visibles de un régimen (documentos, casos y condiciones)."""
    todos = reg["documentos"] + [d for g in reg["si_te_aplica"] for d in g["items"]] + reg["condiciones"]
    return {d["id"] for d in todos}


def test_la_configuracion_no_tiene_referencias_rotas():
    assert checklist.validar(CK, GIROS) == []


@pytest.mark.parametrize("roto, error", [
    (lambda c: c["items"].append({**c["items"][0]}), "id repetido"),
    (lambda c: c["items"][0].update(rubros=["inexistente"]), "rubro desconocido"),
    (lambda c: c["items"][0].update(caso="inexistente"), "caso desconocido"),
    (lambda c: c["items"][0].update(fuente=""), "falta documento o fuente"),
    (lambda c: c["rubros"]["alimentos"]["giros"].append("no_existe"), "giro desconocido"),
    (lambda c: c["regimenes"]["mef"]["no_disponible"]["giros"].append("no_existe"), "giro desconocido"),
    (lambda c: c["regimenes"]["comercial"].update(no_disponible={"giros": ["bazar"], "motivo": "x"}), "al menos un régimen"),
    (lambda c: c["regimenes"]["mef"]["excepciones_zonificacion"].update(nada="x"), "excepciones_zonificacion"),
    (lambda c: c["regimenes"]["mef"]["pasos"].append({"texto": "x", "enlace": "nada"}), "enlace desconocido"),
])
def test_validar_detecta_errores_de_configuracion(roto, error):
    cfg = copy.deepcopy(CK)
    roto(cfg)
    assert any(error in e for e in checklist.validar(cfg, GIROS))


@pytest.mark.parametrize("codigo", list(GIROS))
def test_todo_giro_tiene_lista_con_fuente_en_cada_regimen_disponible(codigo):
    ck = armar(codigo)
    disponibles = [r for r in ck["regimenes"] if r["disponible"]]
    assert disponibles and ck["regimen_sugerido"] in {r["codigo"] for r in disponibles}
    for r in disponibles:
        assert r["documentos"], (codigo, r["codigo"])
        for d in r["documentos"] + r["condiciones"] + [d for g in r["si_te_aplica"] for d in g["items"]]:
            assert d["fuente"] and d["documento"]


def test_microempresa_familiar_lleva_las_declaraciones_y_el_sii():
    mef = regimen(armar("bazar"), "mef")
    assert {"mef_dj_simple", "mef_inofensiva", "mef_sii", "cedula", "smapa"} <= ids(mef)
    assert mef["excepciones"] == []
    assert "com_recepcion" not in ids(mef)
    assert "zonificación" in mef["zonificacion"] and "Reglamento Sanitario" in mef["zonificacion"]
    assert len(mef["requisitos"]) == 4
    assert any("SII" in p["texto"] and p.get("enlace") for p in mef["pasos"])


def test_patente_comercial_pide_zonificacion_y_recepcion_final():
    com = regimen(armar("bazar"), "comercial")
    assert {"com_recepcion", "com_sii", "cedula", "smapa"} <= ids(com)
    assert "mef_dj_simple" not in ids(com)
    assert "Dirección de Obras" in com["pasos"][0]["texto"]
    assert com["pasos"][1]["enlace"]["url"] == "https://www.sii.cl/servicios_online/1031-1034.html"


def test_cafeteria_con_consumo_en_el_local_necesita_banos_para_clientes():
    """El ejemplo de Rentas: una cafetería (fuente de soda) debe tener baños (DS 977, art. 73)."""
    for r in armar("fuente_soda")["regimenes"]:
        assert {"cond_banos_publico", "cond_personal_alimentos", "sanitaria_alimentos"} <= ids(r)
        banos = next(c for c in r["condiciones"] if c["id"] == "cond_banos_publico")
        assert "art. 73" in banos["fuente"] and "separados por sexo" in banos["detalle"]
        # La excepción del art. 73 es solo para locales al paso: para llevar o atención en barra.
        assert "al paso" in banos["detalle"] and "para llevar" in banos["detalle"] and "barra" in banos["detalle"]


def test_almacen_necesita_resolucion_sanitaria_pero_no_banos_para_clientes():
    for r in armar("abarrotes")["regimenes"]:
        assert "sanitaria_alimentos" in ids(r) and "cond_banos_publico" not in ids(r)
        # Art. 32 DS 977: vestuarios del personal solo donde se producen o elaboran alimentos.
        assert "cond_personal_alimentos" not in ids(r)


def test_bazar_no_lleva_exigencias_de_otros_rubros():
    ck = armar("bazar")
    assert ck["rubros"] == []
    for r in ck["regimenes"]:
        assert not ids(r) & {"sanitaria_alimentos", "mef_sag", "com_sag", "alcoholes", "sec", "calificacion",
                             "cond_banos_publico"}


@pytest.mark.parametrize("codigo, item", [
    ("mascotas", "com_sag"), ("vivero", "com_sag"), ("floreria", "com_sag"),
    ("botilleria", "alcoholes"), ("restaurante_con_alcohol", "alcoholes"),
    ("farmacia", "sanitaria_farmacia"), ("estacion_servicio", "sec"), ("taller_mecanico", "calificacion"),
])
def test_exigencias_por_rubro(codigo, item):
    assert item in ids(regimen(armar(codigo), "comercial"))


def test_giros_grandes_o_molestos_no_pueden_ser_microempresa_familiar():
    for codigo in ("discoteca", "bar", "supermercado", "estacion_servicio"):
        ck = armar(codigo)
        mef = regimen(ck, "mef")
        assert not mef["disponible"] and mef["motivo_no_disponible"]
        assert ck["regimen_sugerido"] == "comercial"


def test_documentos_segun_el_caso_del_vecino_van_aparte():
    mef = regimen(armar("bazar"), "mef")
    casos = [g["caso"] for g in mef["si_te_aplica"]]
    assert casos[:2] == [CK["casos"]["propietario"], CK["casos"]["arrendatario"]]
    arriendo = next(g for g in mef["si_te_aplica"] if g["caso"] == CK["casos"]["arrendatario"])
    assert "USO HABITACIONAL Y COMERCIAL".lower() in arriendo["items"][0]["detalle"].lower()
    assert not {d["id"] for d in mef["documentos"]} & {"dominio", "mef_arriendo", "sociedad"}


def test_cada_item_del_json_cita_una_lista_oficial_o_una_norma():
    patron = re.compile(r"MAIPU_0[12]|DL 3\.063|DS 977|DTO 102|Ley \d")
    for i in CK["items"]:
        assert patron.search(i["fuente"]), i["id"]


def test_texto_plano_incluye_los_documentos_del_regimen_sugerido():
    ck = armar("fuente_soda")
    lineas = informe._texto_checklist(ck)
    assert lineas[0].startswith("Microempresa familiar")
    assert any("Resolución sanitaria" in l for l in lineas) and any("Baños para clientes" in l for l in lineas)


def test_trabajadores_extranos_segun_el_reglamento():
    """DTO 102, art. 5: es extraño quien no vive en la casa, aunque sea pariente, y quien vive ahí sin serlo."""
    req = regimen(armar("bazar"), "mef")["requisitos"][1]
    assert "no viven en tu casa, aunque sean parientes" in req and "sin ser parientes" in req


def test_la_exencion_de_zonificacion_no_alcanza_a_los_alcoholes():
    for codigo in ("botilleria", "restaurante_con_alcohol"):
        mef = regimen(armar(codigo), "mef")
        assert mef["disponible"] and len(mef["excepciones"]) == 1 and "Ley de Alcoholes" in mef["excepciones"][0]


def test_giros_que_la_referencia_permite_con_otra_autorizacion_siguen_como_mef():
    """Decreto 3466 (Río Claro), art. 9: hoteles, gas y parafina, talleres con pistola pueden acogerse."""
    for codigo in ("hostal", "hotel", "motel", "gas_licuado", "taller_pintura_desabolladura", "vulcanizacion"):
        assert regimen(armar(codigo), "mef")["disponible"], codigo
    motivo = regimen(armar("bar"), "mef")["motivo_no_disponible"]
    assert "Probablemente" in motivo and "Rentas lo confirma" in motivo


def test_resolucion_sanitaria_de_maipu_01_cubre_todo_giro_comercial():
    """MAIPU_01, punto 4: resolución sanitaria o calificación, para el rubro que sea."""
    sanitarias = {"sanitaria_alimentos", "sanitaria_farmacia", "calificacion", "sanitaria_otra"}
    for codigo in GIROS:
        presentes = ids(regimen(armar(codigo), "comercial")) & sanitarias
        assert len(presentes) >= 1, codigo
        assert not ("sanitaria_otra" in presentes and len(presentes) > 1), codigo


def test_la_microempresa_familiar_no_ofrece_sociedades():
    """DTO 102, art. 2: personas naturales; el formulario de Rentas admite EIRL."""
    mef = regimen(armar("bazar"), "mef")
    casos = [g["caso"] for g in mef["si_te_aplica"]]
    assert CK["casos"]["eirl"] in casos and CK["casos"]["sociedad"] not in casos


def test_el_vecino_ve_nombres_de_listas_y_no_codigos():
    for r in armar("fuente_soda")["regimenes"]:
        textos = [r["fuente"]] + [d["fuente"] for d in r["documentos"] + r["condiciones"]]
        assert not any("MAIPU_" in t for t in textos)
    assert any("Requisitos de microempresa familiar de Rentas, punto 1" == d["fuente"].split(";")[0]
               for d in regimen(armar("bazar"), "mef")["documentos"])


def test_texto_plano_respeta_el_regimen_pedido():
    ck = armar("bazar")
    assert informe._texto_checklist(ck, "comercial")[0].startswith("Patente comercial")
    assert informe._texto_checklist(armar("bar"), "mef")[0].startswith("Patente comercial")
