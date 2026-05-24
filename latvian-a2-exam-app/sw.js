/* T-061 — PWA service worker for the Latvian A2 Exam Simulator.
 *
 * Caches:
 *   1. Static shell assets (HTML, CSS, JS, manifest, icon) so the app
 *      boots without a network.
 *   2. Up to MAX_CLIP_CACHE = 50 audio clips from the T-035 listening
 *      feed (under /latvian-listening-library/data/) and their JSON
 *      catalogue, so the vertical listening feed stays usable offline.
 *
 * Strategies:
 *   * Static shell      — cache-first, fall back to network, fall back
 *                         to cached index.html (SPA-style offline route).
 *   * /api/listening-feed and microClips.json — stale-while-revalidate
 *                         so the feed shows the most-recent payload but
 *                         still works after install when offline.
 *   * Listening audio (.mp3/.m4a under
 *     /latvian-listening-library/data/) — cache-first, evict oldest when
 *                         the cache exceeds 50 clips.
 *
 * The cache version is bumped via the CACHE_VERSION constant; old
 * caches are deleted on `activate`.
 */
const CACHE_VERSION = "v1";
const STATIC_CACHE = "lvcodex-a2-static-" + CACHE_VERSION;
const AUDIO_CACHE = "lvcodex-a2-audio-" + CACHE_VERSION;
const API_CACHE = "lvcodex-a2-api-" + CACHE_VERSION;
const MAX_CLIP_CACHE = 50;

const APP_PREFIX = "/latvian-a2-exam-app/";
const LISTENING_AUDIO_PREFIX = "/latvian-listening-library/data/";
const LISTENING_WEB_AUDIO_PREFIX = "/latvian-listening-library/web/data/";
const LISTENING_WEB_PREFIX = "/latvian-listening-library/web/";

const STATIC_ASSETS = [
  APP_PREFIX,
  APP_PREFIX + "index.html",
  APP_PREFIX + "styles.css",
  APP_PREFIX + "app.js",
  APP_PREFIX + "flow-core.js",
  APP_PREFIX + "unified-header.js",
  APP_PREFIX + "manifest.webmanifest",
  APP_PREFIX + "icon.svg",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(STATIC_CACHE)
      .then((cache) =>
        // Use Request objects with cache: "reload" so the install pass
        // does not pick up stale entries from the HTTP cache.
        cache.addAll(
          STATIC_ASSETS.map((url) => new Request(url, { cache: "reload" }))
        )
      )
      .catch(() => {
        /* Network unavailable at install — the SW still installs so
         * subsequent same-origin GETs can populate the cache lazily. */
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
            .filter((name) => name.startsWith("lvcodex-a2-") && !keep.has(name))
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
  if (request.method !== "GET") {
    return;
  }
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) {
    return;
  }

  // 1. Listening audio — cache-first with LRU eviction (max 50 clips).
  if (
    (url.pathname.startsWith(LISTENING_AUDIO_PREFIX) ||
      url.pathname.startsWith(LISTENING_WEB_AUDIO_PREFIX)) &&
    /\.(mp3|m4a|ogg|wav|webm)$/i.test(url.pathname)
  ) {
    event.respondWith(handleAudio(request));
    return;
  }

  // 2. Listening-feed API + catalogue — stale-while-revalidate.
  if (
    url.pathname === "/api/listening-feed" ||
    url.pathname.startsWith("/api/listening-feed/") ||
    url.pathname.endsWith("/microClips.json")
  ) {
    event.respondWith(staleWhileRevalidate(request, API_CACHE));
    return;
  }

  // 3. App shell + listening-library web assets — cache-first.
  if (
    url.pathname.startsWith(APP_PREFIX) ||
    url.pathname.startsWith(LISTENING_WEB_PREFIX)
  ) {
    event.respondWith(cacheFirst(request, STATIC_CACHE));
    return;
  }
});

function cacheFirst(request, cacheName) {
  return caches.open(cacheName).then((cache) =>
    cache.match(request).then((cached) => {
      if (cached) {
        // Refresh in the background so the next load gets the new copy.
        fetch(request)
          .then((response) => {
            if (response && response.ok) {
              cache.put(request, response.clone());
            }
          })
          .catch(() => {
            /* offline — keep cached entry */
          });
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
          // Last-resort offline fallback for navigation requests inside
          // the app shell.
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
          if (response) {
            return response;
          }
          return new Response(
            JSON.stringify({
              error: { code: "offline", message: "Network unavailable" },
              offline: true,
            }),
            {
              status: 503,
              headers: { "Content-Type": "application/json" },
            }
          );
        })
      );
    })
  );
}

function handleAudio(request) {
  return caches.open(AUDIO_CACHE).then((cache) =>
    cache.match(request).then((cached) => {
      if (cached) {
        return cached;
      }
      return fetch(request)
        .then((response) => {
          if (response && response.ok) {
            // Clone before caching — body can only be consumed once.
            cache.put(request, response.clone()).then(() => trimAudioCache(cache));
          }
          return response;
        })
        .catch(() =>
          new Response("", {
            status: 504,
            statusText: "Offline (clip not cached)",
          })
        );
    })
  );
}

function trimAudioCache(cache) {
  // LRU-ish eviction: keep the MOST RECENTLY ADDED 50 clips. The order
  // of `cache.keys()` reflects insertion order in current browsers.
  return cache.keys().then((keys) => {
    if (keys.length <= MAX_CLIP_CACHE) {
      return;
    }
    const excess = keys.length - MAX_CLIP_CACHE;
    return Promise.all(keys.slice(0, excess).map((req) => cache.delete(req)));
  });
}

// Expose constants for unit tests running in a SW-like sandbox. The
// `self.__lvcodexPwa` surface is read by tests/pwa-sw.test.js which
// imports this file with `node --test`. This is a side-effect-free
// addition; production browsers ignore it.
self.__lvcodexPwa = {
  CACHE_VERSION,
  STATIC_CACHE,
  AUDIO_CACHE,
  API_CACHE,
  MAX_CLIP_CACHE,
  STATIC_ASSETS,
  APP_PREFIX,
  LISTENING_AUDIO_PREFIX,
  LISTENING_WEB_PREFIX,
  _internal: {
    cacheFirst,
    staleWhileRevalidate,
    handleAudio,
    trimAudioCache,
  },
};
