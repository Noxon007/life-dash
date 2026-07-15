// Life-Dash Service Worker — minimale PWA-Shell.
// API-Requests gehen IMMER ans Netz (Lebensdaten nie stale cachen);
// nur die App-Shell (HTML/Icons/Manifest) wird gecacht, damit die
// installierte App schnell startet. Offline-Capture-Queue: Phase 2.
const CACHE = "lifedash-shell-v1";
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
  const url = new URL(event.request.url);
  // API, Docs & fremde Origins: nie aus dem Cache
  if (url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/docs") || url.pathname === "/health") return;
  // Shell: network-first mit Cache-Fallback (immer aktuell, offline startfähig)
  event.respondWith(
    fetch(event.request)
      .then((resp) => {
        const copy = resp.clone();
        caches.open(CACHE).then((c) => c.put(event.request, copy)).catch(() => {});
        return resp;
      })
      .catch(() => caches.match(event.request, { ignoreSearch: true }))
  );
});
