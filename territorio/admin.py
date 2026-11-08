from django.contrib import admin

from .models import Barrio, CargaGIS, Calle, Patente


@admin.register(CargaGIS)
class CargaGISAdmin(admin.ModelAdmin):
    list_display = ("inicio", "fin", "fase", "conteos")
    readonly_fields = ("inicio", "fin", "fase", "conteos", "error")

    def has_add_permission(self, request):
        return False


@admin.register(Patente)
class PatenteAdmin(admin.ModelAdmin):
    list_display = ("direccion", "capa", "estado_normalizado", "actividad")
    list_filter = ("capa", "estado_normalizado")
    search_fields = ("direccion", "actividad")

    def has_add_permission(self, request):  # los datos vienen del GIS: solo lectura
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Barrio, Calle)
class SoloLecturaAdmin(admin.ModelAdmin):
    search_fields = ("nombre",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
admin.site.site_header = "Radar Maipú · Administración"
admin.site.site_title = "Radar Maipú"
