"""Gunicorn en producción (contenedor de solo lectura, usuario 10001). Valores por variables de entorno."""
import os

bind = "0.0.0.0:8000"
workers = int(os.environ.get("GUNICORN_WORKERS", "2"))
threads = int(os.environ.get("GUNICORN_THREADS", "2"))
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "60"))
worker_tmp_dir = "/tmp"          # el sistema de archivos es de solo lectura; /tmp es tmpfs
accesslog = "-"
# Ruta sin parámetros (%(U)s, no %(r)s): ni coordenadas ni textos de los vecinos quedan en el registro de acceso.
access_log_format = '%(h)s %(t)s "%(m)s %(U)s %(H)s" %(s)s %(b)s %(L)ss'
errorlog = "-"
forwarded_allow_ips = "*"        # solo HAProxy llega al puerto (publicado en 127.0.0.1)
