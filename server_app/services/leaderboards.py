"""T-052 — Leaderboards (weekly, friend, city).

Reads aggregated XP from the T-034 ``xp_log`` table and ranks learners
across three scopes:

* **weekly** — XP earned in the trailing 7 days (rolling window, UTC).
* **all_time** — every row in ``xp_log`` ever recorded.
* **by_city** — all-time XP filtered by ``accounts.city`` (case-insensitive
  exact match). Returns an empty board when the column is absent.
* **by_friends** — all-time XP filtered to the caller's accepted
  friend list. Uses the lazily-created ``friendships`` table; an
  account with no accepted friends sees only themselves on the board.

Privacy contract
----------------

A leaderboard is, by definition, a list of *other people*. To keep
T-052 PII-safe we expose **only** three fields per row:

* ``rank`` — 1-based position in the ordered list.
* ``account_id`` — the opaque account UUID (already public via session
  responses on multiplayer / SSO).
* ``display_name`` — the explicit ``users.display_name`` if the learner
  set one. Otherwise we fall back to ``Learner-<first-6 of account_id>``.
  **We never surface ``accounts.email`` or ``profiles.full_name`` on a
  leaderboard** because those fields contain real identity data the
  learner did not necessarily consent to publishing.
* ``xp`` — the integer XP total for this scope.

The service also reports whether the caller is on the board (and at
what rank) so the frontend can show "you are #14 of 312" without
needing to scan a paginated payload.

Tie-breaking
------------

When two learners have identical XP the secondary order is
``account_id ASC`` (lexicographic). This is fully deterministic, cheap
to compute in SQL, and leaks no information about the learner identity
(the account UUID is already a session-public field). Ties therefore
never cause two different ranks to swap on subsequent loads.

Caching
-------

Leaderboard queries are read-mostly: the same scope is requested by
every learner during a session and the underlying XP only changes when
``award_xp`` runs. We therefore cache the *full ordered list* for each
scope tuple with a 5-minute TTL keyed by ``(scope, scope_key, limit)``.
A subsequent request for the same caller computes the caller's own
rank from the cached payload — that view is per-caller so it is not
cached itself, but it requires only a dict lookup.

Following the pattern used by :mod:`server_app.services.sso` (OIDC
discovery cache) the TTL is enforced via :func:`time.monotonic`, the
cache is thread-safe via a single lock, and the cache can be flushed
in tests by calling :func:`_reset_cache_for_tests`.

Public surface
--------------

``ensure_leaderboards_schema(conn) -> None``
    Idempotent DDL applier for the ``friendships`` table.

``top_xp_weekly(conn, *, limit=20, now=None) -> list[Entry]``
``top_xp_all_time(conn, *, limit=20) -> list[Entry]``
``top_xp_by_city(conn, city, *, limit=20) -> list[Entry]``
``top_xp_by_friends(conn, account_id, *, limit=20) -> list[Entry]``
    Return ordered board entries (newest XP first).

``build_board(conn, scope, *, account_id, city=None, limit=20, now=None) -> dict``
    Top-level helper used by the route layer. Returns:
    ``{"scope", "scope_key", "as_of", "ttl_seconds", "entries",
       "viewer": {"rank": int|None, "xp": int, "on_board": bool}}``.

``add_friend(conn, account_id, friend_id) -> None``
    Insert a friendship row (idempotent). The friendship is symmetric:
    both directions are stored so the by_friends query only needs a
    single index scan.

``remove_friend(conn, account_id, friend_id) -> None``
    Idempotent inverse. Used by the future T-064 social UI.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

logger = logging.getLogger("lvcodex.leaderboards")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

#: Cache TTL — five minutes is long enough to absorb a frontend that
#: polls aggressively during a leaderboard view, and short enough that
#: an XP award taken now will surface to spectators within the same
#: practice session.
CACHE_TTL_SECONDS = 5 * 60

#: Default and hard-cap page size. Boards above 100 entries are off the
#: visible scroll window in any practical UI and risk leaking the full
#: account list.
DEFAULT_LIMIT = 20
MAX_LIMIT = 100

#: Scope constants — exported so routes/tests don't hard-code strings.
SCOPE_WEEKLY = "weekly"
SCOPE_ALL_TIME = "all_time"
SCOPE_BY_CITY = "by_city"
SCOPE_BY_FRIENDS = "by_friends"

VALID_SCOPES = frozenset(
    {SCOPE_WEEKLY, SCOPE_ALL_TIME, SCOPE_BY_CITY, SCOPE_BY_FRIENDS}
)


# ---------------------------------------------------------------------------
# DDL — friendships table (lazy + idempotent, same shape as T-034)
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS friendships (
    account_id TEXT NOT NULL,
    friend_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'accepted',
    created_at TEXT NOT NULL,
    PRIMARY KEY (account_id, friend_id)
);

CREATE INDEX IF NOT EXISTS idx_friendships_account
    ON friendships(account_id);
"""

