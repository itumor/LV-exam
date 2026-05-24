"""T-034 — XP + streak engine.

Awards experience points (XP) to learners for completing missions,
answering quiz questions correctly, finishing mock exams, and passing a
skill section perfectly. The same module maintains a daily activity
streak: a counter that increments on the first activity of each calendar
day and resets when more than ~36 hours elapse without any awarded XP.

Why a single module?
--------------------

Every award source — missions (T-031), quizzes (T-022 attempt scoring),
mock exams (T-033), and perfect-skill bonuses — shares the same two
side-effects:

1. Append one row to ``xp_log`` describing what was awarded and why.
2. Update ``user_streaks`` to either bump the streak forward by one day,
   keep the existing counter (same-day repeat activity), or reset it to
   one (gap > 36 hours).

Putting both side-effects behind :func:`award_xp` guarantees that every
award is reflected in both the lifetime XP totals and the streak engine.
Callers that only want to touch the streak (e.g. on login) can use
:func:`update_streak` directly.

Tables
------

``xp_log``
    id, account_id, kind, amount, awarded_at, payload

``user_streaks``
    account_id, current_days, longest_days, last_active_date,
    last_active_at, updated_at

Both tables are created lazily by :func:`ensure_xp_schema`, applied via
a once-flag so request hot paths stay cheap.

Award sources + canonical amounts
---------------------------------

* ``mission_complete``          → 10 XP
* ``quiz_correct``              → 2 XP per correct answer
* ``mock_exam_complete``        → 50 XP
* ``perfect_skill_pass``        → 100 XP (bonus, on 15/15 in a skill)

The amount is exposed via :data:`XP_AMOUNTS` so callers don't need to
hard-code numbers; :func:`award_xp` accepts an explicit ``amount`` to
support custom bonuses (e.g. multi-correct batches).

Streak rules
------------

* First activity ever          → ``current_days = 1``.
* Same local day as last       → counter unchanged (idempotent).
* Next calendar day            → ``current_days += 1``.
* Gap > 36 hours               → counter resets to ``1``.
* ``longest_days`` only grows. It is updated whenever ``current_days``
  exceeds it.

The "local day" anchor matches T-031: the learner's IANA timezone read
from ``accounts.user_timezone`` (UTC fallback). The 36-hour gap rule
uses absolute wall-clock seconds between ``last_active_at`` and ``now``
to be timezone-agnostic — so DST shifts cannot accidentally break a
streak.

Public surface
--------------

``ensure_xp_schema(conn) -> None``
    Idempotent DDL applier.

``award_xp(account_id, kind, *, amount=None, payload=None, now=None) -> dict``
    Append one xp_log row + update the streak. Returns the canonical
    summary (``total_xp``, ``current_streak``, ``longest_streak``,
    ``awarded``).

``update_streak(account_id, *, now=None) -> dict``
    Bump the streak without writing an XP row. Returns the same summary
    shape as :func:`get_summary`.

``get_summary(account_id, *, recent_limit=10) -> dict``
    Return totals + the most recent ``xp_log`` rows (default 10).
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger("lvcodex.xp")


# ---------------------------------------------------------------------------
# Canonical award amounts (per T-034 brief)
# ---------------------------------------------------------------------------

KIND_MISSION_COMPLETE = "mission_complete"
KIND_QUIZ_CORRECT = "quiz_correct"
KIND_MOCK_EXAM_COMPLETE = "mock_exam_complete"
KIND_PERFECT_SKILL_PASS = "perfect_skill_pass"

XP_AMOUNTS: dict[str, int] = {
    KIND_MISSION_COMPLETE: 10,
    KIND_QUIZ_CORRECT: 2,
    KIND_MOCK_EXAM_COMPLETE: 50,
    KIND_PERFECT_SKILL_PASS: 100,
}

# Gap window — if the learner has been silent for longer than this, the
# streak resets to 1 on next award. 36 hours gives the learner a full
# "next day" plus a 12-hour grace window across timezones / DST.
STREAK_GAP_HOURS = 36
STREAK_GAP_SECONDS = STREAK_GAP_HOURS * 3600


# ---------------------------------------------------------------------------
# DDL — applied once per connection
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS xp_log (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    amount INTEGER NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    awarded_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_xp_log_account_time
    ON xp_log(account_id, awarded_at DESC);

CREATE TABLE IF NOT EXISTS user_streaks (
    account_id TEXT PRIMARY KEY,
    current_days INTEGER NOT NULL DEFAULT 0,
    longest_days INTEGER NOT NULL DEFAULT 0,
    last_active_date TEXT,
    last_active_at TEXT,
    updated_at TEXT NOT NULL
);
"""

