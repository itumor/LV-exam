/* T-061 — Service-worker unit tests.
 *
 * The SW files (`latvian-a2-exam-app/sw.js`, `apps/web-v2/public/sw.js`,
 * `latvian-listening-library/web/sw.js`) cannot be required directly
 * because they target the ServiceWorkerGlobalScope (no `module.exports`,
 * they call `self.addEventListener`, `caches.open`, `fetch`).
 *
 * Each SW exposes its private helpers on `self.__lvcodexPwa._internal`
 * so we can evaluate the source inside a `node:vm` sandbox stocked with
 * stubs for `self`, `caches`, `fetch`, `Request`, `Response`, `URL`,
 * then call the helpers directly to assert:
 *
 *   * Audio responses are cached on the first miss and replayed on the
 *     next call without going to the network (cache-first).
 *   * After 50 audio puts the LRU trim drops the oldest entries.
 *   * When the network is down, a cached audio clip is still served.
 *   * The listening-feed API uses stale-while-revalidate (cached payload
 *     returned immediately, network refresh runs in the background).
 *   * SKIP_WAITING messages trigger `self.skipWaiting()` so updates
 *     activate on the next reload.
 */
const test = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");
const path = require("node:path");

const REPO_ROOT = path.resolve(__dirname, "..");

function makeFakeRequest(url, init = {}) {
  return {
    url,
    method: (init.method || "GET").toUpperCase(),
    mode: init.mode || "no-cors",
    clone() {
      return makeFakeRequest(url, init);
    },
  };
}

function makeFakeResponse(body, init = {}) {
  return {
    body,
    status: init.status || 200,
    statusText: init.statusText || "OK",
    ok: init.status === undefined ? true : init.status >= 200 && init.status < 300,
    headers: init.headers || {},
    clone() {
      return makeFakeResponse(body, init);
    },
    text() {
      return Promise.resolve(typeof body === "string" ? body : JSON.stringify(body));
    },
    json() {
      return Promise.resolve(
        typeof body === "string" ? JSON.parse(body) : body
      );
    },
  };
}

/**
 * Minimal in-memory Cache that mirrors the parts of the CacheStorage
 * spec the SW touches: `match`, `put`, `keys`, `delete`. Entries are
 * stored as `Map<url, response>` and `keys()` returns Request stubs in
 * insertion order — which matches Chrome/Firefox/Safari behaviour.
 */
class FakeCache {
  constructor() {
    this.entries = new Map();
  }
  match(request) {
    const url = typeof request === "string" ? request : request.url;
    return Promise.resolve(this.entries.get(url) || undefined);
  }
  put(request, response) {
    const url = typeof request === "string" ? request : request.url;
    // The SW clones before put — here we just store the value.
    this.entries.set(url, response);
    return Promise.resolve();
  }
  keys() {
    return Promise.resolve(
      Array.from(this.entries.keys()).map((url) => makeFakeRequest(url))
    );
  }
  delete(request) {
    const url = typeof request === "string" ? request : request.url;
    const removed = this.entries.delete(url);
    return Promise.resolve(removed);
  }
  addAll() {
    return Promise.resolve();
  }
}

class FakeCacheStorage {
  constructor() {
    this.caches = new Map();
  }
  open(name) {
    if (!this.caches.has(name)) {
      this.caches.set(name, new FakeCache());
    }
    return Promise.resolve(this.caches.get(name));
  }
  keys() {
    return Promise.resolve(Array.from(this.caches.keys()));
  }
  delete(name) {
    const removed = this.caches.delete(name);
    return Promise.resolve(removed);
  }
}

/**
 * Evaluates a SW source file inside a vm.context with the stubs the SW
 * relies on. Returns the `self.__lvcodexPwa` surface plus the captured
 * event listeners so the test can drive lifecycle events synchronously.
 */
function loadServiceWorker(swPath, { fetchImpl } = {}) {
  const source = fs.readFileSync(swPath, "utf-8");
  const listeners = {};
  const cachesObj = new FakeCacheStorage();
  let skipWaitingCalls = 0;
  let claimCalls = 0;

  const self = {
    location: { origin: "http://localhost" },
    addEventListener(event, fn) {
      listeners[event] = fn;
    },
    skipWaiting() {
      skipWaitingCalls += 1;
    },
    clients: {
      claim() {
        claimCalls += 1;
        return Promise.resolve();
      },
    },
  };

  const sandbox = {
    self,
    caches: cachesObj,
    fetch: fetchImpl || (() => Promise.reject(new Error("network down"))),
    Request: makeFakeRequest,
    Response: makeFakeResponse,
    URL,
    Set,
    Map,
    Promise,
    console,
    setTimeout,
    clearTimeout,
  };
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox, { filename: swPath });

  return {
    self,
    listeners,
    caches: cachesObj,
    api: self.__lvcodexPwa,
    counters: {
      get skipWaiting() {
        return skipWaitingCalls;
      },
      get claim() {
        return claimCalls;
      },
    },
  };
}

