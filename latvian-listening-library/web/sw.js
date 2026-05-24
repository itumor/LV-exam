/* T-061 — PWA service worker for the Latvian Listening Library
 * (extended from the original T-013 PWA stub).
 *
 * Caches:
 *   * Static shell (HTML/CSS/JS/manifest/icon)         — cache-first.
 *   * Listening data (transcripts/translations/metadata, catalog.json,
 *     microClips.json, /api/listening-feed[/*])         — stale-while-revalidate.
 *   * Listening audio (.mp3/.m4a/.ogg/.wav)             — cache-first with LRU
 *                                                        eviction at the last
 *                                                        50 clips so the
 *                                                        TikTok-style T-035
 *                                                        feed stays usable
 *                                                        offline.
 */
const CACHE_VERSION = "v2";
const STATIC_CACHE = "latvian-listening-static-" + CACHE_VERSION;
const DATA_CACHE = "latvian-listening-data-" + CACHE_VERSION;
const AUDIO_CACHE = "latvian-listening-audio-" + CACHE_VERSION;
const MAX_CLIP_CACHE = 50;

const APP_PREFIX = "/latvian-listening-library/web/";
// Audio is served from BOTH legacy locations — the curated micro-clips
// referenced by feed.js live under web/data/, while the larger library
// catalogue lives under /latvian-listening-library/data/. We accept
// either so cache-first applies in both deployments.
const DATA_PREFIX = "/latvian-listening-library/data/";
const WEB_DATA_PREFIX = "/latvian-listening-library/web/data/";

const STATIC_ASSETS = [
  APP_PREFIX,
  APP_PREFIX + "index.html",
  APP_PREFIX + "feed.html",
  APP_PREFIX + "feed.js",
  APP_PREFIX + "styles.css",
  APP_PREFIX + "app.js",
  APP_PREFIX + "manifest.json",
  APP_PREFIX + "icon.svg",
  APP_PREFIX + "catalog.json",
  APP_PREFIX + "microClips.json",
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
        /* allow lazy population if pre-cache fails */
      })
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  const keep = new Set([STATIC_CACHE, DATA_CACHE, AUDIO_CACHE]);
  event.waitUntil(
    caches
      .keys()
      .then((names) =>
        Promise.all(
          names
            .filter(
              (name) =>
                (name.startsWith("latvian-listening-") ||
                  name === "latvian-listening-v1") &&
                !keep.has(name)
            )
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

  // 1. Audio — cache-first, last-50 LRU. Accept both data/ roots.
  if (
    (url.pathname.startsWith(DATA_PREFIX) ||
      url.pathname.startsWith(WEB_DATA_PREFIX)) &&
    /\.(mp3|m4a|ogg|wav|webm)$/i.test(url.pathname)
  ) {
    event.respondWith(handleAudio(request));
    return;
  }

  // 2. Listening data + feed API — stale-while-revalidate.
  if (
    url.pathname.includes("/transcripts_lv/") ||
    url.pathname.includes("/translations_en/") ||
    url.pathname.includes("/metadata/") ||
    url.pathname.endsWith("/catalog.json") ||
    url.pathname.endsWith("/microClips.json") ||
    url.pathname === "/api/listening-feed" ||
    url.pathname.startsWith("/api/listening-feed/")
  ) {
    event.respondWith(staleWhileRevalidate(request, DATA_CACHE));
    return;
  }

  // 3. App shell — cache-first.
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
  DATA_CACHE,
  AUDIO_CACHE,
  MAX_CLIP_CACHE,
  STATIC_ASSETS,
  APP_PREFIX,
  DATA_PREFIX,
  _internal: { cacheFirst, staleWhileRevalidate, handleAudio, trimAudioCache },
};
