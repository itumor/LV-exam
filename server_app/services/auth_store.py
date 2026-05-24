"""Auth-store service (T-020, extended T-023).

Re-exports the SQLite auth-store helpers from :mod:`server_app.core` and
provides the T-023 unified-accounts surface.

T-023 unifies the identity model across the two front-end surfaces shipped
by lvcodex:

* ``latvian-a2-exam-app/`` (the A2 exam simulator)
* ``latvian-listening-library/`` (the listening micro-feed)

Both apps are served same-origin by the lvcodex Python server, so the
existing ``a2_session`` HTTP-only cookie (Path=/) already covers them.
T-023 exposes two helpers so each app can resolve the *same* session
without re-implementing cookie parsing:

* :func:`resolve_session` — parse a ``Cookie:`` header, return the session
  record (account + profile + listening-profile link) or ``None`` for
  anonymous requests. Works for both surfaces.
* :func:`link_listening_profile` — migration helper that records a link
  between a unified account and a legacy ``listening-library`` profile
  identifier so historical progress can be merged forward.

Storage is a tiny additive table ``listening_profile_links`` created on
demand by :func:`ensure_listening_profile_links_table`. The table is
created the first time :func:`link_listening_profile` (or
:func:`resolve_session` for an authenticated session) is invoked, which
keeps the change backwards-compatible — existing databases pick up the
table at runtime without a separate migration step.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from typing import Any

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
    "ensure_listening_profile_links_table",
    "hash_password",
    "init_auth_store",
    "link_listening_profile",
    "make_session_token",
    "normalize_email",
    "resolve_session",
    "serialize_account",
    "serialize_profile",
    "unlink_listening_profile",
    "upsert_profile",
    "verify_password",
]


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def _parse_cookie_token(cookie_header: str | None) -> str | None:
    """Return the ``a2_session`` token from a raw ``Cookie:`` header value.

    The header is the verbatim string sent by the browser, e.g.
    ``"a2_session=abc; theme=dark"``. ``None`` or empty input returns
    ``None``. Malformed cookies return ``None`` rather than raising —
    anonymous requests must never crash the resolver.
    """

    if not cookie_header:
        return None
    try:
        jar = SimpleCookie()
        jar.load(cookie_header)
    except Exception:  # pragma: no cover — SimpleCookie is permissive
        return None
    morsel = jar.get(AUTH_SESSION_COOKIE)
    if morsel is None:
        return None
    return morsel.value or None


def ensure_listening_profile_links_table(conn: sqlite3.Connection) -> None:
    """Create the ``listening_profile_links`` table if it does not exist.

    The table is intentionally narrow: one row per (account_id,
    listening_profile_id) pair. ``listening_profile_id`` is the opaque
    identifier the listening-library generated client-side before
    unification (typically an email address or a UUID stored in
    ``localStorage``). A composite UNIQUE constraint prevents
    double-linking.
    """

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS listening_profile_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
            listening_profile_id TEXT NOT NULL,
            linked_at TEXT NOT NULL,
            UNIQUE(account_id, listening_profile_id)
        );

        CREATE INDEX IF NOT EXISTS idx_listening_profile_links_account
        ON listening_profile_links(account_id);

        CREATE INDEX IF NOT EXISTS idx_listening_profile_links_legacy_id
        ON listening_profile_links(listening_profile_id);
        """
    )


def _fetch_session_row(
    conn: sqlite3.Connection, token: str, now: str
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT s.token, s.account_id, s.expires_at, s.revoked_at,
               a.email, a.status AS account_status,
               a.created_at AS account_created_at, a.deleted_at,
               a.role,
               p.full_name, p.native_language, p.exam_target_date,
               p.exam_pack_status, p.updated_at AS profile_updated_at
        FROM sessions s
        JOIN accounts a ON a.id = s.account_id
        LEFT JOIN profiles p ON p.account_id = a.id
        WHERE s.token = ?
        """,
        (token,),
    ).fetchone()


def _row_is_active(row: sqlite3.Row, now: str) -> bool:
    if row["revoked_at"] is not None:
        return False
    if row["deleted_at"] is not None:
        return False
    if row["account_status"] != "active":
        return False
    if row["expires_at"] is not None and row["expires_at"] <= now:
        return False
    return True


def _list_listening_links(
    conn: sqlite3.Connection, account_id: str
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT listening_profile_id, linked_at
        FROM listening_profile_links
        WHERE account_id = ?
        ORDER BY linked_at ASC
        """,
        (account_id,),
    ).fetchall()
    return [
        {
            "listening_profile_id": row["listening_profile_id"],
            "linked_at": row["linked_at"],
        }
        for row in rows
    ]


