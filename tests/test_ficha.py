"""Ficha del lugar (opción C): lenguaje vecinal fiel a la norma, otros giros en el mismo punto y vista web."""
import json
import re

import pytest
from django.test import Client

from api import views as api_views
from nucleo import informe, prc_config, usos
from web import presentacion as P

from .test_informe import LAT, LON, generar, gis_falso, via_a

CFG = prc_config.leer()
LENG = P.lenguaje()
GIROS = CFG["giros"]["giros"]
VIA_OK = {"estado": "OK", "frente": [], "cercanas": []}


# ——— Configuración ———
def test_giros_de_referencia_existen_y_no_se_repiten():
    ref = LENG["giros_referencia"]
    assert ref and len(ref) == len(set(ref))
    assert set(ref) <= set(GIROS)


def test_hay_texto_para_cada_condicion_de_la_matriz():
    usadas = set()
    for z in CFG["usos_comercio"]["zonas"].values():
        for bloque in (z.get("comercio"), z.get("servicios_artesanales")):
            if not bloque:
                continue
            usadas |= set((bloque.get("condicion_escala") or {}).values())
            usadas |= set((bloque.get("condicion_giro") or {}).values())
            if bloque.get("condicion_talleres"):
                usadas.add(bloque["condicion_talleres"])
    assert usadas <= set(LENG["condiciones"]), usadas - set(LENG["condiciones"])


def test_hay_texto_corto_para_cada_tipo_de_riesgo():
    tipos = set(json.loads((prc_config.DIR_DEFAULT / "riesgos.json").read_text(encoding="utf-8"))["tipos"])
    assert tipos <= set(LENG["riesgos_chip"])


def test_cada_estado_tiene_titulo_y_texto_corto():
    for e in (usos.PERMITIDO, usos.CON_CONDICION, usos.NO_PERMITIDO, usos.NO_CONCLUYENTE):
        assert LENG["estados"][e]["titulo"] and LENG["estados"][e]["corto"]


# ——— Invariante: la traducción nunca suaviza el veredicto ———
@pytest.mark.parametrize("zona", list(CFG["usos_comercio"]["zonas"]))
def test_la_linea_vecinal_nunca_contradice_el_estado(zona):
    for codigo, g in GIROS.items():
        for escala in (None, "basico", "menor", "mediano", "mayor"):
            r = usos.evaluar(zona, codigo, CFG, vialidad=VIA_OK, escala=escala)
            linea = P.linea_giro(r["estado"], r.get("detalle_escalas"), LENG, alcohol=g["alcohol"], escala=escala,
                                 condicion_texto=any(a["tipo"] == "condicion" for a in r["advertencias"]))
            ctx = f"{zona} {codigo} {escala}: {r['estado']} -> {linea!r}"
            assert linea and "{" not in linea, ctx
            if r["estado"] == usos.PERMITIDO:
                assert linea == LENG["lineas"]["permitido"], ctx
            else:
                assert linea != LENG["lineas"]["permitido"], ctx
            if r["estado"] == usos.NO_PERMITIDO:
                assert linea.startswith("No se permite"), ctx
            if r["estado"] == usos.NO_CONCLUYENTE:
                assert not linea.startswith("Se puede"), ctx
            if r["estado"] == usos.CON_CONDICION:
                assert re.search(r"solo si|salvo|condición|no se permiten", linea, re.IGNORECASE), ctx


def test_alcohol_nunca_aparece_como_permitido():
    for zona in CFG["usos_comercio"]["zonas"]:
        for codigo in (c for c, g in GIROS.items() if g["alcohol"]):
            r = usos.evaluar(zona, codigo, CFG, vialidad=VIA_OK)
            linea = P.linea_giro(r["estado"], r.get("detalle_escalas"), LENG, alcohol=True)
            assert not linea.startswith("Se puede"), (zona, codigo, linea)


# ——— Frases concretas ———
def _linea(zona, giro, escala=None):
    r = usos.evaluar(zona, giro, CFG, vialidad=VIA_OK, escala=escala)
    return P.linea_giro(r["estado"], r.get("detalle_escalas"), LENG, alcohol=GIROS[giro]["alcohol"], escala=escala,
                        condicion_texto=any(a["tipo"] == "condicion" for a in r["advertencias"]))


def test_frases_tipicas():
    assert _linea("ZH-6", "bazar") == "Se puede si es un local de barrio. Más grande, solo si da a una avenida principal."
    assert _linea("ZH-6", "taller_mecanico") == "Solo si el local está en una calle de 20 metros o más de ancho."
    assert _linea("ZH-6", "discoteca") == LENG["lineas"]["prohibido"]
    assert _linea("ZH-6", "botilleria") == LENG["lineas"]["alcohol"]
    assert _linea("ZH-2", "bazar") == "Se puede, salvo locales grandes."
    assert _linea("ZH-6", "bazar", "menor") == "En ese tamaño, solo si el local da a una avenida principal."
    assert _linea("ZH-6", "bazar", "mayor") == LENG["lineas"]["no_tamano"]


