"""Diagnóstico de las capas del GIS municipal. No descarga datos personales.

Mide, sin traer registros individuales:
- conteo de registros por capa,
- valores distintos de campos no personales (estado, tipo, clase de calle, año, etc.).

Uso:  python medir.py            (imprime el informe en pantalla)
      python medir.py > informe.txt   (guardar el informe)
"""
from __future__ import annotations

import sys

import httpx

from app.loader import OID_BY_LAYER, config_from_env
from app.privacy import CALLE_PUBLIC_FIELDS

# Campos no personales cuyos valores interesan para decidir el alcance.
DISTINCT_FIELDS = {
    "Calles": ["CLASE"],
    "Alcoholes": ["estado_pat", "tipo_paten", "Año"],
    "Industriales": ["Status", "estado_pat", "tipo_paten"],
    "Comerciales": ["Status", "estado_pat", "tipo_paten", "subtipo_pa"],
}


def _query(client: httpx.Client, url: str, **params) -> dict:
    base = {"where": "1=1", "f": "json", "returnGeometry": "false"}
    r = client.get(f"{url}/query", params={**base, **params}, timeout=60)
    r.raise_for_status()
    return r.json()


def _valores_paginados(client: httpx.Client, nombre: str, url: str, campo: str):
    """Descarga solo el campo pedido (sin geometría) y devuelve sus valores distintos.

    Se calcula localmente porque la consulta returnDistinctValues devolvió error 400
    en las cuatro capas durante la primera medición.
    """
    valores: set[str] = set()
    offset = 0
    while True:
        d = _query(client, url, outFields=campo, orderByFields=OID_BY_LAYER[nombre],
                   resultOffset=offset, resultRecordCount=2000)
        if "error" in d:
            return None, d["error"]
        feats = d.get("features", [])
        valores.update(str(f["attributes"].get(campo)) for f in feats)
        if not d.get("exceededTransferLimit") or not feats:
            return valores, None
        offset += len(feats)


def medir_capa(client: httpx.Client, nombre: str, url: str) -> list[str]:
    lineas = [f"## {nombre}", f"URL: {url}"]
    try:
        conteo = _query(client, url, returnCountOnly="true")
        if "error" in conteo:
            return lineas + [f"  ERROR del servidor: {conteo['error']}"]
        lineas.append(f"  Registros: {conteo.get('count')}")
        for campo in DISTINCT_FIELDS.get(nombre, []):
            valores, error = _valores_paginados(client, nombre, url, campo)
            if error is not None:
                lineas.append(f"  {campo}: ERROR {error}")
                continue
            ordenados = sorted(valores)
            lineas.append(f"  {campo} ({len(ordenados)} valores distintos): {ordenados[:40]}")
            if len(ordenados) > 40:
                lineas.append(f"  (se muestran 40 de {len(ordenados)})")
    except httpx.HTTPError as e:
        lineas.append(f"  No se pudo conectar: {e}")
    return lineas


def main() -> int:
    calles_url, patentes = config_from_env()
    capas = {"Calles": calles_url, **patentes}
    informe = ["# Medición de capas Radar Maipú", ""]
    with httpx.Client() as client:
        for nombre, url in capas.items():
            informe += medir_capa(client, nombre, url) + [""]
    informe.append("Nota: solo se leen conteos y valores de campos no personales.")
    print("\n".join(informe))
    return 0


if __name__ == "__main__":
    sys.exit(main())
