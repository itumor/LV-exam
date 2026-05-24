"""Exam content versioning service (T-037).

Implements the rapid-update pipeline described in
``docs/content-versioning.md``:

* every exam carries a semantic ``YYYY.MM.N`` version (e.g. ``2026.05.0``),
* edits land as ``draft`` rows in the ``exam_versions`` table,
* admins flip drafts to ``published`` (auto-archives the previous published
  row so a single version is "current" per exam),
* learners always read the currently-published version via the
  ``/api/exams/{id}/content`` endpoint,
* exams that pre-date T-037 fall through a grandfathering layer that pins
  them at ``GRANDFATHERED_VERSION`` (``1.0.0``) so the legacy catalog keeps
  serving content without any data migration.

The table is created lazily on first call (``init_exam_versions_table``)
and the schema is intentionally additive — it does not modify the existing
``exams`` table, so this change is reversible by simply dropping the new
table.

The same logical schema is portable to Postgres: only the constraint
syntax (``CHECK (status IN (...))``) and timestamp default differ, both of
which are pure-Python emitted strings here. T-021 will swap the SQLite
DDL for a PG-native migration without changing the service surface.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any, Iterable

# Status enum for exam_versions.status. Mirrors the workflow described in
# docs/content-versioning.md. ``draft``  -> editable, hidden from learners.
# ``published`` -> currently-served version (exactly one per exam_id).
# ``archived``  -> retained for audit/history, not served.
EXAM_VERSION_STATUSES: tuple[str, ...] = ("draft", "published", "archived")

# Calendar-versioned semantic version: ``YYYY.MM.N``.
# Examples: ``2026.05.0``, ``2026.05.1``, ``2026.12.42``.
# Matches the JSON schema in schemas/exam.schema.json.
VERSION_PATTERN = re.compile(r"^[0-9]{4}\.(0[1-9]|1[0-2])\.[0-9]+$")

# Sentinel returned for exams that do not yet have an exam_versions row.
# These are "grandfathered" — they ship from the static catalog and the
# learner-facing endpoint still serves them as if they were 1.0.0.
GRANDFATHERED_VERSION = "1.0.0"


class ExamVersionError(Exception):
    """Domain error raised when a transition is invalid.

    The route layer maps this to a ``400`` (or ``404`` when ``not_found`` is
    True) ApiError. Keeping a plain exception decouples the service from the
    HTTP layer so the script and the tests can use it without importing the
    full server.
    """

    def __init__(self, message: str, *, not_found: bool = False) -> None:
        super().__init__(message)
        self.not_found = not_found


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def is_valid_version(value: str | None) -> bool:
    """Return True if ``value`` is a well-formed T-037 exam version string."""

    if not isinstance(value, str) or not value:
        return False
    return bool(VERSION_PATTERN.match(value))


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS exam_versions (
    id TEXT PRIMARY KEY,
    exam_id TEXT NOT NULL,
    version TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    payload TEXT NOT NULL DEFAULT '{}',
    published_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(exam_id, version)
)
"""

_CREATE_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_exam_versions_exam_status "
    "ON exam_versions(exam_id, status)"
)


def init_exam_versions_table(conn: sqlite3.Connection) -> None:
    """Create the ``exam_versions`` table if it does not already exist.

    Idempotent. Safe to call from the existing ``init_auth_store`` bootstrap
    or from individual entry points (script, tests). Uses only SQL that is
    portable to Postgres modulo the ``IF NOT EXISTS`` keyword.
    """

    conn.execute(_CREATE_TABLE_SQL)
    conn.execute(_CREATE_INDEX_SQL)


