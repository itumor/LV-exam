"""Audit-log export service (T-043).

Provides the storage layer and the CSV / JSON renderers used by the
``GET /api/admin/audit-export`` endpoint that institutional admins call
to pull a copy of their organisation's audit events.

The endpoint itself is wired in ``server_app/core.py`` via an end-of-file
hook so the modularisation pattern (T-020) is preserved. The endpoint
performs three checks before this module runs the query:

1. ``require_session`` — authenticated session present.
2. The session role must be ``admin`` or ``superadmin``.
3. ``can_export_org`` — superadmins can export any org; plain admins
   may only export their own ``accounts.org_id``.

Storage shape
-------------

The ``audit_events`` table is a thin, append-only ledger keyed by
``org_id`` so the export query can do a single indexed range scan.
Columns:

* ``id``            — opaque ULID-style identifier (``ae_<token>``).
* ``org_id``        — non-null. ``""`` means "platform-wide / no org" and
                      is **never** returned to a non-superadmin exporter.
* ``account_id``    — actor that triggered the event (may be NULL for
                      automated / system events such as cron jobs).
* ``event``         — short machine identifier (e.g. ``login.success``).
* ``occurred_at``   — ISO-8601 UTC timestamp; the date filter compares
                      against the ``YYYY-MM-DD`` prefix.
* ``source_ip``     — best-effort, may be ``""`` when missing.
* ``user_agent``    — best-effort, may be ``""`` when missing.
* ``payload_json``  — JSON-encoded extra context. Free-form by design;
                      the export renderer hands it through verbatim so an
                      operator can inspect the original event in their
                      analysis tool. Sensitive fields (passwords, tokens)
                      must already have been redacted by the caller of
                      ``record_audit_event`` — the renderer does NOT
                      re-redact.

The table is created idempotently by :func:`init_audit_events_table` and
its creation is folded into ``server_app.core.init_auth_store`` via the
end-of-file T-043 hook so existing DBs upgrade on next boot. Postgres
parity lives in ``migrations/postgres/005_audit_events.sql``.
"""

from __future__ import annotations

import csv
import io
import json
import re
import secrets
import sqlite3
from datetime import date, datetime, timezone
from typing import Any, Iterable, Mapping

__all__ = [
    "AuditExportError",
    "CSV_HEADER",
    "MAX_EXPORT_ROWS",
    "can_export_org",
    "init_audit_events_table",
    "normalise_date",
    "query_audit_events",
    "record_audit_event",
    "render_csv",
    "render_json",
]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


# Order matters: this is the canonical column order returned by both the
# CSV writer and the JSON serialiser, and it is contract-tested.
CSV_HEADER: tuple[str, ...] = (
    "id",
    "occurred_at",
    "org_id",
    "account_id",
    "event",
    "source_ip",
    "user_agent",
    "payload",
)


