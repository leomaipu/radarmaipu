from django.apps import AppConfig
from django.core import checks


class TramitesConfig(AppConfig):
    name = "tramites"
    verbose_name = "Trámites (checklist de Rentas)"

    def ready(self):
        checks.register(revisar_checklist, checks.Tags.compatibility)


def revisar_checklist(app_configs=None, **kwargs):
    """`manage.py check` (y el arranque) avisan si checklist_rentas.json referencia giros, rubros o casos que no existen."""
    from nucleo import checklist, prc_config
    cfg = prc_config.cargar()
    return [checks.Error(e, id="tramites.E001", hint="Revisar config/prc/checklist_rentas.json")
            for e in checklist.validar(cfg["checklist_rentas"], cfg["giros"]["giros"])]
