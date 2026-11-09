#!/usr/bin/env bash
# 14-app-radar.sh — Publica "Radar Maipú" (simulador de negocio, Django + GeoDjango) en https://radar.maiproject.cl
#   (el 12 y el 13 ya existen — 12-correo, 13-app-jpltag)
#   - Base PostGIS PROPIA (maipu-radar-db, PostgreSQL 17 + PostGIS 3.5): el PostgreSQL compartido no trae
#     PostGIS y no se toca. Corre como usuario 999, solo lectura, sin capacidades, en una red interna
#     a la que solo llega la app. Datos en /maipu/data/radar-postgis.
#   - Imagen de la app: usuario 10001, solo lectura, sin capacidades, gunicorn en 127.0.0.1:8604.
#     Necesita salida a Internet (red maipu-apps): el informe consulta el GIS municipal en vivo.
#   - Datos del GIS (calles, barrios, patentes vigentes): carga inicial al publicar y recarga semanal
#     (cron). Respaldo diario de la base (14 días) en /maipu/backups/postgres.
#   - Registro DNS firmado (DNSSEC), backend en HAProxy con el certificado comodín.
#   - HAProxy fuerza "geolocation=()" en todas las apps; aquí se permite geolocation=(self) solo para
#     este host ("Usar mi ubicación" del simulador).
#   - MARCHA BLANCA por defecto: todo el sitio solo desde IPs autorizadas (RADAR_SOLO_IPS=si).
#     /admin/ y /api/docs siempre solo desde /etc/haproxy/ips-admin.lst.
# Código: github.com/leomaipu/radarmaipu, entregado como radarmaipu-<commit>.tar.gz junto a este script:
#   git archive --format=tar.gz --prefix=radarmaipu/ -o radarmaipu-$(git rev-parse --short HEAD).tar.gz HEAD
# Idempotente: para publicar una versión nueva, volver a ejecutarlo con el nuevo .tar.gz.
# Uso: sudo bash 14-app-radar.sh [ruta/al/radarmaipu-<commit>.tar.gz]
#      sudo RADAR_SOLO_IPS=no bash 14-app-radar.sh     (abrir a Internet: decisión explícita del municipio)
#      sudo RADAR_PUERTO=8605 bash 14-app-radar.sh     (otro puerto local)
#      sudo RADAR_PRUEBAS=no bash 14-app-radar.sh      (omitir la suite de pruebas; solo en emergencias)
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "Ejecutar con sudo"; exit 1; }
umask 022
trap 'echo "ERROR (código $?) en la línea $LINENO: $BASH_COMMAND" >&2' ERR
DIR_SCRIPT="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
[[ -f "$DIR_SCRIPT/00-config.sh" ]] && source "$DIR_SCRIPT/00-config.sh"

APP=radar
REPO=radarmaipu
ETAPA=14
DOMAIN="${DOMAIN:-maiproject.cl}"
HOST="${APP}.${DOMAIN}"
PUERTO="${RADAR_PUERTO:-8604}"   # 8601 soporte, 8602 reservas, 8603 jpltag
ADMIN_USUARIO="${ADMIN_WEB_USER:-leonardo}"
ADMIN_EMAIL="${EMAIL_ADMIN:-leonardo.trincado@maipu.cl}"
RADAR_SOLO_IPS="${RADAR_SOLO_IPS:-si}"
RADAR_PRUEBAS="${RADAR_PRUEBAS:-si}"
GUNICORN_WORKERS="${GUNICORN_WORKERS:-2}"   # VM de 3,8 GB: ~150 MB la app, ~40 MB la base
GUNICORN_THREADS="${GUNICORN_THREADS:-2}"
MAXCONN=$(( GUNICORN_WORKERS * GUNICORN_THREADS ))
IMG_DB="postgis/postgis:17-3.5"

BASE=/opt/maiproject/apps/$APP
SEC=$BASE/secretos
DATOS=/maipu/data/radar-postgis
RESPALDOS=/maipu/backups/postgres
ZONEFILE="/var/lib/bind/db.${DOMAIN}"
HCFG=/etc/haproxy/haproxy.cfg
HMAP=/etc/haproxy/hosts.map
IPLIST=/etc/haproxy/ips-admin.lst

