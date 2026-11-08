from nucleo.busqueda import buscar_calles, normalizar, separar_numero

CALLES = [
    {"NOMBRE": "PAJARITOS", "CLASE": "CALLE", "SUF_DIREC": "", "path": [(0, 0), (1, 1)]},
    {"NOMBRE": "LLONA, ALBERTO", "CLASE": "CALLE", "SUF_DIREC": "", "path": [(0, 0), (1, 1)]},
    {"NOMBRE": "ERRAZURIZ", "CLASE": "AVENIDA", "SUF_DIREC": "", "path": [(0, 0), (1, 1)]},
]


def test_number_is_separated_and_search_still_finds_street():
    texto, numero = separar_numero("Pajaritos 1200")
    assert texto == "Pajaritos" and numero == "1200"
    out = buscar_calles(CALLES, "Pajaritos 1200")
    assert [c["NOMBRE"] for c in out["resultados"]] == ["PAJARITOS"]
    assert "numeración" in out["aviso"] and "1200" in out["aviso"]


def test_order_comma_and_accents_do_not_matter():
    assert [c["NOMBRE"] for c in buscar_calles(CALLES, "Alberto Llona")["resultados"]] == ["LLONA, ALBERTO"]
    assert [c["NOMBRE"] for c in buscar_calles(CALLES, "llóna alberto")["resultados"]] == ["LLONA, ALBERTO"]


def test_clase_is_searchable_and_no_aviso_without_number():
    out = buscar_calles(CALLES, "avenida errazuriz")
    assert [c["NOMBRE"] for c in out["resultados"]] == ["ERRAZURIZ"]
    assert out["aviso"] is None


def test_empty_or_number_only_query_returns_nothing():
    assert buscar_calles(CALLES, "1200")["resultados"] == []
    assert buscar_calles(CALLES, "   ")["resultados"] == []


def test_normalizar_strips_accents_and_punctuation():
    assert normalizar("Maipú, Ñuñoa.") == "MAIPU NUNOA"