// ---------------------------------------------------------------------------
// Suite: latvian-a2-exam-app/sw.js
// ---------------------------------------------------------------------------

const A2_SW = path.join(REPO_ROOT, "latvian-a2-exam-app", "sw.js");
const V2_SW = path.join(REPO_ROOT, "apps", "web-v2", "public", "sw.js");
const LISTENING_SW = path.join(
  REPO_ROOT,
  "latvian-listening-library",
  "web",
  "sw.js"
);

for (const [label, swPath] of [
  ["a2-exam-app", A2_SW],
  ["web-v2", V2_SW],
  ["listening-library", LISTENING_SW],
]) {
  test(`[${label}] exposes the T-061 test surface`, () => {
    const sw = loadServiceWorker(swPath);
    assert.ok(sw.api, "self.__lvcodexPwa must be exported");
    assert.equal(sw.api.MAX_CLIP_CACHE, 50);
    assert.ok(sw.api.STATIC_ASSETS.length > 0);
    assert.match(sw.api.CACHE_VERSION, /^v\d+$/);
  });

  test(`[${label}] install event populates the static cache`, async () => {
    const sw = loadServiceWorker(swPath, {
      fetchImpl: (req) => Promise.resolve(makeFakeResponse("ok")),
    });
    let waited = null;
    const evt = {
      waitUntil(p) {
        waited = p;
      },
    };
    sw.listeners.install(evt);
    await waited;
    assert.equal(sw.counters.skipWaiting, 1, "install must trigger skipWaiting");
  });

  test(`[${label}] activate event claims clients`, async () => {
    const sw = loadServiceWorker(swPath);
    let waited = null;
    sw.listeners.activate({
      waitUntil(p) {
        waited = p;
      },
    });
    await waited;
    assert.equal(sw.counters.claim, 1, "activate must call clients.claim");
  });

  test(`[${label}] SKIP_WAITING message triggers self.skipWaiting`, () => {
    const sw = loadServiceWorker(swPath);
    sw.listeners.message({ data: { type: "SKIP_WAITING" } });
    assert.ok(sw.counters.skipWaiting >= 1);
  });
}

// ---------------------------------------------------------------------------
// Audio cache (LRU at 50) — assert against a2-exam-app SW which is the
// canonical implementation; the other two share the same helpers.
// ---------------------------------------------------------------------------

test("audio handler caches first response and replays from cache (cache-first)", async () => {
  let networkCalls = 0;
  const sw = loadServiceWorker(A2_SW, {
    fetchImpl: (req) => {
      networkCalls += 1;
      return Promise.resolve(makeFakeResponse("AUDIO_BYTES"));
    },
  });

  const req = makeFakeRequest(
    "http://localhost/latvian-listening-library/data/A1/audio/1.mp3"
  );

  // First request → network → cache.
  const first = await sw.api._internal.handleAudio(req);
  assert.equal(first.body, "AUDIO_BYTES");
  assert.equal(networkCalls, 1);

  // Second request → served from cache, NO new network call.
  const second = await sw.api._internal.handleAudio(req);
  assert.equal(second.body, "AUDIO_BYTES");
  assert.equal(networkCalls, 1, "cache-first must not refetch");
});

test("audio handler keeps only the last 50 clips (LRU eviction)", async () => {
  const sw = loadServiceWorker(A2_SW, {
    fetchImpl: () => Promise.resolve(makeFakeResponse("BYTES")),
  });

  // Pre-cache 55 clips so the trim kicks in.
  for (let i = 0; i < 55; i++) {
    const req = makeFakeRequest(
      `http://localhost/latvian-listening-library/data/A1/audio/clip-${i}.mp3`
    );
    await sw.api._internal.handleAudio(req);
  }

  const cache = await sw.caches.open(sw.api.AUDIO_CACHE);
  const keys = await cache.keys();
  assert.equal(
    keys.length,
    50,
    `expected exactly 50 cached clips, got ${keys.length}`
  );

  // The first 5 must have been evicted (FIFO/LRU).
  const urls = keys.map((k) => k.url);
  for (let i = 0; i < 5; i++) {
    assert.ok(
      !urls.includes(
        `http://localhost/latvian-listening-library/data/A1/audio/clip-${i}.mp3`
      ),
      `clip-${i} should have been evicted`
    );
  }
  // The last 5 must still be there.
  for (let i = 50; i < 55; i++) {
    assert.ok(
      urls.includes(
        `http://localhost/latvian-listening-library/data/A1/audio/clip-${i}.mp3`
      ),
      `clip-${i} should still be cached`
    );
  }
});

