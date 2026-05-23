"""Authentication routes (T-020).

Owns the login/logout/session/registration endpoints and the auth
webhook. Dispatch bodies remain in
:meth:`server_app.core.AppHandler.do_GET` / ``do_POST`` for this PR;
this module re-exports the service-layer helpers they call so future
extraction is a one-step move.
"""

from __future__ import annotations

from server_app.core import (  # noqa: F401
    AUTH_SESSION_COOKIE,
    create_account_record,
    current_session_record,
    expired_session_cookie_header,
    handle_auth_webhook,
    hash_password,
    login_account,
    parse_cookie_value,
    require_session,
    session_cookie_header,
    update_profile,
    verify_password,
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
    "expired_session_cookie_header",
    "handle_auth_webhook",
    "hash_password",
    "login_account",
    "parse_cookie_value",
    "require_session",
    "session_cookie_header",
    "update_profile",
    "verify_password",
]
