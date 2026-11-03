# Radar Maipú: MVP

Portal web progresivo para consultar, sobre un punto del mapa de Maipú, la calle más cercana
y las patentes comerciales próximas. Esta versión es un MVP de backend con datos del catastro
municipal y de patentes 2026.

## Prueba en tu computador

Requisito: Python 3.11 o superior y conexión a internet.

- **Linux / macOS**: en la carpeta del proyecto, ejecuta `bash scripts/prueba_local.sh`.
- **Windows**: en PowerShell, ejecuta `powershell -ExecutionPolicy Bypass -File scripts\prueba_local.ps1`.

El script hace tres cosas:
1. Instala dependencias fijadas (`requirements.txt`) en un entorno `.venv` local.
2. Corre las pruebas automatizadas.
3. Ejecuta `medir.py`, que consulta a gis.maipu.cl solo conteos y valores de campos no
   personales y guarda el resultado en `informe_medicion.md`. Ese informe responde los
   temas pendientes 1 y 2 de la lista de abajo.

Para abrir la API: `.venv/bin/uvicorn app.api:app --port 8000` y visitar `http://127.0.0.1:8000/docs`.
La API carga los datos reales al iniciar, en segundo plano (ver "Carga de datos").

Si el script no puede conectarse al GIS desde tu red, el informe lo indicará. En ese caso
revisa que tu computador tenga salida a `gis.maipu.cl` (algunas redes institucionales la
bloquean).

## Protección de datos personales

- Solo se cargan campos de una lista blanca (`app/privacy.py`). RUT, razón social,
  representante, su dirección personal y códigos SII no entran a la base. La dirección del
  negocio (`DIRECCION`) sí, con aprobación jurídica del 2026-11-03.
- `direc_nego` sigue fuera hasta confirmación escrita de Jurídico.
- Cada capa pide al servidor solo sus campos permitidos (`app/loader.py`), así que los datos
  personales ni siquiera salen del servicio municipal.
- Las pruebas verifican que ningún campo personal llegue a la API (`tests/test_privacy.py`,
  `tests/test_loader.py`).

## Puesta en marcha

```bash
python3 -m venv .venv && .venv/bin/pip install fastapi uvicorn httpx pytest
.venv/bin/python -m pytest -q tests                # pruebas
.venv/bin/uvicorn app.api:app --host 127.0.0.1 --port 8000   # carga desde ArcGIS al iniciar (requiere red a gis.maipu.cl)
```

## Carga de datos

La API responde desde que inicia y carga los datos en segundo plano. `GET /api/health` informa
el avance en `carga`:

- `cargando`: descargando las capas (hasta 3 intentos); los conteos siguen en 0.
- `regeocodificando`: datos ya disponibles; las patentes con Status U o sin punto lo reciben de a poco.
  Puede tardar más de una hora.
- `lista`: terminó.
- `lista_sin_regeocodificar`: hay datos, pero la re-geocodificación se interrumpió (ver el log).
- `error`: no se pudo descargar; reiniciar la API para reintentar (ver el log).

Las patentes que el GIS publica sin coordenadas (`patentes_sin_punto` en `/api/health`) no
aparecen en `/api/patentes` ni `/api/punto`. Todas se re-geocodifican a partir de `DIRECCION`
y reciben punto si el score alcanza el umbral; las demás siguen sin punto.

`cargar.py` sirve solo para probar la carga desde la consola: sus datos no llegan a la API.
Usar un solo worker de uvicorn: cada worker tendría su propia copia y haría su propia carga.

Las URLs del GIS se pueden cambiar con `RM_GIS_BASE` o `RM_CALLES_URL`, sin tocar el código.

## Endpoints

- `GET /api/health`: fase de la carga, conteos cargados y patentes sin punto.
- `GET /api/calles?q=erraz`: busca calles por nombre (sin geometría).
- `GET /api/patentes?minlon=&minlat=&maxlon=&maxlat=`: patentes dentro de un área.
- `GET /api/punto?lon=&lat=&radio_m=150`: calle más cercana y patentes en el radio.

## Limitaciones conocidas del MVP

- El almacén está en memoria: se pierde al reiniciar y no escala. Producción debe usar PostGIS.
- La búsqueda de calles es por subcadena simple, sin normalización de tildes ni abreviaturas.
- La distancia es aproximada (equirectangular local), suficiente a escala comunal.
- No hay interfaz web PWA todavía; el MVP expone la API.

## Dominios confirmados (2026-11-03)

Los valores están en `config/dominios.json`. Cambiarlos no requiere tocar el código.

- `CLASE` de calles: PBN = Paso bajo nivel, PSN = Paso sobre nivel, PTE = Puente, CARRE = Carretera.
- `Status` de patentes: M = Match (geocodificación con match), T = Target (objetivo), U = Unmatch (sin match).
- `estado_pat`: el dato publicado escribe `BLOQUEDADA`; el nombre oficial es `BLOQUEADA`.
  El filtro usa el valor publicado y la API muestra el nombre oficial.
- Patentes bloqueadas: no se muestran (decisión municipal, 2026-11-03). Se controla con `estados_ocultos` en `config/dominios.json`.

Documento para el SITMA: `docs/briefing_sitma.md`.

## Temas pendientes

1. Porcentaje de patentes con `Score` alto, para decidir si los puntos sirven en el mapa.
2. Revisar si una patente aparece en dos capas.
3. Confirmar por escrito con Jurídico si `direc_nego` también queda aprobado (dirección del negocio) y de las condiciones
   de uso de los datos de catastro.
4. Confirmar con el SITMA si el geocodificador BETA tendrá endpoint de producción (ver `docs/briefing_sitma.md`).
5. Ejecutar la carga desde maiproject.cl: el entorno de trabajo no tiene acceso verificado a
   gis.maipu.cl.
6. Validar el flujo de patente comercial con el área de rentas y el checklist de documentos.
7. Repositorio: no se pudo crear `radarmaipu` desde esta sesión (ver mensaje anterior).
8. Interfaz PWA mobile first y manual de marca (Rubik y paleta), aún sin implementar.
