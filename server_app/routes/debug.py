"""Debug-gate routes (T-010 → T-020).

The ``/api/debug/*`` surface is gated behind BOTH the ``?debug=1`` query
parameter AND an admin/superadmin session. The middleware installs a
404 short-circuit on :class:`server_app.core.AppHandler.do_GET` so the
existence of the debug endpoints is not leaked to learner accounts (any
failed gate returns 404, never 401/403).
"""

from __future__ import annotations

from server_app.core import (  # noqa: F401
    DEBUG_API_PREFIX,
    DebugAccessDenied,
    handle_debug_request,
    require_debug_access,
)

ROUTES: list[tuple[str, str]] = [
    ("GET", "/api/debug/session"),
]

__all__ = [
    "DEBUG_API_PREFIX",
    "DebugAccessDenied",
    "ROUTES",
    "handle_debug_request",
    "require_debug_access",
]
