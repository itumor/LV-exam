"""Mock-exam routes (T-033).

Exposes the four endpoints the mock-exam runner needs:

* ``POST /api/mock-exam/start`` — create a new sitting; returns
  per-section durations + the assigned mock-exam id.
* ``POST /api/mock-exam/<id>/section/<skill>/submit`` — submit one
  section's answers; the body may include ``answer_key`` (test override)
  or rely on the snapshot stored on the mock-exam row.
* ``GET  /api/mock-exam/<id>/result`` — return per-skill scores,
  overall 9/15 pass flag, and weak-skill suggestions.
* ``GET  /api/mock-exam/history`` — return the caller's past sittings.

Authentication
--------------

All four routes require an active learner session
(:func:`server_app.core.require_session`). ``account_id`` is read from
the resolved session — never trusted from request input — which gives
multi-user isolation for free at the SQL layer.

Installation pattern
--------------------

Mirrors the T-045 NPC routes: a single :func:`install_mock_exam_routes`
function patches ``AppHandler.do_GET`` / ``do_POST`` exactly once
(guarded by ``_t033_installed``). The hook is idempotent so re-importing
this module does not stack handlers.
"""

from __future__ import annotations

import logging
import re
import urllib.parse
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

from server_app.core import (
    ApiError,
    api_error_response,
    db_connection,
    json_response,
    require_session,
    safe_read_json,
)
from server_app.services import mock_exam as mock_exam_service
from server_app.services import xp as xp_service
from server_app.services.mock_exam import (
    MockExamError,
    MockExamNotFound,
    api_error_from,
)


if TYPE_CHECKING:  # pragma: no cover - typing only
    from server_app.core import AppHandler


logger = logging.getLogger("lvcodex.mock_exam.routes")


ROUTES: list[tuple[str, str]] = [
    ("POST", "/api/mock-exam/start"),
    ("POST", "/api/mock-exam/<mock_exam_id>/section/<skill>/submit"),
    ("GET", "/api/mock-exam/<mock_exam_id>/result"),
    ("GET", "/api/mock-exam/history"),
]


