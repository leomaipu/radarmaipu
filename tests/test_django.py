"""Capa Django: carga a PostGIS, API sobre la base, comercio cercano, checklist y sitio del vecino."""
import json

import httpx
import pytest
from django.contrib.gis.geos import Point
from django.test import Client

from api import comercio, views as api_views
from nucleo import geocode
from territorio import carga
from territorio.models import Barrio, Calle, Patente
from tramites.models import DocumentoChecklist
from web import views as web_views
from web.presentacion import presentar

from .test_informe import LAT, LON, gis_falso, via_a

pytestmark = pytest.mark.django_db


def patente(lon, lat, actividad="BAZAR", estado="VIGENTE", **kw):
    return Patente.objects.create(capa="Comerciales", direccion=kw.pop("direccion", "CALLE 1"), estado_pat=estado,
                                  actividad=actividad, geom=Point(lon, lat, srid=4326) if lon is not None else None, **kw)


# ——— Carga del GIS a PostGIS ———
def _gis_capas(patentes_status="M"):
    """Imita las capas de calles, barrios y patentes del GIS (una página cada una)."""
    def handler(request: httpx.Request) -> httpx.Response:
        ruta = request.url.path
        if "DOM_CATASTRO_MUNICIPAL" in ruta:
            feats = [{"attributes": {"NOMBRE": "AV. PAJARITOS", "CLASE": "AV", "rut_negoci": "1-9"},
                      "geometry": {"paths": [[[-70.76, -33.51], [-70.75, -33.51]]]}}]
        elif "BARRIOS" in ruta:
            feats = [{"attributes": {"BARRIO": "MAIPÚ CENTRO", "ID_BARRIO": 7.0}}]
        elif ruta.endswith("/2/query"):
            feats = [
                {"attributes": {"DIRECCION": "PAJARITOS 1912", "estado_pat": "VIGENTE", "actividad": "BAZAR",
                                "Status": "M", "razon_soci": "JUAN PÉREZ", "rut_negoci": "12.345.678-9"},
                 "geometry": {"x": -70.7577, "y": -33.5100}},
                {"attributes": {"DIRECCION": "SIN PUNTO 10", "estado_pat": "VIGENTE", "actividad": "ALMACEN",
                                "Status": patentes_status}, "geometry": {"x": "NaN", "y": "NaN"}},
            ]
        else:
            feats = []
        return httpx.Response(200, json={"features": feats})
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_carga_reemplaza_tablas_y_no_guarda_datos_personales():
    Patente.objects.create(capa="Comerciales", direccion="VIEJA")
    with _gis_capas() as c:
        conteos = carga.cargar(c)
    assert conteos["patentes"] == 2 and conteos["calles"] == 1 and conteos["barrios"] == 1
    assert not Patente.objects.filter(direccion="VIEJA").exists()
    assert Barrio.objects.get().a_dict() == {"BARRIO": "MAIPÚ CENTRO", "ID_BARRIO": 7}
    assert Calle.objects.get().nombre == "AV. PAJARITOS"
    volcado = json.dumps([p.a_dict() for p in Patente.objects.all()], ensure_ascii=False)
    assert "JUAN" not in volcado and "12.345.678-9" not in volcado
    assert Patente.objects.filter(geom__isnull=True).count() == 1


def test_recarga_conserva_puntos_regeocodificados():
    with _gis_capas() as c:
        carga.cargar(c)
    p = Patente.objects.get(direccion="SIN PUNTO 10")
    p.geom, p.coords_origen, p.score_geocodificacion = Point(-70.75, -33.50, srid=4326), "re-geocodificado", 97
    p.save()
    with _gis_capas() as c:
        conteos = carga.cargar(c)
    p = Patente.objects.get(direccion="SIN PUNTO 10")
    assert p.geom is not None and p.coords_origen == "re-geocodificado"
    assert conteos["conservadas_regeocodificadas"] == 1