TGZ="${1:-$(ls -1t "$DIR_SCRIPT"/${REPO}-*.tar.gz 2>/dev/null | head -1 || true)}"
[[ -f "$TGZ" ]] || { echo "Falta el código: ${REPO}-<commit>.tar.gz junto al script (ver encabezado)"; exit 1; }
VERSION="$(basename "$TGZ" .tar.gz | sed "s/^${REPO}-//")"
[[ "$VERSION" =~ ^[0-9a-f]{7,40}$ ]] || { echo "Nombre de archivo inesperado: $TGZ"; exit 1; }
IMG="maipu/${APP}:${VERSION}"
[[ $RADAR_SOLO_IPS == si || $RADAR_SOLO_IPS == no ]] || { echo "RADAR_SOLO_IPS debe ser si o no"; exit 1; }

[[ -f $IPLIST ]] || { echo "Falta $IPLIST (ejecuta antes 08-observabilidad.sh)"; exit 1; }
DUENO="$(docker ps --format '{{.Names}} {{.Ports}}' | grep -E "127\.0\.0\.1:${PUERTO}->" | awk '{print $1}' | head -1 || true)"
if [[ -n "$DUENO" && "$DUENO" != "maipu-$APP" ]]; then echo "El puerto $PUERTO lo usa $DUENO: elegir otro con RADAR_PUERTO=86xx"; exit 1; fi
if [[ -z "$DUENO" ]] && ss -ltn "sport = :$PUERTO" | grep -q LISTEN; then echo "El puerto $PUERTO ya está en uso en el servidor"; exit 1; fi
if grep -qE "127\.0\.0\.1:${PUERTO}([^0-9]|$)" "$HCFG" && ! grep -q "be_${APP}" "$HCFG"; then echo "HAProxy ya usa 127.0.0.1:$PUERTO para otro backend"; exit 1; fi
pw() { openssl rand -base64 48 | tr -d '/+=\n' | cut -c1-"${1:-32}"; }
aviso() { echo "   AVISO: $*"; }

echo "== 0. Respaldo de configuración =="
BK=/var/backups/maipu-${ETAPA}-${APP}-$(date +%Y%m%d-%H%M%S); install -d -m 700 "$BK"
cp -a /etc/haproxy /var/lib/bind "$BK/"
echo "   $BK"
install -d -m 755 "$BASE" "$BASE/fuentes"
install -d -m 700 "$SEC" "$RESPALDOS"
install -d -o 999 -g 999 -m 700 "$DATOS"

###############################################################################
echo "== 1. Código (versión $VERSION) =="
SRC="$BASE/fuentes/$VERSION"
if [[ ! -d "$SRC" ]]; then
  install -d -m 755 "$SRC"
  tar xzf "$TGZ" -C "$SRC" --strip-components=1 --no-same-owner
fi
# Controles mínimos antes de construir (reglas del servidor): se detiene sin tocar nada si alguno falla
[[ -f "$SRC/Containerfile" && -f "$SRC/requirements.txt" ]] || { echo "El código no trae Containerfile y requirements.txt"; exit 1; }
grep -q 'os.environ.get("DJANGO_SECRET_KEY")' "$SRC/radar/settings.py" || { echo "settings.py no lee DJANGO_SECRET_KEY del entorno: se detiene"; exit 1; }
if grep -rqE "SECRET_KEY *= *['\"][^'\"]{8,}" "$SRC/radar"; then echo "El código trae una SECRET_KEY escrita: se detiene"; exit 1; fi
grep -qE '^USER[[:space:]]+[^r0]' "$SRC/Containerfile" || { echo "El Containerfile no fija un USER sin privilegios: se detiene"; exit 1; }
grep -q -- "--hash=sha256:" "$SRC/requirements.txt" || { echo "requirements.txt sin hashes: se detiene"; exit 1; }
if [[ -f "$SRC/.env" ]]; then echo "El paquete trae .env: se detiene"; exit 1; fi
if grep -rqE 'src="https?://|href="https?://[^"]*\.(js|css)|fonts\.googleapis' "$SRC/web/templates" --include=*.html; then
  echo "Hay recursos externos (CDN) en las plantillas: incompatible con la CSP, se detiene"; exit 1
