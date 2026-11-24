"""Buscador de giros: modo léxico, modo semántico con un embebedor de prueba, adaptador de Ollama y vistas."""
import copy
import json
import threading
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
# Las pruebas unitarias no usan frases del conjunto 'prueba' (ver test_las_pruebas_no_usan_el_conjunto_prueba).
EVALUACION = {f["frase"]: f["conjunto"] for f in FRASES}


def lexico():
    return BuscadorGiros(GIROS, CB)


class EmbebedorConceptos:
    """Doble de un modelo de embeddings: cada concepto es un eje; palabras distintas pueden compartir eje."""

    modelo = "prueba"
    CONCEPTOS = {"servicentro": 0, "estacion": 0, "combustible": 0, "galeria": 1, "comercial": 1,
                 "calzad": 2, "vestuari": 2, "ropa": 2}

    def __init__(self, falla=False, dimension_rara=False, freno=None):
        self.llamadas, self.textos, self.falla, self.dimension_rara, self.freno = 0, 0, falla, dimension_rara, freno
        self.indexacion = []

    def embeber(self, textos, *, indexacion=False):
        self.llamadas += 1
        self.textos += len(textos)
        self.indexacion.append(indexacion)
        if self.freno is not None and indexacion:
            self.freno.wait(5)
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
            salida.append(v[:2] if self.dimension_rara and not indexacion else v)
        return salida


def semantico(**kw):
    emb = EmbebedorConceptos(**kw)
    b = BuscadorGiros(GIROS, CB, emb)
    b.preparar(esperar=True)
    return b, emb


# ——— Datos de evaluación ———

def test_frases_de_evaluacion_son_validas():
    assert len(FRASES) == 100 and len({f["frase"] for f in FRASES}) == 100
    assert sum(f["conjunto"] == "prueba" for f in FRASES) == 50
    for f in FRASES:
        assert set(f["esperado"]) <= set(GIROS), f["frase"]


def test_ejemplos_de_la_configuracion_apuntan_a_giros_existentes():
    assert {k for k in CB["ejemplos"] if not k.startswith("_")} <= set(GIROS)


def test_los_ejemplos_responden_a_frases_de_desarrollo():
    """Cada ejemplo agregado se justifica con una frase fallida de 'desarrollo', nunca de 'prueba'."""
    respaldo = CB["ejemplos"]["_respaldo"]
    for frase in respaldo.values():
        assert EVALUACION.get(frase) == "desarrollo", frase
    ejemplos = {e for k, v in CB["ejemplos"].items() if not k.startswith("_") for e in v}
    cubiertos = {e.strip() for clave in respaldo for e in clave.split(",")}
    assert ejemplos == cubiertos


def test_las_pruebas_no_usan_el_conjunto_prueba():
    usadas = ["quiero poner un almacén en mi casa", "un minimarket de barrio", "barbería para hombres", "taller mecánico",
              "ferretería", "tatuajes", "lentes ópticos", "pan amasado casero", "completos y churrascos al paso",
              "servicentro", "galería comercial"]
    assert all(EVALUACION.get(f) != "prueba" for f in usadas)


def test_ningun_giro_queda_sin_frases():
    assert all(fs for fs in frases_por_giro(GIROS, CB).values())


# ——— Modo léxico ———

def test_raices_sin_tildes_ni_palabras_vacias():
    vacias = frozenset(CB["palabras_vacias"])
    assert raices("Quiero vender PANADERÍAS en mi casa", vacias) == raices("panaderia", vacias)
    assert sin_tildes("Señora Cañón") == "señora cañon"


@pytest.mark.parametrize("frase, giro", [
    ("quiero poner un almacén en mi casa", "abarrotes"),
    ("un minimarket de barrio", "abarrotes"),
    ("barbería para hombres", "peluqueria"),
    ("taller mecánico", "taller_mecanico"),
    ("ferretería", "ferreteria"),
])
def test_modo_lexico_encuentra_el_giro(frase, giro):
    res = lexico().buscar(frase)
    assert res.modo == "lexico" and res.sugerencias[0].codigo == giro


def test_frases_sin_giro_en_radar_no_inventan_sugerencias():
    for frase in ("lentes ópticos", "tatuajes", "asdfgh qwerty"):
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


def test_piso_de_aciertos_del_modo_lexico_en_desarrollo():
    """Piso de regresión solo sobre 'desarrollo'. 'prueba' se informa (manage.py evaluar_buscador), no se exige:
    exigirla en CI la convertiría en un conjunto de ajuste."""
    dev = ev.evaluar(lexico(), FRASES, "desarrollo")
    assert dev["top3_pct"] >= 95