def test_regeocodificar_respeta_umbral(monkeypatch):
    patente(None, None, direccion="ALTA 1", status="U")
    patente(None, None, direccion="BAJA 2", status="U")
    patente(-70.75, -33.5, direccion="OK 3", status="M")

    def forward(client, texto, max_resultados=5):
        return [{"direccion": texto, "score": 99 if texto == "ALTA 1" else 40, "lon": -70.74, "lat": -33.49}]
    monkeypatch.setattr(geocode, "forward", forward)
    r = carga.regeocodificar(httpx.Client())
    assert r == {"candidatas": 2, "actualizadas": 1, "bajo_umbral": 1, "sin_resultado": 0}
    assert Patente.objects.get(direccion="ALTA 1").coords_origen == "re-geocodificado"


# ——— Comercio cercano ———
def test_es_similar_por_prefijo_y_palabra_completa():
    assert comercio.es_similar("FARMACIA Y PERFUMERÍA", ["FARMAC"])
    assert comercio.es_similar("Almacén con expendio de cecinas", ["ALMACEN"])
    assert not comercio.es_similar("BARBERIA", ["BAR "])
    assert comercio.es_similar("BAR Y RESTAURANT", ["BAR "])
    assert not comercio.es_similar(None, ["BAZAR"])


def test_resumen_cuenta_vigentes_en_radio_y_similares():
    patente(LON, LAT + 0.0005, "BAZAR Y PAQUETERIA")           # ~55 m
    patente(LON, LAT + 0.0010, "PELUQUERIA")                    # ~110 m
    patente(LON, LAT + 0.0011, "BAZAR", estado="BLOQUEDADA")    # oculta
    patente(LON, LAT + 0.0100, "BAZAR")                         # ~1,1 km
    r = comercio.resumen(LON, LAT, {"palabras_actividad": ["BAZAR"]}, 300)
    assert r["total"] == 2 and r["similares"] == 1
    assert r["ejemplos_similares"][0]["distancia_m"] < 70
    assert [p["s"] for p in r["puntos"]] == [True, False]


# ——— API sobre la base ———
def test_api_punto_patentes_calles_barrios():
    Calle.objects.create(nombre="AVENIDA LOS PAJARITOS", clase="AV",
                         geom=Calle._meta.get_field("geom").to_python("LINESTRING(-70.761 -33.48, -70.759 -33.48)"))
    Barrio.objects.create(id_barrio=1, nombre="LO ERRÁZURIZ")
    patente(LON, LAT + 0.0005)
    c = Client()
    r = c.get("/api/punto", {"lon": LON, "lat": LAT, "radio_m": 150}).json()
    assert r["calle_cercana"]["NOMBRE"] == "AVENIDA LOS PAJARITOS" and len(r["patentes_cercanas"]) == 1
    assert r["patentes_cercanas"][0]["distancia_m"] == pytest.approx(55.6, abs=2)
    assert c.get("/api/patentes", {"minlon": -70.8, "minlat": -33.6, "maxlon": -70.7, "maxlat": -33.4}).json()["resultados"]
    assert c.get("/api/patentes", {"minlon": -70.7, "minlat": -33.6, "maxlon": -70.8, "maxlat": -33.4}).status_code == 400
    assert c.get("/api/calles", {"q": "pajaritos 1200"}).json()["aviso"]
    assert c.get("/api/barrios", {"q": "errazuriz"}).json()["resultados"] == [{"BARRIO": "LO ERRÁZURIZ", "ID_BARRIO": 1}]
    h = c.get("/api/health").json()
    assert h["patentes"] == 1 and h["carga"] == "sin_cargas"


def test_api_direccion_502_si_el_geocodificador_falla(monkeypatch):
    def boom(client, lon, lat, distance_m=100):
        raise geocode.GeocodeError("caído")
    monkeypatch.setattr(geocode, "reverse", boom)
    assert Client().get("/api/direccion", {"lon": -70.75, "lat": -33.51}).status_code == 502


