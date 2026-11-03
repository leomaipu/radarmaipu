import httpx

from medir import DISTINCT_FIELDS, medir_capa
from app.privacy import PERSONAL_FIELDS, PATENTE_PUBLIC_FIELDS, CALLE_PUBLIC_FIELDS


def test_diagnostic_never_requests_personal_fields():
    for capa, campos in DISTINCT_FIELDS.items():
        assert not (set(campos) & PERSONAL_FIELDS), capa
        assert set(campos) <= set(PATENTE_PUBLIC_FIELDS) | set(CALLE_PUBLIC_FIELDS), capa


def test_medir_capa_reports_count_and_values():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("returnCountOnly") == "true":
            return httpx.Response(200, json={"count": 7})
        return httpx.Response(200, json={"features": [
            {"attributes": {"estado_pat": "VIGENTE"}},
            {"attributes": {"estado_pat": "CADUCADA"}},
        ]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    lineas = medir_capa(client, "Alcoholes", "https://example.test/l")
    texto = "\n".join(lineas)
    assert "Registros: 7" in texto
    assert "estado_pat (2 valores distintos)" in texto
    assert "rut" not in texto.lower()
