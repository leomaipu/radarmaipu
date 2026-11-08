"""Política de seguridad de contenido (CSP). Sin JavaScript en línea: los datos van con json_script.

Los orígenes de imágenes del mapa salen de la configuración (RADAR), así que cambiar el mapa base
por variable de entorno no exige tocar esta política.
"""
from urllib.parse import urlsplit

from django.conf import settings


def _origen(url: str) -> str | None:
    partes = urlsplit(url.replace("{s}", "a"))
    if not partes.scheme or not partes.netloc:
        return None
    host = partes.netloc
    if "{s}" in url:  # subdominios a, b, c… de un servidor de teselas
        host = "*." + host.split(".", 1)[1]
    return f"{partes.scheme}://{host}"


def _politica() -> str:
    r = settings.RADAR
    origenes = sorted({o for o in (_origen(r[k]) for k in ("TILES_URL", "TILES_REFERENCIA_URL", "BASE_MUNICIPAL",
                                                          "PRC_MAPSERVER")) if o})
    mapa = " ".join(origenes)
    return "; ".join([
        "default-src 'self'",
        "script-src 'self'",
        # Leaflet y HTMX fijan estilos en línea en los elementos del mapa.
        "style-src 'self' 'unsafe-inline'",
        f"img-src 'self' data: blob: {mapa}",
        f"connect-src 'self' {mapa}",
        "font-src 'self'",
        "manifest-src 'self'",
        "worker-src 'self'",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "object-src 'none'",
    ])


class PoliticaDeContenido:
    def __init__(self, get_response):
        self.get_response = get_response
        self.politica = _politica()

    def __call__(self, request):
        r = self.get_response(request)
        if not request.path.startswith(("/admin/", "/api/docs")):
            r.setdefault("Content-Security-Policy", self.politica)
        r.setdefault("Permissions-Policy", "geolocation=(self), camera=(), microphone=()")
        return r
