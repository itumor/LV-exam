"""T-032 — SuperMemo-2 (SM-2) spaced-repetition vocabulary service.

This module is the single source of truth for the weak-skill repair queue
that drives a learner's vocabulary review flow. It implements the classic
SM-2 algorithm (Piotr Wozniak, 1985-1990) over a tiny relational schema:

``srs_cards``
    The learner's deck. Each row pairs a Latvian lemma with its English
    gloss and carries the SM-2 state needed to schedule the next review:
    ``ease`` (the easiness factor, default 2.5, floor 1.3),
    ``interval_days`` (current scheduling interval in whole days), and
    ``next_due`` (an ISO-8601 date in UTC).

``srs_reviews``
    Append-only review log. Every call to :func:`review_card` writes one
    row tagged with the user's quality grade (0-5, the canonical SM-2
    scale) and the reviewer's wall-clock timestamp. This is what lets us
    answer "show me cards reviewed this week" and "audit how a card's
    ease drifted over time".

SM-2 in one paragraph
---------------------

The learner grades each recall on a 0-5 scale where ``5`` is "perfect"
and ``0`` is "complete blackout". On every review:

* If the grade is **< 3**, the card is treated as a lapse: ``ease`` is
  re-derived (and floored at 1.3) and the schedule restarts from a fresh
  "first review tomorrow" baseline (``interval_days = 1``). The next
  review keeps the card in the daily queue rather than pushing it weeks
  out.
* If the grade is **>= 3** (recalled), ``ease`` is updated by
  ``EF' = EF + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))`` (the canonical
  SM-2 formula). The new interval is computed from the *repetition
  index*: the first successful recall schedules the card 1 day out, the
  second 6 days, and every subsequent successful recall multiplies the
  previous interval by the (just-updated) ease.

The repetition index resets to zero on a lapse — so a single ``quality 0``
fully resets the card's schedule, even though the ease itself can never
fall below ``1.3``. This is the behaviour the T-032 brief calls out
("quality 0 resets ease"); see :class:`Quality0ResetTests` for the
covering test.

Multi-user isolation
--------------------

Every read and every write filters by ``account_id``. Adding a card to
Alice never surfaces it to Bob's ``GET /api/srs/due`` queue, and
``review_card`` rejects the call when the supplied ``card_id`` does not
belong to the supplied ``account_id`` (``PermissionError``). The HTTP
hooks (see ``server_app/core.py`` T-032 block) wrap the same
``account_id`` plumbing that drives missions/XP — so the request
account_id is the only key that ever leaks into a query.

Public surface
--------------

``ensure_srs_schema(conn) -> None``
    Idempotent DDL applier.

``add_card(conn, account_id, lemma, lv, en, *, now=None) -> dict``
    Insert (or return existing) card with default SM-2 state. Idempotent
    on ``(account_id, lemma)``.

``due_cards(conn, account_id, *, now=None, limit=None) -> list[dict]``
    Return the learner's cards whose ``next_due <= today`` (UTC date),
    sorted oldest-due-first.

``review_card(conn, account_id, card_id, quality, *, now=None) -> dict``
    Apply the SM-2 update for ``quality`` and append one ``srs_reviews``
    row. Returns the updated card.

``get_card(conn, account_id, card_id) -> dict | None``
    Read-only fetcher used by the HTTP layer to validate ownership
    before a review is applied.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("lvcodex.srs")


# ---------------------------------------------------------------------------
# SM-2 constants
# ---------------------------------------------------------------------------

#: SM-2 starts every new card at this ease.
DEFAULT_EASE = 2.5

#: SM-2 floors ease at 1.3 so a streak of bad reviews can never push the
#: card into a degenerate "never review" state.
MIN_EASE = 1.3

#: Canonical first-success interval (days) per the original SM-2 paper.
FIRST_INTERVAL_DAYS = 1

#: Canonical second-success interval (days) per the original SM-2 paper.
SECOND_INTERVAL_DAYS = 6

#: Grades below this value are treated as "lapsed" — the schedule
#: restarts from the FIRST_INTERVAL baseline.
RECALL_THRESHOLD = 3

#: Maximum review limit returned by :func:`due_cards` when the caller
#: doesn't pass an explicit ``limit``. Keeps the daily queue manageable.
DEFAULT_DUE_LIMIT = 50


# ---------------------------------------------------------------------------
# DDL — applied once per connection
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS srs_cards (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    lemma TEXT NOT NULL,
    lv TEXT NOT NULL,
    en TEXT NOT NULL,
    ease REAL NOT NULL DEFAULT 2.5,
    interval_days INTEGER NOT NULL DEFAULT 0,
    repetitions INTEGER NOT NULL DEFAULT 0,
    next_due TEXT NOT NULL,
    last_quality INTEGER,
    last_reviewed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(account_id, lemma)
);

CREATE INDEX IF NOT EXISTS idx_srs_cards_account_due
    ON srs_cards(account_id, next_due);

CREATE TABLE IF NOT EXISTS srs_reviews (
    id TEXT PRIMARY KEY,
    card_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    quality INTEGER NOT NULL,
    ease_after REAL NOT NULL,
    interval_after INTEGER NOT NULL,
    reviewed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_srs_reviews_card_time
    ON srs_reviews(card_id, reviewed_at DESC);

CREATE INDEX IF NOT EXISTS idx_srs_reviews_account_time
    ON srs_reviews(account_id, reviewed_at DESC);
"""

