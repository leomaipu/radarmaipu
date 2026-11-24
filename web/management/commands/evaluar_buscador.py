"""Mide el buscador de giros con las frases de tests/datos/frases_giros.json.

Ejemplos (en el servidor, dentro del contenedor de la app):
  python manage.py evaluar_buscador                              # modo que esté configurado (RM_OLLAMA_URL)
  python manage.py evaluar_buscador --url ""                     # forzar modo léxico, para comparar
  python manage.py evaluar_buscador --modelo bge-m3              # probar otro modelo ya descargado en Ollama
  python manage.py evaluar_buscador --calibrar                   # aciertos por umbral, en 'desarrollo'
Reporte: 'prueba' es la medición honesta (esas frases no se usan para ajustar).
"""
import copy
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from api import buscador as buscador_mod
from nucleo import evaluacion_buscador as ev
from nucleo import prc_config

FRASES = Path(settings.BASE_DIR) / "tests" / "datos" / "frases_giros.json"


class Command(BaseCommand):
    help = "Mide aciertos y latencia del buscador de giros."

    def add_arguments(self, parser):
        parser.add_argument("--url", default=None, help="URL de Ollama (por defecto RM_OLLAMA_URL; vacía: modo léxico)")
        parser.add_argument("--modelo", default=None, help="Modelo de embeddings en Ollama")
        parser.add_argument("--calibrar", action="store_true", help="Aciertos por umbral en el conjunto 'desarrollo'")
        parser.add_argument("--fallos", action="store_true", help="Lista las frases de 'desarrollo' sin acierto")
        parser.add_argument("--json", action="store_true", help="Salida en JSON")

    def handle(self, *args, url=None, modelo=None, calibrar=False, fallos=False, **opciones):
        frases = json.loads(FRASES.read_text(encoding="utf-8"))["frases"]
        cfg = prc_config.cargar()
        if calibrar:
            cfg = copy.deepcopy(cfg)
            cfg["buscador_giros"]["lexico"]["umbral_minimo"] = 0.0
            cfg["buscador_giros"]["semantico"]["umbral_minimo"] = 0.0
            b = buscador_mod.crear(cfg, url, modelo)
            salida = {"modo": b.buscar("almacén").modo,
                      "calibracion": ev.calibrar(b, frases, [round(0.05 * i, 2) for i in range(2, 17)])}
        else:
            b = buscador_mod.crear(cfg, url, modelo)
            b.buscar("almacén")  # primera consulta: construye el índice (no se cuenta en la latencia)
            salida = {}
            for conjunto in ("desarrollo", "prueba"):
                r = ev.evaluar(b, frases, conjunto)
                if not (fallos and conjunto == "desarrollo"):
                    r.pop("fallos")
                salida[conjunto] = r
        if opciones.get("json"):
            self.stdout.write(json.dumps(salida, ensure_ascii=False, indent=1))
            return
        if calibrar:
            self.stdout.write(f"Modo: {salida['modo']}  (conjunto 'desarrollo')")
            self.stdout.write("umbral  top1%  top3%  sin_giro_rechazadas%")
            for f in salida["calibracion"]:
                self.stdout.write(f"{f['umbral']:>6}  {f['top1_pct']!s:>5}  {f['top3_pct']!s:>5}  {f['sin_giro_rechazadas_pct']!s:>5}")
            return
        for conjunto, r in salida.items():
            self.stdout.write(f"[{conjunto}] modo={','.join(r['modos'])} frases={r['frases']} top1={r['top1_pct']}% "
                              f"top3={r['top3_pct']}% sin_giro_rechazadas={r['sin_giro_rechazadas_pct']}% "
                              f"latencia p50={r['latencia_ms']['p50']} ms p95={r['latencia_ms']['p95']} ms")
            for f in r.get("fallos", []):
                self.stdout.write(f"   {f['frase']!r}: esperado {f['esperado']}, obtenido {f['obtenido']}")