def test_negativos_con_ni_y_sin_condicion_repetida():
    assert P._locales(["basico", "mayor"], LENG, "ni") == "locales de barrio ni muy grandes"
    linea = _linea("ZC-1", "peluqueria")
    assert linea.count("condición especial") <= 1, linea


# ——— Descripción de la zona ———
@pytest.mark.parametrize("zona", list(CFG["usos_comercio"]["zonas"]))
def test_toda_zona_con_matriz_tiene_titulo_y_descripcion(zona):
    d = P.describir_zona({"zona": {"estado": "OK", "ordenanza": zona}}, CFG, LENG)
    assert d["titulo"] and d["texto"].startswith(("Barrio residencial", "Sector céntrico")) and d["codigo"] == zona
    assert "{" not in d["texto"]


def test_descripcion_solo_habla_de_las_escalas_evaluadas():
    # Sin tamaño declarado se evalúan básico, menor y mediano: la descripción no menciona la escala mayor.
    for zona in CFG["usos_comercio"]["zonas"]:
        assert "muy grandes" not in P.describir_zona({"zona": {"ordenanza": zona}}, CFG, LENG)["texto"], zona


def test_descripcion_sale_de_la_matriz():
    zh6 = P.describir_zona({"zona": {"ordenanza": "ZH-6"}}, CFG, LENG)
    assert zh6["titulo"] == "Maipú Norte - Sector Villas Pehuén"
    assert "se permiten locales de barrio." in zh6["texto"] and "avenida principal" in zh6["texto"]
    assert "sin viviendas" in P.describir_zona({"zona": {"ordenanza": "ZC-1"}}, CFG, LENG)["texto"]
    # ZH-1 no permite la escala básica: no se puede describir como "comercio de barrio".
    zh1 = P.describir_zona({"zona": {"ordenanza": "ZH-1"}}, CFG, LENG)["texto"]
    assert "No se permiten locales de barrio" in zh1


def test_descripcion_sin_zona_borde_sin_gis_y_zona_especial():
    lz = LENG["zona"]
    assert P.describir_zona({"zona": {"estado": "OK"}}, CFG, LENG)["texto"] == lz["sin_zona"]
    assert P.describir_zona({"zona": {"estado": "NO_DISPONIBLE"}}, CFG, LENG)["texto"] == lz["sin_gis"]
    assert P.describir_zona({"zona": {"estado": "OK", "gis": ["ZH5", "ZH6"]}}, CFG, LENG)["texto"] == lz["varias"]
    ze = P.describir_zona({"zona": {"estado": "OK", "ordenanza": "ZE-1", "descripcion": "Zona Especial 1: Templo Votivo"}},
                          CFG, LENG)
    assert ze["titulo"] == "Templo Votivo" and ze["texto"] == lz["sin_matriz"]


# ——— Chips del lugar ———
def test_chips_de_riesgo_y_de_via():
    inf = generar("bazar", vias=[via_a(25)], riesgos=[("AR-2", "SISMICO")])
    chips = P.chips_lugar(inf, LENG, None)
    textos = [c["texto"] for c in chips]
    assert "Avenida principal: por confirmar" in textos
    assert {"texto": LENG["riesgos_chip"]["AR-2"], "tono": "alerta"} in chips
    sin_riesgo = P.chips_lugar(generar("bazar"), LENG, None)
    assert {"texto": LENG["riesgos_chip"]["ninguno"], "tono": "ok"} in sin_riesgo
    caido = P.chips_lugar(generar("bazar", caidas=(6,)), LENG, None)
    assert {"texto": LENG["riesgos_chip"]["sin_dato"], "tono": "neutro"} in caido
    confirmado = P.chips_lugar(inf, LENG, {"via": "Av. Pajaritos"})
    assert confirmado[0] == {"texto": "Tu local da a Av. Pajaritos", "tono": "ok"}


# ——— Otros giros en el mismo punto ———
def test_evaluar_otros_excluye_el_elegido_y_desconocidos():
    inf = generar("bazar", vias=[via_a(25)])
    otros = informe.evaluar_otros(inf, CFG, ["bazar", "no_existe", "peluqueria", "peluqueria", "discoteca"])
    assert [o["codigo"] for o in otros] == ["peluqueria", "discoteca"]
    assert otros[1]["estado"] == usos.NO_PERMITIDO


def test_evaluar_otros_usa_el_frente_confirmado():
    sin = {o["codigo"]: o["estado"] for o in informe.evaluar_otros(generar("peluqueria", vias=[via_a(25)]), CFG,
                                                                    ["abarrotes"])}
    con = {o["codigo"]: o["estado"] for o in informe.evaluar_otros(
        generar("peluqueria", vias=[via_a(25)], frente_via="T8P"), CFG, ["abarrotes"])}
    assert sin["abarrotes"] == usos.CON_CONDICION and con["abarrotes"] == usos.PERMITIDO


