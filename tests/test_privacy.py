from app.privacy import PATENTE_PUBLIC_FIELDS, PERSONAL_FIELDS, filter_attributes


RAW = {
    "estado_pat": "VIGENTE", "tipo_paten": "COMERCIAL", "Año": "2026",
    "rut_negoci": "12.345.678-9", "razon_soci": "JUAN PEREZ", "nombre_rep": "JUAN PEREZ",
    "rut_rep_le": "9.999.999-9", "direc_rep_": "Calle Falsa 123", "DIRECCION": "Av. X 456",
    "direc_nego": "Av. X 456", "Match_addr": "Av. X 456", "cod_sii": "123",
}


def test_personal_fields_never_pass():
    out = filter_attributes(RAW, PATENTE_PUBLIC_FIELDS)
    assert set(out) <= set(PATENTE_PUBLIC_FIELDS)
    assert not (set(out) & PERSONAL_FIELDS)


def test_public_fields_are_kept():
    out = filter_attributes(RAW, PATENTE_PUBLIC_FIELDS)
    assert out == {"estado_pat": "VIGENTE", "tipo_paten": "COMERCIAL", "Año": "2026"}


def test_whitelist_does_not_overlap_personal_fields():
    assert not (set(PATENTE_PUBLIC_FIELDS) & PERSONAL_FIELDS)
