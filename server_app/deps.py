"""Request-level dependency resolvers (T-020).

Re-exports the small helpers that turn a ``BaseHTTPRequestHandler``
instance into the dependencies that route bodies need: the current
session record, the resolved role, and the client IP (X-Forwarded-For
aware for Fly.io). Future ASGI migration will replace these with
FastAPI ``Depends`` declarations.
"""

from __future__ import annotations

from server_app.core import (  # noqa: F401
    account_role,
    client_ip,
    current_session_record,
    get_session_user_role,
    is_production,
    require_admin_session,
    require_session,
)

__all__ = [
    "account_role",
    "client_ip",
    "current_session_record",
    "get_session_user_role",
    "is_production",
    "require_admin_session",
    "require_session",
]