_RE_START = re.compile(r"^/api/mock-exam/start/?$")
_RE_SUBMIT = re.compile(
    r"^/api/mock-exam/([A-Za-z0-9_\-]+)/section/([a-z]+)/submit/?$"
)
_RE_RESULT = re.compile(r"^/api/mock-exam/([A-Za-z0-9_\-]+)/result/?$")
_RE_HISTORY = re.compile(r"^/api/mock-exam/history/?$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_path(handler: "AppHandler") -> str:
    raw = getattr(handler, "path", "") or ""
    return urllib.parse.urlparse(raw).path or ""


def _parse_qs(handler: "AppHandler") -> dict[str, list[str]]:
    raw = getattr(handler, "path", "") or ""
    return urllib.parse.parse_qs(urllib.parse.urlparse(raw).query)


def _account_id(session: dict[str, Any]) -> str:
    return (session.get("account") or {}).get("id") or ""


def _award_section_xp(account_id: str, result: dict[str, Any]) -> None:
    """Award T-034 XP for a freshly-scored mock-exam section.

    Two award rules fire here:

    * ``perfect_skill_pass`` (100 XP) when ``score == points_possible``
      for this section and ``points_possible > 0``. The skill name is
      stored on the xp_log payload so analytics can break out perfect
      runs by skill.
    * ``mock_exam_complete`` (50 XP) when this submission completes the
      sitting (i.e. ``mock_exam.status == "completed"``).

    Idempotent calls (``result["idempotent"] is True``) are skipped so
    a learner cannot farm XP by re-submitting the same section. XP
    failures are swallowed — never block the underlying exam flow.
    """

    if not account_id or not isinstance(result, dict):
        return
    if result.get("idempotent"):
        return
    section = result.get("section") or {}
    mock = result.get("mock_exam") or {}
    try:
        score = int(section.get("score") or 0)
        possible = int(section.get("points_possible") or 0)
    except (TypeError, ValueError):
        score = 0
        possible = 0
    perfect = possible > 0 and score == possible
    is_complete = mock.get("status") == "completed"
    if not perfect and not is_complete:
        return
    try:
        with db_connection() as conn:
            if perfect:
                xp_service.award_xp(
                    conn,
                    account_id,
                    xp_service.KIND_PERFECT_SKILL_PASS,
                    payload={
                        "skill": section.get("skill"),
                        "mock_exam_id": mock.get("id"),
                        "score": score,
                        "points_possible": possible,
                    },
                )
            if is_complete:
                xp_service.award_xp(
                    conn,
                    account_id,
                    xp_service.KIND_MOCK_EXAM_COMPLETE,
                    payload={
                        "mock_exam_id": mock.get("id"),
                        "level_code": mock.get("level_code"),
                    },
                )
    except Exception:  # noqa: BLE001 - never block the exam on XP failures
        logger.exception("xp_award_failed_for_mock_exam_section")


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


def _handle_start(handler: "AppHandler") -> None:
    """``POST /api/mock-exam/start`` — start a new sitting."""

    try:
        session = require_session(handler)
        payload = safe_read_json(handler)
        level_code = str(payload.get("level_code") or "A2")
        try:
            result = mock_exam_service.start_mock_exam(
                _account_id(session), level_code=level_code
            )
        except MockExamError as error:
            raise api_error_from(error) from error
        json_response(handler, HTTPStatus.OK, {"mock_exam": result})
    except ApiError as error:
        api_error_response(handler, error)
    except PermissionError as error:
        json_response(handler, HTTPStatus.UNAUTHORIZED, {"error": str(error)})


def _handle_submit(
    handler: "AppHandler", mock_exam_id: str, skill: str
) -> None:
    """``POST /api/mock-exam/<id>/section/<skill>/submit``."""

    try:
        session = require_session(handler)
        payload = safe_read_json(handler)
        answers = payload.get("answers") or {}
        answer_key = payload.get("answer_key") or {}
        expired_flag = bool(payload.get("expired", False))
        time_spent = payload.get("time_spent_seconds")
        try:
            time_spent_int = (
                int(time_spent) if time_spent is not None else None
            )
        except (TypeError, ValueError):
            raise ApiError(
                HTTPStatus.BAD_REQUEST,
                "invalid_request",
                "time_spent_seconds must be an integer.",
            )
        try:
            result = mock_exam_service.submit_section(
                mock_exam_id,
                _account_id(session),
                skill,
                answers=answers,
                answer_key=answer_key,
                time_spent_seconds=time_spent_int,
                expired=expired_flag,
            )
        except MockExamNotFound as error:
            raise api_error_from(error) from error
        except MockExamError as error:
            raise api_error_from(error) from error
        _award_section_xp(_account_id(session), result)
        json_response(handler, HTTPStatus.OK, result)
    except ApiError as error:
        api_error_response(handler, error)
    except PermissionError as error:
        json_response(handler, HTTPStatus.UNAUTHORIZED, {"error": str(error)})


def _handle_result(handler: "AppHandler", mock_exam_id: str) -> None:
    """``GET /api/mock-exam/<id>/result``."""

    try:
        session = require_session(handler)
        try:
            result = mock_exam_service.get_result(
                mock_exam_id, _account_id(session)
            )
        except MockExamError as error:
            raise api_error_from(error) from error
        json_response(handler, HTTPStatus.OK, result)
    except ApiError as error:
        api_error_response(handler, error)
    except PermissionError as error:
        json_response(handler, HTTPStatus.UNAUTHORIZED, {"error": str(error)})


def _handle_history(handler: "AppHandler") -> None:
    """``GET /api/mock-exam/history``."""

    try:
        session = require_session(handler)
        qs = _parse_qs(handler)
        limit_raw = (qs.get("limit") or ["20"])[0]
        try:
            limit = int(limit_raw)
        except (TypeError, ValueError):
            limit = 20
        try:
            entries = mock_exam_service.list_history(
                _account_id(session), limit=limit
            )
        except MockExamError as error:
            raise api_error_from(error) from error
        json_response(handler, HTTPStatus.OK, {"mock_exams": entries})
    except ApiError as error:
        api_error_response(handler, error)
    except PermissionError as error:
        json_response(handler, HTTPStatus.UNAUTHORIZED, {"error": str(error)})


# ---------------------------------------------------------------------------
# Hook installation (T-045 pattern)
# ---------------------------------------------------------------------------


def install_mock_exam_routes() -> None:
    """Patch ``AppHandler.do_GET`` / ``do_POST`` to dispatch mock-exam routes.

    Idempotent — uses an ``_t033_installed`` flag on :class:`AppHandler`
    so re-importing the module does not stack handlers.
    """

    from server_app.core import AppHandler

    if getattr(AppHandler, "_t033_installed", False):
        return

    original_do_get = AppHandler.do_GET
    original_do_post = AppHandler.do_POST

    def patched_do_get(self: "AppHandler") -> None:  # type: ignore[no-redef]
        path = _resolve_path(self)
        if _RE_HISTORY.match(path):
            _handle_history(self)
            return
        m = _RE_RESULT.match(path)
        if m:
            _handle_result(self, m.group(1))
            return
        original_do_get(self)

    def patched_do_post(self: "AppHandler") -> None:  # type: ignore[no-redef]
        path = _resolve_path(self)
        if _RE_START.match(path):
            _handle_start(self)
            return
        m = _RE_SUBMIT.match(path)
        if m:
            _handle_submit(self, m.group(1), m.group(2))
            return
        original_do_post(self)

    AppHandler.do_GET = patched_do_get  # type: ignore[assignment]
    AppHandler.do_POST = patched_do_post  # type: ignore[assignment]
    AppHandler._t033_installed = True  # type: ignore[attr-defined]
    logger.info("mock_exam_routes_installed")


# Install on import — the package __init__ relies on import-time wiring.
install_mock_exam_routes()

# Ensure the DDL is queued up so the first request doesn't pay the cost.
try:
    mock_exam_service.ensure_mock_exam_tables()
except Exception:  # noqa: BLE001 — never crash import if DB is unavailable
    logger.exception("mock_exam_table_init_failed")


__all__ = [
    "ROUTES",
    "install_mock_exam_routes",
]
