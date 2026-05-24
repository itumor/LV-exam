"""Mock-exam orchestration service (T-033).

A *mock exam* is a full timed sitting that walks the learner through the
four canonical A2 skills — listening, reading, writing, speaking — in
that order. Each section has a fixed time budget; the runner auto-submits
when the budget elapses (frontend) or when the server detects the budget
has been exceeded on a late submission (server-side guard).

Why a separate service from :mod:`server_app.services.attempts`?
---------------------------------------------------------------

The single-exam attempt lifecycle (T-022) treats every attempt as one
opaque blob with a single ``answer_payload`` and ``score_payload``. A
mock exam is *four* attempts logically stitched together with per-section
timers and a per-section pass flag (the 9/15 rule from T-025). We
deliberately reuse:

* :func:`server_app.core.compute_objective_score` — per-section
  scoring; we feed it a single-skill answer key + answers and pick out
  the relevant ``by_skill`` bucket.
* :func:`server_app.services.schema_a2.is_passing` — the 9/15 rule.
* :data:`server_app.services.schema_a2.A2_SKILLS` — canonical skill
  order.

The mock-exam *runner* persists state in two new tables:

* ``mock_exams`` — one row per sitting (account, level, status, section
  budgets, current section, start/finish timestamps).
* ``mock_exam_section_scores`` — one row per (mock_exam_id, skill)
  recording score, points_possible, time_spent, expired flag, and the
  raw answers blob.

The result endpoint stitches both rows back into a learner-facing
payload with ``per_skill`` scores, ``overall_pass`` (9/15 on all four
sections), and a ``weak_skill_suggestions`` list that drives the
weak-skill repair queue.

Section durations
-----------------

Per the T-033 brief, the canonical A2 mock-exam budgets are::

    listening  25 minutes
    reading    30 minutes
    writing    35 minutes
    speaking   15 minutes  (10-15 min range; we use the upper bound)

The mock-exam runner uses the values in
:data:`SECTION_DURATIONS_SECONDS` directly so the timer contract is
locked in code and reviewable in one place.

Determinism + safety
--------------------

* All writes go through :func:`server_app.core.db_connection` so the
  T-021 Postgres dual-write hook covers us automatically.
* Section submissions are idempotent per (mock_exam_id, skill): a second
  call returns the existing row instead of double-scoring.
* The result endpoint is read-only and safe to call repeatedly.
* Multi-user isolation is enforced at the SQL layer — every read/write
  filters on ``account_id`` so a guessed mock-exam id is useless to a
  different user.
"""

from __future__ import annotations

import json
import logging
import secrets
import sqlite3
import threading
from typing import Any, Mapping

from server_app.core import (
    ApiError,
    compute_objective_score,
    db_connection,
    now_iso,
)
from server_app.services.schema_a2 import (
    A2_MIN_PER_SKILL,
    A2_SKILLS,
    is_passing,
)


__all__ = [
    "SECTION_DURATIONS_SECONDS",
    "TOTAL_DURATION_SECONDS",
    "MockExamError",
    "MockExamNotFound",
    "MockExamSectionAlreadySubmitted",
    "MockExamSectionExpired",
    "api_error_from",
    "ensure_mock_exam_tables",
    "expire_section",
    "get_result",
    "list_history",
    "start_mock_exam",
    "submit_section",
]


logger = logging.getLogger("lvcodex.mock_exam")


# ---------------------------------------------------------------------------
# Constants — per-section budgets (the timer contract).
# ---------------------------------------------------------------------------


# Per the T-033 brief. Speaking uses the upper bound of the 10-15 min
# range published in the official Naturalizacijas parvalde sitting; the
# frontend timer reads these values verbatim.
SECTION_DURATIONS_SECONDS: dict[str, int] = {
    "listening": 25 * 60,
    "reading": 30 * 60,
    "writing": 35 * 60,
    "speaking": 15 * 60,
}


# Total exam wall-clock time. Used by the frontend to render the overall
# remaining countdown and by tests as a sanity check.
TOTAL_DURATION_SECONDS: int = sum(SECTION_DURATIONS_SECONDS.values())


