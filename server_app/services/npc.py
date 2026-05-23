"""AI NPC roleplay service (T-045).

Loads NPC character profiles from ``content/npcs/*.json``, builds a
persona-flavoured prompt for Groq (``llama-3.3-70b-versatile``), and
persists multi-turn conversation history per learner so the user can
resume a roleplay across sessions.

The service deliberately reuses two pre-existing pieces of infrastructure
shipped by **T-026 (AI quota + schema validation)**:

* :func:`server_app.services.quota.reserve_daily_ai_quota` — daily request
  ceiling per (user_key, plan). The same ledger gates writing/speaking
  scoring (T-013) and now NPC turns. A 429 means the learner has burned
  their daily AI allowance across **all** features combined, which is the
  right shape for cost telemetry (T-027).
* :class:`server_app.models.ai.AICandidate` + the pydantic validation
  pattern — the NPC turn request/response shapes below use the same
  ``ConfigDict(extra='ignore', str_strip_whitespace=True)`` so the
  surface looks identical to the rest of the AI pipeline.

Conversation persistence
------------------------
Each (account_id, npc_id, conversation_id) tuple owns a row in the
``npc_conversations`` table and one row per turn in
``npc_conversation_turns``. The first POST to
``/api/npc/{npc_id}/turn`` without a ``conversation_id`` creates a new
conversation; subsequent posts append. Multi-user isolation is enforced
at the SQL layer: every read/write filters on ``account_id`` so user A
cannot ever read user B's conversation, even if they guess the id.

Groq call shape
---------------
The system prompt is rendered from the NPC JSON (persona + speech_style +
safety_rules); the messages array carries the last
``NPC_HISTORY_TURN_LIMIT`` turns to keep the prompt small and the cost
predictable. Token usage is returned so T-027's cost telemetry can record
it. We deliberately keep ``temperature=0.7`` (more creative than the
scoring evaluator's 0.2) because roleplay benefits from a little
variation, but cap ``max_completion_tokens`` at 320 so a runaway model
cannot inflate the bill.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from server_app.core import db_connection, provider_config  # noqa: F401
from server_app.services.quota import (
    QuotaExceededError,
    reserve_daily_ai_quota,
)


logger = logging.getLogger("lvcodex.npc")


# ---------------------------------------------------------------------------
# Constants + paths
# ---------------------------------------------------------------------------


ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_NPC_ROOT = ROOT / "content" / "npcs"
NPC_HISTORY_TURN_LIMIT = 12  # last N turns shipped to the LLM
NPC_MAX_USER_MESSAGE_CHARS = 800
NPC_MAX_NPC_REPLY_CHARS = 1_200
NPC_DEFAULT_TEMPERATURE = 0.7
NPC_DEFAULT_MAX_TOKENS = 320
NPC_GROQ_TIMEOUT_SECONDS = 30
_DDL_LOCK = threading.Lock()
_DDL_APPLIED = False


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class NPCError(Exception):
    """Base error for NPC service surface."""

    status_code = 400

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class NPCNotFound(NPCError):
    status_code = 404


class NPCInvalidRequest(NPCError):
    status_code = 400


class NPCProviderError(NPCError):
    status_code = 502


# ---------------------------------------------------------------------------
# Pydantic schemas (T-026 pattern)
# ---------------------------------------------------------------------------


class NPCTurnRequest(BaseModel):
    """Inbound body for ``POST /api/npc/{npc_id}/turn``."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    message: str = Field(..., min_length=1, max_length=NPC_MAX_USER_MESSAGE_CHARS)
    conversation_id: Optional[str] = Field(default=None, max_length=64)

    @field_validator("conversation_id")
    @classmethod
    def _normalize_conversation_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class NPCTurnState(BaseModel):
    """Snapshot returned alongside the reply so the frontend can re-render."""

    model_config = ConfigDict(extra="ignore")

    npc_id: str
    conversation_id: str
    turn_index: int = Field(ge=1)
    history_length: int = Field(ge=0)
    quota_used: int = Field(ge=0)
    quota_limit: int = Field(ge=0)
    quota_resets_at: str


