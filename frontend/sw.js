// Life-Dash Service Worker — minimale PWA-Shell.
// API-Requests gehen IMMER ans Netz (Lebensdaten nie stale cachen);
// nur die App-Shell (HTML/Icons/Manifest) wird gecacht, damit die
// installierte App schnell startet.
//
// P5.1 (0.36.0): Die Warteschlange fürs Offline-Erfassen liegt bewusst NICHT
// hier, sondern in der Seite (localStorage + `flushOutbox`). Background Sync
// wäre der Lehrbuchweg, hätte aber zwei Wege zum Senden ergeben — einen im
// Worker, einen in der Seite —, und iOS kennt die API bis heute nicht. Eine
// Regel an zwei Orten widerspricht sich still (Anmerkung 106); die Seite ist
// der Ort, an dem der Nutzer den Stand auch SEHEN kann.
//
// Was der Worker für P5.1 beitragen muss, ist genau eins: die App muss sich
// ohne Netz überhaupt öffnen lassen — auch unter `/share`, wohin das
// Teilen-Menü navigiert, und mit `?view=input` aus der Verknüpfung. Beide
// Adressen stehen in keinem Cache, deshalb der Navigations-Rückfall unten.
// v3 (Anmerkung 180): das Zeichen ist neu. Ohne den Sprung behielte jeder,
// der die App schon einmal geöffnet hat, das alte Symbol — der Shell-Cache
// liefert es aus, und zwar so lange, bis dieser Name sich ändert.
//
// v4 (Anmerkung 207): Leaflet und markercluster kommen aus dem eigenen Haus
// statt von unpkg — und stehen damit ZUM ERSTEN MAL in dieser Liste. Vorher
// war die Offline-Karte keine: der Worker durfte ein fremdes Skript nicht
// lesen, also fehlte ohne Netz nicht die Kachel, sondern die Bibliothek. Die
// Bilder gehören dazu (Leaflet sucht sie relativ zu seinem CSS), sonst öffnet
// die Karte offline ohne Marker.
// v5 (Anmerkung 223): `world-countries.geojson` steht in der Liste. Der
// Welt-Reiter war die einzige Hauptansicht, die ohne Netz nichts zeigte — die
// Karte lag seit v4 im eigenen Haus, ihre Umrisse nicht. Der Fetch-Handler
// unten holte sie zwar beim ersten Aufruf in den Cache, aber nur für den, der
// den Reiter im Netz schon einmal geöffnet hatte: eine Offline-Fähigkeit, die
// davon abhängt, ob jemand vorher zufällig irgendwo geklickt hat, ist keine.
const CACHE = "lifedash-shell-v5";
const SHELL = ["/", "/index.html", "/manifest.json", "/icon.svg", "/icon-maskable.svg",
               "/icon-comb.svg", "/world-countries.geojson",
               "/vendor/leaflet.js", "/vendor/leaflet.css",
               "/vendor/leaflet.markercluster.js",
               "/vendor/MarkerCluster.css", "/vendor/MarkerCluster.Default.css",
               "/vendor/images/marker-icon.png", "/vendor/images/marker-icon-2x.png",
               "/vendor/images/marker-shadow.png",
               "/vendor/images/layers.png", "/vendor/images/layers-2x.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);
  // API, Docs & fremde Origins: nie aus dem Cache
  if (url.origin !== location.origin) return;
  // Anmerkung 223: `/redoc` gehört dazu. Von den beiden Doku-Oberflächen stand
  // nur `/docs` hier — dieselbe Sorte Seite, dieselbe Begründung (fremdes
  // Skript vom CDN, nichts, was in einen App-Cache gehört), und die zweite
  // Hälfte fehlte. Dieselbe Auslassung wie bei `_CSP_EXEMPT` im Server, nur
  // andersherum.
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/docs")
      || url.pathname.startsWith("/redoc") || url.pathname === "/health") return;
  // Nur GET landet je im Cache — ein POST hat dort nichts verloren.
  if (req.method !== "GET") return;
  const isNav = req.mode === "navigate";
  // Shell: network-first mit Cache-Fallback (immer aktuell, offline startfähig)
  event.respondWith(
    fetch(req)
      .then((resp) => {
        // Nur brauchbare Antworten cachen: eine 404 als Shell-Fallback wäre
        // schlimmer als gar keine.
        if (resp && resp.ok && resp.type === "basic") {
          const copy = resp.clone();
          caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
        }
        return resp;
      })
      .catch(async () => {
        const hit = await caches.match(req, { ignoreSearch: true });
        if (hit) return hit;
        // Jede Navigation endet in derselben Single-Page-App: `/share` und
        // `/?view=input` gibt es als Datei nicht, die App liest ihre Adresse
        // beim Start selbst aus. Ohne diese Zeile ist die Antwort aufs Teilen
        // ohne Netz eine Browser-Fehlerseite — also genau der Fall, für den
        // P5.1 existiert.
        if (isNav) return (await caches.match("/index.html")) || (await caches.match("/"));
        return Response.error();
      })
  );
});
