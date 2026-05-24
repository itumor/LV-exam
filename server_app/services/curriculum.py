"""T-054 — AI curriculum generator.

Generates a short, personalised Latvian-A2 micro-lesson for a learner who
is weak in a specific skill (``listening`` / ``reading`` / ``writing`` /
``speaking``). The lesson is produced by a single Groq chat-completion
call and then **cached** in the ``curriculum_lessons`` table for a TTL
window so a repeat ``POST /api/curriculum/generate`` with the same
``(account_id, weak_skill)`` pair within the TTL returns the same lesson
without burning another Groq round-trip.

Why caching matters
-------------------

The lesson is deterministic for the lifetime of a cache row: every call
hashes ``(account_id, weak_skill, srs_seed)`` into a ``cache_key`` and
stores the resulting JSON content under that key. The cache TTL is 24 h
by default — well below the natural cadence at which a learner's
readiness signature drifts. If the learner's SRS deck changes
substantially (newly added cards on the same lemma) the ``srs_seed``
ingredient of the cache key shifts, so a fresh lesson is generated
automatically. Tests pin both branches.

Inputs the generator considers
------------------------------

1. **T-030 readiness** — the per-skill rolled-up avg (so the prompt can
   say "you are at 7.4/15, aim for 9").
2. **T-032 SRS deck** — the learner's currently-due vocabulary cards
   for the target skill. We pull up to ``LESSON_SRS_SEED_LIMIT`` lemmas
   and splice them into the prompt so the lesson reuses words the
   learner is already practising. This is the single biggest signal that
   makes the lesson feel "personal".
3. **Weak skill** — either passed in by the caller or auto-derived as
   the worst-badge skill from the readiness payload. The auto-derivation
   means the route handler does not need to know the readiness shape.

Output shape (JSON returned to the client)
------------------------------------------

.. code-block:: json

    {
      "lesson_id": "lsn_…",
      "account_id": "acct_…",
      "weak_skill": "listening",
      "cached": false,
      "expires_at": "2026-05-25T08:00:00Z",
      "content": {
         "title": "Sarunas slimnīcā",
         "objective": "Saprast pacienta sūdzības par sāpēm.",
         "vocab": [{"lv": "sāpes", "en": "pain"}, ...],
         "drills": [
            {"prompt_lv": "...", "prompt_en": "...", "answer_lv": "...", "rationale_en": "..."},
            ...
         ],
         "reflection_prompt_en": "Why did this drill feel hardest?"
      },
      "quota": {"used": 1, "limit": 50, "resets_at": "..."},
      "usage": {"prompt_tokens": ..., "completion_tokens": ...}
    }

The :data:`content` schema is the contract the frontend depends on, so
the Pydantic shape (:class:`LessonContent`) lives in this module — a
malformed Groq reply is rejected at the service boundary, never reaches
the route handler.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import threading
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from server_app.core import db_connection
from server_app.services import readiness as readiness_service
from server_app.services import schema_a2
from server_app.services import srs as srs_service
from server_app.services.npc import (
    NPCProviderError,
    call_groq_chat,
)
from server_app.services.quota import (
    AIQuotaLedger,
    QuotaExceededError,
    reserve_daily_ai_quota,
)

logger = logging.getLogger("lvcodex.curriculum")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Default lesson cache lifetime (24 h is the natural "one practice day").
LESSON_CACHE_TTL_SECONDS = 24 * 3600

#: Max number of SRS lemmas spliced into the prompt as the personalisation seed.
LESSON_SRS_SEED_LIMIT = 8

#: Groq sampling parameters — low-ish temperature so the lesson reads
#: like a textbook page, not a creative writing exercise.
LESSON_DEFAULT_TEMPERATURE = 0.4
LESSON_DEFAULT_MAX_TOKENS = 900

#: Cap on the persisted ``content`` JSON to keep the DB row small even if
#: Groq returns a wall of text. Counted in UTF-8 bytes after serialisation.
LESSON_CONTENT_MAX_BYTES = 16_384

#: Hard cap on lessons returned from ``GET /api/curriculum/lessons``.
LESSON_LIST_LIMIT = 20

ALLOWED_SKILLS: tuple[str, ...] = schema_a2.A2_SKILLS  # ("listening", "reading", "writing", "speaking")


_DDL_LOCK = threading.Lock()
_DDL_APPLIED = False


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class LessonVocabItem(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    lv: str = Field(..., min_length=1, max_length=80)
    en: str = Field(..., min_length=1, max_length=160)


class LessonDrill(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    prompt_lv: str = Field(..., min_length=1, max_length=600)
    prompt_en: str = Field(..., min_length=1, max_length=600)
    answer_lv: str = Field(..., min_length=1, max_length=400)
    rationale_en: str = Field(default="", max_length=600)


class LessonContent(BaseModel):
    """Validated lesson body returned by Groq and persisted to the cache."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    title: str = Field(..., min_length=1, max_length=160)
    objective: str = Field(..., min_length=1, max_length=400)
    vocab: list[LessonVocabItem] = Field(default_factory=list, max_length=20)
    drills: list[LessonDrill] = Field(default_factory=list, max_length=10)
    reflection_prompt_en: str = Field(default="", max_length=400)

    @field_validator("drills")
    @classmethod
    def _at_least_one_drill(cls, value: list[LessonDrill]) -> list[LessonDrill]:
        if not value:
            raise ValueError("lesson must contain at least one drill")
        return value


