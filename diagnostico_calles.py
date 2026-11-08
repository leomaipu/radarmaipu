"""Muestra cómo está escrita una calle en el catastro municipal (solo nombres de calles).

Uso:  python diagnostico_calles.py PAJARITOS "LLONA"
"""
import sys

import httpx

from nucleo.loader import config_from_env


def main(terminos: list[str]) -> None:
    calles_url, _ = config_from_env()
    with httpx.Client(timeout=60) as client:
        for termino in terminos:
            t = termino.upper().replace("'", "")
            where = f"UPPER(NOMBRE) LIKE '%{t}%'"
            r = client.get(f"{calles_url}/query", params={
                "where": where, "outFields": "NOMBRE,CLASE,SUF_DIREC",
                "returnGeometry": "false", "f": "json", "resultRecordCount": 50})
            data = r.json()
            print(f"\n== {termino} ==  (where: {where})")
            if "error" in data:
                print("  ERROR:", data["error"])
                continue
            feats = data.get("features", [])
            if not feats:
                print("  Sin resultados. Probar con una parte más corta del nombre.")
            for f in feats:
                a = f["attributes"]
                print(f"  NOMBRE={a.get('NOMBRE')!r}  CLASE={a.get('CLASE')!r}  SUF_DIREC={a.get('SUF_DIREC')!r}")


if __name__ == "__main__":
    main(sys.argv[1:] or ["PAJARITOS", "LLONA"])