# Hard cap on returned rows. Keeps a malformed query from streaming
# millions of records and stalling the http.server thread. Operators can
# narrow the date window to pull more than this in chunks.
MAX_EXPORT_ROWS: int = 10_000


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class AuditExportError(ValueError):
    """Raised for caller-fixable problems (bad date, missing org)."""


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS audit_events (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    account_id TEXT,
    event TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    source_ip TEXT NOT NULL DEFAULT '',
    user_agent TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}'
)
"""

_CREATE_INDEX_ORG_TIME_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_audit_events_org_time "
    "ON audit_events (org_id, occurred_at)"
)


def init_audit_events_table(conn: sqlite3.Connection) -> None:
    """Create ``audit_events`` + its supporting index if absent.

    Idempotent. Mirrors the bootstrap pattern used by the SSO and tenant
    services so an operator restoring a fresh SQLite from backup picks
    up the schema on first request without having to run the migration
    runner separately.
    """

    conn.execute(_CREATE_TABLE_SQL)
    conn.execute(_CREATE_INDEX_ORG_TIME_SQL)


# ---------------------------------------------------------------------------
# Insert helper
# ---------------------------------------------------------------------------


def _new_event_id() -> str:
    # ``ae_`` prefix mirrors the prefixing convention used elsewhere
    # (``acct_``, ``att_``, ``ssop_``) so the id is greppable in logs.
    return f"ae_{secrets.token_hex(12)}"


def _iso_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def record_audit_event(
    conn: sqlite3.Connection,
    *,
    org_id: str,
    event: str,
    account_id: str | None = None,
    occurred_at: str | None = None,
    source_ip: str = "",
    user_agent: str = "",
    payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Append a row to ``audit_events``; returns the inserted dict.

    The caller is responsible for redacting sensitive fields from
    ``payload`` — the export renderer hands the JSON back verbatim. We
    JSON-encode ``payload`` here so storage shape stays well-formed even
    if the caller passed a sub-dict containing tuples / sets / dates.
    """

    init_audit_events_table(conn)
    org_id_norm = (org_id or "").strip().lower()
    event_norm = (event or "").strip()
    if not event_norm:
        raise AuditExportError("event is required.")
    payload_bytes = json.dumps(
        dict(payload or {}), ensure_ascii=False, sort_keys=True, default=str
    )
    row = {
        "id": _new_event_id(),
        "org_id": org_id_norm,
        "account_id": account_id,
        "event": event_norm,
        "occurred_at": occurred_at or _iso_now(),
        "source_ip": source_ip or "",
        "user_agent": user_agent or "",
        "payload_json": payload_bytes,
    }
    conn.execute(
        """
        INSERT INTO audit_events (
            id, org_id, account_id, event, occurred_at,
            source_ip, user_agent, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row["id"],
            row["org_id"],
            row["account_id"],
            row["event"],
            row["occurred_at"],
            row["source_ip"],
            row["user_agent"],
            row["payload_json"],
        ),
    )
    return row


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------


def normalise_date(value: str | None, *, field: str) -> str:
    """Validate ``YYYY-MM-DD`` and return it, or raise AuditExportError."""

    if value is None:
        raise AuditExportError(f"{field} is required (YYYY-MM-DD).")
    raw = value.strip()
    if not raw:
        raise AuditExportError(f"{field} is required (YYYY-MM-DD).")
    if not _DATE_RE.match(raw):
        raise AuditExportError(f"{field} must be ISO-8601 date (YYYY-MM-DD).")
    # date.fromisoformat enforces real-world dates (Feb 30 rejected).
    try:
        date.fromisoformat(raw)
    except ValueError as exc:
        raise AuditExportError(f"{field} is not a valid date: {raw!r}.") from exc
    return raw


def query_audit_events(
    conn: sqlite3.Connection,
    *,
    org_id: str,
    from_date: str,
    to_date: str,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return audit events for ``org_id`` falling in the ``[from, to]`` window.

    The bounds are inclusive on the date boundary: ``from_date`` is
    expanded to ``00:00:00Z`` and ``to_date`` to ``23:59:59Z``. ``occurred_at``
    is compared as a string, which works because the stored value is the
    canonical ISO-8601 ``YYYY-MM-DDTHH:MM:SSZ`` form and is sortable
    lexicographically.

    Raises :class:`AuditExportError` for caller-fixable issues
    (empty org, swapped date range).
    """

    init_audit_events_table(conn)
    org_id_norm = (org_id or "").strip().lower()
    if not org_id_norm:
        raise AuditExportError("org_id is required.")
    start = normalise_date(from_date, field="from")
    end = normalise_date(to_date, field="to")
    if end < start:
        raise AuditExportError("'to' must be on or after 'from'.")

    start_iso = f"{start}T00:00:00Z"
    end_iso = f"{end}T23:59:59Z"
    capped = MAX_EXPORT_ROWS if limit is None else max(1, min(int(limit), MAX_EXPORT_ROWS))

    cursor = conn.execute(
        """
        SELECT id, org_id, account_id, event, occurred_at,
               source_ip, user_agent, payload_json
          FROM audit_events
         WHERE org_id = ?
           AND occurred_at >= ?
           AND occurred_at <= ?
         ORDER BY occurred_at ASC, id ASC
         LIMIT ?
        """,
        (org_id_norm, start_iso, end_iso, capped),
    )
    rows: list[dict[str, Any]] = []
    for row in cursor.fetchall():
        rows.append(_row_to_dict(row))
    return rows


def _row_to_dict(row: sqlite3.Row | Mapping[str, Any]) -> dict[str, Any]:
    payload_raw = row["payload_json"] if "payload_json" in row.keys() else "{}"
    try:
        payload = json.loads(payload_raw) if payload_raw else {}
    except (TypeError, ValueError):
        # Defensive: never let a malformed legacy row break the export.
        payload = {"_unparseable": str(payload_raw)}
    return {
        "id": row["id"],
        "org_id": row["org_id"],
        "account_id": row["account_id"],
        "event": row["event"],
        "occurred_at": row["occurred_at"],
        "source_ip": row["source_ip"],
        "user_agent": row["user_agent"],
        "payload": payload,
    }


# ---------------------------------------------------------------------------
# Permission check
# ---------------------------------------------------------------------------


def can_export_org(session: Mapping[str, Any], requested_org_id: str) -> bool:
    """Return True iff ``session`` may export ``requested_org_id``.

    Rules:

    * ``superadmin`` may export any org (including ``""`` platform events).
    * ``admin`` may export only the org id stored on their account
      (``accounts.org_id``). Their session payload exposes this as
      ``session["account"]["org_id"]``.
    * Everyone else is denied.

    Empty ``requested_org_id`` is rejected for non-superadmins so a
    misconfigured admin cannot accidentally pull cross-tenant events.
    """

    account = session.get("account") if isinstance(session, Mapping) else None
    if not isinstance(account, Mapping):
        return False
    role = str(account.get("role") or "user")
    org_norm = (requested_org_id or "").strip().lower()
    if role == "superadmin":
        return True
    if role != "admin":
        return False
    membership = str(account.get("org_id") or "").strip().lower()
    if not membership:
        return False
    return membership == org_norm


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


def render_csv(rows: Iterable[Mapping[str, Any]]) -> str:
    """Serialise rows to CSV using :data:`CSV_HEADER` order.

    Returns a ``str`` (not bytes) so the route handler can pick the right
    Content-Type + charset header. The ``payload`` column is re-encoded
    as JSON inside a single CSV field — operators can split it open in
    their analysis tool of choice.
    """

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(CSV_HEADER)
    for row in rows:
        payload = row.get("payload")
        if isinstance(payload, str):
            payload_text = payload
        else:
            payload_text = json.dumps(
                payload or {}, ensure_ascii=False, sort_keys=True, default=str
            )
        writer.writerow(
            [
                _csv_safe(row.get("id")),
                _csv_safe(row.get("occurred_at")),
                _csv_safe(row.get("org_id")),
                _csv_safe(row.get("account_id")),
                _csv_safe(row.get("event")),
                _csv_safe(row.get("source_ip")),
                _csv_safe(row.get("user_agent")),
                payload_text,
            ]
        )
    return buf.getvalue()


def _csv_safe(value: Any) -> str:
    """Stringify a cell value and neutralise spreadsheet formula injection.

    ``=``/``+``/``-``/``@`` at the start of a CSV cell is treated by
    Excel + Google Sheets as a formula and can exfiltrate data when
    re-opened. We prefix with a single quote, which Excel strips on
    display but which leaves the value unambiguous in the raw file.
    """

    if value is None:
        return ""
    text = str(value)
    if text and text[0] in {"=", "+", "-", "@"}:
        return "'" + text
    return text


def render_json(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Serialise rows to a JSON envelope with metadata.

    The envelope shape is::

        {
          "count": <int>,
          "events": [
            {
              "id": ...,
              "org_id": ...,
              "account_id": ...,
              "event": ...,
              "occurred_at": ...,
              "source_ip": ...,
              "user_agent": ...,
              "payload": {...}
            },
            ...
          ]
        }

    The ``events`` list is the canonical wire shape — analytics
    consumers should rely on the field names, not the surrounding
    envelope keys, when joining against other datasets.
    """

    materialised = [dict(r) for r in rows]
    return {
        "count": len(materialised),
        "events": materialised,
    }
