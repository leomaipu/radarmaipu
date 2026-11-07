import copy
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import api, informe, prc_config, prc_gis, usos
from app.privacy import PERSONAL_FIELDS

CFG = prc_config.leer()
LAT, LON = -33.48, -70.76


def gis_falso(zona=("ZH6", "Zona Habitacional 6: Maipú Norte - Sector Villas Pehuén"), capa_zona=3,
              vias=(), riesgos=(), bleve=None, caidas=(), registro=None):
    """MockTransport que imita /MapServer/<capa>/query. `caidas`: capas que responden 500."""
    def handler(request: httpx.Request) -> httpx.Response:
        capa = int(request.url.path.rstrip("/").split("/")[-2])
        params = request.url.params
        if registro is not None:
            registro.append((capa, dict(params)))
        if capa in caidas:
            return httpx.Response(500)
        feats = []
        if capa == capa_zona and zona and "distance" not in params:
            feats = [{"attributes": {"ZONA": zona[0], "DESCRIPCION": zona[1]}}]
        elif capa == 0:
            feats = [{"attributes": v["attributes"], "geometry": v["geometry"]} for v in vias]
        elif capa == 6:
            feats = [{"attributes": {"TIPO_DE_AR": t, "DESCRIPCIO": d}} for t, d in riesgos]
        elif capa == 5 and bleve:
            feats = [{"attributes": {"BUFF_DIST": bleve}}]
        return httpx.Response(200, json={"features": feats})
    return httpx.Client(transport=httpx.MockTransport(handler))


def via_a(metros_norte, jerarquia="Troncal", ancho=30.0, nombre="Av. Pajaritos", codigo="T8P",
          observacion="EXISTENTE", ancho_prop=None):
    """Polilínea este-oeste a `metros_norte` metros del punto de prueba."""
    dlat = metros_norte / 111_195
    return {"attributes": {"JERARQUIA": jerarquia, "VIA": nombre, "CODIGO": codigo, "ANCHO_EXIS": str(ancho),
                           "ANCHO_PROP": ancho if ancho_prop is None else ancho_prop, "OBSERVACIO": observacion},
            "geometry": {"paths": [[[LON - 0.001, LAT + dlat], [LON + 0.001, LAT + dlat]]]}}


def generar(giro="bazar", cfg=CFG, escala=None, frente_via=None, **kw):
    with gis_falso(**kw) as c:
        gis = prc_gis.consultar_punto(c, LON, LAT, cfg)
    return informe.generar(LAT, LON, giro, cfg, gis, escala=escala, ahora="2026-11-09T10:00:00-03:00",
                           frente_via=frente_via)


def con_mod4(vigente: bool) -> dict:
    cfg = copy.deepcopy(CFG)
    cfg["modificaciones"]["MOD_4"]["vigente"] = vigente
    return cfg


def test_informe_tiene_la_forma_del_documento():
    inf = generar()
    for clave in ("version_informe", "fecha_generacion", "punto", "zona", "giro", "resultado", "advertencias",
                  "fuentes", "checklist_rentas", "aviso"):
        assert clave in inf
    assert inf["zona"] == {"estado": "OK", "gis": "ZH6", "ordenanza": "ZH-6",
                           "descripcion": "Zona Habitacional 6: Maipú Norte - Sector Villas Pehuén"}
    assert inf["giro"]["clase_ordenanza"] == "2.2 Comercio"
    assert inf["resultado"]["articulo"] == "Art. 34, ZH-6"
    assert inf["checklist_rentas"] == {"estado": "pendiente_lista_oficial", "items": []}
    assert inf["aviso"] == informe.AVISO
    assert any(f.get("pagina") == 27 for f in inf["fuentes"])


def test_frente_por_proximidad_no_habilita_pero_lo_sugiere():
    inf = generar(vias=[via_a(25)])  # 25 m del eje de una vía de 30 m: 15 + 20 de margen
    assert inf["resultado"]["estado"] == usos.CON_CONDICION
    assert inf["vialidad"]["frente"][0]["via"] == "Av. Pajaritos"
    assert any("frente_via=T8P" in a["texto"] for a in inf["advertencias"])


def test_frente_declarado_sobre_via_cercana_habilita():
    inf = generar(vias=[via_a(25)], frente_via="t8p")
    assert inf["resultado"]["estado"] == usos.PERMITIDO
    assert any("declarado por el usuario" in a["texto"] for a in inf["advertencias"])


def test_frente_declarado_que_no_esta_cerca_se_ignora():
    inf = generar(vias=[via_a(25)], frente_via="X99")
    assert inf["resultado"]["estado"] == usos.CON_CONDICION
    assert any("no se consideró" in a["texto"] for a in inf["advertencias"])


