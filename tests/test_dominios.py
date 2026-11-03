import json

from app import dominios
from app.ingest import normalize_calle, normalize_patente


def test_clase_codes_are_expanded_as_confirmed():
    assert dominios.descripcion_clase("PBN") == "Paso bajo nivel"
    assert dominios.descripcion_clase("PSN") == "Paso sobre nivel"
    assert dominios.descripcion_clase("PTE") == "Puente"
    assert dominios.descripcion_clase("CARRE") == "Carretera"


def test_unknown_code_is_kept_not_invented():
    assert dominios.descripcion_clase("XYZ") == "XYZ"


def test_status_codes_match_confirmed_definitions():
    assert dominios.descripcion_status("M") == "Match"
    assert dominios.descripcion_status("T") == "Target"
    assert dominios.descripcion_status("U") == "Unmatch"


def test_misspelled_blocked_value_maps_to_official_name_but_raw_kept():
    p = normalize_patente({"attributes": {"estado_pat": "BLOQUEDADA"},
                           "geometry": {"x": -70.7, "y": -33.5}}, "Comerciales")
    assert p["estado_pat"] == "BLOQUEDADA"          # dato tal como viene
    assert p["estado_normalizado"] == "BLOQUEADA"   # nombre oficial


def test_hidden_states_empty_by_default_pending_decision():
    # Decisión pendiente: la lista debe estar vacía hasta que la municipalidad decida.
    assert json.loads(dominios.RUTA_DEFAULT.read_text(encoding="utf-8"))["estados_ocultos"] == []
    assert dominios.estado_oculto("BLOQUEDADA") is False


def test_calle_gets_description():
    c = normalize_calle({"attributes": {"NOMBRE": "X", "CLASE": "PBN"},
                         "geometry": {"paths": [[[-70.7, -33.5], [-70.69, -33.5]]]}})
    assert c["CLASE_DESC"] == "Paso bajo nivel"
