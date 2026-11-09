# Despliegue en maiproject.cl

Radar Maipú se publica en **https://radar.maiproject.cl** con el script
[`deploy/servidor/14-app-radar.sh`](../deploy/servidor/14-app-radar.sh), con el mismo patrón que
el resto de las apps del servidor (`09-app-soporte`, `10-app-reservas`, `13-app-jpltag`). El script
va en la carpeta `~/maiproject-scripts/` del servidor, junto a `00-config.sh`.

## Arquitectura

```
Internet ─► HAProxy (TLS comodín, HSTS, IPs de admin) ─► 127.0.0.1:8604 ─► maipu-radar (gunicorn, UID 10001)
                                                                             │ red interna del proyecto
                                                                             ├──► maipu-radar-db (PostGIS 17-3.5, UID 999)
                                                                             │    /maipu/data/radar-postgis
                                                                             └──► red maipu-apps ─► gis.maipu.cl (informe en vivo)
```

- **Base PostGIS propia.** El PostgreSQL compartido del servidor (`maipu-postgres`) no trae la extensión
  PostGIS, y modificarlo afectaría a las demás apps. Por eso Radar tiene su propio PostgreSQL 17 + PostGIS
  en una red interna a la que solo llega la app (sin puertos publicados).
- **Contenedores endurecidos.** Solo lectura, sin capacidades, `no-new-privileges`, usuarios sin
  privilegios (10001 la app, 999 la base). `collectstatic` corre al construir la imagen.
- **Salida a Internet.** La app está en `maipu-apps` porque el informe consulta el GIS municipal y el
  geocodificador en vivo. El navegador carga el mapa base de Esri y las imágenes del GIS directamente
  (la CSP lo permite solo para esos orígenes).

## Publicar una versión

```bash
# En el repositorio (git archive toma HEAD: el código debe estar commiteado)
git archive --format=tar.gz --prefix=radarmaipu/ -o radarmaipu-$(git rev-parse --short HEAD).tar.gz HEAD
scp radarmaipu-<commit>.tar.gz deploy/servidor/14-app-radar.sh maiproject:maiproject-scripts/
# En el servidor
cd ~/maiproject-scripts && sudo bash 14-app-radar.sh radarmaipu-<commit>.tar.gz | tee salida-14-$(date +%F).txt
```

El script se detiene **sin tocar lo publicado** si la versión trae una `SECRET_KEY` escrita, un
`.env`, recursos de CDN en las plantillas, dependencias sin hashes, una imagen que corre como root,
migraciones reescritas o **si falla la suite de pruebas** (corre en la imagen nueva contra un PostGIS
desechable, sin salida a Internet). Antes de migrar respalda la base; si la configuración nueva de
HAProxy no es válida, restaura la anterior.

## Marcha blanca

Por defecto todo el sitio responde solo a las IPs de administración (`/etc/haproxy/ips-admin.lst`).
Abrirlo a Internet es una decisión del municipio:

```bash
sudo RADAR_SOLO_IPS=no bash 14-app-radar.sh radarmaipu-<commit>.tar.gz
```

`/admin/` (checklist de Rentas) y `/api/docs` quedan siempre restringidos a esas IPs.

## Detalles del proxy

- HAProxy termina TLS y pone HSTS; Django no los repite (`DJANGO_DETRAS_DE_PROXY=1` silencia esos dos
  avisos de `check --deploy`, que queda sin observaciones).
- HAProxy fuerza `Permissions-Policy: geolocation=()` en todas las apps. El bloque de Radar lo cambia a
  `geolocation=(self)` solo para `radar.maiproject.cl`, para que funcione "Usar mi ubicación".
- Chequeo de salud: `GET /api/salud` (la app responde y la base acepta consultas).
- Cuerpos de más de 1 MB se cortan con 413 (la app no recibe archivos).

## Tareas programadas (`/etc/cron.d/maipu-radar`)

| Cuándo | Qué |
| --- | --- |
| Domingos 04:30 | `cargar_gis`: recarga calles, barrios y patentes. Log en `/var/log/maipu-radar-carga.log` |
| Diario 03:40 | `pg_dump` de la base en `/maipu/backups/postgres/radar-AAAA-MM-DD.dump` (14 días) |

## Secretos (en `/opt/maiproject/apps/radar/secretos/`, 600)

`django_secret_key`, `db_password` (los genera el script la primera vez), `app.env`, `db.env` y
`credenciales-admin.txt` (usuario administrador de Django; `sudo cat` para verla).

## Pendientes

- Incluir los respaldos de `/maipu/backups/postgres/radar-*` en el respaldo externo del servidor.
- Abrir a Internet cuando el municipio lo decida (ver "Marcha blanca").
