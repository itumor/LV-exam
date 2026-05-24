"""Procedural story routes (T-055).

Installs two HTTP endpoints that drive the choose-your-own-adventure
surface:

* ``POST /api/stories/generate-chapter``
      Produce the next chapter of the learner's branching Latvian
      narrative. Reads any pending ``choice_id`` so the new chapter
      acknowledges the previous selection. Returns the new chapter +
      a full state snapshot.

* ``GET  /api/stories/state``
      Return the learner's current story state (seed, chapters,
      pending-choice flag, finished flag). Pure read — no LLM call,
      no quota consumed.

The dispatch hooks compose with the existing chain (rate-limit →
metrics → debug-gate → routing) by wrapping the *current*
``do_GET`` / ``do_POST`` so the new paths win first and unrelated
paths still fall through. Same self-installer pattern as T-064.

Why the routes live here and not in :mod:`server_app.core`
---------------------------------------------------------

The newer routes (T-064 multiplayer, this T-055 module) own their full
dispatch wiring inside the route module so the per-domain audit
(``tests/server/test_modularization.py``) can attribute behaviour to a
single file. The older route modules (T-053 companion, T-045 NPC etc.)
were hooked from ``server_app/core.py`` because at import time the
``server_app.routes`` package eagerly pulls in modules that referenced
symbols defined later in :mod:`server_app.core`. By the time T-064
landed, the import graph had been untangled enough that route modules
can call back into :mod:`server_app.core` safely — so we follow the
newer pattern.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
from http import HTTPStatus
from typing import TYPE_CHECKING

from server_app.core import (
    ApiError,
    api_error_response,
    json_response,
    log_event,
    require_session,
    safe_read_json,
)
from server_app.services import procedural_story as story_service
from server_app.services.procedural_story import (  # noqa: F401  — re-export
    ChoiceOption,
    GenerateChapterRequest,
    GenerateChapterResponse,
    MAX_CHAPTERS_PER_STORY,
    MAX_CHOICES,
    MAX_HISTORY_CHAPTERS,
    MAX_NARRATIVE_CHARS,
    MIN_CHOICES,
    ProceduralStoryError,
    ProceduralStoryFinished,
    ProceduralStoryInvalidRequest,
    ProceduralStoryProviderError,
    QuotaExceededError,
    StoryChapter,
    StoryStateSnapshot,
    ensure_procedural_story_tables_ready,
    generate_chapter,
    load_state,
    parse_generate_request,
    reset_state,
)

if TYPE_CHECKING:  # pragma: no cover
    from server_app.core import AppHandler


logger = logging.getLogger("lvcodex.procedural_story.routes")


ROUTES: list[tuple[str, str]] = [
    ("POST", "/api/stories/generate-chapter"),
    ("GET", "/api/stories/state"),
]


_GENERATE_PATH = "/api/stories/generate-chapter"
_STATE_PATH = "/api/stories/state"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_path(handler: "AppHandler") -> str:
    raw = getattr(handler, "path", "") or ""
    return urllib.parse.urlparse(raw).path or ""


def _matches(path: str, target: str) -> bool:
    return path == target or path.rstrip("/") == target


def _account_id(session: dict) -> str:
    return (session.get("account") or {}).get("id") or ""


def _plan_from_session(session: dict) -> str:
    profile = session.get("profile") or {}
    return profile.get("exam_pack_status") or "free"


# ---------------------------------------------------------------------------
# Route bodies
# ---------------------------------------------------------------------------


def _handle_generate(handler: "AppHandler") -> None:
    """``POST /api/stories/generate-chapter`` — produce the next chapter."""

    try:
        session = require_session(handler)
        account_id = _account_id(session)
        if not account_id:
            json_response(
                handler,
                HTTPStatus.UNAUTHORIZED,
                {"error": "Authentication required."},
            )
            return
        plan = _plan_from_session(session)
        raw_body = safe_read_json(handler)
        try:
            response = generate_chapter(
                account_id=account_id,
                plan=plan,
                raw_body=raw_body,
            )
        except story_service.ProceduralStoryInvalidRequest as error:
            raise ApiError(
                HTTPStatus.BAD_REQUEST,
                "procedural_story_invalid_request",
                str(error),
            ) from error
        except story_service.ProceduralStoryFinished as error:
            raise ApiError(
                HTTPStatus.CONFLICT,
                "procedural_story_finished",
                str(error),
            ) from error
        except QuotaExceededError as error:
            raise ApiError(
                HTTPStatus.TOO_MANY_REQUESTS,
                "ai_quota_exceeded",
                str(error),
            ) from error
        except story_service.ProceduralStoryProviderError as error:
            raise ApiError(
                HTTPStatus.BAD_GATEWAY,
                "procedural_story_provider_unavailable",
                str(error),
            ) from error
        json_response(handler, HTTPStatus.OK, json.loads(response.model_dump_json()))
    except ApiError as error:
        api_error_response(handler, error)
    except PermissionError as error:
        json_response(handler, HTTPStatus.UNAUTHORIZED, {"error": str(error)})
    except Exception as error:  # noqa: BLE001 - defence in depth
        log_event(
            "error",
            "procedural_story_generate_failed",
            error=type(error).__name__,
        )
        json_response(
            handler,
            HTTPStatus.INTERNAL_SERVER_ERROR,
            {"error": "procedural_story_unavailable"},
        )


def _handle_state(handler: "AppHandler") -> None:
    """``GET /api/stories/state`` — read-only snapshot of the story."""

    try:
        session = require_session(handler)
        account_id = _account_id(session)
        if not account_id:
            json_response(
                handler,
                HTTPStatus.UNAUTHORIZED,
                {"error": "Authentication required."},
            )
            return
        try:
            state = load_state(account_id)
        except story_service.ProceduralStoryInvalidRequest as error:
            raise ApiError(
                HTTPStatus.BAD_REQUEST,
                "procedural_story_invalid_request",
                str(error),
            ) from error
        json_response(handler, HTTPStatus.OK, json.loads(state.model_dump_json()))
    except ApiError as error:
        api_error_response(handler, error)
    except PermissionError as error:
        json_response(handler, HTTPStatus.UNAUTHORIZED, {"error": str(error)})
    except Exception as error:  # noqa: BLE001 - defence in depth
        log_event(
            "error",
            "procedural_story_state_failed",
            error=type(error).__name__,
        )
        json_response(
            handler,
            HTTPStatus.INTERNAL_SERVER_ERROR,
            {"error": "procedural_story_unavailable"},
        )


# ---------------------------------------------------------------------------
# Hook installation (T-064 pattern)
# ---------------------------------------------------------------------------


def install_procedural_story_routes() -> None:
    """Patch ``AppHandler.do_GET`` / ``do_POST`` to dispatch the routes.

    Idempotent — uses a ``_t055_installed`` flag on :class:`AppHandler`
    so re-importing the module does not stack handlers.
    """

    from server_app.core import AppHandler

    if getattr(AppHandler, "_t055_installed", False):
        return

    original_do_get = AppHandler.do_GET
    original_do_post = AppHandler.do_POST

    def patched_do_get(self: "AppHandler") -> None:  # type: ignore[no-redef]
        path = _resolve_path(self)
        if _matches(path, _STATE_PATH):
            _handle_state(self)
            return
        original_do_get(self)

    def patched_do_post(self: "AppHandler") -> None:  # type: ignore[no-redef]
        path = _resolve_path(self)
        if _matches(path, _GENERATE_PATH):
            _handle_generate(self)
            return
        original_do_post(self)

    AppHandler.do_GET = patched_do_get  # type: ignore[assignment]
    AppHandler.do_POST = patched_do_post  # type: ignore[assignment]
    AppHandler._t055_installed = True  # type: ignore[attr-defined]
    logger.info("procedural_story_routes_installed")


install_procedural_story_routes()


try:
    ensure_procedural_story_tables_ready()
except Exception:  # noqa: BLE001 — never crash import if DB is unavailable
    pass


__all__ = [
    "ChoiceOption",
    "GenerateChapterRequest",
    "GenerateChapterResponse",
    "MAX_CHAPTERS_PER_STORY",
    "MAX_CHOICES",
    "MAX_HISTORY_CHAPTERS",
    "MAX_NARRATIVE_CHARS",
    "MIN_CHOICES",
    "ProceduralStoryError",
    "ProceduralStoryFinished",
    "ProceduralStoryInvalidRequest",
    "ProceduralStoryProviderError",
    "ROUTES",
    "StoryChapter",
    "StoryStateSnapshot",
    "ensure_procedural_story_tables_ready",
    "generate_chapter",
    "install_procedural_story_routes",
    "load_state",
    "parse_generate_request",
    "reset_state",
]
