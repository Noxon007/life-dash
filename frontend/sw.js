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
const CACHE = "lifedash-shell-v2";
const SHELL = ["/", "/index.html", "/manifest.json", "/icon.svg", "/icon-maskable.svg"];

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
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/docs") || url.pathname === "/health") return;
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
