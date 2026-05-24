"""AI NPC roleplay routes (T-045).

The dispatch bodies are installed at import time via the
:func:`install_npc_routes` hook below, mirroring the T-037 / T-022 pattern
where each post-modularization feature wires its own ``do_GET`` /
``do_POST`` wrapper onto :class:`server_app.core.AppHandler`. The handler
delegates to :mod:`server_app.services.npc` which owns the persona load,
Groq call, quota reservation, and conversation persistence.

Routes
------

* ``GET  /api/npc``                          — list available NPCs.
* ``GET  /api/npc/<npc_id>``                 — return a single NPC profile.
* ``POST /api/npc/<npc_id>/turn``            — submit a learner message and
                                               receive an NPC reply.

Authentication
--------------

All three routes require an active learner session
(:func:`server_app.core.require_session`). The ``account_id`` resolved
from the session is the only identity allowed to read or extend a
conversation, which gives multi-user isolation for free at the SQL layer.
"""

from __future__ import annotations

import json
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
from server_app.services import npc as npc_service
from server_app.services.quota import QuotaExceededError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from server_app.core import AppHandler


logger = logging.getLogger("lvcodex.npc.routes")


ROUTES: list[tuple[str, str]] = [
    ("GET", "/api/npc"),
    ("GET", "/api/npc/<npc_id>"),
    ("POST", "/api/npc/<npc_id>/turn"),
]


_NPC_LIST_RE = re.compile(r"^/api/npc/?$")
_NPC_TURN_RE = re.compile(r"^/api/npc/([a-z0-9-]+)/turn/?$")
_NPC_DETAIL_RE = re.compile(r"^/api/npc/([a-z0-9-]+)/?$")


def _resolve_path(handler: "AppHandler") -> str:
    """Normalise ``handler.path`` to the URL path without query string."""

    raw = getattr(handler, "path", "") or ""
    return urllib.parse.urlparse(raw).path or ""


def _npc_list_handler(handler: "AppHandler") -> None:
    """``GET /api/npc`` — return the available NPC summaries."""

    try:
        require_session(handler)
        summaries = npc_service.list_npcs()
        json_response(handler, HTTPStatus.OK, {"npcs": summaries})
    except PermissionError as error:
        json_response(handler, HTTPStatus.UNAUTHORIZED, {"error": str(error)})


def _npc_detail_handler(handler: "AppHandler", npc_id: str) -> None:
    """``GET /api/npc/<npc_id>`` — return one NPC's full profile."""

    try:
        require_session(handler)
        try:
            profile = npc_service.load_npc(npc_id)
        except npc_service.NPCNotFound as error:
            raise ApiError(HTTPStatus.NOT_FOUND, "npc_not_found", str(error)) from error
        # Drop large internal-only fields if any exist; keep the JSON
        # shape stable for the frontend chat UI.
        json_response(handler, HTTPStatus.OK, {"npc": profile})
    except ApiError as error:
        api_error_response(handler, error)
    except PermissionError as error:
        json_response(handler, HTTPStatus.UNAUTHORIZED, {"error": str(error)})


def _npc_turn_handler(handler: "AppHandler", npc_id: str) -> None:
    """``POST /api/npc/<npc_id>/turn`` — generate the next NPC reply."""

    try:
        session = require_session(handler)
        account = session.get("account") or {}
        account_id = account.get("id") or ""
        plan = (session.get("profile") or {}).get("exam_pack_status") or "free"
        raw_body = safe_read_json(handler)
        try:
            response = npc_service.generate_turn(
                account_id=account_id,
                plan=plan,
                npc_id=npc_id,
                raw_body=raw_body,
            )
        except npc_service.NPCNotFound as error:
            raise ApiError(HTTPStatus.NOT_FOUND, "npc_not_found", str(error)) from error
        except npc_service.NPCInvalidRequest as error:
            raise ApiError(
                HTTPStatus.BAD_REQUEST, "npc_invalid_request", str(error)
            ) from error
        except QuotaExceededError as error:
            raise ApiError(
                HTTPStatus.TOO_MANY_REQUESTS, "ai_quota_exceeded", str(error)
            ) from error
        except npc_service.NPCProviderError as error:
            raise ApiError(
                HTTPStatus.BAD_GATEWAY, "npc_provider_unavailable", str(error)
            ) from error
        json_response(handler, HTTPStatus.OK, json.loads(response.model_dump_json()))
    except ApiError as error:
        api_error_response(handler, error)
    except PermissionError as error:
        json_response(handler, HTTPStatus.UNAUTHORIZED, {"error": str(error)})


# ---------------------------------------------------------------------------
# Hook installation (T-037 pattern)
# ---------------------------------------------------------------------------


def install_npc_routes() -> None:
    """Patch ``AppHandler.do_GET`` / ``do_POST`` to dispatch NPC routes.

    Idempotent — uses an ``_t045_installed`` flag on :class:`AppHandler`
    so re-importing the module does not stack handlers. The chain wraps
    the *current* ``do_GET`` / ``do_POST`` so it composes correctly with
    the rate-limit (T-015), metrics (T-014), debug-gate (T-010),
    versioning (T-037), and attempt-store (T-022) hooks already on the
    class.
    """

    from server_app.core import AppHandler

    if getattr(AppHandler, "_t045_installed", False):
        return

    original_do_get = AppHandler.do_GET
    original_do_post = AppHandler.do_POST

    def patched_do_get(self: "AppHandler") -> None:  # type: ignore[no-redef]
        path = _resolve_path(self)
        if _NPC_LIST_RE.match(path):
            _npc_list_handler(self)
            return
        # ``/api/npc/<id>/turn`` is POST-only, so the detail regex matches
        # any id-shaped path. Make sure we don't shadow ``/api/npc`` itself
        # which has its own handler above.
        match = _NPC_DETAIL_RE.match(path)
        if match and not _NPC_TURN_RE.match(path):
            _npc_detail_handler(self, match.group(1))
            return
        original_do_get(self)

    def patched_do_post(self: "AppHandler") -> None:  # type: ignore[no-redef]
        path = _resolve_path(self)
        match = _NPC_TURN_RE.match(path)
        if match:
            _npc_turn_handler(self, match.group(1))
            return
        original_do_post(self)

    AppHandler.do_GET = patched_do_get  # type: ignore[assignment]
    AppHandler.do_POST = patched_do_post  # type: ignore[assignment]
    AppHandler._t045_installed = True  # type: ignore[attr-defined]
    logger.info("npc_routes_installed")


# Install on import — the package __init__ relies on import-time wiring
# (see the T-037 pattern in core.py).
install_npc_routes()
# Ensure the DDL is queued up so the first request doesn't pay the cost.
try:
    npc_service.ensure_npc_tables_ready()
except Exception:  # noqa: BLE001 — never crash import if DB is unavailable
    logger.exception("npc_table_init_failed")


__all__ = [
    "ROUTES",
    "install_npc_routes",
]
