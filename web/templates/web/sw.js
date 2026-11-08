/* Service worker de Radar Maipú (versión {{ version }}).
   Archivos estáticos: primero la caché. Páginas: primero la red, con página sin conexión de respaldo.
   La API y los paneles del informe nunca se guardan: el resultado debe ser siempre actual. */
const CACHE = "radar-{{ version }}";
const ARCHIVOS = {{ archivos|safe }};

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ARCHIVOS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k.startsWith("radar-") && k !== CACHE)
    .map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;            // mapas base y GIS: siempre a la red
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/panel/") || url.pathname.startsWith("/admin/")) return;
  if (url.pathname.startsWith("/static/")) {
    e.respondWith(caches.match(req).then((r) => r || fetch(req).then((resp) => {
      const copia = resp.clone();
      if (resp.ok) caches.open(CACHE).then((c) => c.put(req, copia));
      return resp;
    })));
    return;
  }
  if (req.mode === "navigate") {
    e.respondWith(fetch(req).then((resp) => {
      if (resp.ok && url.pathname === "/") {
        const copia = resp.clone();
        caches.open(CACHE).then((c) => c.put("/", copia));
      }
      return resp;
    }).catch(() => caches.match("/").then((r) => r || caches.match("/offline/"))));
  }
});
