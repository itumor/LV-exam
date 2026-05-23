"""Auth-store service (T-020).

Re-exports the SQLite auth-store helpers from :mod:`server_app.core`.
The store handles accounts, sessions, password hashing, and the
bootstrap superadmin flow.
"""

from __future__ import annotations

from server_app.core import (  # noqa: F401
    AUTH_SESSION_COOKIE,
    create_session,
    db_connection,
    ensure_bootstrap_superadmin,
    hash_password,
    init_auth_store,
    make_session_token,
    normalize_email,
    serialize_account,
    serialize_profile,
    upsert_profile,
    verify_password,
)

__all__ = [
    "AUTH_SESSION_COOKIE",
    "create_session",
    "db_connection",
    "ensure_bootstrap_superadmin",
    "hash_password",
    "init_auth_store",
    "make_session_token",
    "normalize_email",
    "serialize_account",
    "serialize_profile",
    "upsert_profile",
    "verify_password",
]