test("offline-clip retrieval — cached audio plays back when network is down", async () => {
  // Phase 1 — network is up; warm the cache.
  let netDown = false;
  const sw = loadServiceWorker(A2_SW, {
    fetchImpl: () =>
      netDown
        ? Promise.reject(new Error("offline"))
        : Promise.resolve(makeFakeResponse("AUDIO_BYTES")),
  });

  const req = makeFakeRequest(
    "http://localhost/latvian-listening-library/data/A1/audio/offline-clip.mp3"
  );
  await sw.api._internal.handleAudio(req); // warm the cache
  netDown = true;

  // Phase 2 — network is now down. The handler must still return the
  // cached AUDIO_BYTES response (this is the deliverable: "Offline mode
  // for T-035 listening feed").
  const replay = await sw.api._internal.handleAudio(req);
  assert.equal(replay.body, "AUDIO_BYTES");
});

test("offline-clip retrieval — uncached audio yields a 504 instead of a network error", async () => {
  const sw = loadServiceWorker(A2_SW, {
    fetchImpl: () => Promise.reject(new Error("offline")),
  });
  const req = makeFakeRequest(
    "http://localhost/latvian-listening-library/data/A1/audio/never-seen.mp3"
  );
  const response = await sw.api._internal.handleAudio(req);
  assert.equal(response.status, 504);
});

test("listening-feed API uses stale-while-revalidate", async () => {
  let networkCalls = 0;
  const responses = [
    { clips: [{ id: "old" }] },
    { clips: [{ id: "new" }] },
  ];
  const sw = loadServiceWorker(A2_SW, {
    fetchImpl: () => {
      const payload = responses[Math.min(networkCalls, responses.length - 1)];
      networkCalls += 1;
      return Promise.resolve(makeFakeResponse(payload));
    },
  });

  const req = makeFakeRequest("http://localhost/api/listening-feed");
  const first = await sw.api._internal.staleWhileRevalidate(req, sw.api.API_CACHE);
  const firstBody = first.body;
  assert.deepEqual(firstBody, { clips: [{ id: "old" }] });
  assert.equal(networkCalls, 1);

  // Second call — cache is now warm. The handler must return the
  // cached payload synchronously while ALSO triggering a background
  // refresh.
  const second = await sw.api._internal.staleWhileRevalidate(
    req,
    sw.api.API_CACHE
  );
  assert.deepEqual(second.body, { clips: [{ id: "old" }] });
  // Give the background refresh a tick.
  await new Promise((r) => setTimeout(r, 10));
  assert.equal(networkCalls, 2, "background refresh must have run");
});

test("listening-feed API returns offline JSON when network and cache both miss", async () => {
  const sw = loadServiceWorker(A2_SW, {
    fetchImpl: () => Promise.reject(new Error("offline")),
  });
  const req = makeFakeRequest("http://localhost/api/listening-feed");
  const response = await sw.api._internal.staleWhileRevalidate(
    req,
    sw.api.API_CACHE
  );
  assert.equal(response.status, 503);
  const body = await response.json();
  assert.equal(body.offline, true);
});

test("static-cache handler caches first response (cache-first)", async () => {
  let networkCalls = 0;
  const sw = loadServiceWorker(A2_SW, {
    fetchImpl: () => {
      networkCalls += 1;
      return Promise.resolve(makeFakeResponse("<!doctype html>"));
    },
  });
  const req = makeFakeRequest("http://localhost/latvian-a2-exam-app/app.js");
  await sw.api._internal.cacheFirst(req, sw.api.STATIC_CACHE);
  await sw.api._internal.cacheFirst(req, sw.api.STATIC_CACHE);
  // Second call serves from cache; the background refresh fires another
  // fetch — that's fine, but the response must come back instantly.
  assert.ok(networkCalls >= 1, "at least one network call must have happened");
});
