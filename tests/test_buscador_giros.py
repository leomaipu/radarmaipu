"""Buscador de giros: modo léxico, modo semántico con un embebedor de prueba, adaptador de Ollama y vistas."""
import copy
import json
from pathlib import Path

import httpx
import pytest
from django.core.management import call_command
from django.test import Client

from api import buscador as buscador_mod
from nucleo import evaluacion_buscador as ev
from nucleo import prc_config
from nucleo.buscador_giros import BuscadorGiros, EmbeddingsNoDisponibles, frases_por_giro, raices, sin_tildes
from nucleo.ollama import OllamaEmbebedor

CFG = prc_config.cargar()
GIROS = CFG["giros"]["giros"]
CB = CFG["buscador_giros"]
FRASES = json.loads((Path(__file__).parent / "datos" / "frases_giros.json").read_text(encoding="utf-8"))["frases"]


def lexico():
    return BuscadorGiros(GIROS, CB)


class EmbebedorConceptos:
    """Doble de un modelo de embeddings: cada concepto es un eje; palabras distintas pueden compartir eje."""

    modelo = "prueba"
    CONCEPTOS = {"bencin": 0, "estacion": 0, "combustible": 0, "mall": 1, "comercial": 1,
                 "zapatill": 2, "calzad": 2, "vestuari": 2, "ropa": 2}

    def __init__(self, falla=False):
        self.llamadas, self.textos, self.falla = 0, 0, falla

    def embeber(self, textos):
        self.llamadas += 1
        self.textos += len(textos)
        if self.falla:
            raise EmbeddingsNoDisponibles("caído")
        salida = []
        for t in textos:
            v = [0.0] * 4
            for palabra in sin_tildes(t).split():
                for raiz, eje in self.CONCEPTOS.items():
                    if palabra.startswith(raiz):
                        v[eje] += 1
            v[3] = 0.05  # componente común: nada tiene similitud cero
            salida.append(v)
        return salida


# ——— Datos de evaluación ———

def test_frases_de_evaluacion_son_validas():
    assert len(FRASES) == 100 and len({f["frase"] for f in FRASES}) == 100
    assert sum(f["conjunto"] == "prueba" for f in FRASES) == 50
    for f in FRASES:
        assert set(f["esperado"]) <= set(GIROS), f["frase"]


def test_ejemplos_de_la_configuracion_apuntan_a_giros_existentes():
    assert {k for k in CB["ejemplos"] if not k.startswith("_")} <= set(GIROS)


def test_ningun_giro_queda_sin_frases():
    assert all(fs for fs in frases_por_giro(GIROS, CB).values())


# ——— Modo léxico ———

def test_raices_sin_tildes_ni_palabras_vacias():
    vacias = frozenset(CB["palabras_vacias"])
    assert raices("Quiero vender PANADERÍAS en mi casa", vacias) == raices("panaderia", vacias)
    assert sin_tildes("Señora Cañón") == "señora cañon"


@pytest.mark.parametrize("frase, giro", [
    ("vendo completos y churrascos", "fuente_soda"),
    ("quiero poner un almacén", "abarrotes"),
    ("barbería", "peluqueria"),
    ("taller mecánico", "taller_mecanico"),
    ("pan amasado", "amasanderia"),
])
def test_modo_lexico_encuentra_el_giro(frase, giro):
    res = lexico().buscar(frase)
    assert res.modo == "lexico" and res.sugerencias[0].codigo == giro


def test_frases_sin_giro_en_radar_no_inventan_sugerencias():
    for frase in ("clases de inglés", "tatuajes", "asdfgh qwerty"):
        assert lexico().buscar(frase).sugerencias == []


def test_consultas_cortas_o_vacias_no_buscan():
    b = lexico()
    for q in ("", "  ", "pa", None):
        assert b.buscar(q).sugerencias == []


def test_consulta_larga_se_recorta():
    b = lexico()
    assert len(b.consulta_valida("almacén " * 100)) == CB["max_caracteres"]


def test_maximo_de_sugerencias():
    assert len(lexico().buscar("venta de ropa zapatos telas regalos juguetes").sugerencias) <= CB["max_sugerencias"]


def test_piso_de_aciertos_del_modo_lexico():
    """Piso de regresión. 'prueba' no se usa para ajustar: es la medición honesta."""
    b = lexico()
    dev, prueba = ev.evaluar(b, FRASES, "desarrollo"), ev.evaluar(b, FRASES, "prueba")
    assert dev["top3_pct"] >= 95 and prueba["top3_pct"] >= 70 and prueba["sin_giro_rechazadas_pct"] == 100


# ——— Modo semántico (doble de prueba) ———

def test_modo_semantico_encuentra_lo_que_el_lexico_no():
    assert lexico().buscar("bencinera").sugerencias == []
    b = BuscadorGiros(GIROS, CB, EmbebedorConceptos())
    res = b.buscar("bencinera")
    assert res.modo == "semantico" and res.sugerencias[0].codigo == "estacion_servicio"
    assert res.sugerencias[0].semantico is not None and res.sugerencias[0].frase