fi
echo "   $SRC"

###############################################################################
echo "== 2. Secretos y variables =="
[[ -f $SEC/django_secret_key ]] || ( umask 077; python3 -c 'import secrets; print(secrets.token_urlsafe(64))' >"$SEC/django_secret_key" )
[[ -f $SEC/db_password ]] || ( umask 077; pw 40 >"$SEC/db_password" )
( umask 077
cat >"$SEC/db.env" <<EOF
POSTGRES_DB=radar
POSTGRES_USER=radar
POSTGRES_PASSWORD=$(cat "$SEC/db_password")
PGDATA=/var/lib/postgresql/data/pgdata
EOF
cat >"$SEC/app.env" <<EOF
DJANGO_SECRET_KEY=$(cat "$SEC/django_secret_key")
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=${HOST},localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=https://${HOST}
DJANGO_DETRAS_DE_PROXY=1
POSTGRES_HOST=db
POSTGRES_DB=radar
POSTGRES_USER=radar
POSTGRES_PASSWORD=$(cat "$SEC/db_password")
GUNICORN_WORKERS=${GUNICORN_WORKERS}
GUNICORN_THREADS=${GUNICORN_THREADS}
TZ=America/Santiago
EOF
)
echo "   $SEC/app.env y $SEC/db.env (600)"

###############################################################################
echo "== 3. Construir la imagen y probarla =="
docker build -q -f "$SRC/Containerfile" -t "$IMG" "$SRC" | sed 's/^/   /'
U="$(docker image inspect -f '{{.Config.User}}' "$IMG")"
[[ -n "$U" && "$U" != root && "$U" != 0 && "$U" != 0:0 ]] || { echo "La imagen corre como root: se detiene"; exit 1; }
echo "   Usuario de la imagen: $U"
docker pull -q "$IMG_DB" | sed 's/^/   /'

# Puerta de calidad: la suite completa corre en la imagen NUEVA contra un PostGIS desechable, en una red
# sin salida a Internet (las pruebas del GIS en vivo quedan fuera). Si falla, no se toca nada publicado.
if [[ $RADAR_PRUEBAS == si ]]; then
  echo -n "   Pruebas de la versión $VERSION: "
  RED_P="maipu-radar-pruebas-$$"; DB_P="maipu-radar-pruebas-db-$$"; LOGP="$(mktemp)"
  limpiar() { docker rm -f "$DB_P" >/dev/null 2>&1 || true; docker network rm "$RED_P" >/dev/null 2>&1 || true; rm -f "$LOGP"; }
  docker network create --internal "$RED_P" >/dev/null
  docker run -d --name "$DB_P" --network "$RED_P" --tmpfs /var/lib/postgresql/data -e POSTGRES_PASSWORD=solo-pruebas \
    "$IMG_DB" >/dev/null
  for i in {1..60}; do docker exec "$DB_P" psql -U postgres -qAt -c 'select 1' >/dev/null 2>&1 && break; sleep 1; done; sleep 2
  if docker run --rm --network "$RED_P" --read-only --tmpfs /tmp:size=128m --cap-drop ALL --security-opt no-new-privileges:true \
       -e DJANGO_SECRET_KEY=solo-pruebas -e POSTGRES_HOST="$DB_P" -e POSTGRES_USER=postgres \
       -e POSTGRES_PASSWORD=solo-pruebas -e POSTGRES_DB=postgres \
       "$IMG" python -m pytest -q -p no:cacheprovider tests >"$LOGP" 2>&1; then
    echo "OK ($(grep -oE '[0-9]+ passed' "$LOGP" | tail -1))"
    limpiar
  else
    echo "FALLARON — no se publica esta versión"; tail -25 "$LOGP" | sed 's/^/      /'
    limpiar; docker rmi "$IMG" >/dev/null 2>&1 || true; exit 1
  fi
fi

cat >"$BASE/compose.yaml" <<EOF
name: maipu-${APP}

x-seguro: &seguro
  restart: unless-stopped
  read_only: true
  cap_drop: [ALL]
  security_opt: ["no-new-privileges:true"]

