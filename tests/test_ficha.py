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
ESCALAS = ("basico", "menor", "mediano", "mayor")


def _textos(r):
    return [a["texto"] for a in r["advertencias"] if a["tipo"] == "condicion"]


def _linea(zona, giro, escala=None):
    r = usos.evaluar(zona, giro, CFG, vialidad=VIA_OK, escala=escala)
    return P.linea_giro(r["estado"], r.get("detalle_escalas"), LENG, alcohol=GIROS[giro]["alcohol"], escala=escala,
                        textos=_textos(r))


def _zona(codigo):
    return P.describir_zona({"zona": {"estado": "OK", "ordenanza": codigo}}, CFG, LENG)


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


def test_las_escalas_usan_los_nombres_de_la_norma_y_del_formulario():
    # Árbitro, hallazgo 1: "mediano" no puede traducirse como otra palabra que el vecino lea como otra escala.
    for e in ESCALAS:
        assert P.NOMBRE_ESCALA[e] in LENG["escalas"][e], e


def test_las_condiciones_de_via_coinciden_con_las_jerarquias_de_vialidad():
    # Árbitro, hallazgo 3: el texto no puede ser más estricto ni más permisivo que vialidad.json.
    v = CFG["vialidad"]
    assert {"Servicio", "local"} <= set(v["jerarquias_estructurantes"])
    assert "avenida principal" not in LENG["condiciones"]["vialidad_estructurante"]
    assert "Plan Regulador" in LENG["condiciones"]["vialidad_estructurante"]
    for j in v["jerarquias_colectora_o_mayor"]:
        assert j.lower() in LENG["condiciones"]["colectora_o_mayor"]


# ——— Invariante: la traducción nunca suaviza el veredicto ———
@pytest.mark.parametrize("zona", list(CFG["usos_comercio"]["zonas"]))
def test_la_linea_vecinal_nunca_contradice_el_estado(zona):
    for codigo, g in GIROS.items():
        for escala in (None, *ESCALAS):
            r = usos.evaluar(zona, codigo, CFG, vialidad=VIA_OK, escala=escala)
            linea = P.linea_giro(r["estado"], r.get("detalle_escalas"), LENG, alcohol=g["alcohol"], escala=escala,
                                 textos=_textos(r))
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
                assert re.search(r"solo si|salvo|condición|no en escala", linea, re.IGNORECASE), ctx
            # Cada escala con condición o prohibida se nombra en la frase (sin tope abierto: hallazgo 2), salvo que
            # todas las escalas evaluadas compartan la misma condición ("Solo si…" las cubre a todas).
            det = r.get("detalle_escalas") or {}
            uniforme = len({(d["estado"], d.get("condicion")) for d in det.values()}) == 1
            for e, d in det.items():
                if d["estado"] != "SI" and not escala and r["estado"] == usos.CON_CONDICION and not uniforme:
                    assert LENG["escalas"][e] in linea, ctx


def test_alcohol_nunca_aparece_como_permitido():
    for zona in CFG["usos_comercio"]["zonas"]:
        for codigo in (c for c, g in GIROS.items() if g["alcohol"]):
            r = usos.evaluar(zona, codigo, CFG, vialidad=VIA_OK)
            linea = P.linea_giro(r["estado"], r.get("detalle_escalas"), LENG, alcohol=True)
            assert not linea.startswith("Se puede"), (zona, codigo, linea)


# ——— Frases concretas ———
def test_frases_tipicas():
    assert _linea("ZH-6", "bazar") == ("Se puede en escala básica (de barrio). En escala menor y mediana, solo si "
                                       "da a una vía del Plan Regulador.")
    assert _linea("ZH-6", "taller_mecanico") == "Solo si está en una calle de 20 metros o más de ancho."
    assert _linea("ZH-6", "discoteca") == LENG["lineas"]["prohibido"]
    assert _linea("ZH-6", "botilleria") == LENG["lineas"]["alcohol"]
    assert _linea("ZH-2", "bazar") == "Se puede, salvo en escala mediana."
    assert _linea("ZH-6", "bazar", "menor") == "En esa escala, solo si da a una vía del Plan Regulador."
    assert _linea("ZH-6", "bazar", "mayor") == LENG["lineas"]["no_tamano"]


def test_zh2_escala_mediana_no_se_lee_como_permitida():
    # Árbitro, hallazgo 1: ZH-2 prohíbe la escala mediana; la cabecera y la fila deben decir lo mismo.
    cab = _zona("ZH-2")["texto"]
    assert cab == "Barrio residencial. Comercio: escala básica (de barrio) y menor, sí; escala mediana y mayor, no."
    assert _linea("ZH-2", "bazar", "mediano") == LENG["lineas"]["no_tamano"]


def test_condicion_escrita_se_cita_en_la_fila():
    # Árbitro, hallazgo 5: ZC-1 peluquería solo al interior del mercado municipal.
    linea = _linea("ZC-1", "peluqueria")
    assert "mercado municipal" in linea and linea.count("condición especial") <= 1, linea