def test_p95_por_rango_mas_cercano():
    marcas = []  # 20 consultas de 1 ms, 2 ms, ... 20 ms (pares de lecturas del reloj)
    for i in range(1, 21):
        marcas += [0, i / 1000]
    reloj = iter(marcas).__next__
    r = ev.evaluar(lexico(), [{"frase": "ferretería", "esperado": ["ferreteria"], "conjunto": "x"}] * 20, reloj=reloj)
    assert r["latencia_ms"]["p95"] == 19.0 and r["latencia_ms"]["p50"] == 10.5


# ——— Modo semántico (doble de prueba) ———

def test_modo_semantico_encuentra_lo_que_el_lexico_no():
    assert lexico().buscar("servicentro").sugerencias == []
    b, _ = semantico()
    res = b.buscar("servicentro")
    assert res.modo == "semantico" and res.sugerencias[0].codigo == "estacion_servicio"
    assert res.sugerencias[0].semantico is not None and res.sugerencias[0].frase


def test_indice_semantico_se_construye_una_vez_y_por_lotes():
    b, emb = semantico()
    total_frases = sum(len(fs) for fs in b.frases.values())
    lotes = -(-total_frases // CB["semantico"]["tamano_lote"])
    assert emb.llamadas == lotes and emb.textos == total_frases and all(emb.indexacion)
    b.buscar("servicentro")
    b.buscar("galería comercial")
    assert emb.llamadas == lotes + 2 and emb.indexacion[-1] is False


def test_mientras_se_arma_el_indice_el_vecino_recibe_modo_lexico_sin_esperar():
    freno = threading.Event()
    emb = EmbebedorConceptos(freno=freno)
    b = BuscadorGiros(GIROS, CB, emb)
    res = b.buscar("barbería para hombres")  # el índice queda armándose en otro hilo, frenado
    assert res.modo == "lexico" and res.sugerencias[0].codigo == "peluqueria"
    freno.set()
    assert b.preparar(esperar=True) and b.buscar("servicentro").modo == "semantico"


class Reloj:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_si_el_indice_falla_se_reintenta_solo_despues_de_la_pausa():
    emb, reloj = EmbebedorConceptos(falla=True), Reloj()
    b = BuscadorGiros(GIROS, CB, emb, reloj=reloj)
    assert not b.preparar(esperar=True)
    llamadas = emb.llamadas
    res = b.buscar("barbería para hombres")
    b._hilo.join()
    assert res.modo == "lexico" and emb.llamadas == llamadas  # en pausa: no reintenta
    reloj.t = CB["semantico"]["pausa_tras_falla_s"] + 1
    emb.falla = False
    assert b.preparar(esperar=True)


def test_si_el_embebedor_falla_o_responde_vectores_raros_responde_en_modo_lexico():
    b, emb = semantico()
    emb.falla = True
    res = b.buscar("barbería para hombres")
    assert res.modo == "lexico" and res.sugerencias[0].codigo == "peluqueria"
    b2, _ = semantico(dimension_rara=True)
    assert b2.buscar("barbería para hombres").modo == "lexico"


def test_frase_mostrada_vacia_si_no_comparte_palabras():
    b = lexico()
    assert b._mejor_frase_lexica("ferreteria", "zzz") == ""
    assert b._mejor_frase_lexica("peluqueria", "barberías") == "barbería"


# ——— Adaptador de Ollama ———

def ollama(manejador, reloj=None):
    return OllamaEmbebedor("http://ollama:11434/", "paraphrase-multilingual", 2, 60, 30,
                           cliente=httpx.Client(transport=httpx.MockTransport(manejador)), reloj=reloj or Reloj())


def test_ollama_pide_embeddings_al_endpoint_correcto():
    pedidos = []

    def manejador(req):
        pedidos.append(req)
        cuerpo = json.loads(req.content)
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2]] * len(cuerpo["input"])})

    emb = ollama(manejador)
    assert emb.embeber(["a", "b"]) == [[0.1, 0.2], [0.1, 0.2]]
    assert str(pedidos[0].url) == "http://ollama:11434/api/embed"
    assert json.loads(pedidos[0].content) == {"model": "paraphrase-multilingual", "input": ["a", "b"]}
    assert pedidos[0].extensions["timeout"]["read"] == 2
    emb.embeber(["a"], indexacion=True)
    assert pedidos[1].extensions["timeout"]["read"] == 30


