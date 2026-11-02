import httpx

from app.loader import fetch_layer


def test_pagination_follows_exceeded_transfer_limit():
    pages = [
        {"features": [{"attributes": {"OBJECTID": 1}}], "exceededTransferLimit": True},
        {"features": [{"attributes": {"OBJECTID": 2}}]},
    ]
    seen_offsets = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_offsets.append(request.url.params["resultOffset"])
        return httpx.Response(200, json=pages[len(seen_offsets) - 1])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    feats = fetch_layer(client, "https://example.test/layer", "NOMBRE", "OBJECTID")
    assert [f["attributes"]["OBJECTID"] for f in feats] == [1, 2]
    assert seen_offsets == ["0", "1"]


def test_arcgis_error_raises():
    import pytest

    def handler(request):
        return httpx.Response(200, json={"error": {"code": 400, "message": "bad"}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(RuntimeError):
        fetch_layer(client, "https://example.test/layer", "NOMBRE", "OBJECTID")


def test_requests_only_whitelisted_fields_per_layer():
    from app.loader import PATENTE_FIELDS_BY_LAYER, OID_BY_LAYER
    from app.privacy import PERSONAL_FIELDS, PATENTE_PUBLIC_FIELDS

    for layer, fields in PATENTE_FIELDS_BY_LAYER.items():
        assert not (set(fields) & PERSONAL_FIELDS), layer
        assert set(fields) <= set(PATENTE_PUBLIC_FIELDS), layer
        assert layer in OID_BY_LAYER
    assert OID_BY_LAYER["Comerciales"] == "OBJECTID_1"  # no tiene OBJECTID
    assert "Status" not in PATENTE_FIELDS_BY_LAYER["Alcoholes"]  # Alcoholes no lo tiene
