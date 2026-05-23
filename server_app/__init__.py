"""lvcodex server application package (T-020).

This package replaces the historical 5800-line ``server.py`` monolith. The
public API of the package is intentionally narrow — only ``create_app()``
and ``serve()`` are guaranteed stable. Every other name re-exported from
``server_app.core`` is provided for backwards compatibility with the
existing test suite (``import server`` continues to work via the
top-level ``server.py`` shim, which simply ``from server_app import *``).

Middleware / hook ordering (load-time, MUST be preserved):

    1. rate-limit     (``server_app.routes.rate_limit``)   — T-015
    2. metrics        (``server_app.routes.metrics``)      — T-014
    3. debug-gate     (``server_app.routes.debug``)        — T-010
    4. routing        (``AppHandler.do_GET`` / ``do_POST``)

The rate-limit hook short-circuits 429s before any other work runs; the
metrics hook wraps the routing layer so every request (including 429s
from rate-limit) records latency + status; the debug-gate hook intercepts
``/api/debug/*`` and returns 404 for non-admins before the router sees the
path. The actual install order is enforced by ``server_app.core``, which
applies the hooks in this exact sequence at module import time. The
ordering matters: swapping rate-limit and metrics would cause the
histogram to lose all rejected requests, and moving the debug gate after
routing would leak the existence of debug endpoints to anonymous callers.

The five end-of-file hook blocks (T-010 debug, T-011 legal, T-014
metrics, T-015 rate-limit, T-018 speaking-upload) have been split into
per-domain modules under ``server_app/routes/`` to make merge collisions
on this surface less likely going forward. Their implementations remain
in ``server_app.core`` for this PR so behaviour is bit-for-bit identical
to ``develop``; subsequent PRs (T-020a / T-020b) will move the bodies
into their respective route modules.
"""

from __future__ import annotations

# Import the core module FIRST. Loading it has the side effect of wiring
# every hook (rate-limit → metrics → debug-gate → routing → uploads) onto
# ``AppHandler`` in the documented order. ``serve()`` and ``main()`` are
# then exposed for the shim entrypoint.
from . import core  # noqa: F401  (side-effect: hook installation)
from .core import (  # noqa: F401  (re-exported for ``import server``)
    AppHandler,
    DualStackServer,
    main,
)


def create_app() -> type:
    """Return the HTTP request handler class used by :func:`serve`.

    The current implementation uses Python's stdlib ``ThreadingHTTPServer``
    so there is no FastAPI/Starlette ``app`` object to return — instead we
    return the ``AppHandler`` class, which is the closest analogue and is
    what ``DualStackServer`` consumes when bound to a port. A future task
    will migrate the server to an ASGI framework and change this signature
    to return a callable ASGI application; the entrypoint
    (``serve()``) is the stable boundary.
    """

    return AppHandler


def serve() -> int:
    """Boot the HTTP server. Returns the exit code (always ``0`` today).

    Delegates to :func:`server_app.core.main`, which loads the dotenv
    config, initialises Sentry + the auth store, and starts the
    :class:`DualStackServer` on ``PORT`` (default 4173). The function
    blocks until the server is stopped (e.g. SIGINT).
    """

    return main()


__all__ = [
    "AppHandler",
    "DualStackServer",
    "create_app",
    "main",
    "serve",
]
