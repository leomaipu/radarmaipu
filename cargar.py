"""Carga los datos desde ArcGIS al almacén en memoria. Uso: python cargar.py"""
import httpx

from app.api import store
from app.loader import config_from_env, load_all
from app.regeocode import regeocodificar


def sink(kind: str, rec: dict) -> None:
    (store.calles if kind == "calle" else store.patentes).append(rec)


if __name__ == "__main__":
    calles_url, patente_layers = config_from_env()
    with httpx.Client() as client:
        counts = load_all(client, calles_url, patente_layers, sink)
        resumen = regeocodificar(store.patentes, client)
    print("Carga completa:", counts)
    print("Re-geocodificación (Status U):", resumen)
