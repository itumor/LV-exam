"""Per-domain route modules (T-020 / T-020b).

Each submodule documents the routes owned by a single domain.
The ``do_GET`` / ``do_POST`` dispatch chain still lives in
:mod:`server_app.core` so the route literals stay visible to the
modularisation audit, but per-domain modules own:

* the route registry (``ROUTES`` tuple, used by the audit list and
  the OpenAPI contract test); and
* (where the body has been peeled) the actual ``handle_*`` functions
  the dispatch calls into — T-020b moved the billing + admin handler
  bodies into :mod:`server_app.routes.billing` and
  :mod:`server_app.routes.admin`. Other modules still re-export
  helpers from :mod:`server_app.core` for ownership boundaries until
  their bodies get peeled in follow-up tickets.

The audited route table (consumed by
``tests/server/test_modularization.py``) is assembled by importing each
submodule's ``ROUTES`` constant.
"""

from __future__ import annotations

from . import (  # noqa: F401  (re-exported for the audit list)
    admin,
    attempts,
    auth,
    avatars,
    billing,
    companion,
    curriculum,
    debug,
    exams,
    healthz,
    institutional,
    leaderboards,
    legal,
    listening_feed,
    metrics,
    mock_exam,
    multiplayer,
    npc,
    procedural_story,
    rate_limit,
    sso,
    srs,
    story,
    tenant,
    tutor,
    uploads,
    voice,
    xp,
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
    sso,
    srs,
    tenant,
    npc,
    voice,
    mock_exam,
    xp,
    institutional,
    tutor,
    companion,
    multiplayer,
    curriculum,
    story,
    leaderboards,
    procedural_story,
    avatars,
):
    for _method, _pattern in _module.ROUTES:
        ROUTES.append((_method, _pattern, _module.__name__.rsplit(".", 1)[-1]))

__all__ = [
    "ROUTES",
    "admin",
    "attempts",
    "auth",
    "avatars",
    "billing",
    "companion",
    "curriculum",
    "debug",
    "exams",
    "healthz",
    "institutional",
    "leaderboards",
    "legal",
    "listening_feed",
    "metrics",
    "mock_exam",
    "multiplayer",
    "npc",
    "procedural_story",
    "rate_limit",
    "sso",
    "srs",
    "story",
    "tenant",
    "tutor",
    "uploads",
    "voice",
    "xp",
]
