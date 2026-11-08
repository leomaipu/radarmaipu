"""Capas del GIS municipal copiadas a PostGIS. Solo campos de la lista blanca (nucleo/privacy.py)."""
from django.contrib.gis.db import models


class Calle(models.Model):
    nombre = models.CharField(max_length=200, blank=True, null=True, db_index=True)
    clase = models.CharField(max_length=40, blank=True, null=True)
    clase_desc = models.CharField(max_length=80, blank=True, null=True)
    suf_direc = models.CharField(max_length=40, blank=True, null=True)
    geom = models.LineStringField(geography=True, srid=4326)

    class Meta:
        verbose_name_plural = "calles"

    def __str__(self):
        return self.nombre or f"Calle {self.pk}"

    def a_dict(self) -> dict:
        return {"NOMBRE": self.nombre, "CLASE": self.clase, "SUF_DIREC": self.suf_direc, "CLASE_DESC": self.clase_desc}


class Barrio(models.Model):
    id_barrio = models.IntegerField(unique=True)
    nombre = models.CharField(max_length=120)

    def __str__(self):
        return self.nombre

    def a_dict(self) -> dict:
        return {"BARRIO": self.nombre, "ID_BARRIO": self.id_barrio}


class Patente(models.Model):
    capa = models.CharField(max_length=20)
    direccion = models.CharField(max_length=250, blank=True, null=True)
    estado_pat = models.CharField(max_length=40, blank=True, null=True, db_index=True)
    estado_normalizado = models.CharField(max_length=40, blank=True, null=True)
    tipo_paten = models.CharField(max_length=80, blank=True, null=True)
    subtipo_pa = models.CharField(max_length=80, blank=True, null=True)
    actividad = models.TextField(blank=True, null=True)
    anio = models.CharField(max_length=8, blank=True, null=True)
    semestre = models.CharField(max_length=4, blank=True, null=True)
    status = models.CharField(max_length=4, blank=True, null=True)
    status_desc = models.CharField(max_length=40, blank=True, null=True)
    score = models.CharField(max_length=12, blank=True, null=True)
    match_type = models.CharField(max_length=12, blank=True, null=True)
    geom = models.PointField(geography=True, srid=4326, null=True, blank=True)
    coords_origen = models.CharField(max_length=30, blank=True, null=True)
    score_geocodificacion = models.FloatField(null=True, blank=True)

    def __str__(self):
        return f"{self.capa}: {self.direccion}"

    def a_dict(self) -> dict:
        d = {
            "DIRECCION": self.direccion, "estado_pat": self.estado_pat, "tipo_paten": self.tipo_paten,
            "subtipo_pa": self.subtipo_pa, "actividad": self.actividad, "Año": self.anio, "semestre": self.semestre,
            "Status": self.status, "Score": self.score, "Match_type": self.match_type,
            "estado_normalizado": self.estado_normalizado, "Status_DESC": self.status_desc, "capa": self.capa,
            "lon": self.geom.x if self.geom else None, "lat": self.geom.y if self.geom else None,
        }
        if self.coords_origen:
            d["coords_origen"] = self.coords_origen
        return {k: v for k, v in d.items() if v is not None or k in ("lon", "lat")}


class CargaGIS(models.Model):
    """Bitácora de cada carga desde el GIS (comando cargar_gis)."""
    inicio = models.DateTimeField(auto_now_add=True)
    fin = models.DateTimeField(null=True, blank=True)
    fase = models.CharField(max_length=40, default="cargando")
    conteos = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-inicio"]
        verbose_name = "carga del GIS"
        verbose_name_plural = "cargas del GIS"
