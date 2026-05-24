"""Admin-console routes (T-020 / T-020b).

Owns the body of every admin-only endpoint. The dispatch
(``self.path == "/api/admin/..."`` branches inside
:meth:`AppHandler.do_GET` / ``do_POST``) still calls into this
module so the route literals remain visible to the modularisation
audit, but every byte of admin business logic for the GET/POST
overview, accounts, exams, attempts, and settings endpoints lives
here.

Routes owned (handler bodies live in this module):

GET endpoints
    * ``GET /api/admin/overview``
    * ``GET /api/admin/accounts``
    * ``GET /api/admin/exams``
    * ``GET /api/admin/exams/<exam_id>``
    * ``GET /api/admin/attempts``
    * ``GET /api/admin/settings``

POST endpoints
    * ``POST /api/admin/exams``
    * ``POST /api/admin/exams/<exam_id>``
    * ``POST /api/admin/exams/<exam_id>/status``
    * ``POST /api/admin/exams/<exam_id>/delete``
    * ``POST /api/admin/accounts/<account_id>``
    * ``POST /api/admin/settings``

The other admin routes (``/api/admin/exams/<id>/publish``,
``/api/admin/exams/<id>/versions``, ``/api/admin/schema``,
``/api/admin/audit-export``) are installed via end-of-file
monkey-patch hooks (T-025 / T-037 / T-043) in
:mod:`server_app.core` and remain dispatched there. They are
listed in ``ROUTES`` below for the audit list.

Each handler takes the live :class:`AppHandler` instance and any
URL-captured groups (e.g. ``exam_id``) as positional args. The
module is imported through :mod:`server_app.core` so callers go via
``_core.handle_*`` indirection — that way ``patch.object(server,
"json_response", …)`` test patterns still reach the live response
function.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING

# Import the module (not symbols) so that
# ``patch.object(server_app.core, "json_response", ...)`` reaches the
# reference site here. Direct ``from server_app.core import json_response``
# binds a *local* name at import time and bypasses unittest.mock patches.
from server_app import core as _core

# Re-export the legacy-named symbols for code that imports them from this
# module (``from server_app.routes.admin import save_admin_exam``).
admin_overview = _core.admin_overview
can_manage_account = _core.can_manage_account
delete_admin_exam = _core.delete_admin_exam
list_admin_accounts = _core.list_admin_accounts
list_admin_attempts = _core.list_admin_attempts
list_admin_settings = _core.list_admin_settings
require_admin_session = _core.require_admin_session
save_admin_exam = _core.save_admin_exam
save_admin_settings = _core.save_admin_settings
update_admin_account = _core.update_admin_account
update_admin_exam_status = _core.update_admin_exam_status

if TYPE_CHECKING:  # pragma: no cover - typing only
    from server_app.core import AppHandler


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
    # T-043 — Audit-log export (CSV default, JSON via Accept or ?format).
    ("GET", "/api/admin/audit-export"),
]


# ---------------------------------------------------------------------------
# Internal helper for the shared admin error-handling block.
# ---------------------------------------------------------------------------


def _handle_admin_errors(handler: "AppHandler", func) -> None:
    """Run ``func()`` with the standard admin try / except wrapper.

    Every admin GET / POST in :meth:`AppHandler.do_GET` / ``do_POST``
    used the identical 4-line ``except ApiError / PermissionError``
    block. This helper centralises it so each handler body is just
    the bit unique to its route.
    """

    try:
        func()
    except _core.ApiError as error:
        _core.api_error_response(handler, error)
    except PermissionError as error:
        _core.json_response(handler, HTTPStatus.UNAUTHORIZED, {"error": str(error)})


# ---------------------------------------------------------------------------
# GET handler bodies (peeled from server_app/core.py — T-020b).
# ---------------------------------------------------------------------------


def handle_admin_overview(handler: "AppHandler") -> None:
    """GET ``/api/admin/overview`` — admin/superadmin only."""

    def _body() -> None:
        _core.require_admin_session(handler)
        _core.json_response(handler, HTTPStatus.OK, _core.admin_overview())

    _handle_admin_errors(handler, _body)


def handle_admin_accounts_list(handler: "AppHandler") -> None:
    """GET ``/api/admin/accounts`` — admin/superadmin only."""

    def _body() -> None:
        _core.require_admin_session(handler)
        _core.json_response(handler, HTTPStatus.OK, _core.list_admin_accounts())

    _handle_admin_errors(handler, _body)


def handle_admin_exams_list(handler: "AppHandler") -> None:
    """GET ``/api/admin/exams`` — admin catalog (includes drafts)."""

    def _body() -> None:
        session = _core.require_admin_session(handler)
        _core.json_response(handler, HTTPStatus.OK, _core.list_exam_catalog(session))

    _handle_admin_errors(handler, _body)


def handle_admin_exam_detail(handler: "AppHandler", exam_id: str) -> None:
    """GET ``/api/admin/exams/<exam_id>`` — full exam row with answer key."""

    def _body() -> None:
        _core.require_admin_session(handler)
        with _core.db_connection() as conn:
            row = conn.execute(
                "SELECT * FROM exams WHERE id = ?", (exam_id,)
            ).fetchone()
        if row is None:
            raise _core.ApiError(
                HTTPStatus.NOT_FOUND, "exam_not_found", "Exam not found."
            )
        _core.json_response(
            handler,
            HTTPStatus.OK,
            {"exam": _core.serialize_exam_catalog(row, include_answer_key=True)},
        )

    _handle_admin_errors(handler, _body)


def handle_admin_attempts_list(handler: "AppHandler") -> None:
    """GET ``/api/admin/attempts`` — attempt history (admin)."""

    def _body() -> None:
        _core.require_admin_session(handler)
        _core.json_response(handler, HTTPStatus.OK, _core.list_admin_attempts())

    _handle_admin_errors(handler, _body)


def handle_admin_settings_list(handler: "AppHandler") -> None:
    """GET ``/api/admin/settings`` — runtime feature flag dump."""

    def _body() -> None:
        _core.require_admin_session(handler)
        _core.json_response(handler, HTTPStatus.OK, _core.list_admin_settings())

    _handle_admin_errors(handler, _body)


# ---------------------------------------------------------------------------
# POST handler bodies (peeled from server_app/core.py — T-020b).
# ---------------------------------------------------------------------------


def handle_admin_exams_create(handler: "AppHandler") -> None:
    """POST ``/api/admin/exams`` — create a new exam catalog row."""

    payload = _core.safe_read_json(handler)
    session = _core.require_admin_session(handler)
    _core.json_response(
        handler, HTTPStatus.OK, _core.save_admin_exam(payload, session)
    )


def handle_admin_exam_update(handler: "AppHandler", exam_id: str) -> None:
    """POST ``/api/admin/exams/<exam_id>`` — update an exam catalog row."""

    payload = _core.safe_read_json(handler)
    session = _core.require_admin_session(handler)
    _core.json_response(
        handler,
        HTTPStatus.OK,
        _core.save_admin_exam(payload, session, exam_id),
    )


def handle_admin_exam_status(handler: "AppHandler", exam_id: str) -> None:
    """POST ``/api/admin/exams/<exam_id>/status`` — toggle published / draft."""

    payload = _core.safe_read_json(handler)
    _core.require_admin_session(handler)
    _core.json_response(
        handler,
        HTTPStatus.OK,
        _core.update_admin_exam_status(exam_id, payload),
    )


def handle_admin_exam_delete(handler: "AppHandler", exam_id: str) -> None:
    """POST ``/api/admin/exams/<exam_id>/delete`` — soft-delete an exam."""

    _core.require_admin_session(handler)
    _core.json_response(
        handler, HTTPStatus.OK, _core.delete_admin_exam(exam_id)
    )


def handle_admin_account_update(handler: "AppHandler", account_id: str) -> None:
    """POST ``/api/admin/accounts/<account_id>`` — promote / suspend / etc."""

    payload = _core.safe_read_json(handler)
    session = _core.require_admin_session(handler)
    _core.json_response(
        handler,
        HTTPStatus.OK,
        _core.update_admin_account(account_id, payload, session),
    )


def handle_admin_settings_save(handler: "AppHandler") -> None:
    """POST ``/api/admin/settings`` — update runtime feature flags."""

    payload = _core.safe_read_json(handler)
    _core.require_admin_session(handler)
    _core.json_response(
        handler, HTTPStatus.OK, _core.save_admin_settings(payload)
    )


__all__ = [
    "ROUTES",
    "admin_overview",
    "can_manage_account",
    "delete_admin_exam",
    "handle_admin_account_update",
    "handle_admin_accounts_list",
    "handle_admin_attempts_list",
    "handle_admin_exam_delete",
    "handle_admin_exam_detail",
    "handle_admin_exam_status",
    "handle_admin_exam_update",
    "handle_admin_exams_create",
    "handle_admin_exams_list",
    "handle_admin_overview",
    "handle_admin_settings_list",
    "handle_admin_settings_save",
    "list_admin_accounts",
    "list_admin_attempts",
    "list_admin_settings",
    "require_admin_session",
    "save_admin_exam",
    "save_admin_settings",
    "update_admin_account",
    "update_admin_exam_status",
]
