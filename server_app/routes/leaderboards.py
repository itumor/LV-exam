"""T-052 — Leaderboards routes (re-export module).

The actual dispatch wiring lives in :mod:`server_app.core` (look for the
``T-052`` hook block) so it can be installed at the right point in the
``do_GET`` wrapper chain — specifically **before** the T-036 SPA static
handler so that T-036 stays the outermost ``do_GET`` wrapper.

This module exists for two reasons:

1. The modularization audit (``tests/server/test_modularization.py``)
   reads ``ROUTES`` from each per-domain module to verify every
   documented route resolves to a dispatch path.
2. Re-exporting the service surface keeps a stable import path
   (``server_app.routes.leaderboards``) for downstream code and tests.

Routes
------

``GET /api/leaderboards/weekly``
    Top N learners by XP earned in the trailing 7 days.

``GET /api/leaderboards/friends``
    Top N among the caller's accepted friends (caller always included).

``GET /api/leaderboards/by-city``
    Top N learners by all-time XP, filtered by the ``city`` query
    parameter (case-insensitive). Returns an empty board if the
    ``accounts.city`` column has not been provisioned.

All three endpoints accept an optional ``?limit=`` query parameter
(default 20, hard cap 100). Authentication is required: the response
includes a per-caller ``viewer`` block so the frontend can show
"you are #14 of 312" without exposing PII.
"""

from __future__ import annotations

from server_app.services.leaderboards import (  # noqa: F401
    CACHE_TTL_SECONDS,
    DEFAULT_LIMIT,
    MAX_LIMIT,
    SCOPE_ALL_TIME,
    SCOPE_BY_CITY,
    SCOPE_BY_FRIENDS,
    SCOPE_WEEKLY,
    VALID_SCOPES,
    add_friend,
    build_board,
    ensure_leaderboards_schema,
    remove_friend,
    top_xp_all_time,
    top_xp_by_city,
    top_xp_by_friends,
    top_xp_weekly,
)

ROUTES: list[tuple[str, str]] = [
    ("GET", "/api/leaderboards/weekly"),
    ("GET", "/api/leaderboards/friends"),
    ("GET", "/api/leaderboards/by-city"),
]

__all__ = [
    "CACHE_TTL_SECONDS",
    "DEFAULT_LIMIT",
    "MAX_LIMIT",
    "ROUTES",
    "SCOPE_ALL_TIME",
    "SCOPE_BY_CITY",
    "SCOPE_BY_FRIENDS",
    "SCOPE_WEEKLY",
    "VALID_SCOPES",
    "add_friend",
    "build_board",
    "ensure_leaderboards_schema",
    "remove_friend",
    "top_xp_all_time",
    "top_xp_by_city",
    "top_xp_by_friends",
    "top_xp_weekly",
]
