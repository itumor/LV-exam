"""Tutor dashboard routes — T-042.

Re-exports the tutor service surface and documents the public routes.
Like T-030 / T-031 / T-041, the actual ``do_GET`` dispatch is installed
by the end-of-file T-042 hook in :mod:`server_app.core` so that this
module stays import-time-free and is safe to import from the
modularization audit list.

Routes owned here:

* ``GET /api/tutor/students`` — list the tutor's org members + their
  per-skill readiness summary (T-030).
* ``GET /api/tutor/students/<account_id>/report`` — render a single
  student report (HTML).
"""

from __future__ import annotations

from server_app.services.tutor import (  # noqa: F401
    PLAN_TIER_STANDARD,
    PLAN_TIER_TUTOR,
    STUDENT_ROLES,
    TUTOR_ROLES,
    TutorError,
    assert_tutor,
    build_student_report_html,
    find_orgs_for_tutor,
    get_student_report,
    init_tutor_extensions,
    is_tutor_for_org,
    list_students,
)

ROUTES: list[tuple[str, str]] = [
    ("GET", "/api/tutor/students"),
    ("GET", "/api/tutor/students/<account_id>/report"),
]

__all__ = [
    "PLAN_TIER_STANDARD",
    "PLAN_TIER_TUTOR",
    "ROUTES",
    "STUDENT_ROLES",
    "TUTOR_ROLES",
    "TutorError",
    "assert_tutor",
    "build_student_report_html",
    "find_orgs_for_tutor",
    "get_student_report",
    "init_tutor_extensions",
    "is_tutor_for_org",
    "list_students",
]
