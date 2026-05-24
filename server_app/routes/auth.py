"""Authentication routes (T-020 / T-020a).

Owns the login/logout/session/registration endpoints, the profile mutation
endpoint, the account export/delete endpoints, and the auth webhook.

T-020a moves the actual request-handler bodies out of
:mod:`server_app.core` into this module. The dispatch chain inside
``AppHandler.do_GET`` / ``AppHandler.do_POST`` still owns the path-literal
match (so the modularisation audit test in
``tests/server/test_modularization.py`` keeps seeing the string literals
in ``server_app.core``), but each branch now delegates to a per-route
function defined here. Behaviour is preserved exactly — response bodies,
status codes, headers, cookie attributes and error mapping are all
identical to the pre-refactor implementation.

The helper symbols that other modules / tests import from
``server_app.routes.auth`` (``handle_auth_webhook``, ``login_account``,
etc.) are still re-exported from :mod:`server_app.core` so the public
surface of the routes module does not regress.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING

from server_app.core import (  # noqa: F401
    AUTH_SESSION_COOKIE,
    create_account_record,
    current_session_record,
    delete_account,
    expired_session_cookie_header,
    export_account,
    handle_auth_webhook,
    hash_password,
    login_account,
    parse_cookie_value,
    require_session,
    session_cookie_header,
    update_profile,
    verify_password,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from server_app.core import AppHandler


# ---------------------------------------------------------------------------
# Request handler bodies (peeled out of server_app.core in T-020a).
#
# Each function takes the live ``AppHandler`` instance as its only argument
# and writes the response via the handler's ``send_response`` / ``wfile``
# helpers. The bodies are intentional copies of the pre-T-020a inline
# branches — they do not change behaviour.
# ---------------------------------------------------------------------------


def do_session_get(handler: "AppHandler") -> None:
    """``GET /api/session`` — return the active session record (or anon)."""

    from server_app import core as _core

    session = current_session_record(handler)
    _core.json_response(
        handler,
        HTTPStatus.OK,
        {"authenticated": bool(session), **(session or {})},
    )


def do_account_export(handler: "AppHandler") -> None:
    """``GET /api/account/export`` — GDPR-style data export for the learner."""

    from server_app import core as _core

    try:
        session = require_session(handler)
        _core.json_response(handler, HTTPStatus.OK, export_account(session))
    except PermissionError as error:
        _core.json_response(
            handler, HTTPStatus.UNAUTHORIZED, {"error": str(error)}
        )


def do_register_post(handler: "AppHandler") -> None:
    """``POST /api/auth/register`` — create account + session cookie."""

    from server_app import core as _core

    allowed, retry_after = _core.check_rate_limit(
        f"register:{_core.client_ip(handler)}",
        limit_env="AUTH_REGISTER_RATE_LIMIT",
        window_env="AUTH_REGISTER_RATE_WINDOW_SECONDS",
    )
    if not allowed:
        _core.json_response_with_headers(
            handler,
            HTTPStatus.TOO_MANY_REQUESTS,
            {"error": "Too many registration attempts. Try again later."},
            {"Retry-After": str(retry_after)},
        )
        return
    payload = _core.safe_read_json(handler)
    response, token = create_account_record(payload)
    _core.json_response_with_headers(
        handler,
        HTTPStatus.CREATED,
        {**response, "authenticated": True},
        {"Set-Cookie": session_cookie_header(token)},
    )


def do_login_post(handler: "AppHandler") -> None:
    """``POST /api/auth/login`` — verify credentials + issue session cookie."""

    from server_app import core as _core

    allowed, retry_after = _core.check_rate_limit(
        f"login:{_core.client_ip(handler)}",
        limit_env="AUTH_LOGIN_RATE_LIMIT",
        window_env="AUTH_LOGIN_RATE_WINDOW_SECONDS",
    )
    if not allowed:
        _core.json_response_with_headers(
            handler,
            HTTPStatus.TOO_MANY_REQUESTS,
            {"error": "Too many login attempts. Try again later."},
            {"Retry-After": str(retry_after)},
        )
        return
    payload = _core.safe_read_json(handler)
    response, token = login_account(payload)
    _core.json_response_with_headers(
        handler,
        HTTPStatus.OK,
        {**response, "authenticated": True},
        {"Set-Cookie": session_cookie_header(token)},
    )


def do_logout_post(handler: "AppHandler") -> None:
    """``POST /api/auth/logout`` — revoke session row + clear cookie."""

    from server_app import core as _core

    token = parse_cookie_value(handler, AUTH_SESSION_COOKIE)
    if token:
        with _core.db_connection() as conn:
            conn.execute(
                "UPDATE sessions SET revoked_at = ? WHERE token = ?",
                (_core.now_iso(), token),
            )
    _core.json_response_with_headers(
        handler,
        HTTPStatus.OK,
        {"ok": True},
        {"Set-Cookie": expired_session_cookie_header()},
    )


def do_profile_post(handler: "AppHandler") -> None:
    """``POST /api/profile`` — update mutable profile fields for the learner."""

    from server_app import core as _core

    payload = _core.safe_read_json(handler)
    session = require_session(handler)
    _core.json_response(
        handler, HTTPStatus.OK, update_profile(payload, session)
    )


def do_account_delete_post(handler: "AppHandler") -> None:
    """``POST /api/account/delete`` — self-serve account deletion (T-052)."""

    from server_app import core as _core

    session = require_session(handler)
    _core.json_response(handler, HTTPStatus.OK, delete_account(session))


def do_auth_webhook_post(handler: "AppHandler") -> None:
    """``POST /api/webhooks/auth`` — accept upstream identity provider events."""

    from server_app import core as _core

    _core.json_response(
        handler, HTTPStatus.OK, handle_auth_webhook(handler)
    )


ROUTES: list[tuple[str, str]] = [
    ("POST", "/api/auth/register"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/logout"),
    ("GET", "/api/session"),
    ("POST", "/api/profile"),
    ("POST", "/api/webhooks/auth"),
    ("GET", "/api/account/export"),
    ("POST", "/api/account/delete"),
]

__all__ = [
    "AUTH_SESSION_COOKIE",
    "ROUTES",
    "create_account_record",
    "current_session_record",
    "delete_account",
    "do_account_delete_post",
    "do_account_export",
    "do_auth_webhook_post",
    "do_login_post",
    "do_logout_post",
    "do_profile_post",
    "do_register_post",
    "do_session_get",
    "expired_session_cookie_header",
    "export_account",
    "handle_auth_webhook",
    "hash_password",
    "login_account",
    "parse_cookie_value",
    "require_session",
    "session_cookie_header",
    "update_profile",
    "verify_password",
]
