"""T-031 — Daily mission routes (re-export module).

The actual dispatch wiring lives in :mod:`server_app.core` (look for the
``T-031`` hook block) so it can sit at the right point in the install
chain — specifically, ``do_GET`` must be wrapped **before** the T-036
SPA static handler so that T-036 stays the outermost ``do_GET`` wrapper.

This module exists for two reasons:

1. The modularization audit (``tests/server/test_modularization.py``)
   reads ``ROUTES`` from each per-domain module to verify every
   documented route resolves to a dispatch path.
2. Re-exporting the service surface keeps a stable import path
   (``server_app.routes.missions``) for downstream code and tests.
"""

from __future__ import annotations

from server_app.services.missions import (  # noqa: F401
    complete_mission,
    compute_weak_skill,
    ensure_missions_schema,
    get_or_generate_today,
    local_date_for_account,
)

ROUTES: list[tuple[str, str]] = [
    ("GET", "/api/missions/today"),
    ("POST", "/api/missions/<mission_id>/complete"),
]

__all__ = [
    "ROUTES",
    "complete_mission",
    "compute_weak_skill",
    "ensure_missions_schema",
    "get_or_generate_today",
    "local_date_for_account",
]
