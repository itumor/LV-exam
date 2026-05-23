"""Rate-limit middleware module (T-015 → T-020).

Not a routable endpoint — this module owns the per-IP / per-session
token-bucket middleware that intercepts every ``/api/*`` request before
the route dispatch runs. ``ROUTES`` is intentionally empty; the entry
in ``server_app.routes.__init__.ROUTES`` exists so the audit list can
prove rate-limit is in the load-time hook chain.

Wire order (see :mod:`server_app.__init__`):
    **rate-limit**  →  metrics  →  debug-gate  →  routing
"""

from __future__ import annotations

from server_app.core import (  # noqa: F401
    _t015_enforce,
    _t015_install_middleware,
    _t015_role_for,
    _t015_send_rate_limited,
    _t015_session_id_for,
)

# Rate-limit is a middleware, not a route. The audit list keeps a single
# pseudo-entry so the modularisation test can prove the middleware is
# installed (verified by inspecting AppHandler for the ``_t015_installed``
# marker attribute).
ROUTES: list[tuple[str, str]] = [
    ("MIDDLEWARE", "/api/*"),
]

__all__ = [
    "ROUTES",
    "_t015_enforce",
    "_t015_install_middleware",
    "_t015_role_for",
    "_t015_send_rate_limited",
    "_t015_session_id_for",
]