_DDL_APPLIED = False
_DDL_LOCK = threading.Lock()


def ensure_xp_schema(conn: sqlite3.Connection) -> None:
    """Create the two T-034 tables if they don't already exist.

    Safe to call on every request; the once-flag short-circuits after
    the first successful execution. Tests reset the flag through
    :func:`_reset_ddl_cache_for_tests`.
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
    """Drop the once-flag — used by tests that point at a tmpfile DB."""

    global _DDL_APPLIED
    with _DDL_LOCK:
        _DDL_APPLIED = False


# ---------------------------------------------------------------------------
# Timezone + datetime helpers
# ---------------------------------------------------------------------------


def _now(now: datetime | None = None) -> datetime:
    """Return a tz-aware UTC datetime; coerce naive inputs to UTC."""

    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def _now_iso(now: datetime | None = None) -> str:
    return _now(now).isoformat().replace("+00:00", "Z")


def _resolve_timezone(name: str | None) -> ZoneInfo:
    candidate = (name or "UTC").strip() or "UTC"
    try:
        return ZoneInfo(candidate)
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning("xp: unknown timezone %r — falling back to UTC", candidate)
        return ZoneInfo("UTC")


def _account_timezone(conn: sqlite3.Connection, account_id: str) -> ZoneInfo:
    """Read the learner's IANA timezone from ``accounts.user_timezone``.

    Returns UTC on missing column / row / unparseable value — same
    fallback shape as :mod:`server_app.services.missions`.
    """

    try:
        row = conn.execute(
            "SELECT user_timezone FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()
    except sqlite3.OperationalError:
        return ZoneInfo("UTC")
    if row is None:
        return ZoneInfo("UTC")
    try:
        tz_name = row["user_timezone"] if "user_timezone" in row.keys() else None
    except (IndexError, KeyError, TypeError):
        tz_name = None
    return _resolve_timezone(tz_name)


def _local_date(conn: sqlite3.Connection, account_id: str, now: datetime) -> str:
    """Return ``YYYY-MM-DD`` in the learner's local timezone."""

    tz = _account_timezone(conn, account_id)
    return now.astimezone(tz).strftime("%Y-%m-%d")


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        # Tolerate both "Z" and "+00:00" suffixes.
        text = value.replace("Z", "+00:00") if value.endswith("Z") else value
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# Streak engine
# ---------------------------------------------------------------------------


def _load_streak(
    conn: sqlite3.Connection, account_id: str
) -> tuple[int, int, str | None, datetime | None]:
    """Return ``(current_days, longest_days, last_active_date, last_active_at)``."""

    row = conn.execute(
        """
        SELECT current_days, longest_days, last_active_date, last_active_at
        FROM user_streaks WHERE account_id = ?
        """,
        (account_id,),
    ).fetchone()
    if row is None:
        return (0, 0, None, None)
    return (
        int(row["current_days"] or 0),
        int(row["longest_days"] or 0),
        row["last_active_date"],
        _parse_iso(row["last_active_at"]),
    )


