"""Metrics route (T-014 → T-020).

The Prometheus ``GET /metrics`` endpoint and its instrumentation hook
were originally added in the T-014 end-of-file block in ``server.py``.
T-020 keeps the install logic in :mod:`server_app.core` (so the hook
ordering is enforced at package import time) and exposes the route
metadata + registry accessor here for ownership and the audit list.

The registry implementation lives in :mod:`server_app.metrics` (formerly
``server/metrics.py``, moved into the package by T-020). The
``_t014_install_metrics_hook`` function in :mod:`server_app.core`
imports the module by file path with ``importlib.util`` so the legacy
loader contract is unchanged — tests that load ``server/metrics.py``
directly via ``importlib`` still work because the file remained at the
old top-level path until the test fixture was updated.

Wire order (see :mod:`server_app.__init__`):
    rate-limit  →  **metrics**  →  debug-gate  →  routing
"""

from __future__ import annotations

from server_app.core import _t014_install_metrics_hook  # noqa: F401

ROUTES: list[tuple[str, str]] = [
    ("GET", "/metrics"),
]


def get_registry():
    """Return the in-process :class:`RequestMetrics` registry.

    Resolved lazily because the hook is installed at module import time —
    importing this route module after ``server_app`` is loaded is
    guaranteed to return the same registry instance the request handler
    is observing.
    """

    from server_app import core as _core

    return getattr(_core, "METRICS_REGISTRY", None)


__all__ = ["ROUTES", "get_registry"]