# ——— Checklist de Rentas desde el panel ———
def test_checklist_del_panel_llega_al_informe(monkeypatch):
    monkeypatch.setattr(api_views, "cliente_gis", lambda: gis_falso())
    DocumentoChecklist.objects.create(nombre="Formulario de solicitud", orden=1)
    DocumentoChecklist.objects.create(nombre="Resolución sanitaria", clase="2.2", orden=2)
    DocumentoChecklist.objects.create(nombre="Patente de alcoholes", solo_alcohol=True, orden=3)
    DocumentoChecklist.objects.create(nombre="Solo peluquería", giro="peluqueria", orden=4)
    DocumentoChecklist.objects.create(nombre="Inactivo", activo=False)
    inf = api_views.construir_informe(LAT, LON, "bazar", None, None)
    assert inf["checklist_rentas"]["estado"] == "lista_oficial"
    assert [i["documento"] for i in inf["checklist_rentas"]["items"]] == ["Formulario de solicitud", "Resolución sanitaria"]


def test_sin_checklist_queda_pendiente(monkeypatch):
    monkeypatch.setattr(api_views, "cliente_gis", lambda: gis_falso())
    inf = api_views.construir_informe(LAT, LON, "bazar", None, None)
    assert inf["checklist_rentas"] == {"estado": "pendiente_lista_oficial", "items": []}
    assert inf["comercio_cercano"]["total"] == 0


# ——— Sitio del vecino ———
@pytest.fixture
def web(monkeypatch):
    monkeypatch.setattr(api_views, "cliente_gis", lambda: gis_falso(vias=[via_a(25)], riesgos=[("AR-2", "SISMICO")]))
    return Client()


def test_inicio_tiene_marca_pwa_y_tres_pasos(web):
    html = web.get("/").content.decode()
    for esperado in ("logo-maipu", 'rel="manifest"', "¿Dónde quieres", "¿Qué negocio quieres", 'id="config-radar"',
                     "No reemplaza el Certificado de Informaciones Previas", 'lang="es-CL"'):
        assert esperado in html, esperado
    assert html.count('name="giro"') == 63


def test_panel_informe_muestra_veredicto_aviso_y_pregunta_de_frente(web):
    html = web.get("/panel/informe/", {"lat": LAT, "lon": LON, "giro": "bazar"}).content.decode()
    assert "Compatible con condiciones" in html
    assert "Informe orientativo." in html and "Certificado de Informaciones Previas" in html
    assert 'data-frente="T8P"' in html and "¿Tu local da a Av. Pajaritos?" in html
    html = web.get("/panel/informe/", {"lat": LAT, "lon": LON, "giro": "bazar", "frente_via": "T8P"}).content.decode()
    assert ">Compatible<" in html and "Indicaste que tu local da a" in html


@pytest.mark.parametrize("params", [
    {"lat": "x", "lon": LON, "giro": "bazar"},
    {"lat": LAT, "lon": LON, "giro": "<script>alert(1)</script>"},
    {"lat": LAT, "lon": LON, "giro": "bazar", "escala": "gigante"},
    {"lat": LAT, "lon": LON, "giro": "bazar", "frente_via": "a b<"},
    {"lat": 200, "lon": LON, "giro": "bazar"},
])
def test_panel_informe_rechaza_parametros_invalidos(web, params):
    assert web.get("/panel/informe/", params).status_code == 400


def test_panel_buscar(web, monkeypatch):
    monkeypatch.setattr(geocode, "forward", lambda client, q, max_resultados=5: [
        {"direccion": "1912 LOS PAJARITOS, MAIPU CENTRO, MAIPÚ", "score": 100, "lon": -70.757, "lat": -33.51},
        {"direccion": "1912 LOS PAJARITOS, MAIPU CENTRO, MAIPÚ", "score": 99, "lon": -70.757, "lat": -33.51},
        {"direccion": "SIN PUNTO", "score": 80, "lon": None, "lat": None}])
    html = web.get("/panel/buscar/", {"q": "pajaritos 1912"}).content.decode()
    assert html.count('class="direccion"') == 1 and 'data-lat="-33.510000"' in html
    assert "direccion" not in web.get("/panel/buscar/", {"q": "pa"}).content.decode()


