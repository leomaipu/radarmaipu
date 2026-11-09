"""Configuración de Radar Maipú. Todo lo que cambia entre ambientes viene de variables de entorno."""
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(nombre: str, defecto: bool = False) -> bool:
    return os.environ.get(nombre, "1" if defecto else "0").lower() in ("1", "true", "si", "yes")


DEBUG = _env_bool("DJANGO_DEBUG")
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or ("dev-inseguro" if DEBUG else None)
if not SECRET_KEY:
    raise RuntimeError("Falta DJANGO_SECRET_KEY")
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if h]
CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",
    "territorio",
    "tramites",
    "web",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "web.seguridad.PoliticaDeContenido",
]

ROOT_URLCONF = "radar.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "web.context.ajustes_publicos",
    ]},
}]
WSGI_APPLICATION = "radar.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "HOST": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        "NAME": os.environ.get("POSTGRES_DB", "radar"),
        "USER": os.environ.get("POSTGRES_USER", "radar"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "radar"),
        "CONN_MAX_AGE": 60,
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

LANGUAGE_CODE = "es-cl"
TIME_ZONE = "America/Santiago"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
                    if not DEBUG else "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
if not DEBUG:
    SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    # Activar cuando el sitio se sirva solo por HTTPS (normalmente detrás del proxy municipal).
    SECURE_SSL_REDIRECT = _env_bool("DJANGO_SSL_REDIRECT")
    SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", "0"))
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
# Detrás del proxy del servidor (HAProxy), HSTS y la redirección a HTTPS los pone el proxy: un solo
# responsable, sin cabeceras duplicadas. Por eso se silencian esos dos avisos de check --deploy.
if _env_bool("DJANGO_DETRAS_DE_PROXY"):
    SILENCED_SYSTEM_CHECKS = ["security.W004", "security.W008"]

LOGGING = {
    "version": 1,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {"httpx": {"level": "WARNING"}},
}

# Mapa base: lienzo gris de Esri (sin clave, exige atribución; detalle hasta zoom 16) y, a nivel de calle,
# soleras, predios y áreas verdes del GIS municipal. Todo configurable por variables de entorno.
RADAR = {
    "TILES_URL": os.environ.get(
        "RM_TILES_URL", "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"),
    "TILES_REFERENCIA_URL": os.environ.get(
        "RM_TILES_REFERENCIA_URL",
        "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}"),
    "TILES_MAX_NATIVO": int(os.environ.get("RM_TILES_MAX_NATIVO", "16")),
    "TILES_ATTRIBUTION": os.environ.get(
        "RM_TILES_ATTRIBUTION", "Mapa base: Esri, HERE, Garmin, &copy; OpenStreetMap · Cartografía: GIS Municipalidad de Maipú"),
    "BASE_MUNICIPAL": os.environ.get("RM_BASE_MUNICIPAL_URL", "https://gis.maipu.cl/server/rest/services/MAIPU/BaseMaipu/MapServer"),
    "PRC_MAPSERVER": os.environ.get("RM_PRC_URL", "https://gis.maipu.cl/server/rest/services/MAIPU/PRCMaipu/MapServer"),
    "CENTRO": [-33.5106, -70.7574],
    "API_DOCS_PUBLICA": _env_bool("RM_API_DOCS_PUBLICA"),
    "RADIO_COMERCIO_M": 300,
}
