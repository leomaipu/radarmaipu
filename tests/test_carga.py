import httpx
from fastapi.testclient import TestClient

import app.api as api
from app.carga import carga_inicial
from app.store import Store

CALLE = {"attributes": {"NOMBRE": "ERRAZURIZ", "rut_negoci": "NO"},
         "geometry": {"paths": [[[-70.75, -33.51], [-70.74, -33.51]]]}}
PATENTE = {"attributes": {"Status": "U", "DIRECCION": "5 DE ABRIL 260", "estado_pat": "VIGENTE"},
           "geometry": {"x": "NaN", "y": "NaN"}}  # así publica el GIS las patentes con Status U


def _fabrica(fallos_gis=0, candidatos=None):
    """Simula GIS y geocodificador; las primeras `fallos_gis` consultas al GIS devuelven 500."""
    pendientes = [fallos_gis]

    def handler(request):
        if "findAddressCandidates" in request.url.path:
            if candidatos is None:
                return httpx.Response(200, text="<html>no es json</html>")
            return httpx.Response(200, json={"candidates": candidatos})
        if pendientes[0] > 0:
            pendientes[0] -= 1
            return httpx.Response(500)
        return httpx.Response(200, json={"features": [CALLE if "DOM_CATASTRO" in request.url.path else PATENTE]})

    return lambda: httpx.Client(transport=httpx.MockTransport(handler))


CANDIDATO = [{"address": "0260 5 DE ABRIL", "score": 95, "location": {"x": -70.75, "y": -33.51}}]


def test_carga_publica_datos_y_regeocodifica():
    store, estado = Store(), {}
    carga_inicial(store, estado, crear_cliente=_fabrica(candidatos=CANDIDATO))
    assert estado["fase"] == "lista"
    assert len(store.calles) == 1 and len(store.patentes) == 3  # tres capas de patentes
    assert store.patentes[0]["coords_origen"] == "re-geocodificado"
    assert "rut_negoci" not in store.calles[0]


def test_carga_reintenta_tras_fallo_del_gis():
    store, estado = Store(), {}
    carga_inicial(store, estado, espera_s=0, crear_cliente=_fabrica(fallos_gis=1, candidatos=CANDIDATO))
    assert estado["fase"] == "lista" and store.calles


def test_carga_agota_intentos_y_deja_el_almacen_intacto():
    store, estado = Store(calles=[{"NOMBRE": "PREVIA"}]), {}
    carga_inicial(store, estado, intentos=2, espera_s=0, crear_cliente=_fabrica(fallos_gis=99))
    assert estado["fase"] == "error" and store.calles == [{"NOMBRE": "PREVIA"}]


def test_fallo_de_regeocodificacion_no_retira_los_datos():
    store, estado = Store(), {}
    carga_inicial(store, estado, crear_cliente=_fabrica(candidatos=None))
    assert estado["fase"] == "lista_sin_regeocodificar" and len(store.patentes) == 3


def test_api_inicia_la_carga_y_health_informa_la_fase(monkeypatch):
    def falsa(store, estado):
        estado["fase"] = "lista"

    monkeypatch.setattr(api, "carga_inicial", falsa)
    monkeypatch.setitem(api.estado_carga, "fase", "sin_iniciar")
    with TestClient(api.app) as client:
        api.hilo_carga.join(timeout=5)
        assert client.get("/api/health").json()["carga"] == "lista"


def test_patente_sin_punto_no_rompe_busquedas_y_health_la_cuenta(monkeypatch):
    con_punto = {"estado_pat": "VIGENTE", "lon": -70.745, "lat": -33.51}
    sin_punto = {"estado_pat": "VIGENTE", "Status": "U", "lon": None, "lat": None}
    monkeypatch.setattr(api.store, "patentes", [con_punto, sin_punto])
    client = TestClient(api.app)  # sin "with": no inicia la carga real
    assert client.get("/api/health").json()["patentes_sin_punto"] == 1
    bbox = client.get("/api/patentes", params={"minlon": -70.8, "minlat": -33.6, "maxlon": -70.7, "maxlat": -33.5})
    assert bbox.json()["resultados"] == [con_punto]
    punto = client.get("/api/punto", params={"lon": -70.745, "lat": -33.51, "radio_m": 100})
    assert len(punto.json()["patentes_cercanas"]) == 1


def test_bajo_umbral_deja_la_patente_sin_punto():
    store, estado = Store(), {}
    bajo = [{"address": "X", "score": 40, "location": {"x": -70.7, "y": -33.5}}]
    carga_inicial(store, estado, crear_cliente=_fabrica(candidatos=bajo))
    assert estado["fase"] == "lista" and store.patentes[0]["lon"] is None