@pytest.mark.parametrize("obs", ["APERTURA", "Aeertura", "eliminado 59 etapa 2"])
def test_tramo_no_construido_no_es_frente_ni_se_puede_declarar(obs):
    inf = generar(vias=[via_a(10, observacion=obs, codigo="S9M")], frente_via="S9M")
    assert inf["resultado"]["estado"] == usos.CON_CONDICION
    assert inf["vialidad"]["frente"] == []
    assert inf["vialidad"]["cercanas"][0]["excluida"]


def test_via_20m_usa_ancho_existente_no_el_propuesto():
    inf = generar("taller_mecanico", zona=("ZH5", "Zona Habitacional 5"),
                  vias=[via_a(5, ancho=12, ancho_prop=30.0, jerarquia="Colectora")], frente_via="T8P")
    assert inf["resultado"]["estado"] == usos.CON_CONDICION
    inf = generar("taller_mecanico", zona=("ZH5", "Zona Habitacional 5"),
                  vias=[via_a(5, ancho=24, jerarquia="Colectora")], frente_via="T8P")
    assert inf["resultado"]["estado"] == usos.PERMITIDO


def test_jerarquia_nula_o_fuera_del_limite_no_es_frente():
    for jer in (None, "Fuera Límite Urbano"):
        inf = generar(vias=[via_a(5, jerarquia=jer)], frente_via="T8P")
        assert inf["resultado"]["estado"] == usos.CON_CONDICION


def test_via_cercana_pero_sin_frente_no_habilita():
    inf = generar(vias=[via_a(38)])  # dentro del radio de 40 m, fuera de 15 + 20
    assert inf["resultado"]["estado"] == usos.CON_CONDICION
    assert inf["vialidad"]["frente"] == []


# 7. Mod. 4 no vigente
def test_mod4_no_vigente_usa_alturas_base_y_advierte():
    inf = generar(cfg=con_mod4(False), zona=("ZH8", "Zona Habitacional 8: Corredores"))
    assert inf["edificacion"]["altura_maxima"]["equip_todas_y_multifamiliar"] == "Libre según rasantes"
    assert inf["edificacion"]["modificacion_4"] == "no_vigente"
    assert any("vigencia por confirmar" in a["texto"] for a in inf["advertencias"])


# 8. Mod. 4 vigente
def test_mod4_vigente_cambia_altura_zh8_y_prohibe_apart_hotel():
    cfg = con_mod4(True)
    inf = generar("apart_hotel", cfg=cfg, zona=("ZH8", "Zona Habitacional 8: Corredores"))
    assert inf["edificacion"]["altura_maxima"]["equip_todas_y_multifamiliar"] == "9 pisos / 27 m"
    assert inf["edificacion"]["altura_maxima"]["vivienda_unifamiliar"] == "9 m"
    assert inf["resultado"]["estado"] == usos.NO_PERMITIDO
    assert next(f for f in inf["fuentes"] if f["titulo"] == "Modificación N°4")["vigente"] is True


# 9. ZC-2 "solo continua" no cambia
def test_zc2_solo_continua_sin_cambio_con_mod4():
    inf = generar(cfg=con_mod4(True), zona=("ZC2", "Centro Comercial"), capa_zona=2)
    alturas = inf["edificacion"]["altura_maxima"]
    assert alturas["solo_continua"] == "18 m"
    assert alturas["continua_y_aislada"] == "4 pisos / 12 m"


# 10. Capa no disponible
def test_vialidad_caida_queda_no_disponible_sin_excepcion():
    inf = generar(caidas={0})
    assert inf["secciones"]["vialidad"] == "NO_DISPONIBLE"
    assert inf["resultado"]["estado"] == usos.CON_CONDICION
    assert any("no disponible" in a["texto"] for a in inf["advertencias"])


def test_todas_las_capas_caidas_dan_no_concluyente():
    inf = generar(caidas={0, 1, 2, 3, 4, 5, 6})
    assert inf["secciones"] == {"zona": "NO_DISPONIBLE", "vialidad": "NO_DISPONIBLE", "riesgos": "NO_DISPONIBLE"}
    assert inf["resultado"]["estado"] == usos.NO_CONCLUYENTE
    assert inf["aviso"] == informe.AVISO


def test_capa_de_zona_caida_no_se_confunde_con_fuera_de_zona():
    inf = generar(zona=None, caidas={2})
    assert inf["zona"]["estado"] == "NO_DISPONIBLE"
    assert "fuera de zona" not in inf["resultado"]["motivo"].lower()


def test_capa_de_zonas_especiales_caida_no_permite_concluir():
    # Existe al menos un polígono ZE-8 sobre ZH-6: sin la capa 1 no se puede descartar.
    inf = generar(caidas={1}, vias=[via_a(25)], frente_via="T8P")
    assert inf["zona"]["estado"] == "NO_DISPONIBLE" and inf["zona"]["capas_fallidas"] == [1]
    assert inf["resultado"]["estado"] == usos.NO_CONCLUYENTE


