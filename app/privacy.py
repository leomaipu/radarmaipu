"""Whitelist de campos por capa. Solo estos campos se cargan y se exponen.

Campos personales (RUT, razón social, representante, direcciones personales)
quedan fuera por diseño: no están en la lista blanca, así que nunca entran a la base.
"""
from __future__ import annotations

# Campos de patentes que pueden exponerse públicamente.
PATENTE_PUBLIC_FIELDS = (
    "estado_pat",
    "tipo_paten",
    "subtipo_pa",
    "actividad",
    "Año",
    "semestre",
    "Status",
    "Score",
    "Match_type",
)

# Campos personales conocidos: deben ser excluidos siempre.
PERSONAL_FIELDS = frozenset({
    "rut_negoci", "razon_soci", "rut_rep_le", "nombre_rep", "direc_rep_",
    "direc_nego", "DIRECCION", "Match_addr", "ARC_Single", "rol_neg", "clave", "rol",
    "fecha_emis", "fecha_pago", "total_paga", "total_emis", "sucursal", "cod_sii",
})

CALLE_PUBLIC_FIELDS = ("CLASE", "NOMBRE", "SUF_DIREC")


def filter_attributes(attributes: dict, allowed: tuple[str, ...]) -> dict:
    """Devuelve solo los atributos permitidos. Nunca devuelve campos personales."""
    return {k: attributes[k] for k in allowed if k in attributes and k not in PERSONAL_FIELDS}
