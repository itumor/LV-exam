"""Per-domain route modules (T-020).

Each submodule documents the routes owned by a single domain and
re-exports the dispatch helpers and constants used by
:class:`server_app.core.AppHandler`. The actual ``do_GET`` / ``do_POST``
dispatch still lives in :mod:`server_app.core` so that this refactor is
provably behaviour-preserving — but ownership and review boundaries are
now drawn by these per-domain files.

The audited route table (consumed by
``tests/server/test_modularization.py``) is assembled by importing each
submodule's ``ROUTES`` constant.
"""

from __future__ import annotations

from . import (  # noqa: F401  (re-exported for the audit list)
    admin,
    attempts,
    auth,
    billing,
    debug,
    exams,
    healthz,
    legal,
    listening_feed,
    metrics,
    rate_limit,
    uploads,
)

# Assemble a registry of (method, route_pattern, owner_module) tuples so
# the modularization test can prove every documented route resolves to a
# dispatch path inside ``AppHandler``.
ROUTES: list[tuple[str, str, str]] = []
for _module in (
    healthz,
    metrics,
    auth,
    exams,
    attempts,
    billing,
    admin,
    uploads,
    legal,
    debug,
    listening_feed,
    rate_limit,
):
    for _method, _pattern in _module.ROUTES:
        ROUTES.append((_method, _pattern, _module.__name__.rsplit(".", 1)[-1]))

__all__ = [
    "ROUTES",
    "admin",
    "attempts",
    "auth",
    "billing",
    "debug",
    "exams",
    "healthz",
    "legal",
    "listening_feed",
    "metrics",
    "rate_limit",
    "uploads",
]
