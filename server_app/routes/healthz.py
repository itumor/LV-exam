"""Health-check route (T-020, extended in T-028).

Owns the GET ``/healthz`` endpoint that Fly.io probes via the Docker
HEALTHCHECK directive. The handler body lives inline in
:meth:`server_app.core.AppHandler.do_GET` (a small ``json_response``)
and is documented here for ownership and the modularization audit.

Response shape (T-028 — multi-region warm-standby readiness)::

    {
      "status": "ok",
      "region": "lhr"   # value of ``FLY_REGION`` env var; ``unknown`` if unset
    }

The ``region`` field lets the multi-region health-check workflow
(``.github/workflows/region-health.yml``) verify cross-region routing.
"""

from __future__ import annotations

from server_app.core import json_response  # noqa: F401

ROUTES: list[tuple[str, str]] = [
    ("GET", "/healthz"),
]

__all__ = ["ROUTES", "json_response"]