services:
  db:
    <<: *seguro
    image: ${IMG_DB}
    container_name: maipu-${APP}-db
    user: "999:999"
    command: ["postgres", "-c", "shared_buffers=64MB", "-c", "max_connections=30", "-c", "timezone=UTC"]
    env_file: [./secretos/db.env]
    tmpfs: ["/tmp:size=32m", "/var/run/postgresql:size=8m"]
    volumes: ["${DATOS}:/var/lib/postgresql/data"]
    mem_limit: 384m
    pids_limit: 100
    healthcheck:
      test: ["CMD-SHELL", "psql -U radar -d radar -qAt -c 'select 1' >/dev/null"]
      interval: 15s
      timeout: 5s
      start_period: 60s
      retries: 5
    networks: [interna]

  web:
    <<: *seguro
    image: ${IMG}
    container_name: maipu-${APP}
    env_file: [./secretos/app.env]
    ports: ["127.0.0.1:${PUERTO}:8000"]
    tmpfs: ["/tmp:size=64m"]
    mem_limit: 512m
    pids_limit: 200
    depends_on:
      db: {condition: service_healthy}
    healthcheck:
      test: ["CMD", "python", "-c", "import http.client as h; c=h.HTTPConnection('127.0.0.1', 8000, timeout=5); c.request('GET', '/api/salud', headers={'Host': 'localhost'}); exit(0 if c.getresponse().status == 200 else 1)"]
      interval: 30s
      timeout: 6s
      start_period: 30s
      retries: 3
    networks: [interna, apps]   # apps: salida a Internet (GIS municipal y geocodificador)

networks:
  interna:
    internal: true             # solo la app llega a la base
  apps:
    external: true
    name: maipu-apps
EOF
docker network inspect maipu-apps >/dev/null 2>&1 || docker network create maipu-apps >/dev/null

###############################################################################
echo "== 4. Base, migraciones, datos del GIS y arranque =="
DC=(docker compose -f "$BASE/compose.yaml")
RUN=("${DC[@]}" run --rm -T web)
"${DC[@]}" up -d db 2>&1 | grep -v '^ *$' | sed 's/^/   /'
echo -n "   Esperando a PostGIS"
for i in {1..60}; do
  docker exec maipu-$APP-db psql -U radar -d radar -qAt -c 'select postgis_lib_version()' >/dev/null 2>&1 && { echo " OK ($(docker exec maipu-$APP-db psql -U radar -d radar -qAt -c 'select postgis_lib_version()'))"; break; }
  echo -n "."; sleep 3
  [[ $i -eq 60 ]] && { echo; echo "PostGIS no respondió. Revisa: docker logs --tail 60 maipu-$APP-db"; exit 1; }
done
psqlapp() { docker exec -i maipu-$APP-db psql -U radar -d radar -v ON_ERROR_STOP=1 -qAt "$@"; }
# ¿Esta versión borró o renombró migraciones ya aplicadas? Entonces se detiene antes de tocar nada.
HUERFANAS=""
if [[ "$(psqlapp -c "SELECT to_regclass('public.django_migrations') IS NOT NULL")" == t ]]; then
  for m in $(psqlapp -c "SELECT app||'/'||name FROM django_migrations WHERE app IN ('territorio','tramites')"); do
    [[ -f "$SRC/${m%%/*}/migrations/${m#*/}.py" ]] || HUERFANAS+="${m} "
  done
fi
if [[ -n "$HUERFANAS" ]]; then
  echo "   ATENCIÓN: esta versión borró o renombró migraciones ya aplicadas: ${HUERFANAS}. No se cambió nada."; exit 1
fi
if [[ "$(psqlapp -c "SELECT to_regclass('public.tramites_documentochecklist') IS NOT NULL")" == t ]]; then
  RESP=$RESPALDOS/${APP}-antes-${VERSION}-$(date +%Y%m%d-%H%M%S).dump
  docker exec maipu-$APP-db pg_dump -U radar -Fc radar >"$RESP"; chmod 600 "$RESP"
  echo "   Respaldo previo: $RESP"
