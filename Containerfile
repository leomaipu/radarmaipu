# Imagen de la aplicación: Python + bibliotecas geoespaciales que necesita GeoDjango (GDAL, GEOS, PROJ).
# Corre como usuario sin privilegios (10001) y funciona con el sistema de archivos de solo lectura.
FROM docker.io/library/python:3.12-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends binutils gdal-bin libproj-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --require-hashes -r requirements.txt

COPY . .
RUN DJANGO_SECRET_KEY=build python manage.py collectstatic --noinput \
 && groupadd -g 10001 app && useradd -u 10001 -g app -M -s /usr/sbin/nologin app

USER 10001
EXPOSE 8000
CMD ["gunicorn", "radar.wsgi:application", "-c", "radar/gunicorn.conf.py"]
