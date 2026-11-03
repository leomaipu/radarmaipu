# Prueba completa del MVP en Windows (PowerShell). Requisito: Python 3.11 o superior.
Set-Location (Split-Path -Parent $PSScriptRoot)

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --quiet -r requirements.txt

Write-Host "== 1. Pruebas automatizadas =="
.\.venv\Scripts\python.exe -m pytest -q tests

Write-Host "== 2. Medicion de las capas municipales (solo conteos y valores no personales) =="
.\.venv\Scripts\python.exe medir.py | Tee-Object -FilePath informe_medicion.md

Write-Host "== 3. Servidor =="
Write-Host "Para abrir la API (carga los datos al iniciar): .\.venv\Scripts\uvicorn.exe app.api:app --port 8000"
Write-Host "Luego visita http://127.0.0.1:8000/docs"