# Status values mirror the attempt-status taxonomy (started / in_progress
# / completed / expired) so admin dashboards can filter both with one
# enum. ``completed`` means all four sections submitted (or expired);
# ``expired`` means the overall wall-clock budget elapsed before that.
_STATUS_STARTED = "started"
_STATUS_IN_PROGRESS = "in_progress"
_STATUS_COMPLETED = "completed"
_STATUS_EXPIRED = "expired"


_DDL_LOCK = threading.Lock()
_DDL_APPLIED = False


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class MockExamError(Exception):
    """Base error for mock-exam orchestration."""


class MockExamNotFound(MockExamError):
    """Raised when a mock_exam row does not exist or is not owned."""


class MockExamSectionAlreadySubmitted(MockExamError):
    """Raised when a section has already been submitted (idempotent path)."""


class MockExamSectionExpired(MockExamError):
    """Raised when a submission arrives after the section budget elapsed.

    Carries the (now zero-scored) section payload so the route handler
    can still record a 0-point row and surface a learner-friendly
    message.
    """


# ---------------------------------------------------------------------------
# Schema bootstrapping
# ---------------------------------------------------------------------------


_CREATE_MOCK_EXAMS = """
CREATE TABLE IF NOT EXISTS mock_exams (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    level_code TEXT NOT NULL DEFAULT 'A2',
    status TEXT NOT NULL DEFAULT 'started',
    sections_payload TEXT NOT NULL,
    current_skill TEXT,
    started_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    completed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


_CREATE_SECTION_SCORES = """
CREATE TABLE IF NOT EXISTS mock_exam_section_scores (
    id TEXT PRIMARY KEY,
    mock_exam_id TEXT NOT NULL REFERENCES mock_exams(id) ON DELETE CASCADE,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    skill TEXT NOT NULL CHECK (skill IN ('listening','reading','writing','speaking')),
    score INTEGER NOT NULL DEFAULT 0,
    points_possible INTEGER NOT NULL DEFAULT 0,
    duration_seconds INTEGER NOT NULL DEFAULT 0,
    time_spent_seconds INTEGER NOT NULL DEFAULT 0,
    expired_boolean INTEGER NOT NULL DEFAULT 0,
    passed_boolean INTEGER NOT NULL DEFAULT 0,
    answer_payload TEXT NOT NULL DEFAULT '{}',
    score_payload TEXT NOT NULL DEFAULT '{}',
    submitted_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (mock_exam_id, skill)
)
"""


_CREATE_INDEX_MOCK_EXAMS_ACCOUNT = (
    "CREATE INDEX IF NOT EXISTS idx_mock_exams_account_started "
    "ON mock_exams (account_id, started_at DESC)"
)
_CREATE_INDEX_SECTION_SCORES_MOCK = (
    "CREATE INDEX IF NOT EXISTS idx_mock_exam_section_scores_mock "
    "ON mock_exam_section_scores (mock_exam_id, skill)"
)


def ensure_mock_exam_tables(conn: sqlite3.Connection | None = None) -> None:
    """Create the two mock-exam tables if they do not exist.

    Idempotent. Callable from the route hook's import-time wiring and
    from tests that bootstrap a fresh DB. Optional ``conn`` argument
    lets tests pass an already-open connection (matching the pattern
    used by :func:`server_app.services.schema_a2.init_a2_schema_tables`).
    """

    global _DDL_APPLIED

    def _apply(c: sqlite3.Connection) -> None:
        c.execute(_CREATE_MOCK_EXAMS)
        c.execute(_CREATE_SECTION_SCORES)
        c.execute(_CREATE_INDEX_MOCK_EXAMS_ACCOUNT)
        c.execute(_CREATE_INDEX_SECTION_SCORES_MOCK)

    if conn is not None:
        _apply(conn)
        return

    with _DDL_LOCK:
        if _DDL_APPLIED:
            return
        try:
            with db_connection() as opened:
                _apply(opened)
            _DDL_APPLIED = True
        except Exception:  # noqa: BLE001
            logger.exception("mock_exam_tables_init_failed")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_mock_exam(row: sqlite3.Row) -> dict[str, Any]:
    sections = json.loads(row["sections_payload"] or "{}")
    return {
        "id": row["id"],
        "account_id": row["account_id"],
        "level_code": row["level_code"],
        "status": row["status"],
        "sections": sections,
        "current_skill": row["current_skill"],
        "started_at": row["started_at"],
        "expires_at": row["expires_at"],
        "completed_at": row["completed_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _row_to_section_score(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "mock_exam_id": row["mock_exam_id"],
        "skill": row["skill"],
        "score": int(row["score"]),
        "points_possible": int(row["points_possible"]),
        "duration_seconds": int(row["duration_seconds"]),
        "time_spent_seconds": int(row["time_spent_seconds"]),
        "expired": bool(row["expired_boolean"]),
        "passed": bool(row["passed_boolean"]),
        "submitted_at": row["submitted_at"],
        "score_payload": json.loads(row["score_payload"] or "{}"),
    }


def _load_owned_mock_exam(
    conn: sqlite3.Connection, mock_exam_id: str, account_id: str
) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM mock_exams WHERE id = ? AND account_id = ?",
        (mock_exam_id, account_id),
    ).fetchone()
    if row is None:
        raise MockExamNotFound(f"Mock exam {mock_exam_id!r} not found.")
    return row


def _next_skill(submitted: set[str]) -> str | None:
    for skill in A2_SKILLS:
        if skill not in submitted:
            return skill
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def start_mock_exam(
    account_id: str,
    *,
    level_code: str = "A2",
    mock_exam_id: str | None = None,
    started_at: str | None = None,
    expires_at: str | None = None,
) -> dict[str, Any]:
    """Create a new mock-exam sitting for ``account_id``.

    Returns the canonical mock-exam payload (see :func:`_row_to_mock_exam`)
    plus a ``durations`` map echoing :data:`SECTION_DURATIONS_SECONDS`
    so the frontend can render its timer without an extra round-trip.

    ``mock_exam_id`` / ``started_at`` / ``expires_at`` are test
    overrides; production callers should leave them ``None`` and let the
    service generate fresh values.
    """

    if not account_id:
        raise MockExamError("account_id is required.")

    ensure_mock_exam_tables()
    now = started_at or now_iso()
    mid = mock_exam_id or f"mock_{secrets.token_hex(8)}"

    sections = {
        skill: {
            "duration_seconds": SECTION_DURATIONS_SECONDS[skill],
            "ordinal": ordinal,
        }
        for ordinal, skill in enumerate(A2_SKILLS, start=1)
    }

    # If the caller did not provide an explicit expires_at, compute one
    # by adding the total wall-clock budget to ``now``. The frontend
    # uses this as the overall ceiling; per-section auto-submit uses
    # the per-section ``duration_seconds`` instead.
    if expires_at is None:
        expires_at = _shift_iso(now, TOTAL_DURATION_SECONDS)

    with db_connection() as conn:
        ensure_mock_exam_tables(conn)
        existing = conn.execute(
            "SELECT id FROM mock_exams WHERE id = ?", (mid,)
        ).fetchone()
        if existing is not None:
            row = _load_owned_mock_exam(conn, mid, account_id)
            return _decorate_with_durations(_row_to_mock_exam(row))
        conn.execute(
            """
            INSERT INTO mock_exams (
                id, account_id, level_code, status, sections_payload,
                current_skill, started_at, expires_at, completed_at,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
            """,
            (
                mid,
                account_id,
                level_code,
                _STATUS_STARTED,
                json.dumps(sections, ensure_ascii=False),
                A2_SKILLS[0],
                now,
                expires_at,
                now,
                now,
            ),
        )
        row = _load_owned_mock_exam(conn, mid, account_id)
    return _decorate_with_durations(_row_to_mock_exam(row))


def submit_section(
    mock_exam_id: str,
    account_id: str,
    skill: str,
    *,
    answers: Mapping[str, Any] | None = None,
    answer_key: Mapping[str, Any] | None = None,
    time_spent_seconds: int | None = None,
    expired: bool = False,
    submitted_at: str | None = None,
) -> dict[str, Any]:
    """Score a single section and persist the result.

    Parameters
    ----------
    mock_exam_id, account_id
        Identifies the sitting + the caller. ``account_id`` MUST come
        from a verified session — never trust client input here.
    skill
        One of ``listening`` / ``reading`` / ``writing`` / ``speaking``.
    answers, answer_key
        Single-skill answer + key blobs. The mock-exam runner ships the
        same shape ``compute_objective_score`` accepts at the section
        level, e.g. ``{"task1": ["A", "B"]}``. Both are optional — a
        timer-expiry call passes ``{}`` and gets a 0-point row.
    time_spent_seconds
        Wall-clock seconds the learner actually spent on the section.
        Bounded at the section budget so a misbehaving client cannot
        report 30 minutes on a 25-minute section.
    expired
        When ``True``, the row is marked as auto-submitted on timeout
        and the score is taken from whatever ``answers`` were collected
        before the timer fired (typically a partial set).
    submitted_at
        Test override — production callers leave ``None`` to use the
        current server time.
    """

    if skill not in A2_SKILLS:
        raise MockExamError(f"Unknown skill {skill!r}.")
    if not account_id:
        raise MockExamError("account_id is required.")

    ensure_mock_exam_tables()
    now = submitted_at or now_iso()
    safe_answers = dict(answers or {})
    safe_key = dict(answer_key or {})

    # Build the section-shape inputs ``compute_objective_score``
    # expects: it scores all four skills at once, but the consumer only
    # cares about the one skill's bucket. Filling the other three with
    # empty dicts is the cheapest way to reuse the existing logic
    # without duplicating its parsing rules.
    full_key = {s: (safe_key if s == skill else {}) for s in A2_SKILLS}
    full_answers = {s: (safe_answers if s == skill else {}) for s in A2_SKILLS}
    scoring = compute_objective_score(full_key, full_answers)
    bucket = (scoring.get("by_skill") or {}).get(skill) or {}
    objective_correct = int(bucket.get("objective_correct", 0) or 0)
    objective_possible = int(bucket.get("objective_possible", 0) or 0)
    passed = objective_correct >= A2_MIN_PER_SKILL

    with db_connection() as conn:
        ensure_mock_exam_tables(conn)
        mock_row = _load_owned_mock_exam(conn, mock_exam_id, account_id)

        if mock_row["status"] in {_STATUS_COMPLETED, _STATUS_EXPIRED}:
            existing = conn.execute(
                "SELECT * FROM mock_exam_section_scores "
                "WHERE mock_exam_id = ? AND skill = ?",
                (mock_exam_id, skill),
            ).fetchone()
            if existing is not None:
                return {
                    "section": _row_to_section_score(existing),
                    "mock_exam": _row_to_mock_exam(mock_row),
                    "idempotent": True,
                }
            raise MockExamError(
                f"Mock exam {mock_exam_id!r} is {mock_row['status']}; "
                "cannot submit new sections."
            )

        # Idempotent: a second submit for the same skill returns the
        # original row instead of double-scoring.
        existing = conn.execute(
            "SELECT * FROM mock_exam_section_scores "
            "WHERE mock_exam_id = ? AND skill = ?",
            (mock_exam_id, skill),
        ).fetchone()
        if existing is not None:
            mock_row_refreshed = _load_owned_mock_exam(
                conn, mock_exam_id, account_id
            )
            return {
                "section": _row_to_section_score(existing),
                "mock_exam": _row_to_mock_exam(mock_row_refreshed),
                "idempotent": True,
            }

        duration = SECTION_DURATIONS_SECONDS[skill]
        # Clamp time-spent at the budget so a misreporting client can't
        # report > duration. A negative value is coerced to zero.
        if time_spent_seconds is None:
            recorded_time = duration if expired else duration
        else:
            recorded_time = max(0, min(int(time_spent_seconds), duration))

        section_id = f"mock_sec_{secrets.token_hex(8)}"
        conn.execute(
            """
            INSERT INTO mock_exam_section_scores (
                id, mock_exam_id, account_id, skill, score, points_possible,
                duration_seconds, time_spent_seconds, expired_boolean,
                passed_boolean, answer_payload, score_payload, submitted_at,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                section_id,
                mock_exam_id,
                account_id,
                skill,
                objective_correct,
                objective_possible,
                duration,
                recorded_time,
                1 if expired else 0,
                1 if passed else 0,
                json.dumps(safe_answers, ensure_ascii=False),
                json.dumps(scoring, ensure_ascii=False),
                now,
                now,
            ),
        )

        # Advance the mock-exam status: if this was the last skill,
        # mark completed; otherwise move current_skill to the next.
        submitted_rows = conn.execute(
            "SELECT skill FROM mock_exam_section_scores WHERE mock_exam_id = ?",
            (mock_exam_id,),
        ).fetchall()
        submitted = {r["skill"] for r in submitted_rows}
        next_skill = _next_skill(submitted)
        if next_skill is None:
            new_status = _STATUS_COMPLETED
            completed_at = now
        else:
            new_status = _STATUS_IN_PROGRESS
            completed_at = None
        conn.execute(
            """
            UPDATE mock_exams
            SET status = ?,
                current_skill = ?,
                completed_at = COALESCE(?, completed_at),
                updated_at = ?
            WHERE id = ?
            """,
            (new_status, next_skill, completed_at, now, mock_exam_id),
        )
        section_row = conn.execute(
            "SELECT * FROM mock_exam_section_scores WHERE id = ?",
            (section_id,),
        ).fetchone()
        mock_row_refreshed = _load_owned_mock_exam(
            conn, mock_exam_id, account_id
        )

    return {
        "section": _row_to_section_score(section_row),
        "mock_exam": _row_to_mock_exam(mock_row_refreshed),
        "idempotent": False,
    }