# ——— Descripción de la zona ———
@pytest.mark.parametrize("zona", list(CFG["usos_comercio"]["zonas"]))
def test_la_cabecera_nombra_cada_escala_con_su_estado(zona):
    d = _zona(zona)
    assert d["titulo"] and d["texto"].startswith(("Barrio residencial", "Sector céntrico")) and d["codigo"] == zona
    assert "{" not in d["texto"]
    escalas = CFG["usos_comercio"]["zonas"][zona]["comercio"]["escalas"]
    partes = d["texto"].split("Comercio: ", 1)[1].split(".")[0].split("; ")
    for e, estado in escalas.items():
        parte = [p for p in partes if LENG["escalas"][e] in p]
        assert len(parte) == 1, (zona, e, d["texto"])
        fin = {"NO": ", no", "SI": ", sí"}.get(estado)
        assert parte[0].endswith(fin) if fin else ", solo si " in parte[0], (zona, e, d["texto"])


def test_descripcion_sale_de_la_matriz():
    zh6 = _zona("ZH-6")
    assert zh6["titulo"] == "Maipú Norte - Sector Villas Pehuén"
    assert zh6["texto"] == ("Barrio residencial. Comercio: escala básica (de barrio), sí; escala menor y mediana, "
                            "solo si da a una vía del Plan Regulador; escala mayor, no.")
    assert "sin viviendas" in _zona("ZC-1")["texto"]
    zh1 = _zona("ZH-1")["texto"]
    assert "escala básica (de barrio)" in zh1 and ", no" in zh1
    # Árbitro, hallazgo 4: la condición escrita para todo el comercio de la zona se anuncia en la cabecera.
    assert LENG["zona"]["comercio_texto"] in zh1


def test_descripcion_sin_zona_borde_sin_gis_no_reconocida_y_especial():
    lz = LENG["zona"]
    assert P.describir_zona({"zona": {"estado": "OK"}}, CFG, LENG)["texto"] == lz["sin_zona"]
    assert P.describir_zona({"zona": {"estado": "NO_DISPONIBLE"}}, CFG, LENG)["texto"] == lz["sin_gis"]
    assert P.describir_zona({"zona": {"estado": "OK", "gis": ["ZH5", "ZH6"]}}, CFG, LENG)["texto"] == lz["varias"]
    # Árbitro, hallazgo 7: un código del GIS no reconocido no es "punto sin zona".
    assert P.describir_zona({"zona": {"estado": "OK", "gis": "ZX9", "ordenanza": None}}, CFG, LENG)["texto"] \
        == lz["no_reconocida"]
    ze = P.describir_zona({"zona": {"estado": "OK", "ordenanza": "ZE-1", "descripcion": "Zona Especial 1: Templo Votivo"}},
                          CFG, LENG)
    assert ze["titulo"] == "Templo Votivo" and ze["texto"] == lz["sin_matriz"]


def test_zona_no_reconocida_abre_el_detalle():
    vm = P.presentar(generar("bazar", zona=("ZX9", "Zona rara")), cfg=CFG)
    assert vm["ficha"]["lugar"]["titulo"] == LENG["zona"]["titulo_no_reconocida"] and vm["abrir_detalle"]


# ——— Chips del lugar ———
def test_chips_de_riesgo_y_de_via():
    inf = generar("bazar", vias=[via_a(25)], riesgos=[("AR-2", "SISMICO")])
    chips = P.chips_lugar(inf, LENG, None)
    assert {"texto": "Vía del Plan Regulador: por confirmar", "tono": "neutro", "tipo": "via"} in chips
    assert {"texto": LENG["riesgos_chip"]["AR-2"], "tono": "alerta", "tipo": "riesgo"} in chips
    assert {"texto": LENG["riesgos_chip"]["ninguno"], "tono": "ok", "tipo": "riesgo"} in P.chips_lugar(
        generar("bazar"), LENG, None)
    assert {"texto": LENG["riesgos_chip"]["sin_dato"], "tono": "neutro", "tipo": "riesgo"} in P.chips_lugar(
        generar("bazar", caidas=(6,)), LENG, None)


def test_frente_indicado_no_se_muestra_como_verificado():
    # Árbitro, hallazgo 8: con la vía declarada que no cumple, sigue visible la condición pendiente.
    inf = generar("taller_mecanico", vias=[via_a(25, ancho=15.0)], frente_via="T8P")
    chips = P.chips_lugar(inf, LENG, {"via": "Av. Pajaritos"})
    assert chips[0] == {"texto": "Indicaste que tu local da a Av. Pajaritos", "tono": "neutro", "tipo": "via"}
    assert any(c["texto"].startswith(LENG["condiciones_chip"]["via_20m"]) for c in chips)


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
    f = P.ficha(inf, CFG, informe.evaluar_otros(inf, CFG, list(GIROS)), None, LENG)
    assert len(f["otros"]) == LENG["max_otros"]
    assert f["principal"]["principal"] and f["principal"]["codigo"] == "bazar"
    assert {e["clase"] for e in f["leyenda"]} == {x["clase"] for x in [f["principal"], *f["otros"]]}


