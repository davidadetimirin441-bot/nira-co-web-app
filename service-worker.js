const CACHE_NAME = "nira-co-global-source-v1";
const APP_SHELL = [
  "./",
  "./global-deal-sourcer.html",
  "./manifest.webmanifest",
  "./assets/nira-co-building-logo.png",
  "./assets/ratada-logo.svg",
  "./assets/apple-touch-icon.png",
  "./assets/ratada-icon-192.png",
  "./assets/ratada-icon-512.png",
  "./assets/manchester.png",
  "./assets/birmingham.png",
  "./assets/dubai.png",
  "./assets/liverpool.png",
  "./assets/lagos.png",
  "./assets/algarve.png"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(names.map((name) => name === CACHE_NAME ? null : caches.delete(name)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;

  event.respondWith(
    caches.match(event.request).then((cached) => {
      return cached || fetch(event.request).then((response) => {
        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        return response;
      });
    })
  );
});