def test_panel_buscar_geocodificador_caido(web, monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("x")
    monkeypatch.setattr(geocode, "forward", boom)
    assert "no responde" in web.get("/panel/buscar/", {"q": "pajaritos"}).content.decode()


def test_manifest_service_worker_y_offline(web):
    m = json.loads(web.get("/manifest.webmanifest").content)
    assert m["display"] == "standalone" and m["start_url"].startswith("/") and m["lang"] == "es-CL"
    assert {"192x192", "512x512"} <= {i["sizes"] for i in m["icons"]}
    assert any(i["purpose"] == "maskable" for i in m["icons"])
    sw = web.get("/sw.js")
    cuerpo = sw.content.decode()
    assert sw["Content-Type"].startswith("application/javascript") and sw["Cache-Control"] == "no-cache"
    assert "/offline/" in cuerpo and '"/api/"' in cuerpo
    assert web.get("/offline/").status_code == 200


def test_leyenda_se_sirve_desde_el_gis_y_se_guarda_en_cache(web, monkeypatch):
    from django.core.cache import cache
    cache.clear()
    llamadas = []

    def handler(request):
        llamadas.append(request.url)
        return httpx.Response(200, json={"layers": [
            {"layerId": 3, "layerName": "ZH", "legend": [{"label": "ZH1", "contentType": "image/png", "imageData": "AAA"}]},
            {"layerId": 0, "layerName": "Vialidad", "legend": [{"label": "", "contentType": "image/png", "imageData": "B"}]}]})
    real = httpx.Client
    monkeypatch.setattr(web_views.httpx, "Client", lambda: real(transport=httpx.MockTransport(handler)))
    d = json.loads(web.get("/panel/leyenda/").content)
    assert d == {"capas": [{"id": 3, "nombre": "ZH", "items": [{"etiqueta": "ZH1", "img": "data:image/png;base64,AAA"}]}]}
    web.get("/panel/leyenda/")
    assert len(llamadas) == 1


def _inf(estado, detalle, frente):
    return {"resultado": {"estado": estado, "motivo": "", "articulo": None, "detalle_escalas": detalle},
            "advertencias": [], "vialidad": {"frente": frente}, "zona": {}, "edificacion": None,
            "giro": {"escala": "basico"}}


def test_presentacion_no_ofrece_frente_si_el_resultado_no_depende_de_la_via():
    inf = _inf("PERMITIDO", {}, [{"via": "X", "codigo": "C", "jerarquia": "Troncal", "confirmado": False}])
    assert presentar(inf)["frentes_sugeridos"] == []
    assert presentar(inf)["escala_nombre"] == "básica"


def test_presentacion_solo_ofrece_vias_que_cumplen_la_condicion_pendiente():
    angosta = {"via": "Manuel Rodríguez", "codigo": "S68M", "jerarquia": "Servicio", "ancho_m": 12.0}
    ancha = {"via": "Av. Pajaritos", "codigo": "T8P", "jerarquia": "Troncal", "ancho_m": 30.0}
    taller = _inf("PERMITIDO_CON_CONDICION", {"basico": {"estado": "CONDICION", "condicion": "via_20m"}}, [angosta, ancha])
    assert [v["codigo"] for v in presentar(taller)["frentes_sugeridos"]] == ["T8P"]
    bazar = _inf("PERMITIDO_CON_CONDICION", {"menor": {"estado": "CONDICION", "condicion": "vialidad_estructurante"}},
                 [angosta])
    assert [v["codigo"] for v in presentar(bazar)["frentes_sugeridos"]] == ["S68M"]
    zh1 = _inf("PERMITIDO_CON_CONDICION", {"menor": {"estado": "CONDICION", "condicion": "colectora_o_mayor"}}, [angosta])
    assert presentar(zh1)["frentes_sugeridos"] == []


# ——— Cobertura que venía de la versión FastAPI ———
def test_api_oculta_patentes_bloqueadas():
    patente(LON, LAT + 0.0003, estado="BLOQUEDADA")
    patente(LON, LAT + 0.0004)
    c = Client()
    assert len(c.get("/api/punto", {"lon": LON, "lat": LAT}).json()["patentes_cercanas"]) == 1
    caja = {"minlon": -70.8, "minlat": -33.6, "maxlon": -70.7, "maxlat": -33.4}
    assert [p["estado_pat"] for p in c.get("/api/patentes", caja).json()["resultados"]] == ["VIGENTE"]


def test_api_barrios_orden_y_validacion():
    for i, n in enumerate(["PORTAL DEL SOL", "CLOTARIO BLEST", "Ñuñoa Test", "MAIPÚ CENTRO"]):
        Barrio.objects.create(id_barrio=i, nombre=n)
    c = Client()
    assert [b["BARRIO"] for b in c.get("/api/barrios").json()["resultados"]] == [
        "CLOTARIO BLEST", "MAIPÚ CENTRO", "Ñuñoa Test", "PORTAL DEL SOL"]
    assert c.get("/api/barrios", {"q": "a"}).status_code == 422
    assert [b["ID_BARRIO"] for b in c.get("/api/barrios", {"q": "maipu cen"}).json()["resultados"]] == [3]


def test_api_calles_no_expone_geometria():
    Calle.objects.create(nombre="ERRAZURIZ", clase="AV",
                         geom=Calle._meta.get_field("geom").to_python("LINESTRING(-70.75 -33.51, -70.74 -33.51)"))
    r = Client().get("/api/calles", {"q": "erraz"}).json()["resultados"]
    assert r == [{"NOMBRE": "ERRAZURIZ", "CLASE": "AV", "SUF_DIREC": None, "CLASE_DESC": None}]


def test_cargar_gis_si_vacia_no_recarga(monkeypatch):
    from django.core.management import call_command
    llamado = []
    monkeypatch.setattr("territorio.carga.ejecutar", lambda *a, **k: llamado.append(1))
    patente(LON, LAT)
    call_command("cargar_gis", "--si-vacia")
    assert llamado == []


def test_carga_reintenta_y_registra_error(monkeypatch):
    intentos = []

    def falla(client):
        intentos.append(1)
        raise httpx.ConnectError("caído")
    monkeypatch.setattr(carga, "cargar", falla)
    b = carga.ejecutar(False, reintentos=3, espera_s=0)
    assert len(intentos) == 3 and b.fase == "error" and "ConnectError" in b.error


# ——— Seguridad ———
def test_cabeceras_de_seguridad(web):
    r = web.get("/")
    csp = r["Content-Security-Policy"]
    assert "script-src 'self'" in csp and "unsafe-eval" not in csp and "frame-ancestors 'none'" in csp
    assert "https://server.arcgisonline.com" in csp and "https://gis.maipu.cl" in csp
    assert r["X-Frame-Options"] == "DENY"
    assert "onsubmit" not in r.content.decode() and "onclick" not in r.content.decode()


def test_leyenda_con_gis_caido_no_queda_en_cache(web, monkeypatch):
    from django.core.cache import cache
    cache.clear()

    def handler(request):
        return httpx.Response(500)
    real = httpx.Client
    monkeypatch.setattr(web_views.httpx, "Client", lambda: real(transport=httpx.MockTransport(handler)))
    r = web.get("/panel/leyenda/")
    assert r.status_code == 503 and r["Cache-Control"] == "no-store"


def test_advertencias_de_via_para_el_vecino():
    adv = [{"tipo": "vialidad", "texto": "Frente probable a X (Troncal), estimado por proximidad al eje (5 m). "
                                         "No se da por cumplido: si el predio enfrenta esa vía, repetir la consulta con frente_via=T8P."},
           {"tipo": "riesgo", "texto": "Riesgo sísmico."}]
    base = {"advertencias": adv, "vialidad": {"frente": []}, "zona": {}, "edificacion": None, "giro": {}}
    cond = presentar({**base, "resultado": {"estado": "PERMITIDO_CON_CONDICION", "motivo": "", "detalle_escalas": {}}})
    assert "frente_via" not in " ".join(a["texto"] for a in cond["advertencias"])
    no = presentar({**base, "resultado": {"estado": "NO_PERMITIDO", "motivo": "", "detalle_escalas": {}}})
    assert [a["etiqueta"] for a in no["advertencias"]] == ["Área de riesgo"]
