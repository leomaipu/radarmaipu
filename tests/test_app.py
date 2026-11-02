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