def expire_section(
    mock_exam_id: str,
    account_id: str,
    skill: str,
    *,
    answers: Mapping[str, Any] | None = None,
    answer_key: Mapping[str, Any] | None = None,
    time_spent_seconds: int | None = None,
    submitted_at: str | None = None,
) -> dict[str, Any]:
    """Auto-submit on timer expiry — convenience wrapper.

    Equivalent to :func:`submit_section` with ``expired=True``. Kept as
    a separate name so the route handler and tests can express intent
    explicitly.
    """

    return submit_section(
        mock_exam_id,
        account_id,
        skill,
        answers=answers,
        answer_key=answer_key,
        time_spent_seconds=time_spent_seconds,
        expired=True,
        submitted_at=submitted_at,
    )


def get_result(mock_exam_id: str, account_id: str) -> dict[str, Any]:
    """Return the full result payload for a sitting.

    Shape (learner-facing):

    .. code-block:: json

        {
          "mock_exam": {...},
          "per_skill": {
            "listening": {"score": 11, "passed": true, "expired": false,
                          "time_spent_seconds": 1400, ...},
            ...
          },
          "overall": {
            "total_score": 38,
            "total_possible": 60,
            "pass": false,
            "min_per_skill": 9
          },
          "weak_skill_suggestions": ["writing", "speaking"],
          "completed": false
        }
    """

    ensure_mock_exam_tables()
    with db_connection() as conn:
        ensure_mock_exam_tables(conn)
        mock_row = _load_owned_mock_exam(conn, mock_exam_id, account_id)
        section_rows = conn.execute(
            "SELECT * FROM mock_exam_section_scores "
            "WHERE mock_exam_id = ? ORDER BY skill",
            (mock_exam_id,),
        ).fetchall()

    per_skill: dict[str, dict[str, Any]] = {}
    weak: list[str] = []
    total_score = 0
    total_possible = 0
    for row in section_rows:
        entry = _row_to_section_score(row)
        per_skill[entry["skill"]] = {
            "score": entry["score"],
            "points_possible": entry["points_possible"],
            "passed": entry["passed"],
            "expired": entry["expired"],
            "time_spent_seconds": entry["time_spent_seconds"],
            "duration_seconds": entry["duration_seconds"],
            "submitted_at": entry["submitted_at"],
        }
        total_score += entry["score"]
        total_possible += entry["points_possible"]
        if not entry["passed"]:
            weak.append(entry["skill"])

    # Skills that have not been submitted yet are reported as "missing"
    # so the result page can show a placeholder row instead of silently
    # dropping the section.
    for skill in A2_SKILLS:
        if skill not in per_skill:
            per_skill[skill] = {
                "score": None,
                "points_possible": None,
                "passed": False,
                "expired": False,
                "time_spent_seconds": None,
                "duration_seconds": SECTION_DURATIONS_SECONDS[skill],
                "submitted_at": None,
            }

    completed = len(section_rows) == len(A2_SKILLS)
    # ``is_passing`` is the single source of truth for the 9/15 rule
    # (T-025). We pass the raw score map so a re-implementation drift
    # is impossible.
    scoring_map = {
        skill: per_skill[skill]["score"] or 0 for skill in A2_SKILLS
    }
    overall_pass = completed and is_passing(scoring_map)

    return {
        "mock_exam": _row_to_mock_exam(mock_row),
        "per_skill": per_skill,
        "overall": {
            "total_score": total_score,
            "total_possible": total_possible,
            "pass": overall_pass,
            "min_per_skill": A2_MIN_PER_SKILL,
        },
        "weak_skill_suggestions": weak,
        "completed": completed,
    }


