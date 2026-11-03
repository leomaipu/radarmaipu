"""Prueba la carga desde ArcGIS e imprime los conteos. Uso: python cargar.py

No deja datos disponibles para la API: el almacén vive en la memoria de este proceso.
La API carga sus propios datos al iniciar (ver app/carga.py).
"""
import httpx

from app.carga import cargar_en_store
from app.regeocode import regeocodificar
from app.store import Store

if __name__ == "__main__":
    store = Store()
    with httpx.Client() as client:
        counts = cargar_en_store(store, client)
        print("Carga completa:", counts, flush=True)
        print("Re-geocodificación:", regeocodificar(store.patentes, client))