_DDL_APPLIED = False
_DDL_LOCK = threading.Lock()


def ensure_leaderboards_schema(conn: sqlite3.Connection) -> None:
    """Create the friendships table if it doesn't already exist.

    Idempotent + cheap after first call (once-flag short-circuits).
    """

    global _DDL_APPLIED
    if _DDL_APPLIED:
        return
    with _DDL_LOCK:
        if _DDL_APPLIED:
            return
        conn.executescript(_DDL)
        _DDL_APPLIED = True


def _reset_ddl_cache_for_tests() -> None:
    """Drop the DDL once-flag — used by tests pointing at a tmpfile DB."""

    global _DDL_APPLIED
    with _DDL_LOCK:
        _DDL_APPLIED = False


# ---------------------------------------------------------------------------
# In-process cache (5-min TTL, thread-safe, keyed by scope tuple)
# ---------------------------------------------------------------------------

# Map cache key -> (expires_at_monotonic, entries)
_CACHE: dict[tuple, tuple[float, list[dict[str, Any]]]] = {}
_CACHE_LOCK = threading.Lock()


def _cache_get(key: tuple) -> list[dict[str, Any]] | None:
    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached is None:
            return None
        expires_at, payload = cached
        if expires_at < now:
            # Expired — drop and miss.
            _CACHE.pop(key, None)
            return None
        # Return a shallow copy so callers can't mutate the cached list.
        return [dict(row) for row in payload]


def _cache_put(key: tuple, payload: list[dict[str, Any]]) -> None:
    expires_at = time.monotonic() + CACHE_TTL_SECONDS
    with _CACHE_LOCK:
        _CACHE[key] = (expires_at, [dict(row) for row in payload])


def _reset_cache_for_tests() -> None:
    """Drop every cached board. Tests call this in :meth:`setUp`."""

    with _CACHE_LOCK:
        _CACHE.clear()


# ---------------------------------------------------------------------------
# Privacy-safe display name resolution
# ---------------------------------------------------------------------------


def _anonymize(account_id: str) -> str:
    """Return ``Learner-<first6>`` for accounts without a display name.

    Never leaks email or full name. The first six characters of the
    account UUID are enough for the learner to recognise themselves
    while staying unique for other viewers.
    """

    fragment = (account_id or "")[:6] or "anon"
    return f"Learner-{fragment}"


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except sqlite3.OperationalError:
        return False
    for row in rows:
        try:
            name = row["name"]
        except (IndexError, KeyError, TypeError):
            try:
                name = row[1]
            except (IndexError, KeyError, TypeError):
                continue
        if name == column:
            return True
    return False


def _has_table(conn: sqlite3.Connection, table: str) -> bool:
    try:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
    except sqlite3.OperationalError:
        return False
    return row is not None


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------


def _now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Display-name resolution: best-effort lookup in users + profiles
# ---------------------------------------------------------------------------