class NPCTurnResponse(BaseModel):
    """Validated outbound body for the route + provider answer surface."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    reply: str = Field(..., min_length=1, max_length=NPC_MAX_NPC_REPLY_CHARS)
    state: NPCTurnState
    usage: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Character profile loader
# ---------------------------------------------------------------------------


def npc_root_dir() -> Path:
    """Resolve the directory that contains ``*.json`` NPC profiles.

    Honours ``LVCODEX_NPC_ROOT`` for tests so a tempdir can swap the live
    catalogue without touching the repo content.
    """

    override = os.getenv("LVCODEX_NPC_ROOT", "").strip()
    if override:
        return Path(override).resolve()
    return DEFAULT_NPC_ROOT


def list_npcs(root: Optional[Path] = None) -> list[dict[str, Any]]:
    """Return a list of NPC summary dicts (id, name, role, location).

    Used by the frontend selector. The summaries are small enough to ship
    inline so we don't need a separate per-NPC GET.
    """

    target = root or npc_root_dir()
    summaries: list[dict[str, Any]] = []
    if not target.exists():
        return summaries
    for path in sorted(target.glob("*.json")):
        try:
            profile = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            logger.warning("npc_profile_unreadable path=%s error=%s", path, error)
            continue
        npc_id = (profile.get("id") or path.stem).strip()
        if not npc_id:
            continue
        summaries.append(
            {
                "id": npc_id,
                "name": profile.get("name", npc_id),
                "role": profile.get("role", ""),
                "location": profile.get("location", ""),
                "language_level": profile.get("language_level", "A2"),
            }
        )
    return summaries


def load_npc(npc_id: str, *, root: Optional[Path] = None) -> dict[str, Any]:
    """Load a single NPC profile by id.

    Validates that the id matches ``[a-z0-9-]+`` to keep the filesystem
    lookup safe from traversal, then reads the JSON. Raises
    :class:`NPCNotFound` if the file is missing or empty.
    """

    cleaned = (npc_id or "").strip().lower()
    if not cleaned or not all(ch.isalnum() or ch == "-" for ch in cleaned):
        raise NPCNotFound(f"Unknown NPC id: {npc_id!r}")
    target_root = root or npc_root_dir()
    path = target_root / f"{cleaned}.json"
    if not path.exists():
        raise NPCNotFound(f"Unknown NPC id: {cleaned!r}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise NPCNotFound(f"NPC profile is unreadable: {cleaned!r}") from error
    if not isinstance(data, dict) or not data.get("name"):
        raise NPCNotFound(f"NPC profile is malformed: {cleaned!r}")
    data.setdefault("id", cleaned)
    return data


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def build_system_prompt(npc: dict[str, Any]) -> str:
    """Render the system prompt for the LLM from the NPC profile."""

    persona = (npc.get("persona") or "").strip()
    speech_style = (npc.get("speech_style") or "").strip()
    safety_rules = npc.get("safety_rules") or []
    common_scenarios = npc.get("common_scenarios") or []
    vocabulary = npc.get("vocabulary_focus") or []

    lines = [
        f"You are {npc.get('name', 'an NPC')}, a {npc.get('role', 'Latvian-speaking character')} "
        f"in {npc.get('location', 'Latvia')}. You are roleplaying with a learner of Latvian at "
        f"level {npc.get('language_level', 'A2')}.",
        "",
        "Persona:",
        persona or "(no extra persona description)",
        "",
        f"Speech style: {speech_style or 'simple, polite A2 Latvian.'}",
        "",
        "You must:",
        "- Always reply in Latvian.",
        "- Stay in character — never break the fourth wall.",
        "- Use sentences appropriate for an A2 learner (short, common vocabulary).",
        "- Keep replies to at most 3 short sentences.",
        "- If the learner writes in English, reply in Latvian and politely repeat the question slowly.",
    ]
    if vocabulary:
        lines.append(
            "- Prefer vocabulary related to your role: " + ", ".join(vocabulary) + "."
        )
    if common_scenarios:
        lines.append("")
        lines.append("Common scenarios you can steer toward:")
        for scenario in common_scenarios:
            lines.append(f"  * {scenario}")
    if safety_rules:
        lines.append("")
        lines.append("Hard safety rules:")
        for rule in safety_rules:
            lines.append(f"  - {rule}")
    lines.append("")
    lines.append(
        "Reply with plain text only — no JSON, no Markdown fences, no stage directions."
    )
    return "\n".join(lines)


def build_messages(
    npc: dict[str, Any],
    history: list[dict[str, str]],
    user_message: str,
) -> list[dict[str, str]]:
    """Compose the messages array sent to the LLM.

    ``history`` is the persisted dialog (role + content), capped to
    ``NPC_HISTORY_TURN_LIMIT`` most-recent turns. The freshly-supplied
    ``user_message`` is appended as the final ``user`` turn.
    """

    trimmed = history[-NPC_HISTORY_TURN_LIMIT:] if history else []
    messages: list[dict[str, str]] = [
        {"role": "system", "content": build_system_prompt(npc)},
    ]
    for turn in trimmed:
        role = turn.get("role")
        content = (turn.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message.strip()})
    return messages


# ---------------------------------------------------------------------------
# Conversation persistence
# ---------------------------------------------------------------------------


def _ensure_npc_tables(conn: sqlite3.Connection) -> None:
    """Create the NPC tables if missing. ANSI-compatible (Postgres-ready)."""

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS npc_conversations (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            npc_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            turn_count INTEGER NOT NULL DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_npc_conversations_account
            ON npc_conversations(account_id, npc_id);

        CREATE TABLE IF NOT EXISTS npc_conversation_turns (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            npc_id TEXT NOT NULL,
            turn_index INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_npc_turns_conversation
            ON npc_conversation_turns(conversation_id, turn_index);

        CREATE INDEX IF NOT EXISTS idx_npc_turns_account
            ON npc_conversation_turns(account_id);
        """
    )


