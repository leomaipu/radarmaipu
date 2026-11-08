# Imagen de la aplicación: Python + bibliotecas geoespaciales que necesita GeoDjango (GDAL, GEOS, PROJ).
FROM docker.io/library/python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends binutils gdal-bin libproj-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN DJANGO_SECRET_KEY=build python manage.py collectstatic --noinput

EXPOSE 8000
CMD ["gunicorn", "radar.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60"]