_DDL_APPLIED = False
_DDL_LOCK = threading.Lock()


def ensure_srs_schema(conn: sqlite3.Connection) -> None:
    """Create the two T-032 tables if they don't already exist.

    Safe to call on every request — a process-wide once-flag short
    circuits after the first successful run. Tests reset the flag via
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
# Datetime helpers
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


def _today_date(now: datetime | None = None) -> str:
    """Return the UTC calendar date as ``YYYY-MM-DD``.

    SRS scheduling deliberately ignores the learner's local timezone:
    "due today" should always mean a stable, monotone UTC date so a
    learner who reviews late at night and again the next morning gets
    consistent behaviour regardless of which timezone the request hits.
    """

    return _now(now).date().isoformat()


def _shift_date(start: str, days: int) -> str:
    """Return ``start + days`` as ``YYYY-MM-DD``."""

    try:
        anchor = date.fromisoformat(start)
    except ValueError:
        anchor = _now().date()
    return (anchor + timedelta(days=max(0, int(days)))).isoformat()


# ---------------------------------------------------------------------------
# Row serialisation
# ---------------------------------------------------------------------------


def _row_to_card(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "account_id": row["account_id"],
        "lemma": row["lemma"],
        "lv": row["lv"],
        "en": row["en"],
        "ease": float(row["ease"]),
        "interval_days": int(row["interval_days"]),
        "repetitions": int(row["repetitions"]),
        "next_due": row["next_due"],
        "last_quality": (
            int(row["last_quality"]) if row["last_quality"] is not None else None
        ),
        "last_reviewed_at": row["last_reviewed_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


# ---------------------------------------------------------------------------
# Card creation
# ---------------------------------------------------------------------------


def add_card(
    conn: sqlite3.Connection,
    account_id: str,
    lemma: str,
    lv: str,
    en: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Insert (or return) a card with default SM-2 state.

    Idempotent on ``(account_id, lemma)``: a second call with the same
    pair returns the existing card unchanged. A new card is born "due
    today" so the very next ``GET /api/srs/due`` includes it.
    """

    if not account_id:
        raise ValueError("account_id is required")
    if not lemma or not lv or not en:
        raise ValueError("lemma, lv, and en are required")

    ensure_srs_schema(conn)
    instant = _now(now)
    today = _today_date(instant)
    timestamp = _now_iso(instant)

    existing = conn.execute(
        "SELECT * FROM srs_cards WHERE account_id = ? AND lemma = ?",
        (account_id, lemma),
    ).fetchone()
    if existing is not None:
        return _row_to_card(existing)

    card_id = f"srs_{uuid.uuid4().hex[:16]}"
    conn.execute(
        """
        INSERT INTO srs_cards
            (id, account_id, lemma, lv, en, ease, interval_days, repetitions,
             next_due, last_quality, last_reviewed_at, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?, NULL, NULL, ?, ?)
        """,
        (card_id, account_id, lemma, lv, en, DEFAULT_EASE, today, timestamp, timestamp),
    )
    row = conn.execute(
        "SELECT * FROM srs_cards WHERE id = ?", (card_id,)
    ).fetchone()
    return _row_to_card(row)


def get_card(
    conn: sqlite3.Connection, account_id: str, card_id: str
) -> dict[str, Any] | None:
    """Return the card if it belongs to ``account_id`` — else ``None``."""

    ensure_srs_schema(conn)
    row = conn.execute(
        "SELECT * FROM srs_cards WHERE id = ? AND account_id = ?",
        (card_id, account_id),
    ).fetchone()
    return _row_to_card(row) if row is not None else None


# ---------------------------------------------------------------------------
# Due-card selection
# ---------------------------------------------------------------------------


