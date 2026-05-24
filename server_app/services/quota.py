"""Quota / rate-limit service (T-020, T-026).

Re-exports the daily / hourly per-learner quota helpers and the in-process
per-IP rate limiter used by the auth + scoring routes. The token-bucket
implementation (T-015) lives in :mod:`rate_limit` (top-level module); this
service module wraps the quota-checking surface that consumers use.

T-026 additions
---------------
* :class:`AIQuotaLedger` — a DB-backed per-learner per-day quota ledger.
  Persists to the existing SQLite layer used by auth/attempts/billing (see
  :func:`server_app.services.auth_store.db_connection`). When the deployment
  migrates to Postgres (T-021), the same SQL works untouched because the
  DDL uses only ANSI-compatible types.
* :func:`reserve_daily_ai_quota` — high-level helper that checks the ledger
  and atomically reserves a slot or raises :class:`QuotaExceededError` with
  a structured message + reset-time hint for the 429 response body.
* ``LVCODEX_AI_DAILY_LIMIT`` env var — global cap (default 30) applied on
  top of the per-plan limits from :func:`plan_request_limit`. The lower of
  the two wins, so a free-tier user with plan limit 3 still tops out at 3
  but a pro user with plan limit 100 is clamped to 30 by the global cap.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Optional

from server_app.core import (  # noqa: F401
    QuotaExceededError,
    check_rate_limit,
    check_scoring_rate_limit,
    cost_rate_cents_per_1k_tokens,
    db_connection,
    estimate_request_cost_cents,
    estimate_text_tokens,
    plan_cost_limit_cents,
    plan_request_limit,
    reserve_quota,
    retry_limit,
    validate_submission_size,
)
from server_app.models.ai import next_utc_midnight_iso


logger = logging.getLogger("lvcodex.quota")


DEFAULT_AI_DAILY_LIMIT = 30
LEDGER_LOCK = threading.Lock()
_LEDGER_DDL_APPLIED = False


def ai_daily_limit() -> int:
    """Resolve the global per-learner daily AI request cap.

    Reads ``LVCODEX_AI_DAILY_LIMIT`` (default 30). Values ≤ 0 are clamped to
    1 to keep the ledger semantics simple — a "zero limit" deployment would
    need a feature-flag, not an env var.
    """

    raw = os.getenv("LVCODEX_AI_DAILY_LIMIT", str(DEFAULT_AI_DAILY_LIMIT)).strip()
    if not raw:
        return DEFAULT_AI_DAILY_LIMIT
    try:
        value = int(raw)
    except ValueError as error:
        raise RuntimeError(
            "LVCODEX_AI_DAILY_LIMIT must be an integer."
        ) from error
    return max(1, value)


def effective_daily_limit(plan: str) -> int:
    """Return the lower of the per-plan limit and the global LVCODEX cap."""

    plan_cap = plan_request_limit(plan)
    global_cap = ai_daily_limit()
    return min(plan_cap, global_cap) if plan_cap > 0 else global_cap


def _today_utc() -> str:
    """Return today's date string in UTC (YYYY-MM-DD)."""

    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# DB-backed daily ledger
# ---------------------------------------------------------------------------