fi
"${RUN[@]}" python manage.py migrate --noinput 2>&1 | grep -vE '^\s*$' | tail -3 | sed 's/^/   /'
"${RUN[@]}" python manage.py cargar_gis --si-vacia 2>&1 | tail -1 | sed 's/^/   /'
"${DC[@]}" up -d --remove-orphans 2>&1 | grep -v '^ *$' | sed 's/^/   /'
echo -n "   Esperando a la aplicación"
for i in {1..40}; do
  [[ "$(docker inspect -f '{{.State.Health.Status}}' maipu-$APP 2>/dev/null)" == healthy ]] && { echo " OK"; break; }
  echo -n "."; sleep 3
  [[ $i -eq 40 ]] && { echo; echo "No quedó sana. Revisa: docker logs --tail 60 maipu-$APP"; exit 1; }
done

# Administrador inicial (la contraseña queda en un archivo 600; no se imprime)
CRED=$SEC/credenciales-admin.txt
if [[ ! -f $CRED ]]; then
  ( umask 077; printf 'RADAR_ADMIN_USUARIO=%s\nRADAR_ADMIN_CLAVE=%s\n' "$ADMIN_USUARIO" "$(pw 20)-$(pw 4)" >"$CRED" )
fi
# shellcheck disable=SC1090
source "$CRED"
EXISTE="$(docker exec maipu-$APP python manage.py shell -c \
  "from django.contrib.auth import get_user_model as g; print(g().objects.filter(username='${RADAR_ADMIN_USUARIO}').exists())" 2>/dev/null | tail -1)"
if [[ "$EXISTE" != "True" ]]; then
  docker exec -e DJANGO_SUPERUSER_PASSWORD="$RADAR_ADMIN_CLAVE" maipu-$APP python manage.py createsuperuser \
    --noinput --username "$RADAR_ADMIN_USUARIO" --email "$ADMIN_EMAIL" 2>&1 | tail -1 | sed 's/^/   /'
else
  echo "   Administrador '$RADAR_ADMIN_USUARIO' ya existe"
fi
unset RADAR_ADMIN_CLAVE
docker images --format '{{.Repository}}:{{.Tag}}' "maipu/${APP}" | grep -vx "$IMG" | xargs -r docker rmi -f >/dev/null 2>&1 || true

# Recarga semanal del GIS y respaldo diario de la base (14 días)
cat >/etc/cron.d/maipu-radar <<EOF
# 14-app-radar.sh: Radar Maipú
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
# Domingo 04:30: recarga calles, barrios y patentes desde el GIS municipal
30 4 * * 0 root docker exec maipu-${APP} python manage.py cargar_gis >>/var/log/maipu-radar-carga.log 2>&1
# Diario 03:40: respaldo de la base (checklist de Rentas, usuarios y datos cargados)
40 3 * * * root umask 077; docker exec maipu-${APP}-db pg_dump -U radar -Fc radar >${RESPALDOS}/${APP}-\$(date +\%F).dump && find ${RESPALDOS} -name '${APP}-20*.dump' -mtime +14 -delete
EOF
chmod 644 /etc/cron.d/maipu-radar
echo "   Cron: /etc/cron.d/maipu-radar (recarga del GIS los domingos, respaldo diario)"

###############################################################################
echo "== 5. DNS: ${HOST} (zona firmada con DNSSEC) =="
PUBIP="$(dig +short +norec @127.0.0.1 "ns1.${DOMAIN}" A)"
if [[ -z "$(dig +short +norec @127.0.0.1 "$HOST" A)" ]]; then
  TMPZ="$(mktemp)"; EDITA="$(mktemp)"
  cat >"$EDITA" <<'PY'
import sys, time
path, dom, ip, *subs = sys.argv[1:]
out = []
for l in open(path).read().splitlines():
    f = l.split()
    if len(f) >= 11 and f[3] == "SOA":
        old = int(f[6]); f[6] = str(max(old + 1, int(time.strftime("%Y%m%d")) * 100 + 1)); l = " ".join(f)
        print(f"   Serial {old} -> {f[6]}")
    out.append(l)
for s in subs:
    out.append(f"{s}.{dom}. 3600 IN A {ip}")
    print(f"   + {s}.{dom} A {ip}")