def list_history(
    account_id: str, *, limit: int = 20
) -> list[dict[str, Any]]:
    """Return the learner's past mock-exam sittings, newest first.

    Each entry includes the mock-exam header + a flattened ``per_skill``
    score map so the history page can render a leaderboard-style table
    without a second round-trip per row.
    """

    if not account_id:
        raise MockExamError("account_id is required.")
    if limit <= 0:
        limit = 20
    limit = min(limit, 200)

    ensure_mock_exam_tables()
    with db_connection() as conn:
        ensure_mock_exam_tables(conn)
        mock_rows = conn.execute(
            "SELECT * FROM mock_exams "
            "WHERE account_id = ? ORDER BY started_at DESC LIMIT ?",
            (account_id, limit),
        ).fetchall()
        section_rows = conn.execute(
            "SELECT * FROM mock_exam_section_scores "
            "WHERE account_id = ? ORDER BY submitted_at DESC",
            (account_id,),
        ).fetchall()

    sections_by_exam: dict[str, list[sqlite3.Row]] = {}
    for row in section_rows:
        sections_by_exam.setdefault(row["mock_exam_id"], []).append(row)

    out: list[dict[str, Any]] = []
    for mock_row in mock_rows:
        mid = mock_row["id"]
        entries = sections_by_exam.get(mid, [])
        per_skill = {}
        total = 0
        for entry in entries:
            per_skill[entry["skill"]] = {
                "score": int(entry["score"]),
                "passed": bool(entry["passed_boolean"]),
                "expired": bool(entry["expired_boolean"]),
            }
            total += int(entry["score"])
        scoring_map = {
            skill: per_skill.get(skill, {}).get("score") or 0
            for skill in A2_SKILLS
        }
        completed = len(entries) == len(A2_SKILLS)
        overall_pass = completed and is_passing(scoring_map)
        out.append(
            {
                "id": mid,
                "level_code": mock_row["level_code"],
                "status": mock_row["status"],
                "started_at": mock_row["started_at"],
                "completed_at": mock_row["completed_at"],
                "per_skill": per_skill,
                "total_score": total,
                "pass": overall_pass,
                "completed": completed,
            }
        )
    return out


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _decorate_with_durations(payload: dict[str, Any]) -> dict[str, Any]:
    payload["durations_seconds"] = dict(SECTION_DURATIONS_SECONDS)
    payload["total_duration_seconds"] = TOTAL_DURATION_SECONDS
    return payload