def _ensure_ledger_table(conn: sqlite3.Connection) -> None:
    """Create the ledger table if missing.

    DDL is intentionally ANSI-compatible so the same script runs on
    Postgres after T-021 (the boolean + text+integer types match; the
    ``ON CONFLICT`` clause is supported by both SQLite ≥ 3.24 and Postgres
    ≥ 9.5). The unique index pairs (user_key, plan, day) so two different
    plans for the same identity don't collide — useful when a learner
    upgrades mid-day and we want a fresh allowance.
    """

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS ai_quota_ledger (
            user_key TEXT NOT NULL,
            plan TEXT NOT NULL DEFAULT 'free',
            day TEXT NOT NULL,
            request_count INTEGER NOT NULL DEFAULT 0,
            last_request_at TEXT NOT NULL,
            PRIMARY KEY (user_key, plan, day)
        );

        CREATE INDEX IF NOT EXISTS idx_ai_quota_ledger_day
            ON ai_quota_ledger(day);
        """
    )


def _ensure_ledger_ddl_once(conn: sqlite3.Connection) -> None:
    """Apply the DDL exactly once per process (cheap, idempotent)."""

    global _LEDGER_DDL_APPLIED
    if _LEDGER_DDL_APPLIED:
        return
    with LEDGER_LOCK:
        if _LEDGER_DDL_APPLIED:
            return
        _ensure_ledger_table(conn)
        _LEDGER_DDL_APPLIED = True


def _reset_ledger_ddl_cache() -> None:
    """Test hook — clear the once-flag so tempfile DBs re-run the DDL."""

    global _LEDGER_DDL_APPLIED
    with LEDGER_LOCK:
        _LEDGER_DDL_APPLIED = False


class AIQuotaLedger:
    """Per-user daily quota ledger backed by SQLite (Postgres-ready).

    The ledger does **not** replace the existing in-memory ``reserve_quota``
    helper; the in-memory one stays useful for the cost-budget check that
    runs *after* schema validation. This ledger is the source of truth for
    the request-count check that gates whether the request is admitted at
    all, so it must be durable across worker restarts.

    All public methods are thread-safe and idempotent within a single
    transaction (we ``BEGIN IMMEDIATE`` to prevent two concurrent workers
    from over-counting).
    """

    def __init__(self, conn_factory: Optional[Any] = None) -> None:
        # Allow tests + future PG migration to inject a different connection
        # factory without monkeypatching the auth-store import.
        self._conn_factory = conn_factory or db_connection

    def _open(self) -> sqlite3.Connection:
        conn = self._conn_factory()
        _ensure_ledger_table(conn)
        return conn

    def current_usage(self, user_key: str, plan: str, day: Optional[str] = None) -> int:
        """Return the request count for ``user_key`` on ``day`` (UTC)."""

        target_day = day or _today_utc()
        with self._open() as conn:
            row = conn.execute(
                """
                SELECT request_count FROM ai_quota_ledger
                WHERE user_key = ? AND plan = ? AND day = ?
                """,
                (user_key, plan, target_day),
            ).fetchone()
        if row is None:
            return 0
        return int(row[0])

    def reserve(
        self,
        user_key: str,
        plan: str,
        *,
        limit: Optional[int] = None,
        day: Optional[str] = None,
    ) -> dict[str, Any]:
        """Atomically check and increment the daily counter.

        Returns a snapshot dict ``{user_key, plan, day, used, limit,
        resets_at}`` describing the post-increment state. Raises
        :class:`QuotaExceededError` (status 429) if the increment would
        breach the effective daily cap.
        """

        target_day = day or _today_utc()
        cap = limit if limit is not None else effective_daily_limit(plan)
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        with self._open() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
            except sqlite3.OperationalError:
                # already in a tx — fall through; SQLite will serialise on
                # the write below via the WAL journal.
                pass
            row = conn.execute(
                """
                SELECT request_count FROM ai_quota_ledger
                WHERE user_key = ? AND plan = ? AND day = ?
                """,
                (user_key, plan, target_day),
            ).fetchone()
            used = int(row[0]) if row else 0
            if used >= cap:
                conn.rollback()
                snapshot = {
                    "user_key": user_key,
                    "plan": plan,
                    "day": target_day,
                    "used": used,
                    "limit": cap,
                    "resets_at": next_utc_midnight_iso(),
                }
                raise QuotaExceededError(
                    _quota_message(snapshot),
                    status_code=429,
                ).with_traceback(None)
            new_count = used + 1
            conn.execute(
                """
                INSERT INTO ai_quota_ledger (user_key, plan, day, request_count, last_request_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_key, plan, day) DO UPDATE
                    SET request_count = excluded.request_count,
                        last_request_at = excluded.last_request_at
                """,
                (user_key, plan, target_day, new_count, now_iso),
            )
            conn.commit()
        return {
            "user_key": user_key,
            "plan": plan,
            "day": target_day,
            "used": new_count,
            "limit": cap,
            "resets_at": next_utc_midnight_iso(),
        }

    def release(self, user_key: str, plan: str, day: Optional[str] = None) -> None:
        """Decrement the ledger (used when an AI call fails before billing).

        Idempotent — never goes below zero. Callers don't have to wrap this
        in a try/except; missing rows are silently ignored so failed
        first-of-day attempts don't pollute the ledger.
        """

        target_day = day or _today_utc()
        with self._open() as conn:
            row = conn.execute(
                """
                SELECT request_count FROM ai_quota_ledger
                WHERE user_key = ? AND plan = ? AND day = ?
                """,
                (user_key, plan, target_day),
            ).fetchone()
            if row is None or int(row[0]) <= 0:
                return
            conn.execute(
                """
                UPDATE ai_quota_ledger
                SET request_count = request_count - 1
                WHERE user_key = ? AND plan = ? AND day = ?
                """,
                (user_key, plan, target_day),
            )
            conn.commit()


def _quota_message(snapshot: dict[str, Any]) -> str:
    return (
        f"Daily AI scoring quota exceeded for plan '{snapshot['plan']}' "
        f"({snapshot['used']}/{snapshot['limit']}). Resets at {snapshot['resets_at']}."
    )


def reserve_daily_ai_quota(
    user_key: str, plan: str, *, ledger: Optional[AIQuotaLedger] = None
) -> dict[str, Any]:
    """High-level entry: reserve one AI scoring slot for ``user_key``.

    Returns the snapshot dict described in :meth:`AIQuotaLedger.reserve`.
    Raises :class:`QuotaExceededError` on exhaustion.
    """

    real_ledger = ledger or AIQuotaLedger()
    snapshot = real_ledger.reserve(user_key, plan)
    logger.info(
        "ai_quota_reserved user_key=%s plan=%s used=%s limit=%s",
        user_key,
        plan,
        snapshot["used"],
        snapshot["limit"],
    )
    return snapshot


__all__ = [
    "AIQuotaLedger",
    "DEFAULT_AI_DAILY_LIMIT",
    "QuotaExceededError",
    "ai_daily_limit",
    "check_rate_limit",
    "check_scoring_rate_limit",
    "cost_rate_cents_per_1k_tokens",
    "effective_daily_limit",
    "estimate_request_cost_cents",
    "estimate_text_tokens",
    "plan_cost_limit_cents",
    "plan_request_limit",
    "reserve_daily_ai_quota",
    "reserve_quota",
    "retry_limit",
    "validate_submission_size",
]