open(path, "w").write("\n".join(out) + "\n")
PY
  rndc freeze "$DOMAIN"
  if named-compilezone -q -o "$TMPZ" "$DOMAIN" "$ZONEFILE" \
     && python3 "$EDITA" "$TMPZ" "$DOMAIN" "$PUBIP" "$APP" \
     && named-checkzone -q "$DOMAIN" "$TMPZ" \
     && install -o bind -g bind -m 644 "$TMPZ" "$ZONEFILE"; then
    rndc thaw "$DOMAIN" | sed 's/^/   /'
  else
    echo "   Falló la edición de la zona; se deja como estaba"
    rndc thaw "$DOMAIN" || true; rm -f "$TMPZ" "$EDITA"; exit 1
  fi
  rm -f "$TMPZ" "$EDITA"; sleep 3; rndc notify "$DOMAIN" >/dev/null || true
else
  echo "   El registro ya existe"
fi
printf '   %-24s %-15s firma: %s\n' "$HOST" "$(dig +short +norec @127.0.0.1 "$HOST" A)" \
  "$(dig +dnssec +norec @127.0.0.1 "$HOST" A | grep -q RRSIG && echo OK || echo FALTA)"

###############################################################################
echo "== 6. HAProxy =="
grep -q "^${HOST}[[:space:]]" "$HMAP" || printf '%-25s %s\n' "$HOST" "be_${APP}" >>"$HMAP"
python3 - "$HCFG" "$HOST" "$APP" "$PUERTO" "$IPLIST" "$RADAR_SOLO_IPS" "$MAXCONN" "$ETAPA" <<'PY'
import sys, re
cfg, host, app, puerto, iplist, solo_ips, maxconn, etapa = sys.argv[1:]
t = open(cfg).read()
t = re.sub(r"\n?[ \t]*# >>> " + etapa + "-" + app + r"\b.*?# <<< " + etapa + "-" + app + r"[^\n]*\n", "\n", t, flags=re.S)
reglas = [
    f"    # >>> {etapa}-{app}: {host}",
    f"    acl host_{app}     req.hdr(host),field(1,:),lower -m str {host}",
    f"    acl ip_admin_{app} src -f {iplist}",
    f"    acl priv_{app}     path_beg /admin /api/docs /api/openapi.json",
    f"    # La app no recibe archivos: cualquier cuerpo de más de 1 MB se corta aquí",
    f"    http-request deny deny_status 413 if host_{app} {{ req.hdr_val(content-length) gt 1048576 }}",
    f"    # Administración (checklist de Rentas) y documentación de la API: solo IPs autorizadas",
    f"    http-request deny deny_status 403 if host_{app} priv_{app} !ip_admin_{app}",
]
if solo_ips == "si":
    reglas += [f"    # Marcha blanca: todo el sitio solo desde IPs autorizadas",
               f"    http-request deny deny_status 403 if host_{app} !ip_admin_{app}"]
reglas += [
    f"    # \"Usar mi ubicación\" del simulador: geolocation=(self) solo para este host (el resto sigue con ())",
    f"    http-request set-var(txn.geo_{app}) bool(true) if host_{app}",
    f"    http-response set-header Permissions-Policy \"camera=(), microphone=(), geolocation=(self)\" if {{ var(txn.geo_{app}) -m bool }}",
    f"    # <<< {etapa}-{app}",
]
marca = "    # Enrutamiento por nombre"
assert marca in t, "No se encontró el bloque de enrutamiento en haproxy.cfg"
t = t.replace(marca, "\n".join(reglas) + "\n\n" + marca, 1)
t = re.sub(r"\n{3,}", "\n\n", t)
back = f"""
# >>> {etapa}-{app}: backend
backend be_{app}
    # Sala de espera: como máximo {maxconn} solicitudes a la vez en gunicorn; el resto espera hasta 30 s
    timeout queue 30s
    option httpchk
    http-check send meth GET uri /api/salud hdr Host {host}
    server {app} 127.0.0.1:{puerto} check inter 15s maxconn {maxconn}
# <<< {etapa}-{app}
"""
t = t.rstrip("\n") + "\n" + back
open(cfg, "w").write(t)
PY
if haproxy -c -q -f "$HCFG"; then
  systemctl reload haproxy
  echo "   HAProxy recargado (todo el sitio solo IPs autorizadas: $RADAR_SOLO_IPS; máx. $MAXCONN simultáneas)"
