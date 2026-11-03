from app.ingest import normalize_calle, normalize_patente
from app.normalize import clean_text


def test_clean_text_removes_null_markers_and_spaces():
    assert clean_text(" ") is None
    assert clean_text("<Nulo>") is None
    assert clean_text("None") is None
    assert clean_text("PASAJE ") == "PASAJE"


def test_calle_clase_trailing_space_is_normalized():
    c = normalize_calle({"attributes": {"NOMBRE": "X", "CLASE": "PASAJE "},
                         "geometry": {"paths": [[[-70.7, -33.5], [-70.69, -33.5]]]}})
    assert c["CLASE"] == "PASAJE"


def test_codes_are_kept_not_expanded():
    c = normalize_calle({"attributes": {"NOMBRE": "X", "CLASE": "PBN"},
                         "geometry": {"paths": [[[-70.7, -33.5], [-70.69, -33.5]]]}})
    assert c["CLASE"] == "PBN"
    p = normalize_patente({"attributes": {"estado_pat": "BLOQUEDADA", "Año": 2026},
                           "geometry": {"x": -70.7, "y": -33.5}}, "Comerciales")
    assert p["estado_pat"] == "BLOQUEDADA" and p["Año"] == "2026"
