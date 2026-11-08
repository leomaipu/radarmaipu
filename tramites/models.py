"""Checklist de documentos para Rentas. Rentas la mantiene desde el panel de administración."""
from django.db import models

CLASES = [("", "Todos los giros"), ("2.2", "2.2 Comercio"), ("2.10", "2.10 Servicios artesanales"),
          ("1.2", "1.2 Hospedaje")]


class DocumentoChecklist(models.Model):
    nombre = models.CharField("documento", max_length=200)
    detalle = models.TextField(blank=True, help_text="Explicación breve para el vecino.")
    clase = models.CharField("aplica a la clase", max_length=4, choices=CLASES, blank=True, default="")
    giro = models.CharField("aplica solo al giro (código)", max_length=40, blank=True, default="",
                            help_text="Opcional. Código de config/prc/giros.json, por ejemplo 'bazar'.")
    solo_alcohol = models.BooleanField("solo giros con alcohol", default=False)
    orden = models.PositiveIntegerField(default=0)
    activo = models.BooleanField(default=True)
    fuente = models.CharField(max_length=200, blank=True, help_text="Norma u ordenanza que lo exige.")

    class Meta:
        ordering = ["orden", "nombre"]
        verbose_name = "documento de la checklist"
        verbose_name_plural = "checklist de Rentas"

    def __str__(self):
        return self.nombre


def checklist_para(giro: str, clase: str, alcohol: bool) -> list[dict]:
    qs = DocumentoChecklist.objects.filter(activo=True)
    items = []
    for d in qs:
        if d.giro and d.giro != giro:
            continue
        if d.clase and d.clase != clase:
            continue
        if d.solo_alcohol and not alcohol:
            continue
        items.append({"documento": d.nombre, "detalle": d.detalle, "fuente": d.fuente})
    return items
