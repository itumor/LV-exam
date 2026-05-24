"""T-035 — Vertical "TikTok-style" listening feed service.

The feed reuses the existing curated micro-clip dataset shipped with the
listening library (``latvian-listening-library/web/microClips.json``):
each row already carries an ``audio_url`` (relative to the listening
library static root), a Latvian transcript, English translation, and a
three-option micro-quiz with a known answer index. This service turns
that dataset into a paginated feed and persists learner answers so the
XP engine (T-034) and the readiness dashboard (T-030) can read them.

Responsibilities
----------------
* Load and cache the curated clip catalogue from disk.
* Page through it with an opaque ``cursor`` token so the frontend never
  needs to track its own offset (and so we can later swap the in-memory
  source for a Postgres table without changing the API).
* Score a learner's quiz answer, compute an XP delta, and persist the
  attempt so future trains (T-032 weak-skill repair, T-052 leaderboards)
  can derive aggregates from a single source of truth.
* Stay drop-in compatible with the existing rate-limit middleware and
  the unified-accounts session helpers — the route module is thin on
  purpose.

Public surface
--------------
``build_listening_feed(cursor, limit) -> dict``
    Returns ``{"clips": [...], "next_cursor": str|None, "count": int}``.
``record_quiz_answer(clip_id, quiz_answer_index, account_id) -> dict``
    Returns ``{"correct": bool, "xp_delta": int, "answer_index": int,
              "correct_index": int}`` and writes a row to
    ``listening_feed_answers``.

The module avoids importing from :mod:`server_app.core` at import time
(except for ``db_connection`` and ``ApiError``) so it can be unit-tested
without booting the full HTTP handler.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Any

from server_app.core import ApiError, db_connection


logger = logging.getLogger("lvcodex.listening_feed")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# The canonical curated dataset that already ships with the repo. Tests
# can override the path with ``LVCODEX_LISTENING_FEED_PATH`` to point at
# a fixture file.
_DEFAULT_CLIPS_PATH = (
    Path(__file__).resolve().parents[2]
    / "latvian-listening-library"
    / "web"
    / "microClips.json"
)

# How many clips a single page returns when the caller does not specify
# a ``limit``. Picked to match the TikTok-style behaviour where the
# browser pre-fetches the next handful while the current clip plays.
DEFAULT_PAGE_SIZE = 6
MAX_PAGE_SIZE = 24

# XP values for correct vs incorrect answers. Aligned with T-034 (XP +
# streak engine) — a correct answer is one full unit, an incorrect
# answer still rewards engagement so the feed feels generous.
XP_CORRECT = 10
XP_INCORRECT = 2

_CACHE_LOCK = threading.Lock()
_CACHED_CLIPS: list[dict[str, Any]] | None = None
_CACHED_MTIME: float | None = None
_DDL_APPLIED = False


# ---------------------------------------------------------------------------
# Catalogue loading
# ---------------------------------------------------------------------------


def _clips_path() -> Path:
    override = os.environ.get("LVCODEX_LISTENING_FEED_PATH", "").strip()
    if override:
        return Path(override)
    return _DEFAULT_CLIPS_PATH


def _normalise_clip(raw: dict[str, Any], index: int) -> dict[str, Any] | None:
    """Project the raw microClips row into the feed wire shape."""

    if not isinstance(raw, dict):
        return None
    clip_id = str(raw.get("id") or "").strip()
    audio_url = str(raw.get("audio_url") or "").strip()
    options = raw.get("options")
    answer_index = raw.get("answer")
    if not clip_id or not audio_url or not isinstance(options, list):
        return None
    if not options or not all(isinstance(opt, str) for opt in options):
        return None
    try:
        correct_index = int(answer_index)
    except (TypeError, ValueError):
        return None
    if correct_index < 0 or correct_index >= len(options):
        return None
    transcript = str(raw.get("transcript") or "").strip()
    prompt = str(raw.get("prompt") or "Did you understand?").strip()
    # Make the wire payload conservative: never echo back the answer
    # index inside ``micro_quiz`` so the client cannot trivially cheat by
    # reading the network response.
    return {
        "id": clip_id,
        "index": index,
        "audio_url": audio_url,
        "title": str(raw.get("title") or "").strip() or None,
        "transcript": transcript,
        "translation": str(raw.get("translation") or "").strip() or None,
        "difficulty": str(raw.get("difficulty") or "").strip() or None,
        "category": str(raw.get("category") or "").strip() or None,
        "description": str(raw.get("description") or "").strip() or None,
        "duration_seconds": _safe_duration(raw),
        "micro_quiz": {
            "prompt": prompt,
            "prompt_lv": str(raw.get("prompt_lv") or "").strip() or None,
            "options": list(options),
            # We deliberately do NOT include the correct index — the
            # server is the only authority. The client can still grade
            # locally by issuing the POST /answer call.
        },
    }


def _safe_duration(raw: dict[str, Any]) -> int | None:
    start = raw.get("start")
    end = raw.get("end")
    try:
        if start is None or end is None:
            return None
        duration = int(end) - int(start)
    except (TypeError, ValueError):
        return None
    return duration if duration > 0 else None


def _load_clips_from_disk() -> list[dict[str, Any]]:
    path = _clips_path()
    try:
        raw_text = path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise ApiError(
            HTTPStatus.SERVICE_UNAVAILABLE,
            "listening_feed_unavailable",
            "The listening feed catalogue is missing on this server.",
            {"path": str(path)},
        ) from error
    try:
        rows = json.loads(raw_text)
    except json.JSONDecodeError as error:
        raise ApiError(
            HTTPStatus.SERVICE_UNAVAILABLE,
            "listening_feed_invalid",
            "The listening feed catalogue is not valid JSON.",
            {"path": str(path), "reason": str(error)},
        ) from error
    if not isinstance(rows, list):
        raise ApiError(
            HTTPStatus.SERVICE_UNAVAILABLE,
            "listening_feed_invalid",
            "The listening feed catalogue must be a JSON array.",
            {"path": str(path)},
        )
    clips: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        clip = _normalise_clip(row, index)
        if clip is not None:
            clips.append(clip)
    return clips


def load_clips(*, force: bool = False) -> list[dict[str, Any]]:
    """Return the cached clip catalogue, re-loading on file mtime change."""

    global _CACHED_CLIPS, _CACHED_MTIME
    path = _clips_path()
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError as error:
        raise ApiError(
            HTTPStatus.SERVICE_UNAVAILABLE,
            "listening_feed_unavailable",
            "The listening feed catalogue is missing on this server.",
            {"path": str(path)},
        ) from error
    with _CACHE_LOCK:
        if force or _CACHED_CLIPS is None or mtime != _CACHED_MTIME:
            _CACHED_CLIPS = _load_clips_from_disk()
            _CACHED_MTIME = mtime
        return list(_CACHED_CLIPS)


def _public_clip(clip: dict[str, Any]) -> dict[str, Any]:
    """Strip server-only fields before returning to the wire."""

    return {k: v for k, v in clip.items() if k != "index"}


def find_clip(clip_id: str) -> dict[str, Any] | None:
    if not clip_id:
        return None
    for clip in load_clips():
        if clip["id"] == clip_id:
            return clip
    return None


def correct_index_for(clip_id: str) -> int | None:
    """Read the raw clip JSON to find the canonical answer index.

    We keep the answer out of the cached public projection so the wire
    payload returned by :func:`build_listening_feed` cannot leak it. The
    answer lives in the on-disk catalogue and is looked up only when a
    learner submits an answer.
    """

    path = _clips_path()
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    if not isinstance(rows, list):
        return None
    for row in rows:
        if isinstance(row, dict) and str(row.get("id") or "") == clip_id:
            try:
                return int(row.get("answer"))
            except (TypeError, ValueError):
                return None
    return None


# ---------------------------------------------------------------------------
# Cursor encoding
# ---------------------------------------------------------------------------


def _encode_cursor(index: int) -> str:
    payload = json.dumps({"i": int(index)}, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str | None) -> int:
    if cursor is None or cursor == "":
        return 0
    try:
        padding = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(cursor + padding)
        data = json.loads(raw.decode("utf-8"))
        index = int(data.get("i", 0))
    except (ValueError, json.JSONDecodeError, TypeError):
        raise ApiError(
            HTTPStatus.BAD_REQUEST,
            "listening_feed_bad_cursor",
            "The pagination cursor is invalid.",
        )
    if index < 0:
        raise ApiError(
            HTTPStatus.BAD_REQUEST,
            "listening_feed_bad_cursor",
            "The pagination cursor is invalid.",
        )
    return index


# ---------------------------------------------------------------------------
# Feed builder
# ---------------------------------------------------------------------------


def build_listening_feed(
    *, cursor: str | None = None, limit: int | None = None
) -> dict[str, Any]:
    """Return the next page of clips starting at ``cursor``.

    The response shape is intentionally minimal so a fully static client
    can render it without a build step.
    """

    safe_limit = _clamp_limit(limit)
    start_index = _decode_cursor(cursor)
    clips = load_clips()
    if not clips:
        raise ApiError(
            HTTPStatus.SERVICE_UNAVAILABLE,
            "listening_feed_unavailable",
            "No listening feed clips are currently available.",
        )
    end_index = min(len(clips), start_index + safe_limit)
    page = clips[start_index:end_index]
    next_cursor = _encode_cursor(end_index) if end_index < len(clips) else None
    return {
        "clips": [_public_clip(clip) for clip in page],
        "next_cursor": next_cursor,
        "count": len(page),
        "total": len(clips),
    }


def _clamp_limit(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_PAGE_SIZE
    try:
        value = int(limit)
    except (TypeError, ValueError):
        return DEFAULT_PAGE_SIZE
    if value <= 0:
        return DEFAULT_PAGE_SIZE
    return min(MAX_PAGE_SIZE, value)


# ---------------------------------------------------------------------------
# Answer persistence
# ---------------------------------------------------------------------------


_DDL = """
CREATE TABLE IF NOT EXISTS listening_feed_answers (
    id TEXT PRIMARY KEY,
    account_id TEXT,
    clip_id TEXT NOT NULL,
    quiz_answer_index INTEGER NOT NULL,
    correct_index INTEGER NOT NULL,
    is_correct INTEGER NOT NULL,
    xp_delta INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_listening_feed_answers_account
    ON listening_feed_answers(account_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_listening_feed_answers_clip
    ON listening_feed_answers(clip_id, created_at DESC);
"""


def _ensure_answer_table(conn: sqlite3.Connection) -> None:
    """Create the persistence table on first use (idempotent)."""

    global _DDL_APPLIED
    if _DDL_APPLIED:
        return
    with _CACHE_LOCK:
        if _DDL_APPLIED:
            return
        conn.executescript(_DDL)
        _DDL_APPLIED = True


def _reset_ddl_cache_for_tests() -> None:
    """Drop the once-flag so tempfile DBs re-run the DDL in tests."""

    global _DDL_APPLIED
    with _CACHE_LOCK:
        _DDL_APPLIED = False


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def record_quiz_answer(
    clip_id: str,
    quiz_answer_index: int,
    *,
    account_id: str | None = None,
    conn_factory: Any | None = None,
) -> dict[str, Any]:
    """Score one quiz answer, persist it, and return the verdict.

    ``account_id`` may be ``None`` for anonymous learners — the row is
    still written so the analytics pipeline can derive engagement
    funnels. The XP delta in that case is informational only; the XP
    engine (T-034) only applies it to authenticated profiles.
    """

    if not isinstance(clip_id, str) or not clip_id.strip():
        raise ApiError(
            HTTPStatus.BAD_REQUEST,
            "listening_feed_bad_clip",
            "A valid clip_id is required.",
        )
    if not isinstance(quiz_answer_index, int):
        try:
            quiz_answer_index = int(quiz_answer_index)
        except (TypeError, ValueError) as error:
            raise ApiError(
                HTTPStatus.BAD_REQUEST,
                "listening_feed_bad_answer",
                "quiz_answer_index must be an integer.",
            ) from error
    if quiz_answer_index < 0:
        raise ApiError(
            HTTPStatus.BAD_REQUEST,
            "listening_feed_bad_answer",
            "quiz_answer_index must be non-negative.",
        )
    clip = find_clip(clip_id)
    if clip is None:
        raise ApiError(
            HTTPStatus.NOT_FOUND,
            "listening_feed_clip_not_found",
            "No such clip in the listening feed catalogue.",
            {"clip_id": clip_id},
        )
    options = clip["micro_quiz"]["options"]
    if quiz_answer_index >= len(options):
        raise ApiError(
            HTTPStatus.BAD_REQUEST,
            "listening_feed_bad_answer",
            "quiz_answer_index is out of range for this clip.",
            {"clip_id": clip_id, "options_count": len(options)},
        )
    correct_index = correct_index_for(clip_id)
    if correct_index is None:
        # Should not happen because find_clip already validated the
        # row, but guard defensively so callers get a clean 5xx instead
        # of a stack trace.
        raise ApiError(
            HTTPStatus.SERVICE_UNAVAILABLE,
            "listening_feed_unavailable",
            "The clip is missing a canonical answer index.",
        )
    is_correct = quiz_answer_index == correct_index
    xp_delta = XP_CORRECT if is_correct else XP_INCORRECT

    row_id = f"feed_ans_{uuid.uuid4().hex[:16]}"
    created_at = _utc_now_iso()
    factory = conn_factory or db_connection
    with factory() as conn:
        _ensure_answer_table(conn)
        conn.execute(
            """
            INSERT INTO listening_feed_answers
                (id, account_id, clip_id, quiz_answer_index, correct_index,
                 is_correct, xp_delta, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row_id,
                account_id,
                clip_id,
                int(quiz_answer_index),
                int(correct_index),
                1 if is_correct else 0,
                int(xp_delta),
                created_at,
            ),
        )
        conn.commit()

    logger.info(
        "listening_feed_answer clip_id=%s correct=%s account=%s xp=%s",
        clip_id,
        is_correct,
        account_id or "anonymous",
        xp_delta,
    )
    return {
        "id": row_id,
        "clip_id": clip_id,
        "answer_index": int(quiz_answer_index),
        "correct_index": int(correct_index),
        "correct": is_correct,
        "xp_delta": int(xp_delta),
        "created_at": created_at,
    }


__all__ = [
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "XP_CORRECT",
    "XP_INCORRECT",
    "build_listening_feed",
    "correct_index_for",
    "find_clip",
    "load_clips",
    "record_quiz_answer",
]
