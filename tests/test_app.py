from fastapi.testclient import TestClient

from app.api import app, store
from app.geo import haversine_m, point_to_segment_m
from app.ingest import normalize_calle, normalize_patente


def setup_module():
    store.calles = [{"NOMBRE": "ERRAZURIZ", "CLASE": "AVENIDA", "path": [(-70.75, -33.51), (-70.74, -33.51)]}]
    store.patentes = [{"estado_pat": "VIGENTE", "capa": "Comerciales", "lon": -70.745, "lat": -33.5101}]


client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["calles"] == 1


def test_search_calle_hides_geometry():
    r = client.get("/api/calles", params={"q": "erraz"})
    res = r.json()["resultados"]
    assert res and "path" not in res[0] and res[0]["NOMBRE"] == "ERRAZURIZ"


def _barrios_de_prueba():
    from app.api import store as st
    st.barrios = [
        {"BARRIO": "MAIPU CENTRO", "ID_BARRIO": 7},
        {"BARRIO": "LO ERRAZURIZ", "ID_BARRIO": 1},
        {"BARRIO": "PORTAL DEL SOL", "ID_BARRIO": 5},
        {"BARRIO": "CLOTARIO BLEST", "ID_BARRIO": 9},
    ]


def test_barrios_sin_q_devuelve_todos_ordenados():
    _barrios_de_prueba()
    res = client.get("/api/barrios").json()["resultados"]
    assert [b["BARRIO"] for b in res] == ["CLOTARIO BLEST", "LO ERRAZURIZ", "MAIPU CENTRO", "PORTAL DEL SOL"]


def test_buscar_barrio_sin_tildes_y_sin_mayusculas():
    _barrios_de_prueba()
    res = client.get("/api/barrios", params={"q": "maipú cen"}).json()["resultados"]
    assert res == [{"BARRIO": "MAIPU CENTRO", "ID_BARRIO": 7}]
    res = client.get("/api/barrios", params={"q": "clotar"}).json()["resultados"]
    assert [b["ID_BARRIO"] for b in res] == [9]
    assert client.get("/api/barrios", params={"q": "clotrio"}).json()["resultados"] == []  # subcadena, no fonética
    res = client.get("/api/barrios", params={"q": "ERRAZ"}).json()["resultados"]
    assert [b["ID_BARRIO"] for b in res] == [1]


def test_barrio_q_demasiado_corto_rechazado():
    assert client.get("/api/barrios", params={"q": "a"}).status_code == 422


def test_health_reporta_barrios():
    _barrios_de_prueba()
    assert client.get("/api/health").json()["barrios"] == 4


def test_bbox_invalid_rejected():
    r = client.get("/api/patentes", params={"minlon": 1, "minlat": 1, "maxlon": 0, "maxlat": 2})
    assert r.status_code == 400


def test_punto_returns_nearby_patente_and_street():
    r = client.get("/api/punto", params={"lon": -70.745, "lat": -33.5101, "radio_m": 100})
    body = r.json()
    assert body["calle_cercana"]["NOMBRE"] == "ERRAZURIZ"
    assert len(body["patentes_cercanas"]) == 1


def test_haversine_known_distance():
    # ~111.2 km por grado de latitud
    assert abs(haversine_m(0, 0, 0, 1) - 111_195) < 200


def test_point_to_segment_zero_on_line():
    assert point_to_segment_m(0.5, 0.0, (0, 0), (1, 0)) < 0.01


def test_normalize_calle_and_patente_strip_personal_data():
    c = normalize_calle({"attributes": {"NOMBRE": "X", "CLASE": "C", "razon_soci": "NO"},
                         "geometry": {"paths": [[[-70.7, -33.5], [-70.69, -33.5]]]}})
    assert "razon_soci" not in c and c["path"][0] == (-70.7, -33.5)
    p = normalize_patente({"attributes": {"estado_pat": "V", "Año": 2026, "rut_negoci": "1-9"},
                           "geometry": {"x": -70.7, "y": -33.5}}, "Alcoholes")
    assert p["Año"] == "2026" and "rut_negoci" not in p and p["capa"] == "Alcoholes"


def test_patente_without_geometry_skipped():
    assert normalize_patente({"attributes": {}, "geometry": {}}, "Comerciales") is None


def test_blocked_patentes_never_returned_by_bbox_or_punto():
    from app.api import store as st
    st.patentes = [
        {"estado_pat": "BLOQUEDADA", "capa": "Comerciales", "lon": -70.745, "lat": -33.5101},
        {"estado_pat": "VIGENTE", "capa": "Comerciales", "lon": -70.7451, "lat": -33.5101},
    ]
    bbox = client.get("/api/patentes", params={"minlon": -70.8, "minlat": -33.6, "maxlon": -70.7, "maxlat": -33.5})
    assert [p["estado_pat"] for p in bbox.json()["resultados"]] == ["VIGENTE"]
    punto = client.get("/api/punto", params={"lon": -70.745, "lat": -33.5101, "radio_m": 100})
    assert [p["estado_pat"] for p in punto.json()["patentes_cercanas"]] == ["VIGENTE"]
