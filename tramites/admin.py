from django.contrib import admin

from .models import DocumentoChecklist


@admin.register(DocumentoChecklist)
class DocumentoChecklistAdmin(admin.ModelAdmin):
    list_display = ("nombre", "clase", "giro", "solo_alcohol", "orden", "activo")
    list_editable = ("orden", "activo")
    list_filter = ("activo", "clase", "solo_alcohol")
    search_fields = ("nombre", "giro")