def due_cards(
    conn: sqlite3.Connection,
    account_id: str,
    *,
    now: datetime | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return cards whose ``next_due <= today`` for ``account_id``.

    Sorted oldest-due-first (and ``created_at`` ascending as a tie
    breaker) so the learner clears the oldest backlog first. ``limit``
    defaults to :data:`DEFAULT_DUE_LIMIT` to keep the daily queue
    manageable; pass an explicit integer to override.
    """

    ensure_srs_schema(conn)
    today = _today_date(now)
    cap = DEFAULT_DUE_LIMIT if limit is None else max(0, int(limit))
    if cap <= 0:
        return []

    rows = conn.execute(
        """
        SELECT * FROM srs_cards
        WHERE account_id = ? AND next_due <= ?
        ORDER BY next_due ASC, created_at ASC, id ASC
        LIMIT ?
        """,
        (account_id, today, cap),
    ).fetchall()
    return [_row_to_card(row) for row in rows]


# ---------------------------------------------------------------------------
# SM-2 scheduler
# ---------------------------------------------------------------------------


def _next_ease(current: float, quality: int) -> float:
    """Apply the canonical SM-2 ease update.

    ``EF' = EF + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))``

    The result is floored at :data:`MIN_EASE` so a streak of bad reviews
    cannot drive the schedule into the ground.
    """

    q = max(0, min(5, int(quality)))
    delta = 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02)
    return max(MIN_EASE, float(current) + delta)


def _next_interval(
    *, repetitions: int, previous_interval: int, ease: float
) -> int:
    """Map the post-review repetition index to a days-out interval.

    * ``repetitions == 1`` → :data:`FIRST_INTERVAL_DAYS`
    * ``repetitions == 2`` → :data:`SECOND_INTERVAL_DAYS`
    * ``repetitions >= 3`` → ``previous_interval * ease`` (rounded up to
      at least one day so two consecutive grade-3 reviews never collapse
      to a same-day interval).
    """

    if repetitions <= 1:
        return FIRST_INTERVAL_DAYS
    if repetitions == 2:
        return SECOND_INTERVAL_DAYS
    return max(1, int(round(max(1, int(previous_interval)) * float(ease))))


def review_card(
    conn: sqlite3.Connection,
    account_id: str,
    card_id: str,
    quality: int,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Apply the SM-2 update for ``quality`` and append a review row.

    * ``quality`` must be an integer 0-5 (clamped). Anything below
      :data:`RECALL_THRESHOLD` is treated as a lapse: ``repetitions``
      resets to ``0`` and the next review is scheduled
      :data:`FIRST_INTERVAL_DAYS` out so the card stays in the daily
      queue.
    * On a successful recall the ease is bumped via :func:`_next_ease`
      and the new interval is :func:`_next_interval`.

    Raises ``PermissionError`` if ``card_id`` does not belong to
    ``account_id`` — the HTTP layer renders this as a ``404`` (per the
    "isolation by obscurity" rule the existing missions/XP endpoints
    follow).
    """

    if not account_id:
        raise ValueError("account_id is required")
    if not card_id:
        raise ValueError("card_id is required")
    try:
        graded = int(quality)
    except (TypeError, ValueError) as exc:
        raise ValueError("quality must be an integer 0-5") from exc
    if graded < 0 or graded > 5:
        raise ValueError("quality must be an integer 0-5")

    ensure_srs_schema(conn)
    instant = _now(now)
    timestamp = _now_iso(instant)
    today = _today_date(instant)

    row = conn.execute(
        "SELECT * FROM srs_cards WHERE id = ? AND account_id = ?",
        (card_id, account_id),
    ).fetchone()
    if row is None:
        raise PermissionError("card_not_found")

    previous_interval = int(row["interval_days"] or 0)
    repetitions = int(row["repetitions"] or 0)

    if graded < RECALL_THRESHOLD:
        # Lapse — recompute ease, reset the repetition index, schedule a
        # next-day review. The ease floor still applies so a streak of
        # zeroes can never push the card past MIN_EASE.
        new_ease = _next_ease(float(row["ease"]), graded)
        new_repetitions = 0
        new_interval = FIRST_INTERVAL_DAYS
    else:
        new_ease = _next_ease(float(row["ease"]), graded)
        new_repetitions = repetitions + 1
        new_interval = _next_interval(
            repetitions=new_repetitions,
            previous_interval=previous_interval,
            ease=new_ease,
        )

    next_due = _shift_date(today, new_interval)

    conn.execute(
        """
        UPDATE srs_cards
        SET ease = ?,
            interval_days = ?,
            repetitions = ?,
            next_due = ?,
            last_quality = ?,
            last_reviewed_at = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            new_ease,
            new_interval,
            new_repetitions,
            next_due,
            graded,
            timestamp,
            timestamp,
            card_id,
        ),
    )

    review_id = f"rev_{uuid.uuid4().hex[:16]}"
    conn.execute(
        """
        INSERT INTO srs_reviews
            (id, card_id, account_id, quality, ease_after,
             interval_after, reviewed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (review_id, card_id, account_id, graded, new_ease, new_interval, timestamp),
    )

    logger.info(
        "srs_review card=%s account=%s quality=%s ease=%.3f interval=%s next_due=%s",
        card_id,
        account_id,
        graded,
        new_ease,
        new_interval,
        next_due,
    )

    updated = conn.execute(
        "SELECT * FROM srs_cards WHERE id = ?", (card_id,)
    ).fetchone()
    return _row_to_card(updated)


__all__ = [
    "DEFAULT_DUE_LIMIT",
    "DEFAULT_EASE",
    "FIRST_INTERVAL_DAYS",
    "MIN_EASE",
    "RECALL_THRESHOLD",
    "SECOND_INTERVAL_DAYS",
    "add_card",
    "due_cards",
    "ensure_srs_schema",
    "get_card",
    "review_card",
]
