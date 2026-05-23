# lvcodex server architecture

Last updated: 2026-05-23 (T-020 modularisation merged)

## Overview

The lvcodex backend is a Python 3.12 service that serves the Latvian A2
exam simulator (static frontend under `latvian-a2-exam-app/`) and a
REST-style API for authentication, attempts, billing, admin, AI scoring,
and observability. It runs on `http.server.ThreadingHTTPServer` with a
custom dual-stack (IPv6/IPv4) bind. Migration to an ASGI framework
(FastAPI) is tracked separately and is **not** part of T-020.

## Package layout (post T-020)

```
server.py                              # 30-line shim → server_app
server_app/
├── __init__.py                        # exports serve() + create_app()
├── core.py                            # the historic 5800-line body
├── handler.py                         # re-exports AppHandler + DualStackServer
├── deps.py                            # request-level dep helpers
├── metrics.py                         # in-process Prometheus registry (T-014)
├── routes/
│   ├── __init__.py                    # assembles audit ROUTES table
│   ├── admin.py                       # /api/admin/*
│   ├── attempts.py                    # /api/attempts/*, /api/evaluate, /api/dashboard
│   ├── auth.py                        # /api/auth/*, /api/session, /api/profile
│   ├── billing.py                     # /api/billing/*, /api/stripe/webhook
│   ├── debug.py                       # /api/debug/*    (T-010 gate)
│   ├── exams.py                       # /api/exams/*, /api/practice-feed
│   ├── healthz.py                     # /healthz
│   ├── legal.py                       # /legal/*        (T-011)
│   ├── metrics.py                     # /metrics        (T-014)
│   ├── rate_limit.py                  # MIDDLEWARE      (T-015)
│   ├── uploads.py                     # /api/uploads/speaking/*  (T-018)
│   └── voice.py                       # /api/voice/score         (T-046)
├── services/
│   ├── __init__.py
│   ├── attempts.py                    # attempt-lifecycle service layer
│   ├── auth_store.py                  # SQLite auth-store helpers
│   ├── evaluator.py                   # LLM evaluator pipeline
│   ├── quota.py                       # per-IP / per-learner quota helpers
│   ├── sentry_init.py                 # observability bootstrap
│   └── voice.py                       # STT + pronunciation scorer (T-046)
└── models/
    └── __init__.py                    # row mappers + ApiError + redaction
```

The route modules and service modules are **thin re-export modules** for
T-020 — the function bodies still live in `server_app.core`. This is a
deliberate behaviour-preserving choice: the routing dispatcher uses five
end-of-file monkey-patch hook blocks (T-010, T-011, T-014, T-015, T-018)
to compose `AppHandler.do_GET` and `do_POST`, and lifting those bodies
into separate modules would have required re-running the patch chain
against the new class object. T-020a / T-020b will progressively peel
the bodies out, one domain at a time, each behind its own PR with a
narrow regression risk.

## Middleware / hook ordering

The five end-of-file hook blocks are applied at package import time, in
this exact order. Reordering them changes observable behaviour.

```
1. rate-limit  (T-015)  → /api/* requests blocked with 429 + Retry-After
2. metrics     (T-014)  → wraps do_GET/do_POST to record latency + status
                          for EVERY request, including 429s from (1)
3. debug-gate  (T-010)  → /api/debug/* requires ?debug=1 + admin role
                          (returns 404 to learner accounts — no leak)
4. uploads     (T-018)  → patches do_GET/do_POST for /api/uploads/speaking/*
5. routing              → AppHandler.do_GET / do_POST internal dispatch
```

The audit test in `tests/server/test_modularization.py` (`HookOrderingTests`)
verifies marker attributes set by each hook (`_t015_installed`,
`METRICS_REGISTRY`, re-exported gate helpers) so an accidental hook
removal or reorder fails CI loudly.

## Module ownership

| Path | Owner | Notes |
| --- | --- | --- |
| `/server.py` | @itumor | 30-line shim — do not add logic here |
| `/server_app/` | @itumor | structural refactor target (T-020) |
| `/server_app/routes/` | @itumor | per-domain ownership (CODEOWNERS) |
| `/server_app/services/` | @itumor | cross-cutting service layer |
| `/server_app/core.py` | @itumor | hot file — collision-prone, prefer route extraction |

## Backwards compatibility

`server.py` aliases the imported module to `server_app.core` via
`sys.modules[__name__] = _core`. This means:

* `import server` works.
* `server.AUTH_DB_PATH = …` mutates the live module (used by tests).
* `from server import AppHandler` works.
* `python3 server.py` boots the same HTTP server on the same port.

The Fly.io Docker image (`CMD ["python", "server.py"]`) and the
Playwright test runner (`webServer.command: "python3 server.py"`) are
unchanged.

## Migration notes

* The legacy top-level `server/` directory (which previously held
  `metrics.py` only) has been removed. The metrics module lives at
  `server_app/metrics.py` and is loaded by file path via `importlib.util`
  from the T-014 hook so the import does not collide with the
  `server.py` shim.
* No HTTP routes, response codes, headers, or response bodies were
  changed by T-020.
* The Sentry breadcrumb format and the structured JSON log lines emitted
  by `log_event(…)` are identical to the pre-refactor format.

## Future work

* **T-020a**: extract the auth-route bodies into `server_app/routes/auth.py`.
* **T-020b**: extract the billing-route bodies into `server_app/routes/billing.py`.
* **T-021**: migrate `AppHandler` to a FastAPI/Starlette ASGI app behind
  `create_app()`. The signature stays compatible; the implementation flips.
