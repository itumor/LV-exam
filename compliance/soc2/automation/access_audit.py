"""Access-audit evidence collector for SOC 2 (T-070-final).

Pulls a redacted snapshot from the T-043 ``audit_events`` ledger so the
auditor can attest that **CC6.1 / CC6.2 / CC6.3** (logical-access
provisioning + de-provisioning) is monitored.

The collector takes a ``connect`` callable that returns a DB-API 2.0
connection (typically ``sqlite3.connect``). Tests inject an in-memory
SQLite DB so we never touch production data. Production callers point
``connect`` at ``data/lvcodex.db`` via the orchestrator CLI.

Privacy: the raw ledger contains ``payload_json`` blobs that may carry
sensitive context. This collector **never** exports raw payloads — it
only aggregates by ``event`` name and by day. The auditor receives
counts, not user identifiers. Counts older than ``window_days`` are
dropped.

Output schema (stable; do not break without bumping ``schema_version``):

::

    {
      "collector": "access_audit",
      "schema_version": 1,
      "control_refs": ["CC6.1", "CC6.2", "CC6.3", "CC7.2"],
      "generated_at": <iso>,
      "window_days": <int>,
      "since": <iso date prefix>,
      "events_by_type": { "<event>": <count>, ... },
      "events_by_day":  { "YYYY-MM-DD": <count>, ... },
      "joiner_count":   <int>,
      "leaver_count":   <int>,
      "failed_login_count": <int>,
      "unique_actor_count": <int>,
      "table_present":  <bool>
    }
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping

SCHEMA_VERSION = 1

# Mapping from semantic bucket → audit event names emitted by the T-043
# ledger. Kept here rather than inside the SQL so a new event variant
# can be folded in via the same bucket without a migration.
JOINER_EVENTS = {"account.created", "admin.invited", "sso.user.provisioned"}
LEAVER_EVENTS = {"account.deleted", "account.deactivated", "session.revoked"}
FAILED_LOGIN_EVENTS = {"login.failure", "login.locked", "mfa.failure"}


class AccessAuditCollectorError(RuntimeError):
    """Raised when the audit_events table cannot be opened."""


def _table_exists(conn: Any) -> bool:
    try:
        cur = conn.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type='table' AND name='audit_events' LIMIT 1"
        )
    except Exception:
        return False
    row = cur.fetchone()
    return row is not None


def _fetch_rows(conn: Any, since: str) -> list[Mapping[str, Any]]:
    cur = conn.execute(
        "SELECT event, occurred_at, account_id "
        "FROM audit_events "
        "WHERE substr(occurred_at, 1, 10) >= ? "
        "ORDER BY occurred_at ASC",
        (since,),
    )
    rows: list[Mapping[str, Any]] = []
    for row in cur.fetchall():
        if isinstance(row, Mapping):
            rows.append(row)
        else:
            # sqlite3.Row supports index access; coerce defensively.
            rows.append(
                {
                    "event": row[0],
                    "occurred_at": row[1],
                    "account_id": row[2],
                }
            )
    return rows


def collect(
    *,
    connect: Callable[[], Any],
    days: int = 90,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Collect access-audit evidence.

    Parameters
    ----------
    connect:
        Zero-arg callable returning a DB-API connection. The collector
        owns the lifecycle and will close the connection.
    days:
        Rolling window. Default matches the quarterly access review.
    now:
        Injectable clock for tests.
    """
    now = now or datetime.now(timezone.utc)
    since = (now - timedelta(days=days)).strftime("%Y-%m-%d")
    payload: dict[str, Any] = {
        "collector": "access_audit",
        "schema_version": SCHEMA_VERSION,
        "control_refs": ["CC6.1", "CC6.2", "CC6.3", "CC7.2"],
        "generated_at": now.isoformat(),
        "window_days": days,
        "since": since,
        "events_by_type": {},
        "events_by_day": {},
        "joiner_count": 0,
        "leaver_count": 0,
        "failed_login_count": 0,
        "unique_actor_count": 0,
        "table_present": False,
    }

    conn = None
    try:
        conn = connect()
        if not _table_exists(conn):
            return payload
        payload["table_present"] = True
        rows = _fetch_rows(conn, since)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    events_by_type: dict[str, int] = {}
    events_by_day: dict[str, int] = {}
    actors: set[str] = set()
    for row in rows:
        event = str(row.get("event") or "")
        day = str(row.get("occurred_at") or "")[:10]
        actor = row.get("account_id")
        if event:
            events_by_type[event] = events_by_type.get(event, 0) + 1
            if event in JOINER_EVENTS:
                payload["joiner_count"] += 1
            if event in LEAVER_EVENTS:
                payload["leaver_count"] += 1
            if event in FAILED_LOGIN_EVENTS:
                payload["failed_login_count"] += 1
        if day:
            events_by_day[day] = events_by_day.get(day, 0) + 1
        if actor:
            actors.add(str(actor))

    payload["events_by_type"] = {k: events_by_type[k] for k in sorted(events_by_type)}
    payload["events_by_day"] = {k: events_by_day[k] for k in sorted(events_by_day)}
    payload["unique_actor_count"] = len(actors)
    return payload
