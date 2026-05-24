"""T-031 — Daily mission generator + analytics events.

This module is the single source of truth for the three missions a
learner receives every local day:

1. **weak-skill drill** — targets the skill with the lowest objective
   score across the learner's recent attempts (per the T-030 readiness
   signal — see :func:`server_app.core.build_dashboard`'s
   ``skill_progress`` bucket). Cold-start learners (no attempts yet)
   default to ``listening`` because the curated micro-clip library is
   the most welcoming entry point.
2. **listening clip** — one curated clip from the existing
   ``latvian-listening-library/web/microClips.json`` catalogue (shared
   with T-035 to avoid duplicating audio assets).
3. **writing prompt** — one A2 writing prompt from a small built-in
   catalogue. The catalogue mirrors the format used by the existing
   ``exam_bank.parse_writing_task3`` (short_message + informal_letter)
   so a learner switching between missions and the mock exam sees the
   same prompt style.

Determinism contract
--------------------
For a given ``(account_id, local_date)`` pair, :func:`get_or_generate_today`
must return the **same** three missions on every call. This is enforced
by a unique constraint on ``(account_id, local_date, slot)`` and a
deterministic seed (``hash(account_id, local_date)``) used to pick the
listening clip + writing prompt indices. Re-running the generator after
the row exists is a read, not a write.

Completion contract
-------------------
:func:`complete_mission` is idempotent. The first call flips the
``completed_at`` column, increments the per-account streak counter, and
writes one ``mission_completed`` row to ``mission_analytics_events``.
Subsequent calls return the same mission record and are silent — no new
analytics event, no double-counted XP.

Timezone handling
-----------------
The "today" anchor is the **learner's local date**. The function
:func:`local_date_for_account` reads ``accounts.user_timezone`` (an
IANA name, default ``UTC``) and uses :mod:`zoneinfo` to convert the
current UTC instant to a ``YYYY-MM-DD`` string. Missions persisted
under a different ``local_date`` are not returned, so when local
midnight rolls over the learner automatically gets a fresh set.

Public surface
--------------
``ensure_missions_schema(conn) -> None``
    Idempotent DDL applier. Called from ``init_auth_store`` and from
    each entry point so tests don't have to worry about migration
    ordering.

``local_date_for_account(conn, account_id, *, now=None) -> str``
    Return the learner's local date as ``YYYY-MM-DD``.

``get_or_generate_today(conn, account_id, *, now=None) -> list[dict]``
    Returns today's three missions for ``account_id``, generating them
    on first call of the local day.

``complete_mission(conn, account_id, mission_id) -> dict``
    Mark ``mission_id`` complete, idempotently. Returns
    ``{"mission": ..., "summary": ..., "analytics_event_emitted": bool}``.

``compute_weak_skill(conn, account_id) -> str``
    Return the lowest-scoring skill across recent attempts. Falls back
    to ``"listening"`` on cold-start.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from server_app.services.schema_a2 import A2_SKILLS

try:  # T-030 readiness service — preferred weak-skill source.
    from server_app.services import readiness as _readiness_service
except ImportError:  # pragma: no cover - readiness not installed
    _readiness_service = None  # type: ignore[assignment]

logger = logging.getLogger("lvcodex.missions")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Three slots, in stable order. The slot label is persisted so the
# dashboard widget can render them in the same order across reloads
# regardless of insertion order on disk.
SLOT_WEAK_SKILL = "weak_skill_drill"
SLOT_LISTENING = "listening_clip"
SLOT_WRITING = "writing_prompt"

MISSION_SLOTS: tuple[str, ...] = (SLOT_WEAK_SKILL, SLOT_LISTENING, SLOT_WRITING)

# How many recent attempts the weak-skill heuristic considers. Twelve
# matches the dashboard's recent-attempts window so the two views agree.
WEAK_SKILL_LOOKBACK_ATTEMPTS = 12

# Cold-start fallback skill. Picked because the listening library has
# the most curated content for absolute beginners.
COLD_START_SKILL = "listening"

# A small built-in catalogue of A2 writing prompts. Kept here (rather
# than in exam_bank.py) so the missions module remains independent of
# the exam-bank parser's heavier dependencies. New prompts may be added
# freely — the deterministic picker takes ``index % len(prompts)``.
WRITING_PROMPTS: tuple[dict[str, str], ...] = (
    {
        "id": "wp_a2_friend_visit",
        "kind": "informal_letter",
        "title_lv": "Vēstule draugam",
        "title_en": "Letter to a friend",
        "prompt_lv": (
            "Uzraksti īsu vēstuli draugam (40–60 vārdi). Pastāsti, ko tu "
            "darīji pagājušajā nedēļas nogalē un ko plāno darīt nākamajā."
        ),
        "prompt_en": (
            "Write a short letter to a friend (40–60 words). Tell them "
            "what you did last weekend and what you plan to do next."
        ),
        "min_words": "40",
        "max_words": "60",
    },
    {
        "id": "wp_a2_market_note",
        "kind": "short_message",
        "title_lv": "Zīmīte uz ledusskapja",
        "title_en": "Fridge note",
        "prompt_lv": (
            "Uzraksti īsu zīmīti (20–30 vārdi) savai ģimenei: paskaidro, "
            "ka esi aizgājis(-usi) uz veikalu, un saraksti, ko nopirksi."
        ),
        "prompt_en": (
            "Write a short note (20–30 words) for your family: explain "
            "that you've gone to the shop and list what you'll buy."
        ),
        "min_words": "20",
        "max_words": "30",
    },
    {
        "id": "wp_a2_apartment_ad",
        "kind": "short_message",
        "title_lv": "Sludinājums par dzīvokli",
        "title_en": "Apartment advert",
        "prompt_lv": (
            "Tu vēlies izīrēt savu dzīvokli. Uzraksti sludinājumu "
            "(30–40 vārdi): atrašanās vieta, istabu skaits, cena, "
            "kontakts."
        ),
        "prompt_en": (
            "You want to rent out your apartment. Write an advert "
            "(30–40 words): location, number of rooms, price, contact."
        ),
        "min_words": "30",
        "max_words": "40",
    },
    {
        "id": "wp_a2_doctor_appointment",
        "kind": "informal_letter",
        "title_lv": "Lūgums atlikt tikšanos",
        "title_en": "Request to reschedule",
        "prompt_lv": (
            "Uzraksti īsu vēstuli (40–60 vārdi) ārsta reģistratūrai: "
            "paskaidro, kāpēc nevari atnākt uz tikšanos, un piedāvā "
            "jaunu datumu."
        ),
        "prompt_en": (
            "Write a short letter (40–60 words) to your doctor's "
            "reception: explain why you can't attend the appointment "
            "and propose a new date."
        ),
        "min_words": "40",
        "max_words": "60",
    },
    {
        "id": "wp_a2_thank_you_card",
        "kind": "short_message",
        "title_lv": "Pateicības kartīte",
        "title_en": "Thank-you card",
        "prompt_lv": (
            "Uzraksti pateicības kartīti (25–40 vārdi) draugam, kas "
            "tev palīdzēja pārcelties uz jaunu dzīvokli."
        ),
        "prompt_en": (
            "Write a thank-you card (25–40 words) to a friend who "
            "helped you move to a new apartment."
        ),
        "min_words": "25",
        "max_words": "40",
    },
    {
        "id": "wp_a2_weekend_plans",
        "kind": "informal_letter",
        "title_lv": "Aicinājums uz pasākumu",
        "title_en": "Event invitation",
        "prompt_lv": (
            "Uzraksti vēstuli draugam (40–60 vārdi) un aicini viņu uz "
            "tavu dzimšanas dienu: vieta, laiks, ko paņemt līdzi."
        ),
        "prompt_en": (
            "Write a letter (40–60 words) inviting a friend to your "
            "birthday party: place, time, what to bring."
        ),
        "min_words": "40",
        "max_words": "60",
    },
    {
        "id": "wp_a2_bus_stop",
        "kind": "short_message",
        "title_lv": "Ziņa kolēģim",
        "title_en": "Message to a colleague",
        "prompt_lv": (
            "Uzraksti īsu ziņu kolēģim (20–30 vārdi): paskaidro, ka "
            "kavēsi sapulci, un kāpēc."
        ),
        "prompt_en": (
            "Write a short message to a colleague (20–30 words): "
            "explain you'll be late for the meeting, and why."
        ),
        "min_words": "20",
        "max_words": "30",
    },
)


# ---------------------------------------------------------------------------
# Listening clip catalogue — re-uses the T-035 dataset on disk.
# ---------------------------------------------------------------------------

_DEFAULT_CLIPS_PATH = (
    Path(__file__).resolve().parents[2]
    / "latvian-listening-library"
    / "web"
    / "microClips.json"
)
_CLIPS_CACHE_LOCK = threading.Lock()
_CACHED_CLIPS: list[dict[str, Any]] | None = None
_CACHED_CLIPS_MTIME: float | None = None


def _clips_path() -> Path:
    override = os.environ.get("LVCODEX_LISTENING_FEED_PATH", "").strip()
    if override:
        return Path(override)
    return _DEFAULT_CLIPS_PATH


def _load_listening_clips() -> list[dict[str, Any]]:
    """Return the curated listening catalogue, cached by mtime."""

    global _CACHED_CLIPS, _CACHED_CLIPS_MTIME
    path = _clips_path()
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        return []
    with _CLIPS_CACHE_LOCK:
        if _CACHED_CLIPS is None or mtime != _CACHED_CLIPS_MTIME:
            try:
                rows = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                rows = []
            if not isinstance(rows, list):
                rows = []
            _CACHED_CLIPS = [r for r in rows if isinstance(r, dict) and r.get("id")]
            _CACHED_CLIPS_MTIME = mtime
        return list(_CACHED_CLIPS)


def _reset_clip_cache_for_tests() -> None:
    """Drop the cached catalogue so tests can swap in a fixture file."""

    global _CACHED_CLIPS, _CACHED_CLIPS_MTIME
    with _CLIPS_CACHE_LOCK:
        _CACHED_CLIPS = None
        _CACHED_CLIPS_MTIME = None


# ---------------------------------------------------------------------------
# DDL — applied once per connection.
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS daily_missions (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    local_date TEXT NOT NULL,
    slot TEXT NOT NULL,
    kind TEXT NOT NULL,
    skill TEXT,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    payload TEXT NOT NULL,
    completed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(account_id, local_date, slot)
);

CREATE INDEX IF NOT EXISTS idx_daily_missions_account_day
    ON daily_missions(account_id, local_date);

CREATE TABLE IF NOT EXISTS mission_analytics_events (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    event TEXT NOT NULL,
    mission_id TEXT,
    kind TEXT,
    skill TEXT,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_mission_events_account_event
    ON mission_analytics_events(account_id, event, created_at DESC);
"""