def test_alcohol_sin_zona_resuelta_no_culpa_a_la_norma_de_alcoholes():
    # Árbitro, hallazgo 6: si el GIS cayó, la causa no es la norma de alcoholes.
    f = P.ficha(generar("botilleria", caidas=(1, 2, 3, 4)), CFG, [], None, LENG)
    assert f["principal"]["linea"] == LENG["lineas"]["revisar"]
    f = P.ficha(generar("botilleria"), CFG, [], None, LENG)
    assert f["principal"]["linea"] == LENG["lineas"]["alcohol"]


def test_hospedaje_no_muestra_escala_en_el_nombre():
    # Árbitro, hallazgo 9: el motor no evalúa el hospedaje por escala.
    assert P.ficha(generar("hotel", escala="mayor"), CFG, [], None, LENG)["principal"]["nombre"] == "Hotel"
    assert P.ficha(generar("bazar", escala="menor"), CFG, [], None, LENG)["principal"]["nombre"] == "Bazar · escala menor"


def test_fila_principal_permitida_no_repite_se_puede():
    f = P.ficha(generar("peluqueria"), CFG, [], None, LENG)
    assert f["principal"]["titulo"] == "Se puede" and f["principal"]["linea"] == LENG["lineas"]["permitido_principal"]


def test_lector_de_pantalla_no_repite_el_estado():
    inf = generar("bazar", vias=[via_a(25)])
    f = P.ficha(inf, CFG, informe.evaluar_otros(inf, CFG, ["peluqueria", "botilleria"]), None, LENG)
    sr = {o["codigo"]: o["sr"] for o in f["otros"]}
    assert sr["peluqueria"] == "" and sr["botilleria"] == "Por revisar."


def test_dato_ambiguo_del_gis_se_avisa_en_la_cabecera_y_abre_el_detalle():
    vm = P.presentar(generar("peluqueria", zona=("ZH10", "Zona Habitacional 9: El Porvenir")), cfg=CFG)
    assert {"texto": LENG["zona"]["dato_por_corregir"], "tono": "alerta", "tipo": "dato"} in vm["ficha"]["chips"]
    assert vm["abrir_detalle"]


def test_un_riesgo_no_abre_el_detalle_tecnico():
    assert not P.presentar(generar("bazar", riesgos=[("AR-2", "SISMICO")]), cfg=CFG)["abrir_detalle"]


# ——— Vista web (comercio cercano y checklist leen la base) ———
@pytest.fixture
def web(monkeypatch, db):
    monkeypatch.setattr(api_views, "cliente_gis", lambda: gis_falso(vias=[via_a(25)], riesgos=[("AR-2", "SISMICO")]))
    return Client()


def test_panel_muestra_la_ficha_del_lugar(web):
    html = web.get("/panel/informe/", {"lat": LAT, "lon": LON, "giro": "bazar"}).content.decode()
    assert "Maipú Norte - Sector Villas Pehuén" in html and "¿Qué se puede abrir aquí?" in html
    assert LENG["ficha"]["marca_principal"] in html and "Se puede en escala básica (de barrio)" in html
    assert LENG["riesgos_chip"]["AR-2"] in html and "Vía del Plan Regulador: por confirmar" in html
    # El aviso legal va antes del resultado y no dentro de un acordeón.
    assert html.index("Informe orientativo.") < html.index("¿Qué se puede abrir aquí?")
    botones = re.findall(r'data-cambiar-giro="([a-z_]+)"', html)
    assert botones and "bazar" not in botones and len(botones) <= LENG["max_otros"]
    assert set(botones) <= set(LENG["giros_referencia"])
    # El detalle técnico sigue disponible para quien quiera verificar.
    assert "Detalle técnico" in html and "Art. 34, ZH-6" in html and "Compatible con condiciones" in html
    assert 'aria-label="' not in re.search(r'<summary>.*?Detalle técnico.*?</summary>', html, re.S).group(0)


def test_panel_sin_zona_no_ofrece_otros_giros(monkeypatch, db):
    monkeypatch.setattr(api_views, "cliente_gis", lambda: gis_falso(zona=None))
    html = Client().get("/panel/informe/", {"lat": LAT, "lon": LON, "giro": "bazar"}).content.decode()
    assert LENG["zona"]["sin_zona"] in html and "data-cambiar-giro" not in html
    assert "Hay que revisarlo" in html


def test_panel_con_frente_confirmado(web):
    html = web.get("/panel/informe/", {"lat": LAT, "lon": LON, "giro": "bazar", "frente_via": "T8P"}).content.decode()
    assert "Indicaste que tu local da a Av. Pajaritos" in html and "Se puede</p>" in html
