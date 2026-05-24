"""T-053 — AI tutor companion with persistent memory.

The companion is a persistent, single-NPC chat surface that follows the
learner across sessions. Unlike T-045 NPC roleplay (a different character
per scenario, per-conversation history that resets when the learner
switches NPCs), the companion is **one** tutor with **one** rolling
memory blob per learner. The memory is a free-form summary text capped
at 2 KB so the prompt cost stays bounded as the relationship grows.

Why a separate service?
-----------------------

T-045 ``server_app.services.npc`` already owns the Groq plumbing,
quota reservation, and pydantic envelope shapes. Rather than duplicate
that, the companion service:

1. Loads a persona-flavoured system prompt that fronts the **companion**
   (not a roleplay NPC — the companion knows it is an AI tutor and is
   allowed to break character to coach the learner).
2. Reads/writes a single :data:`companion_memory` row per ``user_id``.
3. Builds the LLM messages array as ``[system, memory-as-context, user]``
   and reuses :func:`server_app.services.npc.call_groq_chat` for the
   actual HTTP request so the retry / 429 / model-config code stays in
   one place.
4. After a successful reply, updates the memory summary by appending a
   short fingerprint of the latest exchange and truncating from the
   **front** so the row stays ≤ :data:`COMPANION_MEMORY_BYTE_BUDGET`.

Daily nudges
------------

:func:`compute_daily_nudge` reads the learner's recent activity
patterns (streak, last_active_at, missions_completed) and returns a
short Latvian nudge message. This is intentionally rules-based (no LLM
round-trip) so it can be cheaply rendered server-side on every dashboard
load — the nudge endpoint is a synchronous data-shape, not an AI call.

Tables
------

``companion_memory`` (one row per user)::

    user_id              TEXT PRIMARY KEY
    summary              TEXT NOT NULL DEFAULT ''
    last_updated         TEXT NOT NULL
    conversation_count   INTEGER NOT NULL DEFAULT 0

The full conversation history is **not** persisted (a deliberate design
choice — the companion's memory is the rolling summary, not a verbatim
log). Tests in ``tests/server/test_companion.py`` exercise the
persistence, truncation, and daily-nudge logic.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional
import urllib.request

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from server_app.core import db_connection
from server_app.services.npc import (
    NPCProviderError,
    call_groq_chat,
)
from server_app.services.quota import (
    AIQuotaLedger,
    QuotaExceededError,
    reserve_daily_ai_quota,
)


logger = logging.getLogger("lvcodex.companion")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


# 2 KB hard cap on the persisted memory summary. The spec demands ≤ 2 KB;
# we use bytes (UTF-8) not chars so Latvian diacritics don't accidentally
# inflate the row beyond what the prompt budget can absorb.
COMPANION_MEMORY_BYTE_BUDGET = 2048

COMPANION_MAX_USER_MESSAGE_CHARS = 1_000
COMPANION_MAX_REPLY_CHARS = 1_200
COMPANION_HISTORY_HINT_CHARS = 600  # max chars from the latest exchange we splice into memory
COMPANION_DEFAULT_TEMPERATURE = 0.6
COMPANION_DEFAULT_MAX_TOKENS = 320

# Nudge thresholds (hours / days). These are intentionally easy to
# reason about because the dashboard renders them verbatim.
NUDGE_GAP_HOURS_GENTLE = 24
NUDGE_GAP_HOURS_STRONG = 48
NUDGE_STREAK_CELEBRATION_DAYS = 7

_DDL_LOCK = threading.Lock()
_DDL_APPLIED = False


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class CompanionChatRequest(BaseModel):
    """Inbound body for ``POST /api/companion/chat``."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    message: str = Field(..., min_length=1, max_length=COMPANION_MAX_USER_MESSAGE_CHARS)

    @field_validator("message")
    @classmethod
    def _strip_message(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("message must not be blank")
        return cleaned


class CompanionMemorySnapshot(BaseModel):
    """Persisted memory state returned with every reply so the UI can render."""

    model_config = ConfigDict(extra="ignore")

    user_id: str
    summary: str
    last_updated: str
    conversation_count: int = Field(ge=0)
    summary_bytes: int = Field(ge=0)
    summary_budget_bytes: int = Field(ge=1)


class CompanionChatResponse(BaseModel):
    """Validated outbound body for the route."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    reply: str = Field(..., min_length=1, max_length=COMPANION_MAX_REPLY_CHARS)
    memory: CompanionMemorySnapshot
    quota: dict[str, Any] = Field(default_factory=dict)
    usage: dict[str, Any] = Field(default_factory=dict)


class CompanionNudge(BaseModel):
    """Daily nudge payload — rules-based, no LLM call."""

    model_config = ConfigDict(extra="ignore")

    kind: str  # see NUDGE_KIND_* constants below
    message_lv: str
    message_en: str
    severity: str  # "info" | "warn" | "celebrate"
    last_active_at: Optional[str] = None
    current_streak_days: int = Field(default=0, ge=0)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class CompanionError(Exception):
    """Base class for companion-service errors."""

    status_code = 400

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class CompanionInvalidRequest(CompanionError):
    status_code = 400


class CompanionProviderError(CompanionError):
    status_code = 502


# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------


def _ensure_companion_table(conn: sqlite3.Connection) -> None:
    """Create the ``companion_memory`` table if missing.

    ANSI-compatible DDL — the same script runs on Postgres after T-021.
    """

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS companion_memory (
            user_id TEXT PRIMARY KEY,
            summary TEXT NOT NULL DEFAULT '',
            last_updated TEXT NOT NULL,
            conversation_count INTEGER NOT NULL DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_companion_memory_updated
            ON companion_memory(last_updated);
        """
    )