def _persist_streak(
    conn: sqlite3.Connection,
    account_id: str,
    *,
    current_days: int,
    longest_days: int,
    last_active_date: str,
    last_active_at: datetime,
    updated_at: datetime,
) -> None:
    """Insert or update the streak row for ``account_id``."""

    conn.execute(
        """
        INSERT INTO user_streaks
            (account_id, current_days, longest_days,
             last_active_date, last_active_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(account_id) DO UPDATE SET
            current_days     = excluded.current_days,
            longest_days     = excluded.longest_days,
            last_active_date = excluded.last_active_date,
            last_active_at   = excluded.last_active_at,
            updated_at       = excluded.updated_at
        """,
        (
            account_id,
            int(current_days),
            int(longest_days),
            last_active_date,
            last_active_at.isoformat().replace("+00:00", "Z"),
            updated_at.isoformat().replace("+00:00", "Z"),
        ),
    )


def update_streak(
    conn: sqlite3.Connection,
    account_id: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Bump the daily activity streak for ``account_id``.

    Rules (see module docstring for the rationale):

    * Same local day as ``last_active_date`` → no change.
    * Gap (wall-clock) > :data:`STREAK_GAP_SECONDS` → reset to ``1``.
    * Otherwise → increment by ``1``.
    * ``longest_days`` only grows.

    Returns ``{"current_streak", "longest_streak", "last_active_date"}``.
    """

    ensure_xp_schema(conn)
    instant = _now(now)
    today_local = _local_date(conn, account_id, instant)
    (current_days, longest_days, last_active_date, last_active_at) = _load_streak(
        conn, account_id
    )

    if last_active_date == today_local:
        # Already counted today — idempotent.
        new_current = max(current_days, 1)
        new_longest = max(longest_days, new_current)
        _persist_streak(
            conn,
            account_id,
            current_days=new_current,
            longest_days=new_longest,
            last_active_date=today_local,
            last_active_at=instant,
            updated_at=instant,
        )
        return {
            "current_streak": new_current,
            "longest_streak": new_longest,
            "last_active_date": today_local,
        }

    gap_seconds: float | None
    if last_active_at is None:
        gap_seconds = None
    else:
        gap_seconds = (instant - last_active_at).total_seconds()

    if last_active_at is None or current_days <= 0:
        new_current = 1
    elif gap_seconds is not None and gap_seconds > STREAK_GAP_SECONDS:
        new_current = 1
    else:
        new_current = current_days + 1

    new_longest = max(longest_days, new_current)

    _persist_streak(
        conn,
        account_id,
        current_days=new_current,
        longest_days=new_longest,
        last_active_date=today_local,
        last_active_at=instant,
        updated_at=instant,
    )
    return {
        "current_streak": new_current,
        "longest_streak": new_longest,
        "last_active_date": today_local,
    }


# ---------------------------------------------------------------------------
# Award engine
# ---------------------------------------------------------------------------


def _total_xp(conn: sqlite3.Connection, account_id: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) AS total FROM xp_log WHERE account_id = ?",
        (account_id,),
    ).fetchone()
    return int(row["total"] or 0) if row is not None else 0


def _resolve_amount(kind: str, amount: int | None) -> int:
    """Pick the right XP amount for ``kind``.

    * ``amount`` explicitly provided → use it (clamped to non-negative).
    * Otherwise → default from :data:`XP_AMOUNTS`.
    * Unknown kind without explicit amount → ``0`` (no-op award).
    """

    if amount is not None:
        try:
            value = int(amount)
        except (TypeError, ValueError):
            value = 0
        return max(0, value)
    return XP_AMOUNTS.get(kind, 0)


def award_xp(
    conn: sqlite3.Connection,
    account_id: str,
    kind: str,
    *,
    amount: int | None = None,
    payload: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Award XP for ``kind`` to ``account_id`` and bump the streak.

    * ``amount`` defaults to :data:`XP_AMOUNTS` for canonical kinds.
    * ``payload`` is stored verbatim (JSON) for analytics.
    * The streak is updated as a side-effect — see :func:`update_streak`.

    Returns ``{"awarded": {kind, amount, awarded_at, payload, id},
    "total_xp", "current_streak", "longest_streak", "last_active_date"}``.
    """

    if not account_id:
        raise ValueError("account_id is required")
    if not kind:
        raise ValueError("kind is required")

    ensure_xp_schema(conn)
    instant = _now(now)
    awarded_at = instant.isoformat().replace("+00:00", "Z")
    final_amount = _resolve_amount(kind, amount)

    entry_id = f"xp_{uuid.uuid4().hex[:16]}"
    try:
        payload_json = json.dumps(payload or {}, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        payload_json = "{}"

    if final_amount > 0:
        conn.execute(
            """
            INSERT INTO xp_log (id, account_id, kind, amount, payload, awarded_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (entry_id, account_id, kind, final_amount, payload_json, awarded_at),
        )

    streak = update_streak(conn, account_id, now=instant)
    total_xp = _total_xp(conn, account_id)

    # T-051 — auto-grant any XP-tier avatar unlocks the learner just
    # crossed. Lazy import keeps the XP module free of an avatar
    # dependency at import time (the avatars module reads ``xp_log``,
    # so the two would otherwise form an import cycle if pulled in
    # eagerly). Failures here MUST NOT break the XP award itself —
    # cosmetics are a side-effect, never a precondition.
    try:
        from server_app.services import avatars as _avatars_service

        _avatars_service.grant_xp_unlocks(conn, account_id, now=instant)
    except Exception as exc:  # noqa: BLE001 — never fail an XP award
        logger.warning("xp: avatar auto-grant failed — %s", exc)

    logger.info(
        "xp_awarded account=%s kind=%s amount=%s total=%s streak=%s",
        account_id,
        kind,
        final_amount,
        total_xp,
        streak["current_streak"],
    )
    return {
        "awarded": {
            "id": entry_id if final_amount > 0 else None,
            "kind": kind,
            "amount": final_amount,
            "awarded_at": awarded_at,
            "payload": json.loads(payload_json) if payload_json else {},
        },
        "total_xp": total_xp,
        "current_streak": streak["current_streak"],
        "longest_streak": streak["longest_streak"],
        "last_active_date": streak["last_active_date"],
    }


# ---------------------------------------------------------------------------
# Summary read
# ---------------------------------------------------------------------------


def get_summary(
    conn: sqlite3.Connection,
    account_id: str,
    *,
    recent_limit: int = 10,
) -> dict[str, Any]:
    """Return ``{total_xp, current_streak, longest_streak, recent_log}``.

    ``recent_log`` is the most-recently-awarded ``recent_limit`` rows
    from ``xp_log`` (default 10), ordered newest-first.
    """

    ensure_xp_schema(conn)
    limit = max(0, int(recent_limit))
    total_xp = _total_xp(conn, account_id)
    (current_days, longest_days, last_active_date, _last_active_at) = _load_streak(
        conn, account_id
    )

    recent: list[dict[str, Any]] = []
    if limit > 0:
        rows = conn.execute(
            """
            SELECT id, kind, amount, payload, awarded_at
            FROM xp_log
            WHERE account_id = ?
            ORDER BY awarded_at DESC, id DESC
            LIMIT ?
            """,
            (account_id, limit),
        ).fetchall()
        for row in rows:
            try:
                payload = json.loads(row["payload"]) if row["payload"] else {}
            except (TypeError, ValueError, json.JSONDecodeError):
                payload = {}
            recent.append(
                {
                    "id": row["id"],
                    "kind": row["kind"],
                    "amount": int(row["amount"] or 0),
                    "payload": payload,
                    "awarded_at": row["awarded_at"],
                }
            )

    return {
        "total_xp": total_xp,
        "current_streak": current_days,
        "longest_streak": longest_days,
        "last_active_date": last_active_date,
        "recent_log": recent,
    }


__all__ = [
    "KIND_MISSION_COMPLETE",
    "KIND_MOCK_EXAM_COMPLETE",
    "KIND_PERFECT_SKILL_PASS",
    "KIND_QUIZ_CORRECT",
    "STREAK_GAP_HOURS",
    "STREAK_GAP_SECONDS",
    "XP_AMOUNTS",
    "award_xp",
    "ensure_xp_schema",
    "get_summary",
    "update_streak",
]