@pytest.mark.parametrize("cuerpo", [
    {"features": None},
    {"features": [{"attributes": None, "geometry": None}]},
    {"features": [{"attributes": {"ZONA": None, "JERARQUIA": 7, "VIA": 12, "ANCHO_EXIS": 3.5,
                                  "BUFF_DIST": "800", "TIPO_DE_AR": None}, "geometry": {"paths": [[["x", 1]]]}}]},
    {"features": [None, 5, "x"]},
    {"error": "texto"},
    {"features": "no lista"},
    [1, 2, 3],
])
def test_respuestas_gis_malformadas_no_rompen(cuerpo):
    def handler(request):
        return httpx.Response(200, json=cuerpo)
    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        gis = prc_gis.consultar_punto(c, LON, LAT, CFG)
    inf = informe.generar(LAT, LON, "bazar", CFG, gis)
    assert inf["resultado"]["estado"] in (usos.NO_CONCLUYENTE, usos.CON_CONDICION)
    informe.texto(inf)


def test_bleve_con_distancia_en_texto():
    inf = generar(bleve="800")
    assert any("800" in a["texto"] for a in inf["advertencias"] if a["tipo"] == "riesgo")


def test_art32_no_aparece_donde_la_vivienda_esta_prohibida():
    inf = generar(zona=("ZC1", "Centro Cívico"), capa_zona=2, escala="mayor")
    assert inf["resultado"]["estado"] == usos.NO_PERMITIDO
    assert not any("art. 32" in a["texto"] for a in inf["advertencias"])