def _resolve_display_names(
    conn: sqlite3.Connection, account_ids: Iterable[str]
) -> dict[str, str]:
    """Return ``{account_id: display_name}`` for the given accounts.

    Privacy: we ONLY consider ``users.display_name`` — an explicit,
    learner-chosen field. We never fall back to ``profiles.full_name``
    or ``accounts.email`` because those are PII the learner did not
    consent to publishing on a leaderboard.
    """

    ids = [aid for aid in account_ids if aid]
    if not ids:
        return {}
    result: dict[str, str] = {}

    if _has_table(conn, "users") and _has_column(conn, "users", "display_name"):
        placeholders = ",".join("?" for _ in ids)
        try:
            rows = conn.execute(
                f"""
                SELECT account_id, display_name
                FROM users
                WHERE account_id IN ({placeholders})
                """,
                tuple(ids),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []
        for row in rows:
            try:
                aid = row["account_id"]
                name = row["display_name"]
            except (IndexError, KeyError, TypeError):
                continue
            if aid and isinstance(name, str) and name.strip():
                result[aid] = name.strip()

    for aid in ids:
        result.setdefault(aid, _anonymize(aid))
    return result


# ---------------------------------------------------------------------------
# Raw board queries (uncached — callers go through ``build_board``)
# ---------------------------------------------------------------------------


def _clamp_limit(limit: int | None) -> int:
    try:
        value = int(limit) if limit is not None else DEFAULT_LIMIT
    except (TypeError, ValueError):
        value = DEFAULT_LIMIT
    if value <= 0:
        return DEFAULT_LIMIT
    return min(value, MAX_LIMIT)


def _shape_entries(
    conn: sqlite3.Connection,
    raw_rows: list[tuple[str, int]],
) -> list[dict[str, Any]]:
    """Attach rank + display name to ``[(account_id, xp), ...]``."""

    account_ids = [aid for aid, _ in raw_rows]
    names = _resolve_display_names(conn, account_ids)
    out: list[dict[str, Any]] = []
    for index, (account_id, xp) in enumerate(raw_rows):
        out.append(
            {
                "rank": index + 1,
                "account_id": account_id,
                "display_name": names.get(account_id) or _anonymize(account_id),
                "xp": int(xp or 0),
            }
        )
    return out


def top_xp_weekly(
    conn: sqlite3.Connection,
    *,
    limit: int = DEFAULT_LIMIT,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Top learners by XP earned in the trailing 7 days (UTC)."""

    limit = _clamp_limit(limit)
    instant = _now(now)
    window_start = instant - timedelta(days=7)
    rows = conn.execute(
        """
        SELECT account_id, COALESCE(SUM(amount), 0) AS xp
        FROM xp_log
        WHERE awarded_at >= ?
        GROUP BY account_id
        HAVING xp > 0
        ORDER BY xp DESC, account_id ASC
        LIMIT ?
        """,
        (_iso(window_start), limit),
    ).fetchall()
    raw = [(r["account_id"], int(r["xp"] or 0)) for r in rows]
    return _shape_entries(conn, raw)


def top_xp_all_time(
    conn: sqlite3.Connection, *, limit: int = DEFAULT_LIMIT
) -> list[dict[str, Any]]:
    """Top learners by all-time XP."""

    limit = _clamp_limit(limit)
    rows = conn.execute(
        """
        SELECT account_id, COALESCE(SUM(amount), 0) AS xp
        FROM xp_log
        GROUP BY account_id
        HAVING xp > 0
        ORDER BY xp DESC, account_id ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    raw = [(r["account_id"], int(r["xp"] or 0)) for r in rows]
    return _shape_entries(conn, raw)


def top_xp_by_city(
    conn: sqlite3.Connection,
    city: str,
    *,
    limit: int = DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    """Top learners by all-time XP, scoped to ``accounts.city``.

    Returns an empty list when:

    * ``city`` is blank.
    * The ``accounts.city`` column has not been provisioned yet.
    * No learner in that city has any XP.

    The match is case-insensitive (``LOWER(city) = LOWER(?)``) so common
    spellings ("Rīga" vs "Riga") collide deterministically.
    """

    limit = _clamp_limit(limit)
    needle = (city or "").strip()
    if not needle:
        return []
    if not _has_column(conn, "accounts", "city"):
        return []
    try:
        rows = conn.execute(
            """
            SELECT x.account_id AS account_id,
                   COALESCE(SUM(x.amount), 0) AS xp
            FROM xp_log AS x
            JOIN accounts AS a ON a.id = x.account_id
            WHERE LOWER(COALESCE(a.city, '')) = LOWER(?)
            GROUP BY x.account_id
            HAVING xp > 0
            ORDER BY xp DESC, x.account_id ASC
            LIMIT ?
            """,
            (needle, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    raw = [(r["account_id"], int(r["xp"] or 0)) for r in rows]
    return _shape_entries(conn, raw)


def top_xp_by_friends(
    conn: sqlite3.Connection,
    account_id: str,
    *,
    limit: int = DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    """Top among the caller's accepted friends — caller always included.

    The viewer themselves are always present in the friend board so a
    learner with zero friends still sees their own XP. Otherwise the
    board is filtered to ``friendships.friend_id`` for the caller
    where ``status = 'accepted'``.
    """

    if not account_id:
        return []
    limit = _clamp_limit(limit)
    ensure_leaderboards_schema(conn)

    friend_rows = conn.execute(
        """
        SELECT friend_id FROM friendships
        WHERE account_id = ? AND status = 'accepted'
        """,
        (account_id,),
    ).fetchall()
    friend_ids = {row["friend_id"] for row in friend_rows if row["friend_id"]}
    friend_ids.add(account_id)
    if not friend_ids:
        return []

    placeholders = ",".join("?" for _ in friend_ids)
    rows = conn.execute(
        f"""
        SELECT account_id, COALESCE(SUM(amount), 0) AS xp
        FROM xp_log
        WHERE account_id IN ({placeholders})
        GROUP BY account_id
        HAVING xp > 0
        ORDER BY xp DESC, account_id ASC
        LIMIT ?
        """,
        (*tuple(friend_ids), limit),
    ).fetchall()
    raw = [(r["account_id"], int(r["xp"] or 0)) for r in rows]
    # Make sure the caller appears even with zero XP — privacy-safe
    # because their own account_id is already exposed via session.
    if not any(entry_aid == account_id for entry_aid, _ in raw):
        raw.append((account_id, 0))
        # Re-sort with caller's zero XP placed last (xp DESC, id ASC).
        raw.sort(key=lambda row: (-row[1], row[0]))
        raw = raw[:limit]
    return _shape_entries(conn, raw)


# ---------------------------------------------------------------------------
# Top-level board builder (cached, used by routes)
# ---------------------------------------------------------------------------


def build_board(
    conn: sqlite3.Connection,
    scope: str,
    *,
    account_id: str,
    city: str | None = None,
    limit: int = DEFAULT_LIMIT,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return a fully-rendered board payload for the API layer.

    Shape::

        {
          "scope": "weekly",
          "scope_key": null,            # or city name / "friends:<acct>"
          "as_of": "2026-05-23T19:00:00Z",
          "ttl_seconds": 300,
          "entries": [
            {"rank": 1, "account_id": "...", "display_name": "...", "xp": 1234}
          ],
          "viewer": {
            "rank": 14,         # or null when not on board / no XP
            "xp": 320,
            "on_board": true
          }
        }

    Caches the ``entries`` list with the 5-minute TTL; the per-caller
    ``viewer`` block is computed from the cached list every request.
    """

    if scope not in VALID_SCOPES:
        raise ValueError(f"unknown leaderboard scope: {scope!r}")
    limit = _clamp_limit(limit)
    instant = _now(now)

    if scope == SCOPE_WEEKLY:
        scope_key = None
        cache_key: tuple = ("weekly", limit, instant.strftime("%Y-%m-%d"))
        cached = _cache_get(cache_key)
        if cached is None:
            cached = top_xp_weekly(conn, limit=limit, now=instant)
            _cache_put(cache_key, cached)
        entries = cached
    elif scope == SCOPE_ALL_TIME:
        scope_key = None
        cache_key = ("all_time", limit)
        cached = _cache_get(cache_key)
        if cached is None:
            cached = top_xp_all_time(conn, limit=limit)
            _cache_put(cache_key, cached)
        entries = cached
    elif scope == SCOPE_BY_CITY:
        scope_key = (city or "").strip() or None
        cache_key = ("by_city", limit, (scope_key or "").lower())
        cached = _cache_get(cache_key)
        if cached is None:
            cached = top_xp_by_city(conn, scope_key or "", limit=limit)
            _cache_put(cache_key, cached)
        entries = cached
    else:  # SCOPE_BY_FRIENDS — per-caller, do NOT share cache between callers
        scope_key = f"friends:{account_id}" if account_id else None
        cache_key = ("by_friends", limit, account_id)
        cached = _cache_get(cache_key)
        if cached is None:
            cached = top_xp_by_friends(conn, account_id, limit=limit)
            _cache_put(cache_key, cached)
        entries = cached

    viewer_rank: int | None = None
    viewer_xp = 0
    for entry in entries:
        if entry["account_id"] == account_id:
            viewer_rank = int(entry["rank"])
            viewer_xp = int(entry["xp"])
            break

    return {
        "scope": scope,
        "scope_key": scope_key,
        "as_of": _iso(instant),
        "ttl_seconds": CACHE_TTL_SECONDS,
        "entries": entries,
        "viewer": {
            "rank": viewer_rank,
            "xp": viewer_xp,
            "on_board": viewer_rank is not None,
        },
    }


# ---------------------------------------------------------------------------
# Friendship helpers (used by T-064 multiplayer "add friend" UI, tests)
# ---------------------------------------------------------------------------


def add_friend(
    conn: sqlite3.Connection,
    account_id: str,
    friend_id: str,
    *,
    now: datetime | None = None,
) -> None:
    """Insert a friendship row (idempotent, symmetric).

    Stores both ``(a, b)`` and ``(b, a)`` rows so the by_friends board
    can answer either party's view with a single index scan.
    """

    if not account_id or not friend_id:
        raise ValueError("account_id and friend_id are required")
    if account_id == friend_id:
        raise ValueError("cannot friend yourself")
    ensure_leaderboards_schema(conn)
    created_at = _iso(_now(now))
    for left, right in ((account_id, friend_id), (friend_id, account_id)):
        conn.execute(
            """
            INSERT INTO friendships (account_id, friend_id, status, created_at)
            VALUES (?, ?, 'accepted', ?)
            ON CONFLICT(account_id, friend_id) DO UPDATE SET
                status = excluded.status
            """,
            (left, right, created_at),
        )
    # New friendship invalidates any cached friends boards for both
    # parties — easiest correct behaviour is to nuke the relevant keys.
    with _CACHE_LOCK:
        for key in list(_CACHE.keys()):
            if key[0] == "by_friends" and key[2] in {account_id, friend_id}:
                _CACHE.pop(key, None)


def remove_friend(
    conn: sqlite3.Connection,
    account_id: str,
    friend_id: str,
) -> None:
    """Idempotent inverse of :func:`add_friend`."""

    if not account_id or not friend_id:
        raise ValueError("account_id and friend_id are required")
    ensure_leaderboards_schema(conn)
    conn.execute(
        """
        DELETE FROM friendships
        WHERE (account_id = ? AND friend_id = ?)
           OR (account_id = ? AND friend_id = ?)
        """,
        (account_id, friend_id, friend_id, account_id),
    )
    with _CACHE_LOCK:
        for key in list(_CACHE.keys()):
            if key[0] == "by_friends" and key[2] in {account_id, friend_id}:
                _CACHE.pop(key, None)


__all__ = [
    "CACHE_TTL_SECONDS",
    "DEFAULT_LIMIT",
    "MAX_LIMIT",
    "SCOPE_ALL_TIME",
    "SCOPE_BY_CITY",
    "SCOPE_BY_FRIENDS",
    "SCOPE_WEEKLY",
    "VALID_SCOPES",
    "add_friend",
    "build_board",
    "ensure_leaderboards_schema",
    "remove_friend",
    "top_xp_all_time",
    "top_xp_by_city",
    "top_xp_by_friends",
    "top_xp_weekly",
]