else
  echo "   La configuración de HAProxy no es válida: se restaura la anterior ($BK/haproxy)"
  cp -a "$BK/haproxy/." /etc/haproxy/; haproxy -c -q -f "$HCFG" && systemctl reload haproxy; exit 1
fi

###############################################################################
echo "== 7. Pruebas =="
sleep 3
c() { curl -s -o /dev/null -w '%{http_code}' --resolve "${HOST}:443:127.0.0.1" "https://${HOST}$1" "${@:2}" || true; }
d() { curl -s -o /dev/null -w '%{http_code}' -H "Host: ${HOST}" -H "X-Forwarded-Proto: https" "http://127.0.0.1:${PUERTO}$1" || true; }
ok() { printf '   %-52s %s\n' "$1" "$2"; }
ESPERADO=$([[ $RADAR_SOLO_IPS == si ]] && echo 403 || echo 200)
ok "https://${HOST}/ desde el servidor, no autorizado (${ESPERADO})" "$(c /)"
ok "/admin/ desde IP no autorizada (403)" "$(c /admin/)"
ok "/api/docs desde IP no autorizada (403)" "$(c /api/docs)"
ok "Cuerpo de 2 MB (413)" "$(c /api/salud -X POST -H 'Content-Length: 2097152' --max-time 5)"
ok "App: simulador (200)" "$(d /)"
ok "App: informe del panel (200)" "$(d '/panel/informe/?lat=-33.48&lon=-70.76&giro=bazar')"
ok "App: manifest y service worker (200 200)" "$(d /manifest.webmanifest) $(d /sw.js)"
ok "App: /api/docs cerrado en producción (404)" "$(d /api/docs)"
H="$(curl -sI -H "Host: ${HOST}" -H 'X-Forwarded-Proto: https' "http://127.0.0.1:${PUERTO}/")"
ok "Content-Security-Policy" "$(grep -i '^content-security-policy:' <<<"$H" | cut -c1-60 | tr -d '\r')…"
ok "Datos del GIS (patentes, calles)" "$(docker exec maipu-$APP python manage.py shell -c 'from territorio.models import Patente, Calle; print(Patente.objects.count(), Calle.objects.count())' 2>/dev/null | tail -1)"
ok "El informe consulta el GIS en vivo" "$(curl -s -H "Host: ${HOST}" -H 'X-Forwarded-Proto: https' "http://127.0.0.1:${PUERTO}/api/informe?lat=-33.48&lon=-70.76&giro=bazar" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["zona"].get("ordenanza"), d["resultado"]["estado"])' 2>/dev/null)"
ok "Contenedores corren como (app, base)" "$(docker exec maipu-$APP id -u) $(docker exec maipu-$APP-db id -u)"
ok "Sistema de archivos de solo lectura (app, base)" \
  "$(docker exec maipu-$APP sh -c 'touch /app/x 2>/dev/null && echo ESCRIBIBLE || echo OK') $(docker exec maipu-$APP-db sh -c 'touch /x 2>/dev/null && echo ESCRIBIBLE || echo OK')"
ok "Base sin puertos publicados" "$(docker port maipu-$APP-db | grep -q . && echo REVISAR || echo OK)"
ok "Chequeo de seguridad de Django" "$(docker exec maipu-$APP python manage.py check --deploy 2>&1 | tail -1)"
ok "Migraciones pendientes" "$(docker exec maipu-$APP python manage.py migrate --check >/dev/null 2>&1 && echo ninguna || echo HAY)"
echo
echo "Listo: https://${HOST}  (versión ${VERSION}; todo el sitio solo IPs autorizadas: ${RADAR_SOLO_IPS})"
echo "Administrador de Django: sudo cat $CRED  → https://${HOST}/admin/ (checklist de Rentas)"
echo "Logs: https://logs.${DOMAIN} (maipu-${APP}, maipu-${APP}-db)"
