#!/usr/bin/env bash
# Prueba completa del MVP en tu computador (Linux / macOS).
# Requisitos: Python 3.11 o superior.
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m venv .venv
.venv/bin/python -m pip install --quiet -r requirements.txt

echo "== 1. Pruebas automatizadas =="
.venv/bin/python -m pytest -q tests

echo "== 2. Medición de las capas municipales (solo conteos y valores no personales) =="
.venv/bin/python medir.py | tee informe_medicion.md || echo "(sin conexión al GIS: revisar red)"

echo "== 3. Carga y servidor =="
echo "Para cargar los datos: .venv/bin/python cargar.py"
echo "Para abrir la API:     .venv/bin/uvicorn app.api:app --port 8000"
echo "Luego visita http://127.0.0.1:8000/docs"
