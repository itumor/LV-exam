"""Multiplayer roleplay routes (T-064).

Installs the five endpoints that drive the two-user roleplay surface:

* ``GET  /api/multiplayer/scenarios``
      List the curated A2 scenarios (cafe, airport, shop, doctor,
      neighbour). Returns role metadata so the UI can render a "what
      will I be doing?" preview before the learner queues.

* ``POST /api/multiplayer/queue``
      Place the caller in the matchmaking queue for a scenario, or
      pair immediately if another learner is already waiting. Returns
      either ``{"status":"queued",...}`` or ``{"status":"matched","room":{...}}``.

* ``GET  /api/multiplayer/room/<room_id>/stream``
      Server-Sent Events stream for a paired participant. Yields
      ``hello``, ``message``, ``peer_joined``, ``peer_left``,
      ``room_closed`` and periodic heartbeat frames until either the
      room closes or the client disconnects. Disconnect triggers the
      registry's cleanup logic which broadcasts ``peer_left`` to the
      partner.

* ``POST /api/multiplayer/room/<room_id>/say``
      Publish a message from the caller (text and/or audio). Audio is
      resolved through the T-018 upload store and transcribed via the
      T-046 STT shim so the partner sees both the transcript and a
      playable ``audio_url``.

* ``POST /api/multiplayer/room/<room_id>/leave``
      Explicit leave — closes the room and broadcasts ``peer_left``
      with ``reason: "explicit_leave"``.

The dispatch hooks compose with the existing chain (rate-limit →
metrics → debug-gate → routing) by wrapping the *current*
``do_GET`` / ``do_POST`` so the multiplayer paths win first and
unrelated paths still fall through to the previous handler. This is
the same pattern T-045 (NPC) and T-046 (voice scoring) use.
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
    json_response,
    require_session,
    safe_read_json,
)
from server_app.services import multiplayer as mp_service

if TYPE_CHECKING:  # pragma: no cover
    from server_app.core import AppHandler


logger = logging.getLogger("lvcodex.multiplayer.routes")


ROUTES: list[tuple[str, str]] = [
    ("GET", "/api/multiplayer/scenarios"),
    ("POST", "/api/multiplayer/queue"),
    ("GET", "/api/multiplayer/room/<room_id>/stream"),
    ("POST", "/api/multiplayer/room/<room_id>/say"),
    ("POST", "/api/multiplayer/room/<room_id>/leave"),
]


_SCENARIOS_RE = re.compile(r"^/api/multiplayer/scenarios/?$")
_QUEUE_RE = re.compile(r"^/api/multiplayer/queue/?$")
_STREAM_RE = re.compile(r"^/api/multiplayer/room/([A-Za-z0-9_-]+)/stream/?$")
_SAY_RE = re.compile(r"^/api/multiplayer/room/([A-Za-z0-9_-]+)/say/?$")
_LEAVE_RE = re.compile(r"^/api/multiplayer/room/([A-Za-z0-9_-]+)/leave/?$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_path(handler: "AppHandler") -> str:
    raw = getattr(handler, "path", "") or ""
    return urllib.parse.urlparse(raw).path or ""


def _account_from_session(handler: "AppHandler") -> tuple[str, str]:
    """Resolve (account_id, display_name) from the active session."""

    session = require_session(handler)
    account = session.get("account") or {}
    profile = session.get("profile") or {}
    account_id = (account.get("id") or "").strip()
    display_name = (
        profile.get("full_name") or account.get("email") or "Learner"
    ).strip() or "Learner"
    return account_id, display_name


def _map_service_error(error: mp_service.MultiplayerError) -> ApiError:
    """Translate service-layer exceptions to the HTTP-layer ApiError shape."""

    code_map: dict[type, str] = {
        mp_service.ScenarioNotFound: "scenario_not_found",
        mp_service.RoomNotFound: "room_not_found",
        mp_service.NotParticipant: "not_participant",
        mp_service.RoomFull: "room_full",
        mp_service.InvalidRequest: "invalid_request",
    }
    code = code_map.get(type(error), "multiplayer_error")
    status = error.status_code or HTTPStatus.BAD_REQUEST
    return ApiError(status, code, str(error))


# ---------------------------------------------------------------------------
# Route bodies
# ---------------------------------------------------------------------------


def _handle_list_scenarios(handler: "AppHandler") -> None:
    try:
        require_session(handler)
        scenarios = mp_service.list_scenarios()
        json_response(handler, HTTPStatus.OK, {"scenarios": scenarios})
    except PermissionError as error:
        json_response(handler, HTTPStatus.UNAUTHORIZED, {"error": str(error)})


def _handle_queue(handler: "AppHandler") -> None:
    try:
        account_id, display_name = _account_from_session(handler)
        raw_body = safe_read_json(handler)
        result = mp_service.enqueue(
            account_id=account_id,
            display_name=display_name,
            raw_body=raw_body,
        )
        json_response(handler, HTTPStatus.OK, result)
    except mp_service.MultiplayerError as error:
        api_error_response(handler, _map_service_error(error))
    except PermissionError as error:
        json_response(handler, HTTPStatus.UNAUTHORIZED, {"error": str(error)})


def _handle_say(handler: "AppHandler", room_id: str) -> None:
    try:
        account_id, _ = _account_from_session(handler)
        raw_body = safe_read_json(handler)
        # The upload store + transcribe function are pulled lazily so a
        # test can monkey-patch them, and so the import graph stays
        # shallow at module load.
        upload_store = _lazy_upload_store()
        result = mp_service.send_message(
            room_id=room_id,
            account_id=account_id,
            raw_body=raw_body,
            upload_store=upload_store,
        )
        json_response(handler, HTTPStatus.OK, result)
    except mp_service.MultiplayerError as error:
        api_error_response(handler, _map_service_error(error))
    except PermissionError as error:
        json_response(handler, HTTPStatus.UNAUTHORIZED, {"error": str(error)})


def _handle_leave(handler: "AppHandler", room_id: str) -> None:
    try:
        account_id, _ = _account_from_session(handler)
        mp_service.leave_room(room_id=room_id, account_id=account_id)
        json_response(handler, HTTPStatus.OK, {"status": "left", "room_id": room_id})
    except mp_service.MultiplayerError as error:
        api_error_response(handler, _map_service_error(error))
    except PermissionError as error:
        json_response(handler, HTTPStatus.UNAUTHORIZED, {"error": str(error)})


def _handle_stream(handler: "AppHandler", room_id: str) -> None:
    """Long-lived SSE stream for one participant."""

    try:
        account_id, _ = _account_from_session(handler)
    except PermissionError as error:
        json_response(handler, HTTPStatus.UNAUTHORIZED, {"error": str(error)})
        return

    try:
        # Sanity check the seat membership before we commit to a chunked
        # response (so we can still emit a JSON error if the caller is
        # not a participant).
        mp_service.get_registry().get_room(room_id, account_id=account_id)
    except mp_service.MultiplayerError as error:
        api_error_response(handler, _map_service_error(error))
        return

    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
    handler.send_header("Cache-Control", "no-cache, no-transform")
    handler.send_header("Connection", "keep-alive")
    handler.send_header("X-Accel-Buffering", "no")
    handler.end_headers()

    try:
        for chunk in mp_service.stream_room(room_id, account_id=account_id):
            try:
                handler.wfile.write(chunk.encode("utf-8"))
                handler.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                # Client went away — the generator's ``finally`` will
                # detach the seat and broadcast peer_left.
                return
    except Exception:  # noqa: BLE001 — never let an SSE error crash the worker
        logger.exception(
            "multiplayer_stream_failed room=%s account=%s", room_id, account_id
        )


def _lazy_upload_store() -> "object | None":
    """Return the T-018 ``UploadStore`` singleton if available.

    Pulled at call time so tests can monkey-patch the module attribute
    on :mod:`server_app.routes.uploads` and the patch is honoured.
    """

    try:
        from server_app.routes import uploads
        store = getattr(uploads, "speaking_upload_store", None) or getattr(
            uploads, "UPLOAD_STORE", None
        )
        return store
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Hook installation (T-045 pattern)
# ---------------------------------------------------------------------------


def install_multiplayer_routes() -> None:
    """Patch ``AppHandler.do_GET`` / ``do_POST`` to dispatch multiplayer routes.

    Idempotent — uses a ``_t064_installed`` flag on :class:`AppHandler` so
    re-importing the module does not stack handlers.
    """

    from server_app.core import AppHandler

    if getattr(AppHandler, "_t064_installed", False):
        return

    original_do_get = AppHandler.do_GET
    original_do_post = AppHandler.do_POST

    def patched_do_get(self: "AppHandler") -> None:  # type: ignore[no-redef]
        path = _resolve_path(self)
        if _SCENARIOS_RE.match(path):
            _handle_list_scenarios(self)
            return
        match = _STREAM_RE.match(path)
        if match:
            _handle_stream(self, match.group(1))
            return
        original_do_get(self)

    def patched_do_post(self: "AppHandler") -> None:  # type: ignore[no-redef]
        path = _resolve_path(self)
        if _QUEUE_RE.match(path):
            _handle_queue(self)
            return
        match = _SAY_RE.match(path)
        if match:
            _handle_say(self, match.group(1))
            return
        match = _LEAVE_RE.match(path)
        if match:
            _handle_leave(self, match.group(1))
            return
        original_do_post(self)

    AppHandler.do_GET = patched_do_get  # type: ignore[assignment]
    AppHandler.do_POST = patched_do_post  # type: ignore[assignment]
    AppHandler._t064_installed = True  # type: ignore[attr-defined]
    logger.info("multiplayer_routes_installed")


install_multiplayer_routes()


__all__ = [
    "ROUTES",
    "install_multiplayer_routes",
]
