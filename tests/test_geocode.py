import json

import httpx
import pytest

from nucleo import geocode


REVERSE_OK = {
    "address": {"Match_addr": "0260 5 DE ABRIL, MAIPU CENTRO, MAIPÚ", "ShortLabel": "0260 5 DE ABRIL",
                "Addr_type": "PointAddress", "Neighborhood": "MAIPU CENTRO", "City": "MAIPÚ"},
    "location": {"x": -70.7535, "y": -33.5102, "spatialReference": {"wkid": 4326}},
}


def _client(payload, seen=None):
    def handler(request):
        if seen is not None:
            seen.append(request)
        return httpx.Response(200, json=payload)
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_reverse_returns_address_and_requests_wgs84():
    seen = []
    out = geocode.reverse(_client(REVERSE_OK, seen), -70.7535, -33.5102)
    assert out["direccion"].startswith("0260 5 DE ABRIL")
    assert out["barrio"] == "MAIPU CENTRO" and out["lat"] == -33.5102
    assert seen[0].url.params["outSR"] == "4326"
    assert json.loads(seen[0].url.params["location"])["spatialReference"]["wkid"] == 4326


def test_reverse_without_match_returns_none():
    assert geocode.reverse(_client({"address": {"Match_addr": ""}}), 0, 0) is None


def test_service_error_raises():
    with pytest.raises(geocode.GeocodeError):
        geocode.reverse(_client({"error": {"message": "Unable to complete operation."}}), 0, 0)


def test_forward_returns_candidates():
    payload = {"candidates": [{"address": "5 DE ABRIL 260", "score": 96.1,
                               "location": {"x": -70.75, "y": -33.51}}]}
    out = geocode.forward(_client(payload), "5 de abril 260")
    assert out == [{"direccion": "5 DE ABRIL 260", "score": 96.1, "lon": -70.75, "lat": -33.51}]


def test_base_url_comes_from_config_and_env_overrides(monkeypatch):
    geocode.base_url.cache_clear()
    monkeypatch.delenv("RM_GEOCODER_URL", raising=False)
    assert "LocatorBetaV3dot3" in geocode.base_url()
    geocode.base_url.cache_clear()
    monkeypatch.setenv("RM_GEOCODER_URL", "https://ejemplo.test/GeocodeServer/")
    assert geocode.base_url() == "https://ejemplo.test/GeocodeServer"
    geocode.base_url.cache_clear()
