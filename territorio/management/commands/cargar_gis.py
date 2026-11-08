from django.core.management.base import BaseCommand

from territorio.carga import ejecutar


class Command(BaseCommand):
    help = "Descarga calles, barrios y patentes del GIS municipal a PostGIS (reemplaza los datos anteriores)."

    def add_arguments(self, parser):
        parser.add_argument("--regeocodificar", action="store_true",
                            help="Después de cargar, asigna punto a patentes sin match. Puede tardar más de una hora.")
        parser.add_argument("--limite", type=int, default=None, help="Máximo de patentes a re-geocodificar.")
        parser.add_argument("--reintentos", type=int, default=3, help="Intentos si el GIS no responde.")
        parser.add_argument("--si-vacia", action="store_true", help="Cargar solo si no hay patentes (arranque).")

    def handle(self, *args, **opts):
        from territorio.models import Patente
        if opts["si_vacia"] and Patente.objects.exists():
            self.stdout.write("La base ya tiene datos: no se carga.")
            return
        b = ejecutar(opts["regeocodificar"], opts["limite"], reintentos=opts["reintentos"])
        self.stdout.write(f"{b.fase}: {b.conteos} {b.error}")
        if b.fase == "error":
            raise SystemExit(1)
