"""Story-mode routes (T-050).

Installs two endpoints onto :class:`server_app.core.AppHandler`:

* ``GET  /api/story/state``
      Return the caller's full story-mode state — every mission, every
      scene, current unlock status, and the aggregate progress summary.
      Authenticated.
* ``POST /api/story/<mission_id>/scene/<scene_id>/complete``
      Mark one scene completed. Idempotent. Awards scene XP (T-034) on
      first completion and a mission bonus when the final scene of a
      mission flips. Authenticated.

The dispatch hook follows the T-045 / T-064 wrap-the-current-do_GET
pattern so it composes cleanly with the rate-limit, metrics,
debug-gate, T-022 attempt-store, and T-036 SPA static handlers that
are already on the class. The hook is idempotent (``_t050_installed``
marker) so re-importing the module is a no-op.
"""

from __future__ import annotations

import logging
import re
import urllib.parse
from http import HTTPStatus
from typing import TYPE_CHECKING

from server_app.core import (
    ApiError,
    api_error_response,
    db_connection,
    json_response,
    require_session,
)
from server_app.services import story as story_service

if TYPE_CHECKING:  # pragma: no cover - typing only
    from server_app.core import AppHandler


logger = logging.getLogger("lvcodex.story.routes")


ROUTES: list[tuple[str, str]] = [
    ("GET", "/api/story/state"),
    ("POST", "/api/story/<mission_id>/scene/<scene_id>/complete"),
]


_STATE_RE = re.compile(r"^/api/story/state/?$")
_COMPLETE_RE = re.compile(
    r"^/api/story/([A-Za-z0-9_\-]+)/scene/([A-Za-z0-9_\-]+)/complete/?$"
)


def _resolve_path(handler: "AppHandler") -> str:
    raw = getattr(handler, "path", "") or ""
    return urllib.parse.urlparse(raw).path or ""


def _account_id_from_session(handler: "AppHandler") -> str:
    session = require_session(handler)
    account = session.get("account") or {}
    return (account.get("id") or "").strip()


def _map_service_error(error: story_service.StoryError) -> ApiError:
    code_map: dict[type, str] = {
        story_service.MissionNotFound: "mission_not_found",
        story_service.SceneNotFound: "scene_not_found",
        story_service.MissionLocked: "mission_locked",
        story_service.InvalidStoryRequest: "invalid_request",
    }
    code = code_map.get(type(error), "story_error")
    status = error.status_code or HTTPStatus.BAD_REQUEST
    return ApiError(status, code, str(error))


def _handle_state(handler: "AppHandler") -> None:
    try:
        account_id = _account_id_from_session(handler)
        if not account_id:
            json_response(
                handler,
                HTTPStatus.UNAUTHORIZED,
                {"error": "Authentication required."},
            )
            return
        with db_connection() as conn:
            payload = story_service.get_state(conn, account_id)
        json_response(handler, HTTPStatus.OK, payload)
    except story_service.StoryError as error:
        api_error_response(handler, _map_service_error(error))
    except PermissionError as error:
        json_response(handler, HTTPStatus.UNAUTHORIZED, {"error": str(error)})
    except ApiError as error:
        api_error_response(handler, error)
    except Exception as error:  # noqa: BLE001
        logger.exception("story_state_failed")
        json_response(
            handler,
            HTTPStatus.INTERNAL_SERVER_ERROR,
            {"error": "story_unavailable", "detail": type(error).__name__},
        )


def _handle_complete(handler: "AppHandler", mission_id: str, scene_id: str) -> None:
    try:
        account_id = _account_id_from_session(handler)
        if not account_id:
            json_response(
                handler,
                HTTPStatus.UNAUTHORIZED,
                {"error": "Authentication required."},
            )
            return
        with db_connection() as conn:
            result = story_service.complete_scene(
                conn, account_id, mission_id, scene_id
            )
        json_response(handler, HTTPStatus.OK, result)
    except story_service.StoryError as error:
        api_error_response(handler, _map_service_error(error))
    except PermissionError as error:
        json_response(handler, HTTPStatus.UNAUTHORIZED, {"error": str(error)})
    except ApiError as error:
        api_error_response(handler, error)
    except Exception as error:  # noqa: BLE001
        logger.exception("story_complete_failed")
        json_response(
            handler,
            HTTPStatus.INTERNAL_SERVER_ERROR,
            {"error": "story_unavailable", "detail": type(error).__name__},
        )


def install_story_routes() -> None:
    """Patch ``AppHandler.do_GET`` / ``do_POST`` to dispatch story routes.

    Idempotent — uses a ``_t050_installed`` flag on :class:`AppHandler`
    so re-importing the module does not stack handlers.
    """

    from server_app.core import AppHandler

    if getattr(AppHandler, "_t050_installed", False):
        return

    original_do_get = AppHandler.do_GET
    original_do_post = AppHandler.do_POST

    def patched_do_get(self: "AppHandler") -> None:  # type: ignore[no-redef]
        path = _resolve_path(self)
        if _STATE_RE.match(path):
            _handle_state(self)
            return
        original_do_get(self)

    def patched_do_post(self: "AppHandler") -> None:  # type: ignore[no-redef]
        path = _resolve_path(self)
        match = _COMPLETE_RE.match(path)
        if match:
            _handle_complete(self, match.group(1), match.group(2))
            return
        original_do_post(self)

    AppHandler.do_GET = patched_do_get  # type: ignore[assignment]
    AppHandler.do_POST = patched_do_post  # type: ignore[assignment]
    AppHandler._t050_installed = True  # type: ignore[attr-defined]
    logger.info("story_routes_installed")


install_story_routes()


__all__ = ["ROUTES", "install_story_routes"]
