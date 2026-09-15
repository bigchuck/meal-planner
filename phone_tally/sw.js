// Offline cache for the Meal Tally phone app.
//
// Cache-first: once index.html/master.json have been fetched once, they're
// served from local Cache Storage on every subsequent load, network or not.
// The app only re-fetches from the network when the page sends this worker
// a "refresh" message (see the `refresh` command in index.html).

const CACHE_NAME = "mealtally-v1";
const ASSETS = ["./", "./index.html", "./master.json"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((names) => Promise.all(
        names.filter((n) => n !== CACHE_NAME).map((n) => caches.delete(n))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});

self.addEventListener("message", (event) => {
  if (event.data !== "refresh") return;
  event.waitUntil(
    (async () => {
      const cache = await caches.open(CACHE_NAME);
      await Promise.all(ASSETS.map(async (url) => {
        try {
          const res = await fetch(url, { cache: "reload" });
          if (res.ok) await cache.put(url, res.clone());
        } catch (e) {
          // offline during refresh attempt — leave the existing cached copy in place
        }
      }));
      for (const client of await self.clients.matchAll()) {
        client.postMessage("refresh-done");
      }
    })()
  );
});
