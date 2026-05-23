"""Admin-console routes (T-020).

Every endpoint here requires an admin or superadmin session via
``require_admin_session``. The endpoints expose CRUD over exams,
accounts, attempts, and runtime settings. Learner-facing endpoints
intentionally live in :mod:`server_app.routes.exams` and
:mod:`server_app.routes.attempts` — this module is admin-only.
"""

from __future__ import annotations

from server_app.core import (  # noqa: F401
    admin_overview,
    can_manage_account,
    delete_admin_exam,
    list_admin_accounts,
    list_admin_attempts,
    list_admin_settings,
    require_admin_session,
    save_admin_exam,
    save_admin_settings,
    update_admin_account,
    update_admin_exam_status,
)

ROUTES: list[tuple[str, str]] = [
    ("GET", "/api/admin/overview"),
    ("GET", "/api/admin/accounts"),
    ("POST", "/api/admin/accounts/<account_id>"),
    ("GET", "/api/admin/exams"),
    ("POST", "/api/admin/exams"),
    ("GET", "/api/admin/exams/<exam_id>"),
    ("POST", "/api/admin/exams/<exam_id>"),
    ("POST", "/api/admin/exams/<exam_id>/status"),
    ("POST", "/api/admin/exams/<exam_id>/delete"),
    # T-037 — content versioning pipeline (admin-only).
    ("POST", "/api/admin/exams/<exam_id>/publish"),
    ("GET", "/api/admin/exams/<exam_id>/versions"),
    ("GET", "/api/admin/attempts"),
    ("GET", "/api/admin/settings"),
    ("POST", "/api/admin/settings"),
    # T-025 — A2 exam schema (level + skills + task_types).
    ("GET", "/api/admin/schema"),
]

__all__ = [
    "ROUTES",
    "admin_overview",
    "can_manage_account",
    "delete_admin_exam",
    "list_admin_accounts",
    "list_admin_attempts",
    "list_admin_settings",
    "require_admin_session",
    "save_admin_exam",
    "save_admin_settings",
    "update_admin_account",
    "update_admin_exam_status",
]