class GenerateLessonRequest(BaseModel):
    """Inbound body for ``POST /api/curriculum/generate``.

    ``weak_skill`` is optional — when omitted, the service auto-derives
    the weakest skill from T-030 readiness. ``force_refresh=True`` is the
    cache buster (tests + power users).
    """

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    weak_skill: Optional[str] = Field(default=None)
    force_refresh: bool = Field(default=False)

    @field_validator("weak_skill")
    @classmethod
    def _validate_skill(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return None
        normalised = value.strip().lower()
        if normalised not in ALLOWED_SKILLS:
            raise ValueError(
                f"weak_skill must be one of {ALLOWED_SKILLS!r} (got {value!r})"
            )
        return normalised


class LessonRecord(BaseModel):
    """Row-shaped lesson returned by ``GET /api/curriculum/lessons``."""

    model_config = ConfigDict(extra="ignore")

    lesson_id: str
    account_id: str
    weak_skill: str
    cache_key: str
    content: LessonContent
    created_at: str
    expires_at: str


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class CurriculumError(Exception):
    """Base error class for the curriculum service surface."""

    status_code = 400

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class CurriculumInvalidRequest(CurriculumError):
    status_code = 400


class CurriculumProviderError(CurriculumError):
    status_code = 502


# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------


_DDL = """
CREATE TABLE IF NOT EXISTS curriculum_lessons (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    weak_skill TEXT NOT NULL,
    cache_key TEXT NOT NULL,
    content_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_curriculum_lessons_account_skill
    ON curriculum_lessons(account_id, weak_skill, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_curriculum_lessons_cache_key
    ON curriculum_lessons(cache_key);
"""


def _ensure_curriculum_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(_DDL)


def ensure_curriculum_tables_ready() -> None:
    """Idempotent DDL initialiser. Safe to call on every request."""

    global _DDL_APPLIED
    if _DDL_APPLIED:
        return
    with _DDL_LOCK:
        if _DDL_APPLIED:
            return
        with db_connection() as conn:
            _ensure_curriculum_tables(conn)
        _DDL_APPLIED = True


def _reset_curriculum_ddl_cache() -> None:
    """Test hook — drop the once-flag for a fresh tempfile DB."""

    global _DDL_APPLIED
    with _DDL_LOCK:
        _DDL_APPLIED = False


# ---------------------------------------------------------------------------
# Datetime helpers
# ---------------------------------------------------------------------------


def _now(now: Optional[datetime] = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def _now_iso(now: Optional[datetime] = None) -> str:
    return _now(now).isoformat().replace("+00:00", "Z")


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


# ---------------------------------------------------------------------------
# Weak-skill resolution (uses T-030 readiness)
# ---------------------------------------------------------------------------


def resolve_weak_skill(
    account_id: str,
    *,
    explicit_skill: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> str:
    """Return the skill the lesson should target.

    Priority:

    1. If the caller passed ``explicit_skill`` and it's valid, use it.
    2. Otherwise, ask :func:`readiness.compute_readiness` for the
       per-skill avg and pick the skill with the **lowest** avg_score
       (red badges beat yellow beats green). Ties break in the canonical
       :data:`schema_a2.A2_SKILLS` order so the resolution is deterministic.
    3. If readiness has zero history for every skill (brand-new learner),
       fall back to ``"listening"`` — the conventional first-day skill.
    """

    if explicit_skill is not None:
        normalised = explicit_skill.strip().lower()
        if normalised in ALLOWED_SKILLS:
            return normalised

    own_conn = conn is None
    if own_conn:
        conn = db_connection()
    try:
        payload = readiness_service.compute_readiness(conn, account_id)
    finally:
        if own_conn and conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001 — defensive
                pass

    skills = payload.get("skills") or []
    # Sort: lowest avg first (None → -1 so "no history" ranks worst), then
    # by canonical skill order to keep ties deterministic.
    canonical_index = {skill: idx for idx, skill in enumerate(ALLOWED_SKILLS)}

    def _sort_key(row: dict[str, Any]) -> tuple[float, int]:
        avg = row.get("avg_score")
        # Treat "no history" as the weakest signal (-1.0 ranks below any real avg).
        avg_for_sort = -1.0 if avg is None else float(avg)
        return (avg_for_sort, canonical_index.get(row.get("skill") or "", 99))

    ordered = sorted(skills, key=_sort_key)
    for row in ordered:
        skill = row.get("skill")
        if skill in ALLOWED_SKILLS:
            return skill  # type: ignore[return-value]
    return "listening"


# ---------------------------------------------------------------------------
# SRS seed gathering
# ---------------------------------------------------------------------------


def gather_srs_seed(
    account_id: str,
    *,
    limit: int = LESSON_SRS_SEED_LIMIT,
    conn: Optional[sqlite3.Connection] = None,
) -> list[dict[str, str]]:
    """Pull up to ``limit`` due lemmas from the learner's SRS deck.

    These flow into the prompt as personalisation. Cards are picked
    oldest-due-first (the same order :func:`srs.due_cards` uses) so the
    lesson naturally re-uses the words the learner is currently failing.
    Returns ``[]`` (not ``None``) when the deck is empty so the cache key
    stays a stable hash either way.
    """

    if not account_id:
        return []
    own_conn = conn is None
    if own_conn:
        conn = db_connection()
    try:
        try:
            cards = srs_service.due_cards(conn, account_id, limit=limit)
        except sqlite3.OperationalError:
            # SRS tables not yet initialised — degrade gracefully.
            return []
    finally:
        if own_conn and conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001 — defensive
                pass
    return [
        {"lv": card.get("lv") or "", "en": card.get("en") or ""}
        for card in cards
        if card.get("lv") and card.get("en")
    ]


# ---------------------------------------------------------------------------
# Cache key
# ---------------------------------------------------------------------------


def compute_cache_key(
    account_id: str,
    weak_skill: str,
    srs_seed: list[dict[str, str]],
) -> str:
    """Stable hash of the inputs that define a lesson.

    Determinism is the whole point: the same ``(account, skill, seed)``
    triple always maps to the same key, so two consecutive calls hit the
    cache. The seed is sorted lemma-wise before hashing so two equivalent
    decks (same lemmas, different order) produce the same key.

    Returns the first 24 hex chars of a SHA-256 hash — plenty of entropy
    to avoid collisions in a single-account scope while keeping URL-safe
    short keys.
    """

    seed_normalised = sorted(
        (item.get("lv") or "", item.get("en") or "") for item in srs_seed
    )
    payload = {
        "account_id": account_id,
        "weak_skill": weak_skill,
        "seed": seed_normalised,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    return digest[:24]


# ---------------------------------------------------------------------------
# Cache I/O
# ---------------------------------------------------------------------------


def _row_to_record(row: sqlite3.Row) -> LessonRecord:
    content = LessonContent.model_validate_json(row["content_json"])
    return LessonRecord(
        lesson_id=row["id"],
        account_id=row["account_id"],
        weak_skill=row["weak_skill"],
        cache_key=row["cache_key"],
        content=content,
        created_at=row["created_at"],
        expires_at=row["expires_at"],
    )


def get_cached_lesson(
    cache_key: str,
    *,
    now: Optional[datetime] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Optional[LessonRecord]:
    """Return the cached lesson for ``cache_key`` if it is not expired.

    Expired rows are pruned lazily — the next ``generate_lesson`` call
    after the TTL elapses overwrites the row, so the cache never grows
    unbounded for the same key.
    """

    if not cache_key:
        return None
    ensure_curriculum_tables_ready()
    instant = _now(now)
    own_conn = conn is None
    if own_conn:
        conn = db_connection()
    try:
        _ensure_curriculum_tables(conn)
        row = conn.execute(
            "SELECT * FROM curriculum_lessons WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
    finally:
        if own_conn and conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001 — defensive
                pass
    if row is None:
        return None
    expires = _parse_iso(row["expires_at"])
    if expires is None or expires <= instant:
        return None
    try:
        return _row_to_record(row)
    except ValidationError:
        # Cached row is corrupt / from a previous schema — ignore so the
        # next generation overwrites it.
        return None


def save_lesson(
    *,
    account_id: str,
    weak_skill: str,
    cache_key: str,
    content: LessonContent,
    now: Optional[datetime] = None,
    ttl_seconds: int = LESSON_CACHE_TTL_SECONDS,
) -> LessonRecord:
    """Persist a freshly-generated lesson (or overwrite an expired row).

    Idempotent on ``cache_key``: when the same key already exists the row
    is updated in place rather than duplicated. This is what makes the
    cache a "single-row-per-key" structure.
    """

    ensure_curriculum_tables_ready()
    instant = _now(now)
    created_at = _now_iso(instant)
    expires_at = _now_iso(instant + timedelta(seconds=max(60, int(ttl_seconds))))
    serialised = content.model_dump_json()
    if len(serialised.encode("utf-8")) > LESSON_CONTENT_MAX_BYTES:
        raise CurriculumProviderError(
            "Generated lesson exceeds the persistence budget; refusing to cache.",
            status_code=502,
        )

    lesson_id = f"lsn_{uuid.uuid4().hex[:16]}"
    with db_connection() as conn:
        _ensure_curriculum_tables(conn)
        # Try update first (when the key already exists we keep the SAME
        # row but refresh the content / timestamps so the cache key
        # invariant "one row per key" holds).
        existing = conn.execute(
            "SELECT id FROM curriculum_lessons WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
        if existing is not None:
            lesson_id = existing["id"]
            conn.execute(
                """
                UPDATE curriculum_lessons
                SET weak_skill = ?,
                    content_json = ?,
                    created_at = ?,
                    expires_at = ?
                WHERE cache_key = ?
                """,
                (weak_skill, serialised, created_at, expires_at, cache_key),
            )
        else:
            conn.execute(
                """
                INSERT INTO curriculum_lessons
                    (id, account_id, weak_skill, cache_key, content_json,
                     created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lesson_id,
                    account_id,
                    weak_skill,
                    cache_key,
                    serialised,
                    created_at,
                    expires_at,
                ),
            )
        conn.commit()

    return LessonRecord(
        lesson_id=lesson_id,
        account_id=account_id,
        weak_skill=weak_skill,
        cache_key=cache_key,
        content=content,
        created_at=created_at,
        expires_at=expires_at,
    )


def list_lessons(
    account_id: str,
    *,
    limit: int = LESSON_LIST_LIMIT,
    include_expired: bool = False,
    now: Optional[datetime] = None,
) -> list[LessonRecord]:
    """Return the learner's most-recent cached lessons (newest first).

    ``include_expired=False`` (the default for the route handler) filters
    out rows whose ``expires_at`` is already past — they are technically
    still in the DB but the UX treats them as stale.
    """

    if not account_id:
        return []
    ensure_curriculum_tables_ready()
    instant = _now(now)
    cap = max(1, min(int(limit or 1), LESSON_LIST_LIMIT))
    with db_connection() as conn:
        _ensure_curriculum_tables(conn)
        rows = conn.execute(
            """
            SELECT * FROM curriculum_lessons
            WHERE account_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (account_id, cap),
        ).fetchall()
    out: list[LessonRecord] = []
    for row in rows:
        try:
            record = _row_to_record(row)
        except ValidationError:
            # Skip corrupt rows — they're already invisible via the cache hit.
            continue
        if not include_expired:
            expires = _parse_iso(record.expires_at)
            if expires is None or expires <= instant:
                continue
        out.append(record)
    return out


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


CURRICULUM_SYSTEM_PROMPT = (
    "You are a curriculum designer for Latvian-language A2 learners. "
    "Given a learner profile and a weak skill, you produce ONE short, "
    "self-contained micro-lesson in strict JSON. The lesson must be at "
    "the A2 level, must reuse the learner's vocabulary list when "
    "provided, and must include between 2 and 5 drills. Do NOT include "
    "any prose outside the JSON object. The JSON shape is exactly:\n"
    "{\n"
    "  \"title\": <string in Latvian, <=80 chars>,\n"
    "  \"objective\": <string in Latvian, <=200 chars>,\n"
    "  \"vocab\": [{\"lv\": <Latvian word>, \"en\": <English gloss>}, ...],\n"
    "  \"drills\": [\n"
    "    {\n"
    "      \"prompt_lv\": <drill prompt in Latvian>,\n"
    "      \"prompt_en\": <same prompt in English>,\n"
    "      \"answer_lv\": <expected answer or model answer in Latvian>,\n"
    "      \"rationale_en\": <one-sentence English rationale>\n"
    "    }, ...\n"
    "  ],\n"
    "  \"reflection_prompt_en\": <one-sentence English reflection question>\n"
    "}\n"
    "Be concise: total response under 800 tokens."
)


def build_messages(
    *,
    account_id: str,
    weak_skill: str,
    avg_score: Optional[float],
    srs_seed: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Compose the messages array for the Groq call.

    The user message is a deterministic dump of the learner profile so a
    cache miss followed immediately by an identical retry produces the
    same prompt (modulo Groq sampling noise). The seed is sorted in the
    same way :func:`compute_cache_key` sorts it so the prompt text is
    invariant to insertion order in the SRS deck.
    """

    seed_serialised = sorted(
        ((item.get("lv") or ""), (item.get("en") or "")) for item in srs_seed
    )
    seed_block = (
        "\n".join(f"- {lv} ({en})" for lv, en in seed_serialised if lv)
        or "(no vocabulary in the learner's deck yet)"
    )
    avg_block = (
        f"{avg_score:.1f}/15 (target: 9/15)" if avg_score is not None else "no recent data"
    )
    user_content = (
        f"Learner ID: {account_id}\n"
        f"Weak skill: {weak_skill}\n"
        f"Current per-skill score: {avg_block}\n"
        f"SRS vocabulary to reuse:\n{seed_block}\n\n"
        "Produce the lesson JSON now."
    )
    return [
        {"role": "system", "content": CURRICULUM_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


# ---------------------------------------------------------------------------
# Reply parsing
# ---------------------------------------------------------------------------


def _extract_json_object(text: str) -> str:
    """Return the first ``{...}`` substring in ``text``.

    Groq occasionally wraps JSON in markdown fences or prepends an
    apology line; this strips those so :func:`LessonContent.model_validate_json`
    sees a clean object. Raises :class:`CurriculumProviderError` if no
    object is found at all.
    """

    if not text:
        raise CurriculumProviderError("Groq returned an empty lesson body.", status_code=502)
    stripped = text.strip()
    # Fast path — already a clean JSON object.
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise CurriculumProviderError(
            "Groq response did not contain a JSON object.", status_code=502
        )
    return stripped[start : end + 1]


def parse_lesson_content(raw_reply: str) -> LessonContent:
    """Validate a Groq lesson body against :class:`LessonContent`.

    Surface a :class:`CurriculumProviderError` (502) on any failure so
    the route handler renders it as ``bad_gateway`` — the learner did
    nothing wrong, the upstream model misbehaved.
    """

    payload_str = _extract_json_object(raw_reply)
    try:
        data = json.loads(payload_str)
    except json.JSONDecodeError as error:
        raise CurriculumProviderError(
            f"Groq reply was not valid JSON: {error}", status_code=502
        ) from error
    try:
        return LessonContent.model_validate(data)
    except ValidationError as error:
        raise CurriculumProviderError(
            "Groq lesson body failed schema validation: " + str(error.errors()),
            status_code=502,
        ) from error


# ---------------------------------------------------------------------------
# Request parsing
# ---------------------------------------------------------------------------


def parse_generate_request(raw: Any) -> GenerateLessonRequest:
    try:
        return GenerateLessonRequest.model_validate(raw or {})
    except ValidationError as error:
        raise CurriculumInvalidRequest(
            "Curriculum generate request failed schema validation: "
            + str(error.errors())
        ) from error


# ---------------------------------------------------------------------------
# Top-level generator
# ---------------------------------------------------------------------------


def generate_lesson(
    account_id: str,
    weak_skill: Optional[str] = None,
    *,
    plan: str = "free",
    raw_body: Any = None,
    transport: Optional[Callable[[urllib.request.Request, float], dict[str, Any]]] = None,
    quota_user_key: Optional[str] = None,
    now: Optional[datetime] = None,
    force_refresh: bool = False,
    ttl_seconds: int = LESSON_CACHE_TTL_SECONDS,
) -> dict[str, Any]:
    """Produce (or fetch from cache) a personalised lesson.

    Two calling conventions are supported so the route handler can pass
    ``raw_body`` straight through while tests still call the function
    with explicit kwargs:

    * **Route style** — ``raw_body`` is the parsed JSON body. ``weak_skill``
      and ``force_refresh`` are extracted from it via Pydantic validation.
    * **Direct style** — pass ``weak_skill=...`` and ``force_refresh=...``
      directly; ``raw_body`` is ignored.

    Returns a plain ``dict`` ready to be JSON-serialised — the route
    handler does not need to know about Pydantic models.

    Cache semantics:

    * Cache HIT → no Groq call, no quota debit. The ``cached`` flag is
      ``True`` and ``usage`` is empty.
    * Cache MISS (or ``force_refresh=True``) → reserve a quota slot,
      call Groq, validate the JSON body, persist to the cache, refund
      the slot on any provider failure.
    """

    if not account_id:
        raise CurriculumInvalidRequest("account_id is required.")

    if raw_body is not None and (weak_skill is None and not force_refresh):
        request = parse_generate_request(raw_body)
        weak_skill = request.weak_skill
        force_refresh = bool(request.force_refresh)

    # 1. Resolve the target skill (explicit > readiness-derived > listening).
    resolved_skill = resolve_weak_skill(account_id, explicit_skill=weak_skill)

    # 2. Build the cache key from the SRS seed.
    srs_seed = gather_srs_seed(account_id)
    cache_key = compute_cache_key(account_id, resolved_skill, srs_seed)

    # 3. Cache lookup unless the caller asked for a refresh.
    cached: Optional[LessonRecord] = None
    if not force_refresh:
        cached = get_cached_lesson(cache_key, now=now)
    if cached is not None:
        logger.info(
            "curriculum_cache_hit account=%s skill=%s key=%s",
            account_id,
            resolved_skill,
            cache_key,
        )
        return {
            "lesson_id": cached.lesson_id,
            "account_id": cached.account_id,
            "weak_skill": cached.weak_skill,
            "cache_key": cached.cache_key,
            "cached": True,
            "content": json.loads(cached.content.model_dump_json()),
            "created_at": cached.created_at,
            "expires_at": cached.expires_at,
            "quota": {},
            "usage": {},
        }

    # 4. Cache miss → reserve a quota slot, then call Groq.
    user_key = (quota_user_key or account_id).strip()
    if not user_key:
        raise CurriculumInvalidRequest("Cannot reserve quota: missing user identity.")
    quota_snapshot = reserve_daily_ai_quota(user_key, plan)

    try:
        avg_score = _lookup_avg_score(account_id, resolved_skill)
        messages = build_messages(
            account_id=account_id,
            weak_skill=resolved_skill,
            avg_score=avg_score,
            srs_seed=srs_seed,
        )
        try:
            provider_result = call_groq_chat(
                messages,
                temperature=LESSON_DEFAULT_TEMPERATURE,
                max_tokens=LESSON_DEFAULT_MAX_TOKENS,
                transport=transport,
            )
        except NPCProviderError as error:
            raise CurriculumProviderError(str(error), status_code=error.status_code) from error
        reply_text = (provider_result.get("content") or "").strip()
        content = parse_lesson_content(reply_text)
        record = save_lesson(
            account_id=account_id,
            weak_skill=resolved_skill,
            cache_key=cache_key,
            content=content,
            now=now,
            ttl_seconds=ttl_seconds,
        )
    except Exception:
        # Refund the daily quota slot — same pattern as scoring/companion/NPC.
        try:
            AIQuotaLedger().release(user_key, plan)
        except Exception:  # noqa: BLE001 — defensive
            logger.exception("curriculum_quota_refund_failed user=%s", user_key)
        raise

    logger.info(
        "curriculum_cache_miss account=%s skill=%s key=%s lesson=%s",
        account_id,
        resolved_skill,
        cache_key,
        record.lesson_id,
    )
    return {
        "lesson_id": record.lesson_id,
        "account_id": record.account_id,
        "weak_skill": record.weak_skill,
        "cache_key": record.cache_key,
        "cached": False,
        "content": json.loads(record.content.model_dump_json()),
        "created_at": record.created_at,
        "expires_at": record.expires_at,
        "quota": {
            "used": int(quota_snapshot["used"]),
            "limit": int(quota_snapshot["limit"]),
            "resets_at": str(quota_snapshot["resets_at"]),
        },
        "usage": dict(provider_result.get("usage") or {}),
    }


def _lookup_avg_score(account_id: str, weak_skill: str) -> Optional[float]:
    """Return the per-skill avg from T-030 readiness, or ``None`` if absent."""

    if not account_id:
        return None
    try:
        with db_connection() as conn:
            payload = readiness_service.compute_readiness(conn, account_id)
    except Exception:  # noqa: BLE001 — degrade gracefully
        return None
    for row in payload.get("skills") or []:
        if row.get("skill") == weak_skill:
            avg = row.get("avg_score")
            if avg is None:
                return None
            try:
                return float(avg)
            except (TypeError, ValueError):
                return None
    return None


def list_lessons_for_route(
    account_id: str,
    *,
    limit: int = LESSON_LIST_LIMIT,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Route-shaped payload for ``GET /api/curriculum/lessons``."""

    records = list_lessons(account_id, limit=limit, now=now)
    return {
        "lessons": [
            {
                "lesson_id": r.lesson_id,
                "weak_skill": r.weak_skill,
                "cache_key": r.cache_key,
                "content": json.loads(r.content.model_dump_json()),
                "created_at": r.created_at,
                "expires_at": r.expires_at,
            }
            for r in records
        ],
        "count": len(records),
        "limit": min(limit, LESSON_LIST_LIMIT),
    }


__all__ = [
    "ALLOWED_SKILLS",
    "CURRICULUM_SYSTEM_PROMPT",
    "CurriculumError",
    "CurriculumInvalidRequest",
    "CurriculumProviderError",
    "GenerateLessonRequest",
    "LESSON_CACHE_TTL_SECONDS",
    "LESSON_CONTENT_MAX_BYTES",
    "LESSON_DEFAULT_MAX_TOKENS",
    "LESSON_DEFAULT_TEMPERATURE",
    "LESSON_LIST_LIMIT",
    "LESSON_SRS_SEED_LIMIT",
    "LessonContent",
    "LessonDrill",
    "LessonRecord",
    "LessonVocabItem",
    "QuotaExceededError",
    "build_messages",
    "compute_cache_key",
    "ensure_curriculum_tables_ready",
    "gather_srs_seed",
    "generate_lesson",
    "get_cached_lesson",
    "list_lessons",
    "list_lessons_for_route",
    "parse_generate_request",
    "parse_lesson_content",
    "resolve_weak_skill",
    "save_lesson",
]