def test_indice_semantico_se_construye_una_vez_y_por_lotes():
    emb = EmbebedorConceptos()
    b = BuscadorGiros(GIROS, CB, emb)
    b.buscar("bencinera")
    total_frases = sum(len(fs) for fs in b.frases.values())
    lotes = -(-total_frases // CB["semantico"]["tamano_lote"])
    assert emb.llamadas == lotes + 1 and emb.textos == total_frases + 1
    b.buscar("mall")
    assert emb.llamadas == lotes + 2


def test_si_el_embebedor_falla_responde_en_modo_lexico():
    res = BuscadorGiros(GIROS, CB, EmbebedorConceptos(falla=True)).buscar("vendo completos y churrascos")
    assert res.modo == "lexico" and res.sugerencias[0].codigo == "fuente_soda"


# ——— Adaptador de Ollama ———

class Reloj:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def ollama(manejador, reloj=None):
    transporte = httpx.MockTransport(manejador)
    return OllamaEmbebedor("http://ollama:11434/", "paraphrase-multilingual", 2, 60,
                           cliente=lambda: httpx.Client(transport=transporte), reloj=reloj or Reloj())


def test_ollama_pide_embeddings_al_endpoint_correcto():
    pedidos = []

    def manejador(req):
        pedidos.append(req)
        cuerpo = json.loads(req.content)
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2]] * len(cuerpo["input"])})

    assert ollama(manejador).embeber(["a", "b"]) == [[0.1, 0.2], [0.1, 0.2]]
    assert str(pedidos[0].url) == "http://ollama:11434/api/embed"
    assert json.loads(pedidos[0].content) == {"model": "paraphrase-multilingual", "input": ["a", "b"]}


@pytest.mark.parametrize("respuesta", [
    httpx.Response(500, text="error"),
    httpx.Response(200, json={"otra": 1}),
    httpx.Response(200, json={"embeddings": [[0.1]]}),        # cantidad distinta
    httpx.Response(200, text="no es json"),
])
def test_ollama_con_respuestas_malas_lanza_y_entra_en_pausa(respuesta):
    llamadas, reloj = [], Reloj()

    def manejador(req):
        llamadas.append(req)
        return respuesta

    emb = ollama(manejador, reloj)
    with pytest.raises(EmbeddingsNoDisponibles):
        emb.embeber(["a", "b"])
    with pytest.raises(EmbeddingsNoDisponibles):
        emb.embeber(["a", "b"])
    assert len(llamadas) == 1  # en pausa no vuelve a llamar
    reloj.t = 61
    with pytest.raises(EmbeddingsNoDisponibles):
        emb.embeber(["a", "b"])
    assert len(llamadas) == 2


def test_ollama_sin_conexion_lanza():
    def manejador(req):
        raise httpx.ConnectError("sin red", request=req)

    with pytest.raises(EmbeddingsNoDisponibles):
        ollama(manejador).embeber(["a"])


# ——— Composición, API y sitio ———

@pytest.fixture
def sin_ollama(settings):
    settings.RADAR = {**settings.RADAR, "OLLAMA_URL": ""}
    buscador_mod.reiniciar()
    yield
    buscador_mod.reiniciar()


def test_composicion_sin_url_es_lexica_y_con_url_usa_ollama(sin_ollama):
    assert buscador_mod.crear(url="").embebedor is None
    b = buscador_mod.crear(url="http://ollama:11434", modelo="bge-m3")
    assert isinstance(b.embebedor, OllamaEmbebedor) and b.embebedor.modelo == "bge-m3"
    assert buscador_mod.buscador() is buscador_mod.buscador()


@pytest.mark.django_db
def test_api_sugerir(sin_ollama):
    r = Client().get("/api/giros/sugerir", {"q": "vendo completos y churrascos"})
    assert r.status_code == 200
    datos = r.json()
    assert datos["modo"] == "lexico" and datos["sugerencias"][0]["codigo"] == "fuente_soda"
    assert Client().get("/api/giros/sugerir", {"q": "x" * 201}).status_code == 422


@pytest.mark.django_db
def test_panel_de_sugerencias(sin_ollama):
    c = Client()
    r = c.get("/panel/sugerir-giro/", {"q": "vendo completos y churrascos"})
    html = r.content.decode()
    assert r["Cache-Control"] == "no-store"
    assert 'data-sugerencia="fuente_soda"' in html and "¿Tu negocio es alguno de estos?" in html
    assert c.get("/panel/sugerir-giro/", {"q": "pa"}).content.decode().strip() == ""
    nada = c.get("/panel/sugerir-giro/", {"q": "<script>clases de inglés</script>"}).content.decode()
    assert "data-sin-sugerencias" in nada and "<script>" not in nada and "&lt;script&gt;" in nada


@pytest.mark.django_db
def test_el_paso_2_conecta_el_buscador():
    html = Client().get("/").content.decode()
    assert 'hx-get="/panel/sugerir-giro/"' in html and 'id="sugerencias-giro"' in html


def test_comando_de_evaluacion(sin_ollama, capsys):
    call_command("evaluar_buscador", "--url", "")
    salida = capsys.readouterr().out
    assert "[desarrollo] modo=lexico" in salida and "[prueba] modo=lexico" in salida
    call_command("evaluar_buscador", "--url", "", "--calibrar")
    assert "umbral  top1%" in capsys.readouterr().out


def test_calibrar_no_modifica_la_configuracion_cargada():
    antes = copy.deepcopy(CB)
    call_command("evaluar_buscador", "--url", "", "--calibrar", "--json")
    assert prc_config.cargar()["buscador_giros"] == antes