# ---------------------------------------------------------------------------
# Read APIs
# ---------------------------------------------------------------------------


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    payload_raw = row["payload"] if "payload" in row.keys() else "{}"
    try:
        payload = json.loads(payload_raw) if payload_raw else {}
    except (TypeError, ValueError):
        payload = {}
    return {
        "id": row["id"],
        "exam_id": row["exam_id"],
        "version": row["version"],
        "status": row["status"],
        "payload": payload,
        "published_at": row["published_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def get_current_version(conn: sqlite3.Connection, exam_id: str) -> str:
    """Return the version string a learner should see for ``exam_id``.

    Returns the published version when one exists. Falls back to
    :data:`GRANDFATHERED_VERSION` (``1.0.0``) when no published row exists,
    which preserves backward compatibility for the seeded built-in catalog
    that pre-dates T-037.
    """

    init_exam_versions_table(conn)
    row = conn.execute(
        "SELECT version FROM exam_versions WHERE exam_id = ? AND status = 'published' "
        "ORDER BY published_at DESC, updated_at DESC LIMIT 1",
        (str(exam_id),),
    ).fetchone()
    if row is None:
        return GRANDFATHERED_VERSION
    return str(row["version"])


def get_current_published(
    conn: sqlite3.Connection, exam_id: str
) -> dict[str, Any] | None:
    """Return the full currently-published row for ``exam_id`` or None."""

    init_exam_versions_table(conn)
    row = conn.execute(
        "SELECT * FROM exam_versions WHERE exam_id = ? AND status = 'published' "
        "ORDER BY published_at DESC, updated_at DESC LIMIT 1",
        (str(exam_id),),
    ).fetchone()
    return _row_to_dict(row) if row is not None else None


def get_version(
    conn: sqlite3.Connection, exam_id: str, version: str
) -> dict[str, Any] | None:
    init_exam_versions_table(conn)
    row = conn.execute(
        "SELECT * FROM exam_versions WHERE exam_id = ? AND version = ?",
        (str(exam_id), str(version)),
    ).fetchone()
    return _row_to_dict(row) if row is not None else None


def list_drafts(
    conn: sqlite3.Connection, exam_id: str | None = None
) -> list[dict[str, Any]]:
    """Return all draft exam_versions rows (admin-facing).

    When ``exam_id`` is given, restricts to drafts for that exam. Returns
    newest-first by ``updated_at`` so the freshest pipeline activity is at
    the top of the admin console.
    """

    init_exam_versions_table(conn)
    if exam_id is None:
        rows = conn.execute(
            "SELECT * FROM exam_versions WHERE status = 'draft' "
            "ORDER BY updated_at DESC, created_at DESC"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM exam_versions WHERE exam_id = ? AND status = 'draft' "
            "ORDER BY updated_at DESC, created_at DESC",
            (str(exam_id),),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def list_versions(
    conn: sqlite3.Connection,
    exam_id: str,
    *,
    statuses: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """Return every known version row for ``exam_id``.

    Optional ``statuses`` filter narrows the result to the provided set.
    """

    init_exam_versions_table(conn)
    if statuses is None:
        rows = conn.execute(
            "SELECT * FROM exam_versions WHERE exam_id = ? "
            "ORDER BY version DESC",
            (str(exam_id),),
        ).fetchall()
    else:
        status_list = list(statuses)
        if not status_list:
            return []
        placeholders = ",".join("?" * len(status_list))
        rows = conn.execute(
            f"SELECT * FROM exam_versions WHERE exam_id = ? AND status IN ({placeholders}) "
            "ORDER BY version DESC",
            (str(exam_id), *status_list),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Write APIs
# ---------------------------------------------------------------------------


def _new_id(exam_id: str, version: str) -> str:
    return f"examver_{exam_id}_{version.replace('.', '_')}"


def create_draft(
    conn: sqlite3.Connection,
    exam_id: str,
    version: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Insert (or replace) a draft row.

    A second ``create_draft`` call for the same (exam_id, version) refreshes
    the payload but does NOT silently re-open a published row. Re-drafting a
    published version raises :class:`ExamVersionError`.
    """

    init_exam_versions_table(conn)
    if not exam_id:
        raise ExamVersionError("exam_id is required")
    if not is_valid_version(version):
        raise ExamVersionError(
            f"version '{version}' is not a valid YYYY.MM.N exam version"
        )
    payload_json = json.dumps(payload or {}, ensure_ascii=False)
    now = _now_iso()
    existing = conn.execute(
        "SELECT status FROM exam_versions WHERE exam_id = ? AND version = ?",
        (exam_id, version),
    ).fetchone()
    if existing is not None and existing["status"] in {"published", "archived"}:
        raise ExamVersionError(
            f"exam {exam_id} version {version} is already {existing['status']}"
            " and cannot be re-opened as a draft (cut a new version instead)"
        )
    if existing is None:
        conn.execute(
            "INSERT INTO exam_versions "
            "(id, exam_id, version, status, payload, published_at, created_at, updated_at) "
            "VALUES (?, ?, ?, 'draft', ?, NULL, ?, ?)",
            (_new_id(exam_id, version), exam_id, version, payload_json, now, now),
        )
    else:
        conn.execute(
            "UPDATE exam_versions SET payload = ?, updated_at = ? "
            "WHERE exam_id = ? AND version = ?",
            (payload_json, now, exam_id, version),
        )
    return get_version(conn, exam_id, version) or {}


def publish_version(
    conn: sqlite3.Connection, exam_id: str, version: str
) -> dict[str, Any]:
    """Flip a draft to ``published``.

    Side effects (all atomic within one SQLite transaction):

    * the previously-published version (if any) is moved to ``archived``,
    * the target row's ``status`` becomes ``published``,
    * the target row's ``published_at`` is stamped with the current UTC time.

    Idempotency: re-publishing the same (exam_id, version) when it is
    already published is a no-op that returns the row unchanged. Publishing
    an ``archived`` row is treated the same as publishing a draft — this
    lets admins roll a previous published version forward without inventing
    a new version number, which is the rapid-rollback path described in
    docs/content-versioning.md §4.
    """

    init_exam_versions_table(conn)
    if not is_valid_version(version):
        raise ExamVersionError(
            f"version '{version}' is not a valid YYYY.MM.N exam version"
        )
    target = conn.execute(
        "SELECT * FROM exam_versions WHERE exam_id = ? AND version = ?",
        (exam_id, version),
    ).fetchone()
    if target is None:
        raise ExamVersionError(
            f"exam {exam_id} version {version} not found", not_found=True
        )
    if target["status"] == "published":
        return _row_to_dict(target)
    now = _now_iso()
    # Archive any current published row that is NOT the same version.
    conn.execute(
        "UPDATE exam_versions SET status = 'archived', updated_at = ? "
        "WHERE exam_id = ? AND status = 'published' AND version != ?",
        (now, exam_id, version),
    )
    conn.execute(
        "UPDATE exam_versions "
        "SET status = 'published', published_at = ?, updated_at = ? "
        "WHERE exam_id = ? AND version = ?",
        (now, now, exam_id, version),
    )
    return get_version(conn, exam_id, version) or {}


def archive_version(
    conn: sqlite3.Connection, exam_id: str, version: str
) -> dict[str, Any]:
    init_exam_versions_table(conn)
    target = conn.execute(
        "SELECT * FROM exam_versions WHERE exam_id = ? AND version = ?",
        (exam_id, version),
    ).fetchone()
    if target is None:
        raise ExamVersionError(
            f"exam {exam_id} version {version} not found", not_found=True
        )
    now = _now_iso()
    conn.execute(
        "UPDATE exam_versions SET status = 'archived', updated_at = ? "
        "WHERE exam_id = ? AND version = ?",
        (now, exam_id, version),
    )
    return get_version(conn, exam_id, version) or {}


__all__ = [
    "EXAM_VERSION_STATUSES",
    "GRANDFATHERED_VERSION",
    "VERSION_PATTERN",
    "ExamVersionError",
    "archive_version",
    "create_draft",
    "get_current_published",
    "get_current_version",
    "get_version",
    "init_exam_versions_table",
    "is_valid_version",
    "list_drafts",
    "list_versions",
    "publish_version",
]
