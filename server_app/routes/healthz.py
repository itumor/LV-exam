"""Health-check route (T-020).

Owns the GET ``/healthz`` endpoint that Fly.io probes via the Docker
HEALTHCHECK directive. The handler body lives inline in
:meth:`server_app.core.AppHandler.do_GET` (a 3-line ``json_response``)
and is documented here for ownership and the modularization audit.
"""

from __future__ import annotations

from server_app.core import json_response  # noqa: F401

ROUTES: list[tuple[str, str]] = [
    ("GET", "/healthz"),
]

__all__ = ["ROUTES", "json_response"]
