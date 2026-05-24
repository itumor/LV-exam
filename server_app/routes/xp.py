"""T-034 — XP + streak routes (re-export module).

The actual dispatch wiring lives in :mod:`server_app.core` (look for the
``T-034`` hook block) so it can be installed at the right point in the
``do_GET`` wrapper chain — specifically **before** the T-036 SPA static
handler so that T-036 stays the outermost ``do_GET`` wrapper.

This module exists for two reasons:

1. The modularization audit (``tests/server/test_modularization.py``)
   reads ``ROUTES`` from each per-domain module to verify every
   documented route resolves to a dispatch path.
2. Re-exporting the service surface keeps a stable import path
   (``server_app.routes.xp``) for downstream code and tests.
"""

from __future__ import annotations

from server_app.services.xp import (  # noqa: F401
    KIND_MISSION_COMPLETE,
    KIND_MOCK_EXAM_COMPLETE,
    KIND_PERFECT_SKILL_PASS,
    KIND_QUIZ_CORRECT,
    XP_AMOUNTS,
    award_xp,
    ensure_xp_schema,
    get_summary,
    update_streak,
)

ROUTES: list[tuple[str, str]] = [
    ("GET", "/api/xp/summary"),
]

__all__ = [
    "KIND_MISSION_COMPLETE",
    "KIND_MOCK_EXAM_COMPLETE",
    "KIND_PERFECT_SKILL_PASS",
    "KIND_QUIZ_CORRECT",
    "ROUTES",
    "XP_AMOUNTS",
    "award_xp",
    "ensure_xp_schema",
    "get_summary",
    "update_streak",
]
