import httpx

from app import geocode
from app.regeocode import regeocodificar


def _client(respuesta):
    def handler(request):
        return httpx.Response(200, json=respuesta)
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_u_with_high_score_gets_new_point():
    p = {"Status": "U", "DIRECCION": "5 DE ABRIL 260", "lon": -70.0, "lat": -33.0}
    res = regeocodificar([p], _client({"candidates": [
        {"address": "0260 5 DE ABRIL", "score": 95, "location": {"x": -70.7535, "y": -33.5102}}]}))
    assert res["actualizadas"] == 1
    assert p["lon"] == -70.7535 and p["coords_origen"] == "re-geocodificado"


def test_low_score_keeps_original_point():
    p = {"Status": "U", "DIRECCION": "X", "lon": -70.0, "lat": -33.0}
    res = regeocodificar([p], _client({"candidates": [
        {"address": "X", "score": 40, "location": {"x": -70.7, "y": -33.5}}]}))
    assert res["bajo_umbral"] == 1 and p["lon"] == -70.0


def test_only_status_u_is_processed():
    p = {"Status": "M", "DIRECCION": "X", "lon": -70.0, "lat": -33.0}
    res = regeocodificar([p], _client({"candidates": []}))
    assert res["candidatas"] == 0 and p["lon"] == -70.0


def test_patente_without_direccion_is_skipped():
    p = {"Status": "U", "lon": -70.0, "lat": -33.0}
    assert regeocodificar([p], _client({"candidates": []}))["candidatas"] == 0


def test_loader_requests_direccion_in_patente_layers():
    from app.loader import PATENTE_FIELDS_BY_LAYER
    for capa, campos in PATENTE_FIELDS_BY_LAYER.items():
        assert "DIRECCION" in campos, capa