_DDL_APPLIED = False
_DDL_LOCK = threading.Lock()


def ensure_missions_schema(conn: sqlite3.Connection) -> None:
    """Create the two T-031 tables if they don't already exist.

    Safe to call on every request — the once-flag short-circuits after
    the first successful execution. Tests reset the flag through
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
# Timezone helpers
# ---------------------------------------------------------------------------


def _resolve_timezone(name: str | None) -> ZoneInfo:
    """Return a ZoneInfo for ``name``, falling back to UTC on error."""

    candidate = (name or "UTC").strip() or "UTC"
    try:
        return ZoneInfo(candidate)
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning("missions: unknown timezone %r — falling back to UTC", candidate)
        return ZoneInfo("UTC")


def _account_timezone(conn: sqlite3.Connection, account_id: str) -> ZoneInfo:
    """Read the learner's IANA timezone from ``accounts.user_timezone``.

    Returns UTC when the column is missing (older schemas), the row is
    missing, or the value is unparseable.
    """

    try:
        row = conn.execute(
            "SELECT user_timezone FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()
    except sqlite3.OperationalError:
        return ZoneInfo("UTC")
    if row is None:
        return ZoneInfo("UTC")
    try:
        tz_name = row["user_timezone"] if "user_timezone" in row.keys() else None
    except (IndexError, KeyError, TypeError):
        tz_name = None
    return _resolve_timezone(tz_name)


def local_date_for_account(
    conn: sqlite3.Connection,
    account_id: str,
    *,
    now: datetime | None = None,
) -> str:
    """Return today's date in the learner's local timezone as YYYY-MM-DD."""

    tz = _account_timezone(conn, account_id)
    instant = now if now is not None else datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(tz).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Weak-skill heuristic (T-030 readiness signal)
# ---------------------------------------------------------------------------


def _extract_objective_score(skill_payload: Any) -> tuple[int, int]:
    """Return ``(objective_correct, objective_possible)`` for a skill bucket.

    Accepts both the dashboard's compact shape and the legacy nested
    ``evaluation.scores`` shape produced by ``compute_objective_score``.
    """

    if not isinstance(skill_payload, dict):
        return (0, 0)
    correct = 0
    possible = 0
    for key in ("objective_correct", "points", "score"):
        if key in skill_payload:
            try:
                correct = max(0, int(skill_payload[key]))
                break
            except (TypeError, ValueError):
                continue
    for key in ("objective_possible", "max_points", "max"):
        if key in skill_payload:
            try:
                possible = max(0, int(skill_payload[key]))
                break
            except (TypeError, ValueError):
                continue
    return (correct, possible)


def compute_weak_skill(conn: sqlite3.Connection, account_id: str) -> str:
    """Return the learner's lowest-scoring A2 skill across recent attempts.

    Preferred path: delegate to the T-030 readiness service
    (:func:`server_app.services.readiness.compute_readiness`), which
    aggregates the ``exam_attempt_category_score`` table — the same
    source the dashboard uses. The skill with the lowest ``avg_score``
    among skills that have any sample data is returned (ties broken by
    canonical skill order). Returns :data:`COLD_START_SKILL` when the
    learner has no readiness samples yet.

    Fallback path: if the readiness service is unavailable or raises
    (e.g. older databases without the category_score table), aggregate
    the legacy ``attempts.score_payload`` blob across the most recent
    :data:`WEAK_SKILL_LOOKBACK_ATTEMPTS`.
    """

    if _readiness_service is not None:
        try:
            payload = _readiness_service.compute_readiness(conn, account_id)
        except Exception:  # noqa: BLE001 - never block missions on readiness
            payload = None
        if payload:
            best_skill: str | None = None
            best_avg: float | None = None
            for entry in payload.get("skills", []):
                if not isinstance(entry, dict):
                    continue
                skill = entry.get("skill")
                avg = entry.get("avg_score")
                sample_size = int(entry.get("sample_size") or 0)
                if skill not in A2_SKILLS or avg is None or sample_size <= 0:
                    continue
                if best_avg is None or float(avg) < best_avg:
                    best_avg = float(avg)
                    best_skill = skill
            if best_skill is not None:
                return best_skill

    try:
        rows = conn.execute(
            """
            SELECT score_payload FROM attempts
            WHERE account_id = ?
            ORDER BY submitted_at DESC
            LIMIT ?
            """,
            (account_id, WEAK_SKILL_LOOKBACK_ATTEMPTS),
        ).fetchall()
    except sqlite3.OperationalError:
        return COLD_START_SKILL

    aggregates: dict[str, list[int]] = {skill: [0, 0] for skill in A2_SKILLS}
    for row in rows:
        raw = row["score_payload"] if "score_payload" in row.keys() else None
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        scoring: Any = None
        if isinstance(payload, dict):
            evaluation = payload.get("evaluation")
            if isinstance(evaluation, dict) and isinstance(
                evaluation.get("scores"), dict
            ):
                scoring = evaluation["scores"]
            elif isinstance(payload.get("scoring"), dict):
                scoring = payload["scoring"]
            else:
                scoring = payload
        if not isinstance(scoring, dict):
            continue
        by_skill = scoring.get("by_skill") if isinstance(scoring, dict) else None
        if not isinstance(by_skill, dict):
            by_skill = scoring  # tolerate the flat shape too
        for skill, skill_payload in by_skill.items():
            if skill not in aggregates:
                continue
            correct, possible = _extract_objective_score(skill_payload)
            aggregates[skill][0] += correct
            aggregates[skill][1] += possible

    # Pick the skill with the lowest ratio. If no skill has any
    # attempted points (cold start), fall back to the canonical default.
    best_skill = COLD_START_SKILL
    best_ratio: float | None = None
    has_data = False
    for skill in A2_SKILLS:
        correct, possible = aggregates[skill]
        if possible <= 0:
            continue
        has_data = True
        ratio = correct / possible
        if best_ratio is None or ratio < best_ratio:
            best_ratio = ratio
            best_skill = skill
    if not has_data:
        return COLD_START_SKILL
    return best_skill


# ---------------------------------------------------------------------------
# Mission picker (deterministic per (account, date))
# ---------------------------------------------------------------------------


def _deterministic_index(account_id: str, local_date: str, salt: str, modulo: int) -> int:
    """Stable integer in ``[0, modulo)`` for ``(account, date, salt)``."""

    if modulo <= 0:
        return 0
    h = hashlib.sha256(
        f"{account_id}|{local_date}|{salt}".encode("utf-8")
    ).hexdigest()
    return int(h, 16) % modulo


def _pick_listening_clip(account_id: str, local_date: str) -> dict[str, Any] | None:
    clips = _load_listening_clips()
    if not clips:
        return None
    index = _deterministic_index(account_id, local_date, "listening_clip", len(clips))
    return clips[index]


def _pick_writing_prompt(account_id: str, local_date: str) -> dict[str, str]:
    index = _deterministic_index(
        account_id, local_date, "writing_prompt", len(WRITING_PROMPTS)
    )
    return WRITING_PROMPTS[index]


# ---------------------------------------------------------------------------
# Generation + read
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _build_weak_skill_mission(
    *, account_id: str, local_date: str, weak_skill: str
) -> dict[str, Any]:
    titles = {
        "listening": "Listening drill — repair your weakest skill",
        "reading": "Reading drill — repair your weakest skill",
        "writing": "Writing drill — repair your weakest skill",
        "speaking": "Speaking drill — repair your weakest skill",
    }
    descriptions = {
        "listening": "Tackle three listening exercises focused on your weakest area.",
        "reading": "Read a short A2 passage and answer three comprehension prompts.",
        "writing": "Write one short paragraph targeted at your weakest grammar area.",
        "speaking": "Record one short monologue answering today's speaking prompt.",
    }
    payload = {
        "skill": weak_skill,
        "drill_count": 3,
        "source": "readiness_weak_skill",
    }
    return {
        "slot": SLOT_WEAK_SKILL,
        "kind": "weak_skill_drill",
        "skill": weak_skill,
        "title": titles.get(weak_skill, "Drill — repair your weakest skill"),
        "description": descriptions.get(
            weak_skill, "Complete three quick exercises in your weakest area."
        ),
        "payload": payload,
    }


def _build_listening_mission(
    *, account_id: str, local_date: str
) -> dict[str, Any]:
    clip = _pick_listening_clip(account_id, local_date)
    if clip is None:
        # Catalogue missing on disk — still surface a placeholder so the
        # dashboard always has 3 slots. The user can complete it manually.
        payload = {"source": "listening_clip_unavailable"}
        return {
            "slot": SLOT_LISTENING,
            "kind": "listening_clip",
            "skill": "listening",
            "title": "Listening — today's clip",
            "description": "The listening catalogue is unavailable right now.",
            "payload": payload,
        }
    return {
        "slot": SLOT_LISTENING,
        "kind": "listening_clip",
        "skill": "listening",
        "title": clip.get("title") or "Listening — today's clip",
        "description": clip.get("translation")
        or clip.get("description")
        or "Listen to a short Latvian clip and answer one question.",
        "payload": {
            "clip_id": clip.get("id"),
            "audio_url": clip.get("audio_url"),
            "transcript": clip.get("transcript"),
            "translation": clip.get("translation"),
            "difficulty": clip.get("difficulty"),
            "category": clip.get("category"),
            "source": "microClips.json",
        },
    }


def _build_writing_mission(
    *, account_id: str, local_date: str
) -> dict[str, Any]:
    prompt = _pick_writing_prompt(account_id, local_date)
    return {
        "slot": SLOT_WRITING,
        "kind": "writing_prompt",
        "skill": "writing",
        "title": prompt["title_en"],
        "description": prompt["prompt_en"],
        "payload": {
            "prompt_id": prompt["id"],
            "prompt_kind": prompt["kind"],
            "title_lv": prompt["title_lv"],
            "prompt_lv": prompt["prompt_lv"],
            "min_words": prompt["min_words"],
            "max_words": prompt["max_words"],
            "source": "writing_prompts_catalogue",
        },
    }


def _serialize_mission(row: sqlite3.Row) -> dict[str, Any]:
    try:
        payload = json.loads(row["payload"]) if row["payload"] else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        payload = {}
    return {
        "id": row["id"],
        "account_id": row["account_id"],
        "local_date": row["local_date"],
        "slot": row["slot"],
        "kind": row["kind"],
        "skill": row["skill"],
        "title": row["title"],
        "description": row["description"],
        "payload": payload,
        "completed": bool(row["completed_at"]),
        "completed_at": row["completed_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _ordered_missions(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    serialized = [_serialize_mission(r) for r in rows]
    order = {slot: i for i, slot in enumerate(MISSION_SLOTS)}
    serialized.sort(key=lambda m: order.get(m["slot"], 99))
    return serialized


def _existing_missions(
    conn: sqlite3.Connection, account_id: str, local_date: str
) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM daily_missions WHERE account_id = ? AND local_date = ?",
        (account_id, local_date),
    ).fetchall()


def _generate_missions_for_day(
    conn: sqlite3.Connection, account_id: str, local_date: str
) -> None:
    """Insert the three missions for ``(account_id, local_date)``.

    Uses ``INSERT OR IGNORE`` against the unique constraint so racing
    callers cannot create duplicate slots. After this call returns the
    three rows are guaranteed to exist; the caller re-reads them with
    :func:`_existing_missions`.
    """

    weak_skill = compute_weak_skill(conn, account_id)
    builders = (
        _build_weak_skill_mission(
            account_id=account_id, local_date=local_date, weak_skill=weak_skill
        ),
        _build_listening_mission(account_id=account_id, local_date=local_date),
        _build_writing_mission(account_id=account_id, local_date=local_date),
    )
    now = _now_iso()
    for builder in builders:
        mission_id = f"msn_{uuid.uuid4().hex[:16]}"
        conn.execute(
            """
            INSERT OR IGNORE INTO daily_missions
                (id, account_id, local_date, slot, kind, skill, title,
                 description, payload, completed_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
            """,
            (
                mission_id,
                account_id,
                local_date,
                builder["slot"],
                builder["kind"],
                builder["skill"],
                builder["title"],
                builder["description"],
                json.dumps(builder["payload"], ensure_ascii=False),
                now,
                now,
            ),
        )
    conn.commit()


def get_or_generate_today(
    conn: sqlite3.Connection,
    account_id: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return today's three missions for ``account_id``.

    Generates them on first call of the local day; subsequent calls are
    pure reads. The response shape is:

    .. code-block:: json

        {
          "local_date": "2026-05-23",
          "timezone": "Europe/Riga",
          "missions": [ {slot, kind, ...}, ... ],
          "summary": {"completed": 1, "total": 3, "ratio": 0.33}
        }
    """

    ensure_missions_schema(conn)
    local_date = local_date_for_account(conn, account_id, now=now)
    rows = _existing_missions(conn, account_id, local_date)
    if len(rows) < len(MISSION_SLOTS):
        _generate_missions_for_day(conn, account_id, local_date)
        rows = _existing_missions(conn, account_id, local_date)

    missions = _ordered_missions(rows)
    total = len(missions)
    completed = sum(1 for m in missions if m["completed"])
    tz = _account_timezone(conn, account_id)
    return {
        "local_date": local_date,
        "timezone": str(tz),
        "missions": missions,
        "summary": {
            "completed": completed,
            "total": total,
            "ratio": (completed / total) if total else 0.0,
        },
    }


# ---------------------------------------------------------------------------
# Completion + analytics
# ---------------------------------------------------------------------------


def _insert_analytics_event(
    conn: sqlite3.Connection,
    *,
    account_id: str,
    event: str,
    mission_id: str,
    kind: str,
    skill: str | None,
    payload: dict[str, Any] | None,
) -> str:
    """Append one row to ``mission_analytics_events``.

    Returns the generated event id. Never raises on a payload-serialise
    error — the payload is stored as ``{}`` instead so the ledger is
    always writeable.
    """

    event_id = f"msnev_{uuid.uuid4().hex[:16]}"
    try:
        payload_json = json.dumps(payload or {}, ensure_ascii=False)
    except (TypeError, ValueError):
        payload_json = "{}"
    conn.execute(
        """
        INSERT INTO mission_analytics_events
            (id, account_id, event, mission_id, kind, skill, payload, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            account_id,
            event,
            mission_id,
            kind,
            skill,
            payload_json,
            _now_iso(),
        ),
    )
    return event_id


def complete_mission(
    conn: sqlite3.Connection, account_id: str, mission_id: str
) -> dict[str, Any]:
    """Mark ``mission_id`` complete for ``account_id``. Idempotent.

    Behaviour:

    * Row missing → ``ValueError``.
    * Row belongs to a different account → ``PermissionError``.
    * Row not yet completed → flip ``completed_at`` and emit one
      ``mission_completed`` analytics event.
    * Row already completed → return the same mission record, do NOT
      emit a duplicate analytics event.

    Returns ``{"mission": {...}, "summary": {...},
    "analytics_event_emitted": bool}``.
    """

    ensure_missions_schema(conn)
    row = conn.execute(
        "SELECT * FROM daily_missions WHERE id = ?", (mission_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown mission id: {mission_id}")
    if row["account_id"] != account_id:
        raise PermissionError("mission does not belong to this account")

    event_emitted = False
    if row["completed_at"] is None:
        now = _now_iso()
        conn.execute(
            """
            UPDATE daily_missions
            SET completed_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (now, now, mission_id),
        )
        try:
            payload = json.loads(row["payload"]) if row["payload"] else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}
        _insert_analytics_event(
            conn,
            account_id=account_id,
            event="mission_completed",
            mission_id=mission_id,
            kind=row["kind"],
            skill=row["skill"],
            payload={
                "slot": row["slot"],
                "title": row["title"],
                "local_date": row["local_date"],
                "mission_payload": payload,
            },
        )
        event_emitted = True
        conn.commit()
        row = conn.execute(
            "SELECT * FROM daily_missions WHERE id = ?", (mission_id,)
        ).fetchone()

    mission = _serialize_mission(row)
    summary_rows = conn.execute(
        """
        SELECT
            SUM(CASE WHEN completed_at IS NOT NULL THEN 1 ELSE 0 END) AS completed,
            COUNT(*) AS total
        FROM daily_missions
        WHERE account_id = ? AND local_date = ?
        """,
        (account_id, row["local_date"]),
    ).fetchone()
    completed = int(summary_rows["completed"] or 0)
    total = int(summary_rows["total"] or 0)
    summary = {
        "completed": completed,
        "total": total,
        "ratio": (completed / total) if total else 0.0,
    }
    logger.info(
        "mission_complete account=%s mission=%s emitted=%s completed=%s/%s",
        account_id,
        mission_id,
        event_emitted,
        completed,
        total,
    )
    return {
        "mission": mission,
        "summary": summary,
        "analytics_event_emitted": event_emitted,
    }


__all__ = [
    "COLD_START_SKILL",
    "MISSION_SLOTS",
    "SLOT_LISTENING",
    "SLOT_WEAK_SKILL",
    "SLOT_WRITING",
    "WEAK_SKILL_LOOKBACK_ATTEMPTS",
    "WRITING_PROMPTS",
    "complete_mission",
    "compute_weak_skill",
    "ensure_missions_schema",
    "get_or_generate_today",
    "local_date_for_account",
]
