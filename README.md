# Radar Maipú

Simulador web progresivo (PWA) para vecinos y vecinas que quieren emprender. Muestra si un giro es compatible con el Plan Regulador Comunal de Maipú en un punto del mapa, con sus condiciones, las áreas de riesgo, el comercio cercano y los próximos pasos. Es un **informe orientativo**: no reemplaza el Certificado de Informaciones Previas ni la resolución de la DOM o de Rentas.

## Stack

| Capa | Tecnología |
| --- | --- |
| Backend | Django 5.2 LTS + GeoDjango, API con Django Ninja (`/api/`, documentación en `/api/docs`) |
| Base de datos | PostgreSQL 16 + PostGIS 3.4 |
| Interfaz | Plantillas Django + Leaflet 1.9 + HTMX 2, sin paso de compilación. PWA con manifest y service worker |
| Motor normativo | `nucleo/` (Python puro, sin dependencias de Django) y reglas en `config/prc/` |
| Ejecución | Contenedores (podman o docker). La imagen incluye GDAL, GEOS y PROJ |

## Estructura

```
radar/       configuración del proyecto Django (settings por variables de entorno)
nucleo/      motor: evaluación zona × giro, informe, cliente GIS, geocodificador, lista blanca de privacidad
api/         API pública (Django Ninja) y comercio cercano
territorio/  modelos PostGIS (calles, barrios, patentes), comando cargar_gis y bitácora de cargas
tramites/    checklist de documentos de Rentas, editable en /admin
web/         sitio del vecino: plantillas, CSS, JS, PWA y manual de marca aplicado
config/      reglas del PRC, giros, dominios y servicios externos (se editan sin tocar código)
tests/       pruebas (pytest + pytest-django)
```

## Puesta en marcha (desarrollo)

Requisito: podman (con `systemctl --user start podman.socket`) o docker, ambos con compose.

```bash
podman compose up -d                                   # PostGIS + Django en http://127.0.0.1:8000
podman compose exec web python manage.py cargar_gis    # copia calles, barrios y patentes del GIS a PostGIS
podman compose exec web python manage.py createsuperuser   # para entrar a /admin
```

- Al levantar los contenedores, si la base está vacía se carga sola (`cargar_gis --si-vacia`, con 3 reintentos).
- `cargar_gis --regeocodificar` asigna punto a las patentes sin match. Tarda más de una hora; se puede interrumpir y retomar, y los puntos se conservan en las cargas siguientes.
- Cada carga queda registrada en `/admin` (Cargas del GIS) y en `GET /api/health`.
- El informe consulta el Plan Regulador **en vivo** en el GIS municipal: no depende de la carga.

## Pruebas

```bash
podman compose exec web python -m pytest -q tests          # 201 pruebas
podman compose exec web python -m pytest -q -m gis tests   # en vivo contra gis.maipu.cl
```

Pruebas de navegador (flujos completos en Chrome, con la app corriendo):

```bash
python -m venv .venv-e2e && .venv-e2e/bin/pip install playwright pytest
.venv-e2e/bin/python -m pytest tests_e2e -p no:django -o addopts=""
```

## Producción

La imagen (`Containerfile`) corre gunicorn y sirve los estáticos con whitenoise (nombres con hash, caché inmutable). Variables de entorno:

| Variable | Uso |
| --- | --- |
| `DJANGO_SECRET_KEY` | Obligatoria |
| `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS` | Dominio público |
| `DJANGO_SSL_REDIRECT=1`, `DJANGO_HSTS_SECONDS` | Cuando el sitio se sirva solo por HTTPS |
| `POSTGRES_HOST`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Base de datos PostGIS |
| `RM_PRC_URL`, `RM_GEOCODER_URL`, `RM_GIS_BASE`, `RM_BARRIOS_URL` | Servicios del GIS (opcional) |
| `RM_TILES_URL`, `RM_TILES_REFERENCIA_URL`, `RM_TILES_ATTRIBUTION`, `RM_BASE_MUNICIPAL_URL` | Mapa base (opcional; la CSP se ajusta sola) |
| `RM_API_DOCS_PUBLICA=1` | Publicar `/api/docs` en producción (por defecto solo en desarrollo) |

Despliegue en el servidor municipal (radar.maiproject.cl): ver `docs/deploy.md` y `deploy/servidor/14-app-radar.sh`.

La PWA exige HTTPS en producción (el service worker solo se registra en `localhost` o con HTTPS).

## Mapa

- **Base:** lienzo gris claro de Esri (sin clave; exige atribución). Desde el zoom 16 se suman soleras, predios y áreas verdes de `MAIPU/BaseMaipu` del GIS municipal.
- **Plan Regulador:** imagen oficial de `MAIPU/PRCMaipu` (capas 1 a 4) con su leyenda, servida por `/panel/leyenda/` con caché de un día.
- **Comercio cercano:** patentes vigentes a menos de 300 m, agrupadas. En magenta, las de rubro similar (aproximado: la actividad es texto libre).

## Protección de datos personales

- Solo se cargan campos de una lista blanca (`nucleo/privacy.py`). RUT, razón social, representante, su dirección personal y códigos SII no entran a la base. La dirección del negocio (`DIRECCION`) sí, con aprobación jurídica del 2026-11-03.
- `direc_nego` sigue fuera hasta confirmación escrita de Jurídico.
- Cada capa pide al servidor solo sus campos permitidos (`nucleo/loader.py`), así que los datos personales ni siquiera salen del servicio municipal.
- Las pruebas verifican que ningún campo personal llegue a la base ni a la API (`tests/test_privacy.py`, `tests/test_loader.py`, `tests/test_django.py`, `tests/test_informe.py`).

## Dominios confirmados (2026-11-03)

Los valores están en `config/dominios.json`. Cambiarlos no requiere tocar el código.

- `CLASE` de calles: PBN = Paso bajo nivel, PSN = Paso sobre nivel, PTE = Puente, CARRE = Carretera.
- `Status` de patentes: M = Match, T = Target, U = Unmatch.
- `estado_pat`: el dato publicado escribe `BLOQUEDADA`; el nombre oficial es `BLOQUEADA`. Las patentes bloqueadas no se muestran (`estados_ocultos`).

Documento para el SITMA: `docs/briefing_sitma.md`. Alcance y reglas del informe: `mvp_informe_orientativo.md`.

## Temas pendientes

1. Lista oficial de documentos de Rentas: se carga en `/admin` → Checklist de Rentas, sin tocar código.
2. Confirmar por escrito con Jurídico `direc_nego` y las condiciones de uso de los datos de catastro.
3. Endpoint de producción del geocodificador (hoy BETA; ver `docs/briefing_sitma.md`).
4. Mapa base definitivo: confirmar las condiciones de uso de Esri o publicar `BaseMaipu` como teselas cacheadas en Web Mercator.
5. Pendientes normativos: ver la sección 9 de `mvp_informe_orientativo.md`.