def _shift_iso(iso: str, delta_seconds: int) -> str:
    """Return ``iso`` shifted by ``delta_seconds``.

    The mock-exam frontend treats this purely as an opaque timestamp,
    so we parse using :class:`datetime.fromisoformat` (which accepts
    the trailing ``Z`` form via the ``+00:00`` rewrite) and emit the
    same ``...Z`` shape :func:`now_iso` produces.
    """

    from datetime import datetime, timedelta, timezone

    normalised = iso.replace("Z", "+00:00")
    base = datetime.fromisoformat(normalised)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    shifted = base + timedelta(seconds=delta_seconds)
    return shifted.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def api_error_from(exc: MockExamError) -> ApiError:
    """Translate a service-layer error into a route-layer ``ApiError``."""

    from http import HTTPStatus

    if isinstance(exc, MockExamNotFound):
        return ApiError(HTTPStatus.NOT_FOUND, "mock_exam_not_found", str(exc))
    if isinstance(exc, MockExamSectionAlreadySubmitted):
        return ApiError(
            HTTPStatus.CONFLICT,
            "mock_exam_section_already_submitted",
            str(exc),
        )
    if isinstance(exc, MockExamSectionExpired):
        return ApiError(
            HTTPStatus.CONFLICT, "mock_exam_section_expired", str(exc)
        )
    return ApiError(HTTPStatus.BAD_REQUEST, "mock_exam_invalid_request", str(exc))
