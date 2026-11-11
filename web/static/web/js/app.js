/* Radar Maipú — simulador del vecino. Sin compilación: JavaScript estándar + Leaflet + HTMX. */
(() => {
  "use strict";

  const cfg = JSON.parse(document.getElementById("config-radar").textContent);
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const app = $("#app");
  const hoja = $("#panel");
  const cuerpo = $("#hoja-cuerpo");
  const esEscritorio = () => matchMedia("(min-width: 1024px)").matches;
  // El panel va a la izquierda en escritorio y en teléfonos en horizontal (misma regla que app.css).
  const panelLateral = () => esEscritorio() || matchMedia("(orientation: landscape) and (max-height: 520px)").matches;
  const reducirMovimiento = matchMedia("(prefers-reduced-motion: reduce)").matches;

  const estado = { lat: null, lon: null, dir: null, giro: null, escala: "", frente: "", paso: 1 };

  /* ——— Mapa ——— */
  const LIMITES = L.latLngBounds([-33.60, -70.86], [-33.43, -70.69]);
  const mapa = L.map("mapa", {
    center: cfg.centro, zoom: 14, minZoom: 12, maxZoom: 19, maxBounds: LIMITES.pad(0.4),
    zoomControl: false, attributionControl: true, tap: true,
  });
  L.control.zoom({ position: "bottomright" }).addTo(mapa);
  L.tileLayer(cfg.tiles, { attribution: cfg.atribucion, maxZoom: 19, maxNativeZoom: cfg.tiles_max }).addTo(mapa);
  // A nivel de calle: soleras, predios y áreas verdes del GIS municipal (imagen dinámica, sin caché de teselas).
  const baseMunicipal = L.esri.dynamicMapLayer({ url: cfg.base_municipal, layers: [0, 2, 3], opacity: 0.75, f: "image" });
  const etiquetas = L.tileLayer(cfg.tiles_ref, { maxZoom: 19, maxNativeZoom: cfg.tiles_max, pane: "shadowPane" }).addTo(mapa);
  function detalleMunicipal() {
    if (mapa.getZoom() >= 16) { if (!mapa.hasLayer(baseMunicipal)) baseMunicipal.addTo(mapa); }
    else if (mapa.hasLayer(baseMunicipal)) mapa.removeLayer(baseMunicipal);
  }
  mapa.on("zoomend", detalleMunicipal);
  mapa.attributionControl.setPrefix(false);

  let capaPRC = null;
  // Dos grupos: el de rubro similar (magenta) nunca se mezcla con el resto (violeta).
  const grupoComercio = (similar) => L.markerClusterGroup({
    showCoverageOnHover: false, maxClusterRadius: 44, spiderfyOnMaxZoom: true,
    iconCreateFunction: (c) => {
      const n = c.getChildCount();
      const t = n < 10 ? 34 : n < 100 ? 42 : 50;
      return L.divIcon({ html: `<span>${n}</span>`, className: `cluster-radar${similar ? " cluster-radar--similar" : ""}`, iconSize: [t, t] });
    },
  }).addTo(mapa);
  const capaComercio = grupoComercio(false);
  const capaSimilares = grupoComercio(true);

  const iconoRadar = L.divIcon({
    className: "", iconSize: [22, 22], iconAnchor: [11, 11],
    html: '<div class="marcador-radar"><span class="marcador-radar__onda"></span><span class="marcador-radar__onda"></span><span class="marcador-radar__onda"></span><span class="marcador-radar__centro"></span></div>',
  });
  let marcador = null;
  mapa.createPane("radar").style.zIndex = 650;   // el punto elegido siempre sobre el comercio agrupado

  // "1912 LOS PAJARITOS, MAIPU CENTRO, MAIPÚ, METROPOLITANA DE SANTIAGO" -> "Los Pajaritos 1912, Maipú Centro"
  const MENORES = new Set(["de", "del", "la", "las", "los", "el", "y"]);
  function bonita(dir) {
    if (!dir) return dir;
    let partes = dir.split(",").map((x) => x.trim()).filter((x) => !/^(maip[uú]|metropolitana.*|regi[oó]n.*|chile)$/i.test(x));
    partes = partes.map((p) => p.toLowerCase().replace(/maipu\b/g, "maipú").split(/\s+/)
      .map((w, i) => (i > 0 && MENORES.has(w) ? w : w.charAt(0).toUpperCase() + w.slice(1))).join(" "));
    if (partes[0]) {
      partes[0] = partes[0].replace(/^(\d+[a-z]?)\s+(.+)$/i, "$2 $1");
      partes[0] = partes[0].charAt(0).toUpperCase() + partes[0].slice(1);
    }
    return partes.slice(0, 2).join(", ");
  }

  function desplazamientoVista() {
    // Deja el punto visible fuera del panel: a la derecha en escritorio, arriba en el teléfono.
    if (panelLateral()) return [-(hoja.offsetWidth + 20) / 2, 0];
    return [0, Math.min(hoja.offsetHeight, innerHeight * 0.6) / 2];
  }
  function centrarEn(latlng, zoom) {
    const z = zoom || Math.max(mapa.getZoom(), 16);
    const p = mapa.project(latlng, z).add(L.point(desplazamientoVista()));
    mapa.flyTo(mapa.unproject(p, z), z, { duration: reducirMovimiento ? 0 : 0.8 });
  }

  /* ——— Capa del Plan Regulador (imagen oficial del MapServer) ——— */
  const btnCapas = $("#btn-capas");
  const leyenda = $("#leyenda");
  let leyendaCargada = false;
  function alternarPRC(mostrar) {
    if (mostrar && !capaPRC) {
      capaPRC = L.esri.dynamicMapLayer({ url: cfg.prc, layers: [1, 2, 3, 4], opacity: $("#opacidad-prc").value / 100, f: "image" });
    }
    if (mostrar) { capaPRC.addTo(mapa); cargarLeyenda(); } else if (capaPRC) { mapa.removeLayer(capaPRC); }
    btnCapas.setAttribute("aria-pressed", String(mostrar));
    btnCapas.setAttribute("aria-label", mostrar ? "Ocultar zonas del Plan Regulador" : "Mostrar zonas del Plan Regulador");
    leyenda.hidden = !mostrar;
  }
  btnCapas.addEventListener("click", () => alternarPRC(btnCapas.getAttribute("aria-pressed") !== "true"));
  $("[data-cerrar-leyenda]").addEventListener("click", () => { alternarPRC(false); btnCapas.focus(); });
  $("#opacidad-prc").addEventListener("input", (e) => capaPRC && capaPRC.setOpacity(e.target.value / 100));
  async function cargarLeyenda() {
    if (leyendaCargada) return;
    const lista = $("#leyenda-lista");
    try {
      const r = await fetch(cfg.urls.leyenda);
      if (!r.ok) throw new Error(r.status);
      const datos = await r.json();
      lista.replaceChildren(...datos.capas.flatMap((c) => {
        const titulo = document.createElement("p");
        titulo.className = "leyenda__grupo";
        titulo.textContent = c.nombre;
        return [titulo, ...c.items.map((i) => {
          const fila = document.createElement("div");
          fila.className = "leyenda__item";
          const img = document.createElement("img");
          img.src = i.img; img.alt = "";
          const t = document.createElement("span");
          t.textContent = i.etiqueta;
          fila.append(img, t);
          return fila;
        })];
      }));
      leyendaCargada = true;
    } catch {
      lista.innerHTML = '<p class="sutil">No pudimos cargar la simbología. La capa sigue visible en el mapa.</p>';
    }
  }

  /* ——— Hoja inferior arrastrable (teléfono) ——— */
  const ALTURAS = ["baja", "media", "alta"];
  function altura(a) { hoja.dataset.altura = a; }
  $("#hoja-asa").addEventListener("click", () => {
    const i = ALTURAS.indexOf(hoja.dataset.altura);
    altura(ALTURAS[(i + 1) % ALTURAS.length]);
  });
  (() => {
    const asa = $("#hoja-asa");
    let inicioY = null, inicioAlto = 0, movido = false;
    asa.addEventListener("pointerdown", (e) => {
      if (panelLateral()) return;
      inicioY = e.clientY; inicioAlto = hoja.getBoundingClientRect().height; movido = false;
      asa.setPointerCapture(e.pointerId);
    });
    asa.addEventListener("pointermove", (e) => {
      if (inicioY === null) return;
      const dy = inicioY - e.clientY;
      if (Math.abs(dy) > 6) { movido = true; hoja.classList.add("arrastrando"); hoja.style.setProperty("--alto-hoja", `${Math.max(120, inicioAlto + dy)}px`); }
    });
    asa.addEventListener("pointerup", (e) => {
      if (inicioY === null) return;
      hoja.classList.remove("arrastrando");
      if (movido) {
        const h = inicioAlto + (inicioY - e.clientY);
        hoja.style.removeProperty("--alto-hoja");
        altura(h < innerHeight * 0.32 ? "baja" : h < innerHeight * 0.72 ? "media" : "alta");
        asa.addEventListener("click", (ev) => ev.stopImmediatePropagation(), { once: true, capture: true });
      }
      inicioY = null;
    });
  })();

  /* ——— Pasos ——— */
  const dots = $$(".paso-dot");
  // Clave de la consulta: el informe en pantalla solo vale si coincide con el estado actual.
  const clave = () => [estado.lat, estado.lon, estado.giro, estado.escala, estado.frente].join("|");
  function informeVigente() { return !!$("#informe") && estado.claveInforme === clave(); }
  function refrescarPasos() {
    dots.forEach((d) => (d.disabled = Number(d.dataset.ir) !== estado.paso && !puedeIr(Number(d.dataset.ir))));
  }
  function cambioDeConsulta() {
    actualizarURL();
    refrescarPasos();
  }
  function irA(n, { foco = true, historial = true } = {}) {
    if (historial && n !== estado.paso) history.pushState({ paso: n }, "", location.href);
    const cambiar = () => {
      estado.paso = n;
      app.dataset.paso = n;
      $$(".paso").forEach((p) => (p.hidden = Number(p.dataset.paso) !== n));
      dots.forEach((d) => {
        const k = Number(d.dataset.ir);
        if (k === n) d.setAttribute("aria-current", "step"); else d.removeAttribute("aria-current");
        d.classList.toggle("hecho", k < n);
        d.disabled = !puedeIr(k);
      });
      cuerpo.scrollTop = 0;
      if (!panelLateral()) altura(n === 2 ? "alta" : "media");
      if (foco) {
        const destino = n === 3 ? $("#informe") || $("#resultado") : $(`#paso-${n} .titulo`);
        if (destino) { destino.setAttribute("tabindex", "-1"); destino.focus({ preventScroll: true }); }
      }
    };
    if (document.startViewTransition && !reducirMovimiento) {
      // Una transición nueva puede interrumpir la anterior: eso no es un error.
      const t = document.startViewTransition(cambiar);
      [t.ready, t.finished, t.updateCallbackDone].forEach((p) => p.catch(() => {}));
    } else cambiar();
  }
  function puedeIr(k) {
    if (k === 1) return true;
    if (k === 2) return estado.lat !== null;
    return estado.lat !== null && !!estado.giro && informeVigente();
  }
  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-ir]");
    if (b && !b.disabled) irA(Number(b.dataset.ir));
  });
  let restaurando = false;
  addEventListener("popstate", (e) => {
    const q = new URLSearchParams(location.search);
    restaurando = true;
    const lat = parseFloat(q.get("lat")), lon = parseFloat(q.get("lon"));
    if (Number.isFinite(lat) && Number.isFinite(lon) && (lat !== estado.lat || lon !== estado.lon)) elegirPunto(lat, lon);
    const g = q.get("giro");
    if (g && g !== estado.giro && radios.some((r) => r.value === g)) elegirGiro(g);
    const esc = q.get("escala") || "";
    const radioEsc = $(`input[name="escala"][value="${CSS.escape(esc)}"]`);
    if (radioEsc) { radioEsc.checked = true; estado.escala = esc; }
    estado.frente = /^[A-Za-z0-9._-]{1,20}$/.test(q.get("frente_via") || "") ? q.get("frente_via") : "";
    restaurando = false;
    refrescarPasos();
    const n = (e.state && e.state.paso) || 1;
    irA(puedeIr(n) ? n : n === 3 && puedeIr(2) ? 2 : 1, { historial: false });
  });

  /* ——— Paso 1: ubicación ——— */
  async function elegirPunto(lat, lon, dir = null, { centrar = true } = {}) {
    if (!LIMITES.contains([lat, lon])) {
      avisar("Ese punto está fuera de Maipú. Elige un lugar dentro de la comuna.");
      return;
    }
    estado.lat = +lat.toFixed(6); estado.lon = +lon.toFixed(6); estado.frente = "";
    if (marcador) marcador.setLatLng([lat, lon]); else marcador = L.marker([lat, lon], { icon: iconoRadar, keyboard: false, interactive: false, pane: "radar" }).addTo(mapa);
    if (centrar) centrarEn([lat, lon]);
    $("#elegido").hidden = false;
    $("#paso-1").classList.add("con-punto");
    $("#elegido-sub").textContent = `${estado.lat.toFixed(5)}, ${estado.lon.toFixed(5)}`;
    $("#btn-a-paso-2").disabled = false;
    if (dir) mostrarDireccion(dir); else { mostrarDireccion("Buscando la dirección…"); direccionInversa(lat, lon); }
    cambioDeConsulta();
    if (estado.giro && estado.paso === 3 && !restaurando) simular();
  }
  function mostrarDireccion(texto) {
    estado.dir = texto;
    $("#elegido-dir").textContent = texto;
    $("#paso2-lugar").textContent = texto && !texto.endsWith("…") ? `En ${texto}` : "";
    // La dirección puede llegar después del informe (restaurar desde la URL): actualizar la ficha también.
    const ficha = $("#informe [data-ficha-direccion]");
    if (ficha && texto && !texto.endsWith("…")) { $("span", ficha).textContent = texto; ficha.hidden = false; }
  }
  async function direccionInversa(lat, lon) {
    try {
      const r = await fetch(`${cfg.urls.direccion}?lat=${lat}&lon=${lon}`);
      const d = r.ok ? await r.json() : null;
      if (estado.lat !== +lat.toFixed(6)) return;
      mostrarDireccion(d && d.direccion ? bonita(d.direccion.direccion) : "Punto elegido en el mapa");
    } catch { mostrarDireccion("Punto elegido en el mapa"); }
  }
  mapa.on("click", (e) => {
    elegirPunto(e.latlng.lat, e.latlng.lng, null, { centrar: false });
    if (estado.paso !== 3 && !panelLateral() && hoja.dataset.altura === "baja") altura("media");
  });
  $("#resultados-busqueda").addEventListener("click", (e) => {
    const b = e.target.closest(".direccion");
    if (!b) return;
    elegirPunto(parseFloat(b.dataset.lat), parseFloat(b.dataset.lon), bonita(b.dataset.dir));
    $("#resultados-busqueda").innerHTML = "";
    $("#q").value = "";
    $("#btn-a-paso-2").focus();
  });
  function usarUbicacion(boton) {
    if (!navigator.geolocation) return avisar("Tu navegador no permite obtener la ubicación.");
    boton.classList.add("ocupado");
    navigator.geolocation.getCurrentPosition(
      (p) => { boton.classList.remove("ocupado"); elegirPunto(p.coords.latitude, p.coords.longitude); },
      () => { boton.classList.remove("ocupado"); avisar("No pudimos obtener tu ubicación. Busca la dirección o toca el mapa."); },
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 60000 });
  }
  $("#btn-ubicacion").addEventListener("click", (e) => usarUbicacion(e.currentTarget));
  $("#btn-ubicacion-2").addEventListener("click", (e) => usarUbicacion(e.currentTarget));
  $("#btn-a-paso-2").addEventListener("click", () => irA(2));

  /* ——— Paso 2: giro y escala ——— */
  const radios = $$('input[name="giro"]');
  function elegirGiro(codigo, { desplazar = false } = {}) {
    estado.giro = codigo;
    const r = radios.find((x) => x.value === codigo);
    if (r) { r.checked = true; if (desplazar) r.closest(".giro").scrollIntoView({ block: "center", behavior: reducirMovimiento ? "auto" : "smooth" }); }
    $$(".chip[data-giro]").forEach((c) => c.setAttribute("aria-pressed", String(c.dataset.giro === codigo)));
    $("#btn-simular").disabled = !codigo;
    cambioDeConsulta();
  }
  radios.forEach((r) => r.addEventListener("change", () => elegirGiro(r.value)));
  $$(".chip[data-giro]").forEach((c) => {
    c.setAttribute("aria-pressed", "false");
    c.addEventListener("click", () => elegirGiro(c.dataset.giro, { desplazar: true }));
  });
  $$('input[name="escala"]').forEach((r) => r.addEventListener("change", () => { estado.escala = r.value; cambioDeConsulta(); }));
  const sinTildes = (t) => t.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  $("#filtro-giro").addEventListener("input", (e) => {
    const q = sinTildes(e.target.value.trim());
    let visibles = 0;
    $$("[data-grupo]").forEach((g) => {
      let enGrupo = 0;
      $$(".giro", g).forEach((l) => {
        const ok = !q || sinTildes(l.dataset.buscar).includes(q);
        l.hidden = !ok; if (ok) enGrupo++;
      });
      g.hidden = enGrupo === 0; visibles += enGrupo;
    });
    $("#sin-giros").hidden = visibles > 0;
  });
  $("#btn-simular").addEventListener("click", () => simular());

  /* ——— Paso 3: informe ——— */
  function parametros() {
    const p = new URLSearchParams({ lat: estado.lat, lon: estado.lon, giro: estado.giro });
    if (estado.escala) p.set("escala", estado.escala);
    if (estado.frente) p.set("frente_via", estado.frente);
    return p;
  }
  function simular() {
    if (estado.lat === null || !estado.giro) return;
    const destino = $("#resultado");
    destino.replaceChildren($("#tpl-cargando").content.cloneNode(true));
    destino.setAttribute("aria-busy", "true");
    if (estado.paso !== 3) irA(3, { foco: false });
    actualizarURL();
    htmx.ajax("GET", `${cfg.urls.informe}?${parametros()}`, { target: "#resultado", swap: "innerHTML" })
      .catch(() => {});
  }
  document.body.addEventListener("htmx:afterSwap", (e) => {
    if (e.detail.target.id === "resultados-busqueda") {
      $$(".direccion span", e.detail.target).forEach((s) => (s.textContent = bonita(s.textContent)));
      return;
    }
    if (e.detail.target.id !== "resultado") return;
    e.detail.target.setAttribute("aria-busy", "false");
    const pedida = new URL(e.detail.pathInfo.requestPath, location.origin).searchParams;
    estado.claveInforme = [+pedida.get("lat"), +pedida.get("lon"), pedida.get("giro"), pedida.get("escala") || "",
      pedida.get("frente_via") || ""].join("|");
    refrescarPasos();
    dibujarComercio();
    animarCifras();
    const inf = $("#informe");
    if (inf) {
      const dir = $("[data-ficha-direccion]", inf);
      if (dir && estado.dir && !estado.dir.endsWith("…")) { $("span", dir).textContent = estado.dir; dir.hidden = false; }
      inf.focus({ preventScroll: true });
      anunciar(`Resultado: ${inf.querySelector(".veredicto__titulo").textContent}. ${inf.querySelector(".veredicto__giro").textContent}.`);
    }
    cuerpo.scrollTop = 0;
  });
  document.body.addEventListener("htmx:responseError", (e) => {
    if (!e.detail.target || e.detail.target.id !== "resultado") return;
    if (e.detail.xhr.status === 400) {
      estado.frente = "";
      errorInforme("La consulta no es válida. Vuelve a elegir el lugar y el negocio.", false);
    } else {
      errorInforme("El servidor no pudo generar el informe. Intenta de nuevo en unos minutos.", true);
    }
  });
  document.body.addEventListener("htmx:sendError", (e) => {
    if (e.detail.target && e.detail.target.id === "resultado") errorInforme("Sin conexión. Revisa tu internet e intenta de nuevo.", true);
  });
  function errorInforme(msg, reintentable) {
    const d = $("#resultado");
    d.setAttribute("aria-busy", "false");
    estado.claveInforme = null;
    d.innerHTML = '<div class="esperando" role="alert" tabindex="-1"><p><strong></strong></p></div>';
    d.querySelector("strong").textContent = msg;
    const b = document.createElement("button");
    b.type = "button"; b.className = "boton boton--primario";
    if (reintentable) { b.dataset.reintentar = ""; b.textContent = "Reintentar"; } else { b.dataset.ir = "1"; b.textContent = "Volver a empezar"; }
    d.firstElementChild.append(b);
    d.firstElementChild.focus();
    actualizarURL();
  }
  const anuncio = $("#anuncio");
  function anunciar(texto) { anuncio.textContent = ""; setTimeout(() => (anuncio.textContent = texto), 60); }
  cuerpo.addEventListener("click", (e) => {
    const f = e.target.closest("[data-frente]");
    if (f) { estado.frente = f.dataset.frente; simular(); return; }
    // Ficha del lugar: otro giro en el mismo punto (mismo frente y escala declarados).
    const g = e.target.closest("[data-cambiar-giro]");
    if (g && radios.some((r) => r.value === g.dataset.cambiarGiro)) { elegirGiro(g.dataset.cambiarGiro); simular(); return; }
    if (e.target.closest("[data-reintentar]")) { simular(); return; }
    if (e.target.closest("[data-compartir]")) { compartir(); return; }
    if (e.target.closest("[data-imprimir]")) { window.print(); return; }
    const s = e.target.closest(".similar");
    if (s) { const ll = [parseFloat(s.dataset.lat), parseFloat(s.dataset.lon)]; centrarEn(ll, 18); if (!panelLateral()) altura("baja"); }
  });

  function dibujarComercio() {
    capaComercio.clearLayers();
    capaSimilares.clearLayers();
    const nodo = $("#puntos-comercio");
    if (!nodo) return;
    const puntos = JSON.parse(nodo.textContent);
    const marcadores = puntos.map((p) => {
      const m = L.marker([p.lat, p.lon], {
        similar: p.s, keyboard: false,
        icon: L.divIcon({ className: "", iconSize: p.s ? [16, 16] : [12, 12], html: `<div class="punto-comercio${p.s ? " punto-comercio--similar" : ""}"></div>` }),
      });
      const cont = document.createElement("div");
      const a = document.createElement("strong"); a.textContent = p.a.charAt(0) + p.a.slice(1).toLowerCase();
      const d = document.createElement("div"); d.textContent = p.d;
      cont.append(a, d);
      m.bindPopup(cont);
      return m;
    });
    capaComercio.addLayers(marcadores.filter((m) => !m.options.similar));
    capaSimilares.addLayers(marcadores.filter((m) => m.options.similar));
  }
  function animarCifras() {
    if (reducirMovimiento) return;
    $$("[data-contar]").forEach((el) => {
      const fin = Number(el.dataset.contar);
      const t0 = performance.now();
      const paso = (t) => {
        const k = Math.min(1, (t - t0) / 700);
        el.textContent = Math.round(fin * (1 - Math.pow(1 - k, 3)));
        if (k < 1) requestAnimationFrame(paso);
      };
      requestAnimationFrame(paso);
    });
  }

  /* ——— Estado en la URL (compartir y volver) ——— */
  function actualizarURL() {
    if (restaurando) return;
    const p = new URLSearchParams();
    if (estado.lat !== null) { p.set("lat", estado.lat); p.set("lon", estado.lon); }
    if (estado.giro) p.set("giro", estado.giro);
    if (estado.escala) p.set("escala", estado.escala);
    if (estado.frente) p.set("frente_via", estado.frente);
    history.replaceState({ paso: estado.paso }, "", p.toString() ? `?${p}` : location.pathname);
  }
  async function compartir() {
    const datos = { title: "Radar Maipú", text: `Simulación: ${cfg.giros[estado.giro] || ""} en ${estado.dir || "Maipú"}`, url: location.href };
    try {
      if (navigator.share) await navigator.share(datos);
      else { await navigator.clipboard.writeText(location.href); avisar("Enlace copiado. Puedes pegarlo donde quieras."); }
    } catch { /* el usuario canceló */ }
  }

  /* ——— Avisos breves ——— */
  let tostada;
  function avisar(texto) {
    if (!tostada) {
      tostada = document.createElement("div");
      tostada.setAttribute("role", "status");
      tostada.style.cssText = "position:fixed;left:50%;top:calc(80px + env(safe-area-inset-top,0px));transform:translateX(-50%);z-index:1500;background:#10174A;color:#fff;padding:12px 18px;border-radius:14px;box-shadow:0 18px 48px rgb(16 23 74/.3);max-width:calc(100vw - 32px);font-size:.9rem;transition:opacity .2s";
      document.body.append(tostada);
    }
    tostada.textContent = texto; tostada.style.opacity = "1";
    clearTimeout(tostada._t); tostada._t = setTimeout(() => (tostada.style.opacity = "0"), 4200);
  }

  /* ——— Diálogos ——— */
  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-abrir]");
    if (b) $(`#${b.dataset.abrir}`).showModal();
  });
  $$("dialog").forEach((d) => d.addEventListener("click", (e) => { if (e.target === d) d.close(); }));

  /* ——— PWA ——— */
  $(".buscador").addEventListener("submit", (e) => e.preventDefault());
  // En desarrollo los estáticos no llevan hash: el service worker serviría versiones viejas.
  if ("serviceWorker" in navigator && !cfg.debug) addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => {}));
  let instalacion = null;
  addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); instalacion = e; $("#btn-instalar").hidden = false; });
  $("#btn-instalar").addEventListener("click", async () => {
    if (!instalacion) return;
    instalacion.prompt();
    await instalacion.userChoice;
    instalacion = null; $("#btn-instalar").hidden = true;
  });

  /* ——— Arranque: restaurar desde la URL ——— */
  detalleMunicipal();
  const q = new URLSearchParams(location.search);
  const lat = parseFloat(q.get("lat")), lon = parseFloat(q.get("lon"));
  if (q.get("escala")) {
    const r = $(`input[name="escala"][value="${CSS.escape(q.get("escala"))}"]`);
    if (r) { r.checked = true; estado.escala = r.value; }
  }
  const frenteURL = /^[A-Za-z0-9._-]{1,20}$/.test(q.get("frente_via") || "") ? q.get("frente_via") : "";
  if (q.get("giro") && radios.some((r) => r.value === q.get("giro"))) elegirGiro(q.get("giro"));
  if (Number.isFinite(lat) && Number.isFinite(lon)) {
    elegirPunto(lat, lon);
    estado.frente = frenteURL;
    if (estado.giro && estado.lat !== null) { irA(3, { foco: false, historial: false }); simular(); } else irA(estado.lat !== null ? 2 : 1, { foco: false, historial: false });
  } else {
    irA(1, { foco: false, historial: false });
  }
  actualizarURL();
})();