def test_ollama_no_usa_proxies_del_entorno(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.ejemplo:3128")
    emb = OllamaEmbebedor("http://ollama:11434", "m", 2, 60)
    assert emb._cliente._trust_env is False


@pytest.mark.parametrize("respuesta", [
    httpx.Response(500, text="error"),
    httpx.Response(200, json={"otra": 1}),
    httpx.Response(200, json={"embeddings": [[0.1]]}),        # cantidad distinta
    httpx.Response(200, text="no es json"),
    httpx.Response(200, json={"embeddings": [[0.1, "x"], [0.1, 0.2]]}),   # valor no numérico
    httpx.Response(200, json={"embeddings": [[0.1, 0.2], [0.1]]}),        # dimensiones distintas
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
def test_api_sugerir_por_post(sin_ollama):
    c = Client()
    r = c.post("/api/giros/sugerir", {"q": "barbería para hombres"}, content_type="application/json")
    assert r.status_code == 200
    datos = r.json()
    assert datos["modo"] == "lexico" and datos["sugerencias"][0]["codigo"] == "peluqueria"
    assert c.post("/api/giros/sugerir", {"q": "x" * 201}, content_type="application/json").status_code == 422
    assert c.get("/api/giros/sugerir", {"q": "barbería"}).status_code == 405  # el texto no va en la URL


@pytest.mark.django_db
def test_panel_de_sugerencias_por_post_sin_csrf(sin_ollama):
    c = Client(enforce_csrf_checks=True)
    r = c.post("/panel/sugerir-giro/", {"q": "barbería para hombres"})
    html = r.content.decode()
    assert r.status_code == 200 and r["Cache-Control"] == "no-store"
    assert 'data-sugerencia="peluqueria"' in html and "¿Tu negocio es alguno de estos?" in html
    assert c.post("/panel/sugerir-giro/", {"q": "pa"}).content.decode().strip() == ""
    nada = c.post("/panel/sugerir-giro/", {"q": "<script>lentes ópticos</script>"}).content.decode()
    assert "data-sin-sugerencias" in nada and "<script>" not in nada and "&lt;script&gt;" in nada
    assert c.get("/panel/sugerir-giro/", {"q": "barbería"}).status_code == 405


@pytest.mark.django_db
def test_el_paso_2_conecta_el_buscador():
    html = Client().get("/").content.decode()
    assert 'hx-post="/panel/sugerir-giro/"' in html and 'id="sugerencias-giro"' in html
    assert 'aria-describedby="sugerencias-giro"' not in html


def test_el_registro_de_acceso_no_guarda_parametros():
    import runpy
    fmt = runpy.run_path(str(Path(__file__).resolve().parents[1] / "radar" / "gunicorn.conf.py"))["access_log_format"]
    assert "%(U)s" in fmt and "%(r)s" not in fmt and "%(q)s" not in fmt


def test_comando_de_evaluacion(sin_ollama, capsys):
    call_command("evaluar_buscador", "--url", "")
    salida = capsys.readouterr().out
    assert "[desarrollo] modo=lexico" in salida and "[prueba] modo=lexico" in salida
    call_command("evaluar_buscador", "--url", "", "--calibrar")
    assert "peso_sem  umbral  top1%" in capsys.readouterr().out


def test_calibrar_no_modifica_la_configuracion_cargada():
    antes = copy.deepcopy(CB)
    call_command("evaluar_buscador", "--url", "", "--calibrar", "--json")
    assert prc_config.cargar()["buscador_giros"] == antes


def test_calibrar_recombina_pesos_sin_consultar_de_nuevo():
    cfg = copy.deepcopy(CFG)
    cfg["buscador_giros"]["semantico"]["umbral_minimo"] = 0.0
    cfg["buscador_giros"]["max_sugerencias"] = len(GIROS)
    emb = EmbebedorConceptos()
    b = BuscadorGiros(GIROS, cfg["buscador_giros"], emb)
    b.preparar(esperar=True)
    antes = emb.llamadas
    excluir = set(CB["ejemplos"]["_respaldo"].values())
    tabla = ev.calibrar(b, FRASES, [0.1, 0.5], [0.5, 0.9], "desarrollo", excluir)
    assert [(f["peso_semantico"], f["umbral"]) for f in tabla] == [(0.5, 0.1), (0.5, 0.5), (0.9, 0.1), (0.9, 0.5)]
    assert tabla[0]["frases"] == 50 - len(excluir)
    assert emb.llamadas - antes == tabla[0]["frases"]  # una consulta por frase, no una por combinación


def test_una_falla_inesperada_al_indexar_no_crea_un_hilo_por_tecla():
    class Roto(EmbebedorConceptos):
        def embeber(self, textos, *, indexacion=False):
            self.llamadas += 1
            raise KeyError("config")

    emb, reloj = Roto(), Reloj()
    b = BuscadorGiros(GIROS, CB, emb, reloj=reloj)
    assert not b.preparar(esperar=True)
    for _ in range(5):
        b.buscar("barbería para hombres")
    assert emb.llamadas == 1