def ensure_companion_tables_ready() -> None:
    """Idempotent DDL initialiser. Cheap to call repeatedly."""

    global _DDL_APPLIED
    if _DDL_APPLIED:
        return
    with _DDL_LOCK:
        if _DDL_APPLIED:
            return
        with db_connection() as conn:
            _ensure_companion_table(conn)
        _DDL_APPLIED = True


def _reset_companion_ddl_cache() -> None:
    """Test hook — re-run the DDL for a fresh tempfile DB."""

    global _DDL_APPLIED
    with _DDL_LOCK:
        _DDL_APPLIED = False


def _now_iso(now: Optional[datetime] = None) -> str:
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Memory persistence
# ---------------------------------------------------------------------------


def load_memory(user_id: str) -> dict[str, Any]:
    """Return the memory row for ``user_id``, defaulting to an empty row.

    The companion only ever reads/writes the caller's own row, so the
    multi-user isolation guarantee is encoded in the primary key (the
    learner's ``user_id``). Tests verify that two distinct user_ids never
    share state.
    """

    if not user_id:
        raise CompanionInvalidRequest("user_id is required.")
    ensure_companion_tables_ready()
    with db_connection() as conn:
        _ensure_companion_table(conn)
        row = conn.execute(
            """
            SELECT user_id, summary, last_updated, conversation_count
            FROM companion_memory
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
    if row is None:
        return {
            "user_id": user_id,
            "summary": "",
            "last_updated": "",
            "conversation_count": 0,
        }
    return {
        "user_id": row["user_id"],
        "summary": row["summary"] or "",
        "last_updated": row["last_updated"] or "",
        "conversation_count": int(row["conversation_count"] or 0),
    }


def truncate_summary(summary: str, *, budget_bytes: int = COMPANION_MEMORY_BYTE_BUDGET) -> str:
    """Trim ``summary`` to fit within ``budget_bytes`` UTF-8 bytes.

    The truncation is **front-biased** — we drop the oldest characters
    because the most recent context is the most useful to the model. A
    short leading marker ``"…"`` is kept so the prompt reads naturally.

    Tested by ``CompanionMemoryTruncationTests`` — the assertion is on
    the byte length of the returned string, not the char count.
    """

    if budget_bytes <= 0:
        raise ValueError("budget_bytes must be positive")
    if not summary:
        return ""
    encoded = summary.encode("utf-8")
    if len(encoded) <= budget_bytes:
        return summary
    # Drop from the front, leave a single-char ellipsis marker. The
    # marker itself is 3 bytes (UTF-8 "…") so we reserve that headroom.
    marker = "…"
    marker_bytes = marker.encode("utf-8")
    keep_bytes = budget_bytes - len(marker_bytes)
    if keep_bytes <= 0:
        return marker[:1]  # absurdly small budget — return one char
    tail = encoded[-keep_bytes:]
    # Walk forward to a valid UTF-8 boundary so we don't slice mid-codepoint.
    for offset in range(min(4, len(tail))):
        try:
            decoded = tail[offset:].decode("utf-8")
            return marker + decoded
        except UnicodeDecodeError:
            continue
    # Fallback — empty tail
    return marker


def _append_exchange_to_summary(
    summary: str,
    user_message: str,
    assistant_reply: str,
    *,
    now_iso_value: str,
) -> str:
    """Return the new summary text after appending the latest exchange.

    The format is a tiny YAML-ish trace so the model can read its own
    notes back as plain Latvian/English text without parsing a structure.
    We keep the exchange fingerprint short (each side capped at
    ``COMPANION_HISTORY_HINT_CHARS`` characters) so a single chatty turn
    can't blow the budget.
    """

    user_blurb = (user_message or "").strip().replace("\n", " ")
    assistant_blurb = (assistant_reply or "").strip().replace("\n", " ")
    if len(user_blurb) > COMPANION_HISTORY_HINT_CHARS:
        user_blurb = user_blurb[:COMPANION_HISTORY_HINT_CHARS] + "…"
    if len(assistant_blurb) > COMPANION_HISTORY_HINT_CHARS:
        assistant_blurb = assistant_blurb[:COMPANION_HISTORY_HINT_CHARS] + "…"
    entry = (
        f"[{now_iso_value}]\n"
        f"  learner: {user_blurb}\n"
        f"  tutor: {assistant_blurb}\n"
    )
    if not summary:
        combined = entry
    else:
        combined = summary.rstrip() + "\n" + entry
    return truncate_summary(combined)


def update_memory(
    user_id: str,
    user_message: str,
    assistant_reply: str,
    *,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Persist the new memory state after a successful exchange.

    Returns the updated row in the same shape as :func:`load_memory`.
    Idempotent at the SQL layer via ``ON CONFLICT(user_id)`` — repeated
    calls for the same user_id always succeed and never duplicate rows.
    """

    if not user_id:
        raise CompanionInvalidRequest("user_id is required.")
    ensure_companion_tables_ready()
    current = load_memory(user_id)
    now_iso_value = _now_iso(now)
    new_summary = _append_exchange_to_summary(
        current["summary"], user_message, assistant_reply, now_iso_value=now_iso_value
    )
    new_count = int(current["conversation_count"]) + 1
    with db_connection() as conn:
        _ensure_companion_table(conn)
        conn.execute(
            """
            INSERT INTO companion_memory (user_id, summary, last_updated, conversation_count)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE
                SET summary = excluded.summary,
                    last_updated = excluded.last_updated,
                    conversation_count = excluded.conversation_count
            """,
            (user_id, new_summary, now_iso_value, new_count),
        )
        conn.commit()
    return {
        "user_id": user_id,
        "summary": new_summary,
        "last_updated": now_iso_value,
        "conversation_count": new_count,
    }


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


COMPANION_SYSTEM_PROMPT = (
    "You are Anete, a friendly Latvian language tutor for an A2 learner. "
    "You remember previous conversations with this learner via the memory "
    "summary below. Your job is to encourage daily practice, explain grammar "
    "in plain English when asked, and reply in simple Latvian otherwise. "
    "Keep replies to at most 3 short sentences. Never invent facts about "
    "the learner that are not in the memory summary. If the learner asks "
    "for help, switch to English explanations. Be warm but concise — you "
    "are a tutor, not a therapist."
)


def build_messages(
    memory_summary: str,
    user_message: str,
) -> list[dict[str, str]]:
    """Compose the messages array for the LLM call.

    Memory is injected as a separate ``system`` message so the model sees
    a clean ``[persona, memory, user]`` chain. An empty memory becomes a
    single placeholder line so the prompt shape is always identical
    (which keeps token usage predictable for cost telemetry).
    """

    memory_block = memory_summary.strip() or "(no memory yet — this is your first chat with this learner)"
    return [
        {"role": "system", "content": COMPANION_SYSTEM_PROMPT},
        {
            "role": "system",
            "content": "Memory of past conversations with this learner:\n" + memory_block,
        },
        {"role": "user", "content": user_message.strip()},
    ]


# ---------------------------------------------------------------------------
# Daily nudge
# ---------------------------------------------------------------------------


NUDGE_KIND_WELCOME = "welcome"
NUDGE_KIND_KEEP_STREAK = "keep_streak"
NUDGE_KIND_RETURN_GENTLE = "return_gentle"
NUDGE_KIND_RETURN_STRONG = "return_strong"
NUDGE_KIND_CELEBRATE_STREAK = "celebrate_streak"


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def compute_daily_nudge(
    *,
    last_active_at: Optional[str],
    current_streak_days: int = 0,
    now: Optional[datetime] = None,
) -> CompanionNudge:
    """Return a daily nudge based on the learner's recent pattern.

    Rules (in priority order — first match wins):

    1. **Welcome** — never been active: nudge them to say hello.
    2. **Celebrate streak** — current streak ≥ 7 days: celebrate it.
    3. **Return strong** — gap ≥ 48 h since last activity: urgent nudge.
    4. **Return gentle** — gap ≥ 24 h since last activity: gentle nudge.
    5. **Keep streak** — active today, streak ≥ 1: light "keep it up" line.

    Tested in ``CompanionDailyNudgeTests`` — each branch has at least one
    test that pins both the ``kind`` and the ``severity``.
    """

    streak = max(0, int(current_streak_days or 0))
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    last_active = _parse_iso(last_active_at)

    if last_active is None:
        return CompanionNudge(
            kind=NUDGE_KIND_WELCOME,
            severity="info",
            message_lv="Sveiks! Es esmu Anete. Pasaki “Labdien!”, lai sāktu mūsu pirmo sarunu.",
            message_en="Hi! I'm Anete. Say hello to start our first chat in Latvian.",
            last_active_at=None,
            current_streak_days=0,
        )

    last_active_iso = last_active.isoformat().replace("+00:00", "Z")

    if streak >= NUDGE_STREAK_CELEBRATION_DAYS:
        return CompanionNudge(
            kind=NUDGE_KIND_CELEBRATE_STREAK,
            severity="celebrate",
            message_lv=f"Lieliski! Tava sērija ir {streak} dienas. Turpini tāpat — viens pielietojums šodien?",
            message_en=f"Amazing — a {streak}-day streak. Keep it going with one short chat today.",
            last_active_at=last_active_iso,
            current_streak_days=streak,
        )

    gap = instant - last_active
    gap_hours = gap.total_seconds() / 3600.0

    if gap_hours >= NUDGE_GAP_HOURS_STRONG:
        return CompanionNudge(
            kind=NUDGE_KIND_RETURN_STRONG,
            severity="warn",
            message_lv="Mēs sen neesam runājuši! Atgriezies uz piecām minūtēm — pat viens teikums skaitās.",
            message_en="It's been a while — come back for just five minutes. Even one sentence counts.",
            last_active_at=last_active_iso,
            current_streak_days=streak,
        )

    if gap_hours >= NUDGE_GAP_HOURS_GENTLE:
        return CompanionNudge(
            kind=NUDGE_KIND_RETURN_GENTLE,
            severity="info",
            message_lv="Vai vēlies šodien parunāties latviski? Es esmu šeit, kad esi gatavs(-a).",
            message_en="Want to practise Latvian today? I'm here whenever you're ready.",
            last_active_at=last_active_iso,
            current_streak_days=streak,
        )

    return CompanionNudge(
        kind=NUDGE_KIND_KEEP_STREAK,
        severity="info",
        message_lv="Tu jau šodien biji aktīvs(-a). Turpini! Vēl viens īss vingrinājums?",
        message_en="You've already practised today. Nice! One more short drill?",
        last_active_at=last_active_iso,
        current_streak_days=streak,
    )


# ---------------------------------------------------------------------------
# Request parsing
# ---------------------------------------------------------------------------


def parse_chat_request(raw: Any) -> CompanionChatRequest:
    """Pydantic-validate the inbound chat body."""

    try:
        return CompanionChatRequest.model_validate(raw)
    except ValidationError as error:
        raise CompanionInvalidRequest(
            "Companion chat request payload failed schema validation: "
            + str(error.errors())
        ) from error


# ---------------------------------------------------------------------------
# High-level chat handler
# ---------------------------------------------------------------------------


def generate_chat_reply(
    *,
    account_id: str,
    plan: str,
    raw_body: Any,
    transport: Optional[Callable[[urllib.request.Request, float], dict[str, Any]]] = None,
    quota_user_key: Optional[str] = None,
    now: Optional[datetime] = None,
) -> CompanionChatResponse:
    """End-to-end: validate, reserve quota, call LLM, persist memory.

    Mirrors the shape of :func:`server_app.services.npc.generate_turn` so
    the route handler stays a thin shell. ``transport`` is injected by
    tests to bypass the real Groq HTTP call.

    On provider failure, the daily quota slot is refunded (same pattern
    as T-045 / T-026) so the learner is not punished for a flaky upstream.
    """

    request = parse_chat_request(raw_body)
    user_key = (quota_user_key or account_id or "").strip()
    if not user_key:
        raise CompanionInvalidRequest("Cannot reserve quota: missing user identity.")

    quota_snapshot = reserve_daily_ai_quota(user_key, plan)

    try:
        memory = load_memory(account_id)
        messages = build_messages(memory["summary"], request.message)
        try:
            provider_result = call_groq_chat(
                messages,
                temperature=COMPANION_DEFAULT_TEMPERATURE,
                max_tokens=COMPANION_DEFAULT_MAX_TOKENS,
                transport=transport,
            )
        except NPCProviderError as error:
            # Translate to the companion namespace so the route can match
            # one error hierarchy.
            raise CompanionProviderError(str(error), status_code=error.status_code) from error
        reply_text = (provider_result.get("content") or "").strip()
        if not reply_text:
            raise CompanionProviderError("Groq returned an empty reply.", status_code=502)
        if len(reply_text) > COMPANION_MAX_REPLY_CHARS:
            reply_text = reply_text[:COMPANION_MAX_REPLY_CHARS]
        updated_memory = update_memory(
            account_id,
            request.message,
            reply_text,
            now=now,
        )
    except Exception:
        # Refund the daily quota slot — same pattern as the scoring evaluator
        # and the NPC service. The refund must never re-raise.
        try:
            AIQuotaLedger().release(user_key, plan)
        except Exception:  # noqa: BLE001 — defensive
            logger.exception("companion_quota_refund_failed user=%s", user_key)
        raise

    snapshot = CompanionMemorySnapshot(
        user_id=updated_memory["user_id"],
        summary=updated_memory["summary"],
        last_updated=updated_memory["last_updated"],
        conversation_count=updated_memory["conversation_count"],
        summary_bytes=len(updated_memory["summary"].encode("utf-8")),
        summary_budget_bytes=COMPANION_MEMORY_BYTE_BUDGET,
    )
    response = CompanionChatResponse(
        reply=reply_text,
        memory=snapshot,
        quota={
            "used": int(quota_snapshot["used"]),
            "limit": int(quota_snapshot["limit"]),
            "resets_at": str(quota_snapshot["resets_at"]),
        },
        usage=dict(provider_result.get("usage") or {}),
    )
    logger.info(
        "companion_chat user=%s conversation_count=%s summary_bytes=%s",
        account_id,
        snapshot.conversation_count,
        snapshot.summary_bytes,
    )
    return response


# ---------------------------------------------------------------------------
# Nudge helper backed by XP streak + last activity
# ---------------------------------------------------------------------------


def nudge_for_account(
    account_id: str,
    *,
    now: Optional[datetime] = None,
) -> CompanionNudge:
    """Return the daily nudge for ``account_id``.

    Reads:
        * ``user_streaks.current_days`` / ``user_streaks.last_active_at``
          (T-034) when present
        * ``companion_memory.last_updated`` as a fallback "last activity"
          signal so the nudge still works for learners who have only ever
          chatted with the companion (no XP awards yet).

    Gracefully degrades to the welcome nudge when neither signal is
    available — i.e. brand-new learners always see a friendly hello.
    """

    if not account_id:
        return compute_daily_nudge(last_active_at=None, current_streak_days=0, now=now)

    last_active_at: Optional[str] = None
    streak_days: int = 0
    ensure_companion_tables_ready()
    with db_connection() as conn:
        _ensure_companion_table(conn)
        # XP streak (best signal — set by award_xp on any activity).
        try:
            row = conn.execute(
                """
                SELECT current_days, last_active_at FROM user_streaks
                WHERE account_id = ?
                """,
                (account_id,),
            ).fetchone()
            if row is not None:
                streak_days = int(row["current_days"] or 0)
                last_active_at = (row["last_active_at"] or "") or None
        except sqlite3.OperationalError:
            # user_streaks table not yet created (early environments)
            pass
        # Companion memory fallback.
        if not last_active_at:
            row = conn.execute(
                """
                SELECT last_updated FROM companion_memory
                WHERE user_id = ?
                """,
                (account_id,),
            ).fetchone()
            if row is not None:
                last_active_at = (row["last_updated"] or "") or None
    return compute_daily_nudge(
        last_active_at=last_active_at,
        current_streak_days=streak_days,
        now=now,
    )


__all__ = [
    "COMPANION_DEFAULT_MAX_TOKENS",
    "COMPANION_DEFAULT_TEMPERATURE",
    "COMPANION_HISTORY_HINT_CHARS",
    "COMPANION_MAX_REPLY_CHARS",
    "COMPANION_MAX_USER_MESSAGE_CHARS",
    "COMPANION_MEMORY_BYTE_BUDGET",
    "COMPANION_SYSTEM_PROMPT",
    "CompanionChatRequest",
    "CompanionChatResponse",
    "CompanionError",
    "CompanionInvalidRequest",
    "CompanionMemorySnapshot",
    "CompanionNudge",
    "CompanionProviderError",
    "NUDGE_GAP_HOURS_GENTLE",
    "NUDGE_GAP_HOURS_STRONG",
    "NUDGE_KIND_CELEBRATE_STREAK",
    "NUDGE_KIND_KEEP_STREAK",
    "NUDGE_KIND_RETURN_GENTLE",
    "NUDGE_KIND_RETURN_STRONG",
    "NUDGE_KIND_WELCOME",
    "NUDGE_STREAK_CELEBRATION_DAYS",
    "QuotaExceededError",
    "build_messages",
    "compute_daily_nudge",
    "ensure_companion_tables_ready",
    "generate_chat_reply",
    "load_memory",
    "nudge_for_account",
    "parse_chat_request",
    "truncate_summary",
    "update_memory",
]