def test_error_arcgis_en_json_cuenta_como_caida():
    def handler(request):
        return httpx.Response(200, json={"error": {"code": 400, "message": "Failed to execute query."}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        gis = prc_gis.consultar_punto(c, LON, LAT, CFG)
    assert gis["zona"]["estado"] == gis["vialidad"]["estado"] == gis["riesgos"]["estado"] == "NO_DISPONIBLE"


# 12. Punto sin zona
def test_punto_sin_zona_sugiere_zonas_cercanas():
    inf = generar(zona=None)
    assert inf["resultado"]["estado"] == usos.NO_CONCLUYENTE
    assert "fuera de zona normativa" in inf["resultado"]["motivo"].lower()
    assert inf["edificacion"] is None


def test_registro_gis_inconsistente_zh10_con_descripcion_de_zh9():
    inf = generar(zona=("ZH10", "Zona Habitacional 9: El Porvenir"))
    assert any(a["tipo"] == "calidad_dato" for a in inf["advertencias"])
    # ZH-9 y ZH-10 tienen la misma regla para bazar: el resultado se mantiene.
    assert inf["resultado"]["estado"] == usos.PERMITIDO


def test_registro_inconsistente_con_resultados_distintos_es_no_concluyente():
    inf = generar("bazar", escala="basico", zona=("ZH6", "Zona Habitacional 1: Santa Ana de Chena"))
    assert inf["resultado"]["estado"] == usos.NO_CONCLUYENTE  # ZH-6 sí, ZH-1 no admite escala básico


def test_riesgos_y_bleve_se_agregan_como_advertencias_sin_cambiar_estado():
    base = generar()["resultado"]["estado"]
    inf = generar(riesgos=[("AR-1A", "RECURRENTEMENTE INUNDABLES")], bleve=400.0)
    assert inf["resultado"]["estado"] == base
    textos = " ".join(a["texto"] for a in inf["advertencias"] if a["tipo"] == "riesgo")
    assert "AR-1A" in textos and "400" in textos


def test_consultas_usan_lista_blanca_de_campos_y_punto_wgs84():
    registro = []
    generar(registro=registro)
    capas = {c["id"]: c["outFields"] for c in CFG["zonas"]["capas"]["zonas"]}
    for capa, params in registro:
        assert params["outFields"] != "*" and "*" not in params["outFields"]
        assert params["inSR"] == "4326" and params["geometryType"] == "esriGeometryPoint"
        if capa in capas and "distance" not in params:
            assert params["outFields"] == capas[capa]


def test_texto_muestra_aviso_y_tres_bloques():
    t = informe.texto(generar())
    assert t.startswith("AVISO: " + informe.AVISO)
    assert "1. ZONA" in t and "2. RESULTADO DEL GIRO" in t and "3. ADVERTENCIAS" in t
    assert t.index("1. ZONA") < t.index("2. RESULTADO DEL GIRO") < t.index("3. ADVERTENCIAS")


# API
@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.setattr(api, "cliente_gis", lambda: gis_falso(vias=[via_a(25)], riesgos=[("AR-2", "SISMICO")]))
    return TestClient(api.app)


def test_api_informe_json_y_texto(cliente):
    r = cliente.get("/api/informe", params={"lat": LAT, "lon": LON, "giro": "bazar"})
    assert r.status_code == 200 and r.json()["resultado"]["estado"] == usos.CON_CONDICION
    r = cliente.get("/api/informe", params={"lat": LAT, "lon": LON, "giro": "bazar", "frente_via": "T8P"})
    assert r.status_code == 200 and r.json()["resultado"]["estado"] == usos.PERMITIDO
    assert cliente.get("/api/informe", params={"lat": LAT, "lon": LON, "giro": "bazar",
                                               "frente_via": "a b;"}).status_code == 422
    r = cliente.get("/api/informe", params={"lat": LAT, "lon": LON, "giro": "bazar", "formato": "texto"})
    assert r.status_code == 200 and r.text.startswith("AVISO:")


def test_api_rechaza_giro_libre_y_escala_invalida(cliente):
    assert cliente.get("/api/informe", params={"lat": LAT, "lon": LON, "giro": "venta de cosas"}).status_code == 422
    assert cliente.get("/api/informe", params={"lat": LAT, "lon": LON, "giro": "bazar",
                                               "escala": "enorme"}).status_code == 422


def test_api_giros_y_health(cliente):
    giros = cliente.get("/api/giros").json()["resultados"]
    assert {"codigo": "bazar", "nombre": "Bazar", "clase_ordenanza": "2.2 Comercio",
            "requiere_ordenanza_alcoholes": False} in giros
    cliente.get("/api/informe", params={"lat": LAT, "lon": LON, "giro": "bazar"})
    prc = cliente.get("/api/health").json()["prc"]
    assert prc["config"] == "ok" and prc["capas"]["capa_3"]["estado"] == "OK"


# 11. Privacidad
def _claves(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _claves(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _claves(v)


def test_privacidad_ninguna_respuesta_trae_datos_personales(cliente):
    respuestas = [cliente.get("/api/informe", params={"lat": LAT, "lon": LON, "giro": g}).json()
                  for g in ("bazar", "botilleria", "taller_mecanico", "apart_hotel")]
    respuestas.append(cliente.get("/api/giros").json())
    prohibidas = {k.lower() for k in PERSONAL_FIELDS} | {"rut", "razon_social", "representante", "direc_nego"}
    for resp in respuestas:
        assert not {k.lower() for k in _claves(resp)} & prohibidas
        cuerpo = json.dumps(resp).lower()
        assert "rut_negoci" not in cuerpo and "razon_soci" not in cuerpo and "direc_nego" not in cuerpo


# Pruebas en vivo: correr desde la red municipal o el PC del equipo con `pytest -m gis`.
@pytest.mark.gis
def test_gis_en_vivo_zona_zh6_y_vialidad():
    with httpx.Client() as c:
        gis = prc_gis.consultar_punto(c, -70.7600, -33.4800, CFG)
    assert gis["zona"]["estado"] == "OK"
    assert prc_config.normalizar_zona(gis["zona"]["hits"][0]["gis"], CFG) == "ZH-6"
    assert gis["vialidad"]["estado"] == "OK" and gis["riesgos"]["estado"] == "OK"


@pytest.mark.gis
def test_gis_en_vivo_punto_del_documento_cae_en_area_verde():
    with httpx.Client() as c:
        gis = prc_gis.consultar_punto(c, -70.7535, -33.5102, CFG)
    inf = informe.generar(-33.5102, -70.7535, "bazar", CFG, gis)
    assert inf["zona"]["ordenanza"] == "ZE-8"
    assert inf["resultado"]["estado"] == usos.NO_CONCLUYENTE


def test_frente_declarado_debe_ser_frente_probable():
    inf = generar(vias=[via_a(38, jerarquia="local", ancho=0)], frente_via="T8P")  # local sin ancho a 38 m
    assert inf["resultado"]["estado"] == usos.CON_CONDICION


def test_frente_declarado_en_via_local_advierte_pendiente_dom():
    inf = generar(vias=[via_a(5, jerarquia="local", ancho=12)], frente_via="T8P")
    assert any("pendiente de confirmar con la DOM" in a["texto"] for a in inf["advertencias"])


@pytest.mark.parametrize("cuerpo", [{}, {"features": None}, {"features": [{"attributes": {"ZONA": None}}]}])
def test_zona_sin_codigo_o_sin_features_es_no_disponible(cuerpo):
    def handler(request):
        return httpx.Response(200, json=cuerpo)
    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        gis = prc_gis.consultar_punto(c, LON, LAT, CFG)
    assert gis["zona"]["estado"] == "NO_DISPONIBLE"


def test_ancho_implausible_se_descarta():
    assert prc_gis.ancho_existente("140") is None
    assert prc_gis.ancho_existente("18-25") == 18
    assert prc_gis.ancho_existente("Sin solera") is None