def resolve_session(cookie_header: str | None) -> dict[str, Any] | None:
    """Resolve a session from a raw ``Cookie:`` header.

    Returns the unified session payload — usable from either the exam app
    or the listening-library surface — or ``None`` if the cookie is
    missing, malformed, expired, revoked, or belongs to a soft-deleted
    account.

    The returned shape is intentionally aligned with
    ``server_app.core.current_session_record`` so existing route handlers
    can switch over without further changes:

    .. code-block:: python

        {
            "token": str,
            "account": {"id", "email", "status", "role",
                         "created_at", "deleted_at"},
            "profile": {"account_id", "full_name", "native_language",
                         "exam_target_date", "exam_pack_status",
                         "updated_at"},
            "listening_profile_links": [{...}, ...],
        }
    """

    token = _parse_cookie_token(cookie_header)
    if not token:
        return None
    now = _now_iso()
    with db_connection() as conn:
        ensure_listening_profile_links_table(conn)
        row = _fetch_session_row(conn, token, now)
        if row is None:
            return None
        if not _row_is_active(row, now):
            if (
                row["expires_at"] is not None
                and row["expires_at"] <= now
                and row["revoked_at"] is None
            ):
                conn.execute(
                    "UPDATE sessions SET revoked_at = ? WHERE token = ?",
                    (now, token),
                )
            return None
        conn.execute(
            "UPDATE sessions SET last_seen_at = ? WHERE token = ?",
            (now, token),
        )
        links = _list_listening_links(conn, row["account_id"])
        return {
            "token": row["token"],
            "account": {
                "id": row["account_id"],
                "email": row["email"],
                "status": row["account_status"],
                "role": row["role"] or "user",
                "created_at": row["account_created_at"],
                "deleted_at": row["deleted_at"],
            },
            "profile": {
                "account_id": row["account_id"],
                "full_name": row["full_name"],
                "native_language": row["native_language"],
                "exam_target_date": row["exam_target_date"],
                "exam_pack_status": row["exam_pack_status"] or "free",
                "updated_at": row["profile_updated_at"],
            },
            "listening_profile_links": links,
        }


def link_listening_profile(
    account_id: str,
    listening_profile_id: str,
    *,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Record a link between a unified account and a legacy listening profile.

    Used by ``scripts/link_listening_profiles.py`` to merge listening-library
    progress into the main account graph by matching email addresses or
    other client-side identifiers. The link is idempotent — re-linking the
    same pair is a no-op and the existing ``linked_at`` is preserved.

    Pass ``conn`` to participate in an existing transaction (used by the
    migration script for atomic bulk inserts); otherwise the helper opens
    a fresh connection.
    """

    account_id = (account_id or "").strip()
    listening_profile_id = (listening_profile_id or "").strip()
    if not account_id:
        raise ValueError("account_id is required.")
    if not listening_profile_id:
        raise ValueError("listening_profile_id is required.")

    def _do(active_conn: sqlite3.Connection) -> dict[str, Any]:
        ensure_listening_profile_links_table(active_conn)
        account_row = active_conn.execute(
            "SELECT id FROM accounts WHERE id = ? AND deleted_at IS NULL",
            (account_id,),
        ).fetchone()
        if account_row is None:
            raise LookupError(f"Account {account_id!r} not found or deleted.")
        now = _now_iso()
        existing = active_conn.execute(
            """
            SELECT id, linked_at
            FROM listening_profile_links
            WHERE account_id = ? AND listening_profile_id = ?
            """,
            (account_id, listening_profile_id),
        ).fetchone()
        if existing is not None:
            return {
                "account_id": account_id,
                "listening_profile_id": listening_profile_id,
                "linked_at": existing["linked_at"],
                "created": False,
            }
        active_conn.execute(
            """
            INSERT INTO listening_profile_links
                (account_id, listening_profile_id, linked_at)
            VALUES (?, ?, ?)
            """,
            (account_id, listening_profile_id, now),
        )
        return {
            "account_id": account_id,
            "listening_profile_id": listening_profile_id,
            "linked_at": now,
            "created": True,
        }

    if conn is not None:
        return _do(conn)
    with db_connection() as opened:
        return _do(opened)


def unlink_listening_profile(
    account_id: str,
    listening_profile_id: str,
    *,
    conn: sqlite3.Connection | None = None,
) -> bool:
    """Remove a listening-profile link. Returns ``True`` if a row was removed."""

    def _do(active_conn: sqlite3.Connection) -> bool:
        ensure_listening_profile_links_table(active_conn)
        cur = active_conn.execute(
            """
            DELETE FROM listening_profile_links
            WHERE account_id = ? AND listening_profile_id = ?
            """,
            (account_id, listening_profile_id),
        )
        return cur.rowcount > 0

    if conn is not None:
        return _do(conn)
    with db_connection() as opened:
        return _do(opened)
