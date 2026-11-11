"""Pruebas de punta a punta en el navegador (Playwright + Chrome del sistema).

Requieren la app corriendo (`podman compose up`) y Playwright fuera del contenedor:
    python -m venv .venv-e2e && .venv-e2e/bin/pip install playwright pytest
    RM_E2E_URL=http://127.0.0.1:8000 .venv-e2e/bin/python -m pytest tests_e2e -p no:django
Consultan el GIS municipal en vivo.
"""
import os
import re

import pytest

sync_api = pytest.importorskip("playwright.sync_api")
BASE = os.environ.get("RM_E2E_URL", "http://127.0.0.1:8000").rstrip("/") + "/"
ZH5_TALLER = "?lat=-33.5&lon=-70.77&giro=taller_mecanico"


@pytest.fixture(scope="module")
def navegador():
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch(channel=os.environ.get("RM_E2E_CANAL", "chrome"))
        yield b
        b.close()


@pytest.fixture
def pagina(navegador):
    ctx = navegador.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, locale="es-CL")
    pg = ctx.new_page()
    pg.errores = []
    pg.on("console", lambda m: m.type == "error" and pg.errores.append(m.text))
    pg.on("pageerror", lambda e: pg.errores.append(str(e)))
    yield pg
    ctx.close()


def esperar_informe(pg):
    pg.wait_for_selector("#informe", timeout=30000)
    pg.wait_for_timeout(300)


def test_informe_desde_url_y_sin_errores_de_consola(pagina):
    pagina.goto(BASE + ZH5_TALLER)
    esperar_informe(pagina)
    assert "Taller mecánico" in pagina.inner_text(".veredicto")
    assert pagina.is_visible(".aviso--informe")
    assert pagina.errores == []


def test_cambiar_lugar_invalida_el_resultado_anterior(pagina):
    pagina.goto(BASE + ZH5_TALLER)
    esperar_informe(pagina)
    pagina.click("#informe [data-ir='1']")
    pagina.wait_for_timeout(400)
    pagina.locator("#mapa").click(position={"x": 120, "y": 200})
    pagina.wait_for_timeout(500)
    assert pagina.is_disabled(".paso-dot[data-ir='3']"), "el paso 3 no debe mostrar el informe del punto anterior"
    pagina.click("#btn-a-paso-2")
    pagina.click("#btn-simular")
    esperar_informe(pagina)
    lat = re.search(r"lat=(-?[\d.]+)", pagina.url).group(1)
    assert lat != "-33.5"


def test_cambiar_giro_invalida_el_resultado(pagina):
    pagina.goto(BASE + ZH5_TALLER)
    esperar_informe(pagina)
    pagina.click("#informe [data-ir='2']")
    pagina.click(".chip[data-giro='farmacia']")
    assert "giro=farmacia" in pagina.url
    assert pagina.is_disabled(".paso-dot[data-ir='3']")
    pagina.click("#btn-simular")
    esperar_informe(pagina)
    assert "Farmacia" in pagina.inner_text(".veredicto")


def test_boton_atras_navega_entre_pasos(pagina):
    pagina.goto(BASE)
    pagina.locator("#mapa").click(position={"x": 200, "y": 200})
    pagina.click("#btn-a-paso-2")
    assert pagina.is_visible("#paso-2")
    pagina.go_back()
    pagina.wait_for_timeout(400)
    assert pagina.url.startswith(BASE) and pagina.is_visible("#paso-1")


def test_error_del_servidor_ofrece_reintentar(pagina):
    pagina.route("**/panel/informe/**", lambda r: r.fulfill(status=500, body="error"))
    pagina.goto(BASE + ZH5_TALLER)
    pagina.wait_for_selector("[data-reintentar]", timeout=15000)
    assert pagina.evaluate("document.activeElement.getAttribute('role')") == "alert"


def test_frente_invalido_en_la_url_se_ignora(pagina):
    pagina.goto(BASE + ZH5_TALLER + "&frente_via=a%20b%3C")
    esperar_informe(pagina)
    assert "frente_via" not in pagina.url


def test_indicador_de_busqueda_quieto_sin_consulta(pagina):
    pagina.goto(BASE)
    assert pagina.eval_on_selector("#buscando", "e => getComputedStyle(e).opacity") == "0"


def test_horizontal_usa_panel_lateral(navegador):
    ctx = navegador.new_context(viewport={"width": 844, "height": 390}, is_mobile=True, has_touch=True)
    pg = ctx.new_page()
    pg.goto(BASE + "?lat=-33.48&lon=-70.76&giro=bazar")
    esperar_informe(pg)
    caja = pg.locator("#panel").bounding_box()
    assert caja["width"] < 844 * 0.6 and caja["height"] > 300
    pg.click("#btn-capas")  # no debe quedar tapado por el panel
    assert pg.is_visible("#leyenda")
    ctx.close()


def test_horizontal_boton_simular_siempre_visible(navegador):
    ctx = navegador.new_context(viewport={"width": 844, "height": 390}, is_mobile=True, has_touch=True)
    pg = ctx.new_page()
    pg.goto(BASE + "?lat=-33.48&lon=-70.76")
    pg.wait_for_selector("#paso-2:not([hidden])")
    pg.click(".chip[data-giro='bazar']")
    caja = pg.locator("#btn-simular").bounding_box()
    assert caja and caja["y"] + caja["height"] <= 390, "Simular debe verse sin recorrer los 63 giros"
    ctx.close()


def test_atras_restaura_el_estado_de_la_url(pagina):
    pagina.goto(BASE + ZH5_TALLER)
    esperar_informe(pagina)
    pagina.click("#informe [data-ir='2']")
    pagina.click(".chip[data-giro='farmacia']")
    pagina.click("#btn-simular")
    esperar_informe(pagina)
    assert "Farmacia" in pagina.inner_text(".veredicto")
    pagina.go_back()
    pagina.wait_for_timeout(400)
    pagina.go_back()
    pagina.wait_for_timeout(600)
    assert "giro=taller_mecanico" in pagina.url
    assert pagina.is_checked("input[name='giro'][value='taller_mecanico']")


@pytest.mark.parametrize("ancho,alto", [(844, 390), (667, 375)])
def test_horizontal_aviso_y_resultado_sin_desplazar(navegador, ancho, alto):
    ctx = navegador.new_context(viewport={"width": ancho, "height": alto}, is_mobile=True, has_touch=True)
    pg = ctx.new_page()
    pg.goto(BASE + "?lat=-33.48&lon=-70.76&giro=bazar")
    esperar_informe(pg)
    for sel in (".aviso--informe", ".veredicto .veredicto__titulo"):
        caja = pg.locator(sel).bounding_box()
        assert caja and caja["y"] >= 0 and caja["y"] + caja["height"] <= alto, sel
    ctx.close()


def test_ficha_cambia_de_giro_en_el_mismo_punto(pagina):
    pagina.goto(BASE + ZH5_TALLER)
    esperar_informe(pagina)
    destino = pagina.get_attribute("#informe [data-cambiar-giro] >> nth=0", "data-cambiar-giro")
    pagina.click("#informe [data-cambiar-giro] >> nth=0")
    pagina.wait_for_function("(g) => location.search.includes('giro=' + g)", arg=destino)
    esperar_informe(pagina)
    assert "lat=-33.5" in pagina.url and not pagina.errores