def test_evaluar_otros_respeta_la_zona_ambigua():
    inf = generar("peluqueria", zona=("ZH10", "Zona Habitacional 9: El Porvenir"))
    otros = {o["codigo"]: o for o in informe.evaluar_otros(inf, CFG, list(GIROS))}
    for codigo, o in otros.items():
        a = usos.evaluar("ZH-10", codigo, CFG, vialidad=inf["vialidad"])["estado"]
        b = usos.evaluar("ZH-9", codigo, CFG, vialidad=inf["vialidad"])["estado"]
        if a != b:
            assert o["estado"] == usos.NO_CONCLUYENTE and o["ambigua"], codigo
        else:
            assert o["estado"] == a, codigo


def test_evaluar_otros_vacio_sin_zona_unica_con_matriz():
    assert informe.evaluar_otros(generar("bazar", zona=None), CFG, ["abarrotes"]) == []
    assert informe.evaluar_otros(generar("bazar", zona=("ZE1", "Zona Especial 1: Templo Votivo"), capa_zona=1), CFG,
                                 ["abarrotes"]) == []
    assert informe.evaluar_otros(generar("bazar", caidas=(1, 2, 3, 4)), CFG, ["abarrotes"]) == []


def test_la_ficha_limita_las_filas_y_arma_la_leyenda():
    inf = generar("bazar", vias=[via_a(25)])
    otros = informe.evaluar_otros(inf, CFG, list(GIROS))
    f = P.ficha(inf, CFG, otros, None, LENG)
    assert len(f["otros"]) == LENG["max_otros"]
    assert f["principal"]["principal"] and f["principal"]["codigo"] == "bazar"
    usados = {x["clase"] for x in [f["principal"], *f["otros"]]}
    assert {e["clase"] for e in f["leyenda"]} == usados


# ——— Vista web (comercio cercano y checklist leen la base) ———
@pytest.fixture
def web(monkeypatch, db):
    monkeypatch.setattr(api_views, "cliente_gis", lambda: gis_falso(vias=[via_a(25)], riesgos=[("AR-2", "SISMICO")]))
    return Client()


def test_panel_muestra_la_ficha_del_lugar(web):
    html = web.get("/panel/informe/", {"lat": LAT, "lon": LON, "giro": "bazar"}).content.decode()
    assert "Maipú Norte - Sector Villas Pehuén" in html and "¿Qué se puede abrir aquí?" in html
    assert "Lo que buscas" in html and "Se puede si es un local de barrio" in html
    assert LENG["riesgos_chip"]["AR-2"] in html and "Avenida principal: por confirmar" in html
    # El aviso legal va antes del resultado y no dentro de un acordeón.
    assert html.index("Informe orientativo.") < html.index("¿Qué se puede abrir aquí?")
    botones = re.findall(r'data-cambiar-giro="([a-z_]+)"', html)
    assert botones and "bazar" not in botones and len(botones) <= LENG["max_otros"]
    assert set(botones) <= set(LENG["giros_referencia"])
    # El detalle técnico sigue disponible para quien quiera verificar.
    assert "Detalle técnico" in html and "Art. 34, ZH-6" in html and "Compatible con condiciones" in html


def test_panel_sin_zona_no_ofrece_otros_giros(monkeypatch, db):
    monkeypatch.setattr(api_views, "cliente_gis", lambda: gis_falso(zona=None))
    html = Client().get("/panel/informe/", {"lat": LAT, "lon": LON, "giro": "bazar"}).content.decode()
    assert LENG["zona"]["sin_zona"] in html and "data-cambiar-giro" not in html
    assert "Hay que revisarlo" in html


def test_panel_con_frente_confirmado(web):
    html = web.get("/panel/informe/", {"lat": LAT, "lon": LON, "giro": "bazar", "frente_via": "T8P"}).content.decode()
    assert "Tu local da a Av. Pajaritos" in html and "Se puede</p>" in html


# ——— Correcciones de la revisión adversarial ———
def test_fila_principal_permitida_no_repite_se_puede():
    f = P.ficha(generar("peluqueria"), CFG, [], None, LENG)
    assert f["principal"]["titulo"] == "Se puede" and f["principal"]["linea"] == LENG["lineas"]["permitido_principal"]


def test_lector_de_pantalla_no_repite_el_estado():
    inf = generar("bazar", vias=[via_a(25)])
    f = P.ficha(inf, CFG, informe.evaluar_otros(inf, CFG, ["peluqueria", "botilleria"]), None, LENG)
    sr = {o["codigo"]: o["sr"] for o in f["otros"]}
    assert sr["peluqueria"] == "" and sr["botilleria"] == "Por revisar."


def test_dato_ambiguo_del_gis_se_avisa_en_la_cabecera_y_abre_el_detalle():
    inf = generar("peluqueria", zona=("ZH10", "Zona Habitacional 9: El Porvenir"))
    vm = P.presentar(inf, cfg=CFG)
    assert {"texto": LENG["zona"]["dato_por_corregir"], "tono": "alerta"} in vm["ficha"]["chips"]
    assert vm["abrir_detalle"]


def test_un_riesgo_no_abre_el_detalle_tecnico():
    vm = P.presentar(generar("bazar", riesgos=[("AR-2", "SISMICO")]), cfg=CFG)
    assert not vm["abrir_detalle"]