def ensure_npc_tables_ready() -> None:
    """Idempotent top-level DDL initialiser.

    Cheap to call repeatedly; the once-flag guards against re-running the
    script on every request. Tests reset the flag via
    :func:`_reset_npc_ddl_cache`.
    """

    global _DDL_APPLIED
    if _DDL_APPLIED:
        return
    with _DDL_LOCK:
        if _DDL_APPLIED:
            return
        with db_connection() as conn:
            _ensure_npc_tables(conn)
        _DDL_APPLIED = True


def _reset_npc_ddl_cache() -> None:
    """Test hook — re-run the DDL for a fresh tempfile DB."""

    global _DDL_APPLIED
    with _DDL_LOCK:
        _DDL_APPLIED = False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def get_or_create_conversation(
    account_id: str,
    npc_id: str,
    conversation_id: Optional[str],
) -> dict[str, Any]:
    """Return the conversation row, creating one if no id was supplied.

    Enforces account-isolation: a ``conversation_id`` that belongs to a
    different account is treated as "not found" and a fresh conversation
    is created instead. This is the right shape for the multi-user
    isolation test — guessing another user's id never leaks data, it just
    falls through to a new conversation owned by the caller.
    """

    if not account_id:
        raise NPCInvalidRequest("account_id is required.")
    ensure_npc_tables_ready()
    with db_connection() as conn:
        _ensure_npc_tables(conn)
        if conversation_id:
            row = conn.execute(
                """
                SELECT id, account_id, npc_id, created_at, updated_at, turn_count
                FROM npc_conversations
                WHERE id = ? AND account_id = ? AND npc_id = ?
                """,
                (conversation_id, account_id, npc_id),
            ).fetchone()
            if row is not None:
                return dict(row)
        new_id = uuid.uuid4().hex
        now = _now_iso()
        conn.execute(
            """
            INSERT INTO npc_conversations (id, account_id, npc_id, created_at, updated_at, turn_count)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (new_id, account_id, npc_id, now, now),
        )
        conn.commit()
        return {
            "id": new_id,
            "account_id": account_id,
            "npc_id": npc_id,
            "created_at": now,
            "updated_at": now,
            "turn_count": 0,
        }


def load_history(account_id: str, conversation_id: str) -> list[dict[str, str]]:
    """Return all turns for ``conversation_id`` owned by ``account_id``.

    The account_id filter is the multi-user isolation guarantee — every
    read must include it. Returns an empty list if the conversation does
    not exist or belongs to another account.
    """

    ensure_npc_tables_ready()
    with db_connection() as conn:
        _ensure_npc_tables(conn)
        rows = conn.execute(
            """
            SELECT role, content, turn_index
            FROM npc_conversation_turns
            WHERE conversation_id = ? AND account_id = ?
            ORDER BY turn_index ASC
            """,
            (conversation_id, account_id),
        ).fetchall()
    return [{"role": row["role"], "content": row["content"]} for row in rows]


def append_turns(
    account_id: str,
    conversation: dict[str, Any],
    user_message: str,
    npc_reply: str,
) -> dict[str, Any]:
    """Persist the new user + assistant turns atomically.

    Returns the updated conversation row with ``turn_count`` bumped by two.
    """

    ensure_npc_tables_ready()
    now = _now_iso()
    next_index = int(conversation.get("turn_count", 0)) + 1
    with db_connection() as conn:
        _ensure_npc_tables(conn)
        conn.execute(
            """
            INSERT INTO npc_conversation_turns
                (id, conversation_id, account_id, npc_id, turn_index, role, content, created_at)
            VALUES (?, ?, ?, ?, ?, 'user', ?, ?)
            """,
            (
                uuid.uuid4().hex,
                conversation["id"],
                account_id,
                conversation["npc_id"],
                next_index,
                user_message.strip(),
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO npc_conversation_turns
                (id, conversation_id, account_id, npc_id, turn_index, role, content, created_at)
            VALUES (?, ?, ?, ?, ?, 'assistant', ?, ?)
            """,
            (
                uuid.uuid4().hex,
                conversation["id"],
                account_id,
                conversation["npc_id"],
                next_index + 1,
                npc_reply.strip(),
                now,
            ),
        )
        conn.execute(
            """
            UPDATE npc_conversations
            SET turn_count = ?, updated_at = ?
            WHERE id = ? AND account_id = ?
            """,
            (next_index + 1, now, conversation["id"], account_id),
        )
        conn.commit()
    updated = dict(conversation)
    updated["turn_count"] = next_index + 1
    updated["updated_at"] = now
    return updated


