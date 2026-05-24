/* T-061 — PWA service worker for the Vue 3 v2 SPA (mounted at /v2/).
 *
 * Mirrors the strategy used by /latvian-a2-exam-app/sw.js:
 *   * App-shell (HTML/CSS/JS/manifest) — cache-first with a network
 *     refresh in the background.
 *   * /api/listening-feed + microClips.json — stale-while-revalidate.
 *   * Listening audio (.mp3/.m4a under /latvian-listening-library/data/) —
 *     cache-first with LRU eviction at MAX_CLIP_CACHE = 50 clips so we
 *     can replay the last 50 watched listening clips offline.
 *
 * Hashed Vite assets at /v2/assets/... are cache-first and immutable
 * (their URL changes when the content changes, so the cache is
 * automatically self-purging via the activate-cache-version bump).
 */
const CACHE_VERSION = "v1";
const STATIC_CACHE = "lvcodex-v2-static-" + CACHE_VERSION;
const AUDIO_CACHE = "lvcodex-v2-audio-" + CACHE_VERSION;
const API_CACHE = "lvcodex-v2-api-" + CACHE_VERSION;
const MAX_CLIP_CACHE = 50;

const APP_PREFIX = "/v2/";
const LISTENING_AUDIO_PREFIX = "/latvian-listening-library/data/";
const LISTENING_WEB_AUDIO_PREFIX = "/latvian-listening-library/web/data/";

const STATIC_ASSETS = [
  APP_PREFIX,
  APP_PREFIX + "index.html",
  APP_PREFIX + "manifest.webmanifest",
  APP_PREFIX + "icon.svg",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(STATIC_CACHE)
      .then((cache) =>
        cache.addAll(
          STATIC_ASSETS.map((url) => new Request(url, { cache: "reload" }))
        )
      )
      .catch(() => {
        /* network failure at install — populate lazily on first GET */
      })
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  const keep = new Set([STATIC_CACHE, AUDIO_CACHE, API_CACHE]);
  event.waitUntil(
    caches
      .keys()
      .then((names) =>
        Promise.all(
          names
            .filter((name) => name.startsWith("lvcodex-v2-") && !keep.has(name))
            .map((name) => caches.delete(name))
        )
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") {
    self.skipWaiting();
  }
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (
    (url.pathname.startsWith(LISTENING_AUDIO_PREFIX) ||
      url.pathname.startsWith(LISTENING_WEB_AUDIO_PREFIX)) &&
    /\.(mp3|m4a|ogg|wav|webm)$/i.test(url.pathname)
  ) {
    event.respondWith(handleAudio(request));
    return;
  }

  if (
    url.pathname === "/api/listening-feed" ||
    url.pathname.startsWith("/api/listening-feed/") ||
    url.pathname.endsWith("/microClips.json")
  ) {
    event.respondWith(staleWhileRevalidate(request, API_CACHE));
    return;
  }

  if (url.pathname.startsWith(APP_PREFIX)) {
    event.respondWith(cacheFirst(request, STATIC_CACHE));
    return;
  }
});

function cacheFirst(request, cacheName) {
  return caches.open(cacheName).then((cache) =>
    cache.match(request).then((cached) => {
      if (cached) {
        fetch(request)
          .then((response) => {
            if (response && response.ok) {
              cache.put(request, response.clone());
            }
          })
          .catch(() => {});
        return cached;
      }
      return fetch(request)
        .then((response) => {
          if (response && response.ok) {
            cache.put(request, response.clone());
          }
          return response;
        })
        .catch(() => {
          if (request.mode === "navigate") {
            return cache.match(APP_PREFIX + "index.html");
          }
          return new Response("", { status: 504, statusText: "Offline" });
        });
    })
  );
}

function staleWhileRevalidate(request, cacheName) {
  return caches.open(cacheName).then((cache) =>
    cache.match(request).then((cached) => {
      const network = fetch(request)
        .then((response) => {
          if (response && response.ok) {
            cache.put(request, response.clone());
          }
          return response;
        })
        .catch(() => null);
      return (
        cached ||
        network.then((response) => {
          if (response) return response;
          return new Response(
            JSON.stringify({
              error: { code: "offline", message: "Network unavailable" },
              offline: true,
            }),
            { status: 503, headers: { "Content-Type": "application/json" } }
          );
        })
      );
    })
  );
}

function handleAudio(request) {
  return caches.open(AUDIO_CACHE).then((cache) =>
    cache.match(request).then((cached) => {
      if (cached) return cached;
      return fetch(request)
        .then((response) => {
          if (response && response.ok) {
            cache.put(request, response.clone()).then(() => trimAudioCache(cache));
          }
          return response;
        })
        .catch(
          () =>
            new Response("", {
              status: 504,
              statusText: "Offline (clip not cached)",
            })
        );
    })
  );
}

function trimAudioCache(cache) {
  return cache.keys().then((keys) => {
    if (keys.length <= MAX_CLIP_CACHE) return;
    const excess = keys.length - MAX_CLIP_CACHE;
    return Promise.all(keys.slice(0, excess).map((req) => cache.delete(req)));
  });
}

self.__lvcodexPwa = {
  CACHE_VERSION,
  STATIC_CACHE,
  AUDIO_CACHE,
  API_CACHE,
  MAX_CLIP_CACHE,
  STATIC_ASSETS,
  APP_PREFIX,
  LISTENING_AUDIO_PREFIX,
  _internal: { cacheFirst, staleWhileRevalidate, handleAudio, trimAudioCache },
};