# ---------------------------------------------------------------------------
# Groq call
# ---------------------------------------------------------------------------


def call_groq_chat(
    messages: list[dict[str, str]],
    *,
    model: Optional[str] = None,
    temperature: float = NPC_DEFAULT_TEMPERATURE,
    max_tokens: int = NPC_DEFAULT_MAX_TOKENS,
    config: Optional[dict[str, Any]] = None,
    transport: Optional[Callable[[urllib.request.Request, float], dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Call the Groq chat-completions endpoint and return the parsed JSON.

    ``transport`` is injected by tests to bypass the network. When omitted,
    a small wrapper around :func:`urllib.request.urlopen` is used.
    """

    if config is not None:
        cfg = config
    elif transport is not None:
        # Test path — we don't need real credentials when the transport is
        # mocked, so use a synthetic config. This keeps unit tests fast and
        # decoupled from the real Groq environment.
        cfg = {
            "provider": "groq",
            "api_key": os.getenv("GROQ_API_KEY", "test-key"),
            "model": os.getenv("LLM_MODEL", os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")),
            "base_url": os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
        }
    else:
        cfg = provider_config()
    if cfg.get("provider", "").lower() != "groq":
        raise NPCProviderError(
            f"NPC service only supports the Groq provider (configured: {cfg.get('provider')!r}).",
            status_code=503,
        )
    payload = {
        "model": model or cfg["model"],
        "messages": messages,
        "temperature": temperature,
        "top_p": 1,
        "max_completion_tokens": max_tokens,
    }
    request = urllib.request.Request(
        f"{cfg['base_url']}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {cfg['api_key']}",
            "Content-Type": "application/json",
            "User-Agent": "lvcodex-npc/1.0",
        },
        method="POST",
    )

    if transport is None:
        transport = _default_transport

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            result = transport(request, float(NPC_GROQ_TIMEOUT_SECONDS))
            choices = result.get("choices") or []
            if not choices:
                raise NPCProviderError("Groq returned no choices.", status_code=502)
            content = (choices[0].get("message") or {}).get("content") or ""
            return {
                "content": content.strip(),
                "usage": result.get("usage", {}),
                "model": result.get("model", cfg["model"]),
            }
        except urllib.error.HTTPError as error:
            last_error = error
            if error.code not in {429, 500, 502, 503, 504} or attempt == 2:
                raise NPCProviderError(
                    f"Groq HTTP {error.code}: {error.reason}", status_code=502
                ) from error
            time.sleep(min(2 ** attempt, 4))
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as error:
            last_error = error
            if attempt == 2:
                raise NPCProviderError(
                    f"Groq transport error: {error}", status_code=502
                ) from error
            time.sleep(min(2 ** attempt, 4))

    # Defensive — the loop above always either returns or raises.
    assert last_error is not None  # noqa: S101
    raise NPCProviderError(str(last_error), status_code=502)


def _default_transport(request: urllib.request.Request, timeout: float) -> dict[str, Any]:
    """Production transport for :func:`call_groq_chat`. Excluded from tests."""

    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# High-level turn handler
# ---------------------------------------------------------------------------


def parse_turn_request(raw: Any) -> NPCTurnRequest:
    """Pydantic-validate the inbound body.

    Raises :class:`NPCInvalidRequest` (400) on validation failure so the
    HTTP layer renders the error consistently with the rest of the AI
    surface (T-026 ``parse_ai_score_request`` analogue).
    """

    try:
        return NPCTurnRequest.model_validate(raw)
    except ValidationError as error:
        raise NPCInvalidRequest(
            "NPC turn request payload failed schema validation: " + str(error.errors())
        ) from error


def generate_turn(
    *,
    account_id: str,
    plan: str,
    npc_id: str,
    raw_body: Any,
    npc_root: Optional[Path] = None,
    transport: Optional[Callable[[urllib.request.Request, float], dict[str, Any]]] = None,
    quota_user_key: Optional[str] = None,
) -> NPCTurnResponse:
    """End-to-end handler: validate, reserve quota, call LLM, persist.

    The function is structured so the route handler stays a thin shell —
    everything testable lives here. ``transport`` allows tests to mock the
    Groq HTTP call without touching ``urllib.urlopen``.
    """

    npc = load_npc(npc_id, root=npc_root)
    request = parse_turn_request(raw_body)
    user_key = (quota_user_key or account_id or "").strip()
    if not user_key:
        raise NPCInvalidRequest("Cannot reserve quota: missing user identity.")

    # T-026 quota — raises QuotaExceededError (429) if the learner is over
    # their daily AI ceiling. The release-on-failure pattern from the
    # scoring evaluator is appropriate here too: if the Groq call fails
    # we refund the slot so a flaky provider doesn't burn the quota.
    quota_snapshot = reserve_daily_ai_quota(user_key, plan)

    try:
        conversation = get_or_create_conversation(
            account_id, npc["id"], request.conversation_id
        )
        history = load_history(account_id, conversation["id"])
        messages = build_messages(npc, history, request.message)
        provider_result = call_groq_chat(messages, transport=transport)
        reply_text = provider_result["content"]
        if not reply_text:
            raise NPCProviderError("Groq returned an empty reply.", status_code=502)
        # Hard cap on reply length so the schema-validation step doesn't
        # reject a long-but-otherwise-good response.
        if len(reply_text) > NPC_MAX_NPC_REPLY_CHARS:
            reply_text = reply_text[:NPC_MAX_NPC_REPLY_CHARS]
        conversation = append_turns(account_id, conversation, request.message, reply_text)
    except Exception:
        # Refund the daily quota slot — same pattern as the evaluator.
        try:
            from server_app.services.quota import AIQuotaLedger

            AIQuotaLedger().release(user_key, plan)
        except Exception:  # noqa: BLE001 — defensive; refund must never re-raise
            logger.exception("npc_quota_refund_failed user=%s", user_key)
        raise

    state = NPCTurnState(
        npc_id=npc["id"],
        conversation_id=conversation["id"],
        turn_index=int(conversation["turn_count"]),
        history_length=int(conversation["turn_count"]),
        quota_used=int(quota_snapshot["used"]),
        quota_limit=int(quota_snapshot["limit"]),
        quota_resets_at=str(quota_snapshot["resets_at"]),
    )
    response = NPCTurnResponse(
        reply=reply_text,
        state=state,
        usage=dict(provider_result.get("usage") or {}),
    )
    logger.info(
        "npc_turn npc=%s account=%s conversation=%s turn=%s",
        npc["id"],
        account_id,
        conversation["id"],
        state.turn_index,
    )
    return response


__all__ = [
    "DEFAULT_NPC_ROOT",
    "NPC_DEFAULT_MAX_TOKENS",
    "NPC_DEFAULT_TEMPERATURE",
    "NPC_HISTORY_TURN_LIMIT",
    "NPC_MAX_NPC_REPLY_CHARS",
    "NPC_MAX_USER_MESSAGE_CHARS",
    "NPCError",
    "NPCInvalidRequest",
    "NPCNotFound",
    "NPCProviderError",
    "NPCTurnRequest",
    "NPCTurnResponse",
    "NPCTurnState",
    "QuotaExceededError",
    "append_turns",
    "build_messages",
    "build_system_prompt",
    "call_groq_chat",
    "ensure_npc_tables_ready",
    "generate_turn",
    "get_or_create_conversation",
    "list_npcs",
    "load_history",
    "load_npc",
    "npc_root_dir",
    "parse_turn_request",
]
