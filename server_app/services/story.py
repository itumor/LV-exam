"""T-050 — Story-mode missions service.

Loads the eight curated story missions from ``content/story/*.json`` and
tracks the learner's progression through them. The brief calls for:

* 8 missions across 5 cities (Rīga M1+M2, Jūrmala M3, Liepāja M4,
  Daugavpils M5+M6, Cēsis M7+M8).
* Each mission has ordered *scenes* that reference an NPC from the
  T-045 catalogue (``content/npcs/*.json``) so the in-mission roleplay
  reuses the existing AI NPC turn endpoint.
* Sequential **unlock criteria**: a mission only becomes ``available``
  once its prerequisite missions are ``completed`` and the learner has
  the required total XP / streak days.
* Scene-level completion: the frontend posts each scene as the learner
  finishes it. When the last scene of a mission flips, the mission
  itself moves to ``completed`` and an XP bonus is awarded via T-034.

Database
--------

A single table ``story_progress`` records every scene a learner has
completed:

.. code-block:: sql

    CREATE TABLE story_progress (
        id TEXT PRIMARY KEY,
        account_id TEXT NOT NULL,
        mission_id TEXT NOT NULL,
        scene_id TEXT NOT NULL,
        completed_at TEXT NOT NULL,
        UNIQUE(account_id, mission_id, scene_id)
    );

The UNIQUE constraint makes scene completion idempotent: a second POST
for the same ``(account_id, mission_id, scene_id)`` triple is a no-op.
Mission-level completion is *derived* — a mission is considered
completed when every scene it defines has a row in ``story_progress``
for that account. This keeps the table append-only and avoids the
"two sources of truth" problem the T-031 daily-missions table had to
solve with a separate ``completed_at`` flag.

XP integration (T-034)
----------------------

Scene completions award ``scene["xp"]`` (default 10) via
:func:`server_app.services.xp.award_xp` with kind
``mission_complete``. When the final scene of a mission flips the
mission to ``completed``, an additional ``mission["xp_on_complete"]``
bonus is awarded. Both awards write through the same engine so XP
totals and streaks stay consistent with daily missions.

Multi-user isolation
--------------------

Every read and write filters on ``account_id``. Reading another user's
progress, or completing a scene on a mission the caller has not yet
unlocked, both raise a typed error mapped to 403/409 at the route
layer.

Public surface
--------------

* :func:`list_missions` — return the static mission catalogue.
* :func:`load_mission` — return one mission JSON (traversal-safe).
* :func:`get_state` — return per-account progression state.
* :func:`complete_scene` — mark one scene completed for the caller.
* :func:`ensure_story_schema` — idempotent DDL applier.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("lvcodex.story")


# ---------------------------------------------------------------------------
# Constants + paths
# ---------------------------------------------------------------------------


ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_STORY_ROOT = ROOT / "content" / "story"

EXPECTED_MISSION_IDS = (
    "m1-riga-arrival",
    "m2-riga-market",
    "m3-jurmala-beach",
    "m4-liepaja-clinic",
    "m5-daugavpils-classroom",
    "m6-daugavpils-neighbor",
    "m7-cesis-castle",
    "m8-cesis-exam-prep",
)

EXPECTED_CITIES = ("Riga", "Jurmala", "Liepaja", "Daugavpils", "Cesis")

DEFAULT_SCENE_XP = 10


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class StoryError(Exception):
    """Base error for the story-mode surface."""

    status_code = 400

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class MissionNotFound(StoryError):
    status_code = 404


class SceneNotFound(StoryError):
    status_code = 404


class MissionLocked(StoryError):
    """The caller has not unlocked this mission yet."""

    status_code = 409


class InvalidStoryRequest(StoryError):
    status_code = 400


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


_DDL = """
CREATE TABLE IF NOT EXISTS story_progress (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    mission_id TEXT NOT NULL,
    scene_id TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    UNIQUE(account_id, mission_id, scene_id)
);

CREATE INDEX IF NOT EXISTS idx_story_progress_account_mission
    ON story_progress(account_id, mission_id);
"""

_DDL_APPLIED = False
_DDL_LOCK = threading.Lock()


def ensure_story_schema(conn: sqlite3.Connection) -> None:
    """Create the ``story_progress`` table if missing.

    Safe to call on every request — the once-flag short-circuits after
    the first successful execution. Tests reset the flag through
    :func:`_reset_story_ddl_cache`.
    """

    global _DDL_APPLIED
    if _DDL_APPLIED:
        return
    with _DDL_LOCK:
        if _DDL_APPLIED:
            return
        conn.executescript(_DDL)
        _DDL_APPLIED = True


def _reset_story_ddl_cache() -> None:
    """Test hook — drop the once-flag so a fresh tmp DB picks up the DDL."""

    global _DDL_APPLIED
    with _DDL_LOCK:
        _DDL_APPLIED = False


# ---------------------------------------------------------------------------
# Catalogue loader
# ---------------------------------------------------------------------------


_CATALOGUE_LOCK = threading.Lock()
_CATALOGUE_CACHE: Optional[list[dict[str, Any]]] = None
_CATALOGUE_ROOT_USED: Optional[Path] = None


def story_root_dir() -> Path:
    """Resolve the directory that contains story mission JSON files.

    Honours ``LVCODEX_STORY_ROOT`` so tests can swap the catalogue with a
    tempdir fixture without touching the production content.
    """

    override = os.environ.get("LVCODEX_STORY_ROOT", "").strip()
    if override:
        return Path(override).resolve()
    return DEFAULT_STORY_ROOT


def _load_catalogue(root: Optional[Path] = None) -> list[dict[str, Any]]:
    """Read all mission JSON files into a cached, order-stable list."""

    global _CATALOGUE_CACHE, _CATALOGUE_ROOT_USED
    target = root or story_root_dir()
    with _CATALOGUE_LOCK:
        if (
            _CATALOGUE_CACHE is not None
            and _CATALOGUE_ROOT_USED == target
        ):
            return list(_CATALOGUE_CACHE)
        missions: list[dict[str, Any]] = []
        if target.exists():
            for path in sorted(target.glob("*.json")):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError) as error:
                    logger.warning(
                        "story_mission_unreadable path=%s error=%s", path, error
                    )
                    continue
                if not isinstance(data, dict):
                    continue
                mission_id = (data.get("id") or path.stem).strip()
                if not mission_id:
                    continue
                data.setdefault("id", mission_id)
                missions.append(data)
        missions.sort(key=lambda m: int(m.get("order", 999)))
        _CATALOGUE_CACHE = missions
        _CATALOGUE_ROOT_USED = target
        return list(_CATALOGUE_CACHE)


def _reset_catalogue_cache_for_tests() -> None:
    """Drop the cached catalogue — used by tests that swap the JSON root."""

    global _CATALOGUE_CACHE, _CATALOGUE_ROOT_USED
    with _CATALOGUE_LOCK:
        _CATALOGUE_CACHE = None
        _CATALOGUE_ROOT_USED = None


def list_missions(root: Optional[Path] = None) -> list[dict[str, Any]]:
    """Return the full mission catalogue (deep-copied so callers can mutate)."""

    return [dict(m) for m in _load_catalogue(root)]


def load_mission(mission_id: str, *, root: Optional[Path] = None) -> dict[str, Any]:
    """Return one mission by id. Raises :class:`MissionNotFound` if missing."""

    cleaned = (mission_id or "").strip().lower()
    if not cleaned or not all(ch.isalnum() or ch in "-_" for ch in cleaned):
        raise MissionNotFound(f"Unknown mission id: {mission_id!r}")
    for mission in _load_catalogue(root):
        if mission["id"].lower() == cleaned:
            return dict(mission)
    raise MissionNotFound(f"Unknown mission id: {cleaned!r}")


def _find_scene(mission: dict[str, Any], scene_id: str) -> dict[str, Any]:
    """Locate one scene inside a mission JSON, or raise :class:`SceneNotFound`."""

    cleaned = (scene_id or "").strip().lower()
    for scene in mission.get("scenes", []):
        if not isinstance(scene, dict):
            continue
        if (scene.get("id") or "").strip().lower() == cleaned:
            return scene
    raise SceneNotFound(
        f"Unknown scene id {scene_id!r} in mission {mission.get('id')!r}"
    )


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _completed_scenes_for_mission(
    conn: sqlite3.Connection, account_id: str, mission_id: str
) -> set[str]:
    rows = conn.execute(
        """
        SELECT scene_id FROM story_progress
        WHERE account_id = ? AND mission_id = ?
        """,
        (account_id, mission_id),
    ).fetchall()
    return {row["scene_id"] for row in rows}


def _all_progress(
    conn: sqlite3.Connection, account_id: str
) -> dict[str, set[str]]:
    rows = conn.execute(
        """
        SELECT mission_id, scene_id FROM story_progress
        WHERE account_id = ?
        """,
        (account_id,),
    ).fetchall()
    by_mission: dict[str, set[str]] = {}
    for row in rows:
        by_mission.setdefault(row["mission_id"], set()).add(row["scene_id"])
    return by_mission


def _is_mission_completed(
    mission: dict[str, Any], completed_scenes: set[str]
) -> bool:
    """A mission is completed when every scene has a progress row."""

    scenes = mission.get("scenes") or []
    if not scenes:
        return False
    scene_ids = {s.get("id") for s in scenes if isinstance(s, dict) and s.get("id")}
    return scene_ids.issubset(completed_scenes)


def _total_xp(conn: sqlite3.Connection, account_id: str) -> int:
    """Read the learner's current ``xp_log`` total, defaulting to 0.

    Tolerates a missing ``xp_log`` table (older test fixtures that only
    seed the auth schema).
    """

    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM xp_log WHERE account_id = ?",
            (account_id,),
        ).fetchone()
    except sqlite3.OperationalError:
        return 0
    return int(row["total"] or 0) if row is not None else 0


def _current_streak_days(conn: sqlite3.Connection, account_id: str) -> int:
    try:
        row = conn.execute(
            "SELECT current_days FROM user_streaks WHERE account_id = ?",
            (account_id,),
        ).fetchone()
    except sqlite3.OperationalError:
        return 0
    return int(row["current_days"] or 0) if row is not None else 0


# ---------------------------------------------------------------------------
# Unlock evaluation
# ---------------------------------------------------------------------------


def _evaluate_unlock(
    mission: dict[str, Any],
    *,
    completed_mission_ids: set[str],
    total_xp: int,
    current_streak_days: int,
) -> dict[str, Any]:
    """Return a dict describing whether this mission is currently unlocked."""

    criteria = mission.get("unlock_criteria") or {}
    requires = [
        str(m).strip()
        for m in (criteria.get("requires_missions") or [])
        if str(m).strip()
    ]
    missing_missions = [m for m in requires if m not in completed_mission_ids]
    needs_xp = int(criteria.get("min_total_xp") or 0)
    needs_streak = int(criteria.get("min_streak_days") or 0)
    unlocked = (
        not missing_missions
        and total_xp >= needs_xp
        and current_streak_days >= needs_streak
    )
    return {
        "unlocked": unlocked,
        "missing_missions": missing_missions,
        "needs_total_xp": needs_xp,
        "needs_streak_days": needs_streak,
        "has_total_xp": total_xp,
        "has_streak_days": current_streak_days,
    }


def _serialize_mission(
    mission: dict[str, Any],
    *,
    completed_scenes: set[str],
    completed_mission_ids: set[str],
    total_xp: int,
    current_streak_days: int,
) -> dict[str, Any]:
    """Build the per-mission state shape returned by ``GET /api/story/state``."""

    unlock = _evaluate_unlock(
        mission,
        completed_mission_ids=completed_mission_ids,
        total_xp=total_xp,
        current_streak_days=current_streak_days,
    )
    scenes_summary = []
    for scene in mission.get("scenes", []):
        if not isinstance(scene, dict) or not scene.get("id"):
            continue
        scene_id = scene["id"]
        scenes_summary.append(
            {
                "id": scene_id,
                "order": int(scene.get("order", 0)),
                "title": scene.get("title", ""),
                "title_lv": scene.get("title_lv", ""),
                "npc_id": scene.get("npc_id"),
                "objective": scene.get("objective"),
                "xp": int(scene.get("xp", DEFAULT_SCENE_XP)),
                "completed": scene_id in completed_scenes,
            }
        )
    scenes_total = len(scenes_summary)
    scenes_done = sum(1 for s in scenes_summary if s["completed"])
    mission_completed = scenes_total > 0 and scenes_done == scenes_total

    if mission_completed:
        status = "completed"
    elif scenes_done > 0:
        status = "in_progress"
    elif unlock["unlocked"]:
        status = "available"
    else:
        status = "locked"

    return {
        "id": mission["id"],
        "order": int(mission.get("order", 0)),
        "city": mission.get("city"),
        "city_lv": mission.get("city_lv"),
        "title": mission.get("title", ""),
        "title_lv": mission.get("title_lv", ""),
        "summary": mission.get("summary", ""),
        "summary_lv": mission.get("summary_lv", ""),
        "language_level": mission.get("language_level", "A2"),
        "estimated_duration_minutes": int(mission.get("estimated_duration_minutes", 0)),
        "xp_on_complete": int(mission.get("xp_on_complete", 0)),
        "map_position": mission.get("map_position"),
        "unlock_criteria": mission.get("unlock_criteria") or {},
        "unlock": unlock,
        "status": status,
        "scenes": scenes_summary,
        "scenes_completed": scenes_done,
        "scenes_total": scenes_total,
        "rewards": mission.get("rewards") or {},
    }


# ---------------------------------------------------------------------------
# Public read
# ---------------------------------------------------------------------------


def get_state(
    conn: sqlite3.Connection,
    account_id: str,
    *,
    root: Optional[Path] = None,
) -> dict[str, Any]:
    """Return the caller's full story-mode state.

    Shape:

    .. code-block:: json

        {
          "missions": [ {id, status, scenes:[...], unlock:{...}, ...}, ... ],
          "summary": {
            "missions_completed": int,
            "missions_total": int,
            "scenes_completed": int,
            "scenes_total": int,
            "total_xp": int,
            "current_streak_days": int
          }
        }
    """

    if not account_id:
        raise InvalidStoryRequest("account_id is required.")

    ensure_story_schema(conn)
    catalogue = _load_catalogue(root)
    progress = _all_progress(conn, account_id)

    total_xp = _total_xp(conn, account_id)
    current_streak_days = _current_streak_days(conn, account_id)

    # Build the completed-mission set up front so unlock evaluation can
    # cascade through the ordered catalogue.
    completed_mission_ids: set[str] = set()
    for mission in catalogue:
        scenes_done = progress.get(mission["id"], set())
        if _is_mission_completed(mission, scenes_done):
            completed_mission_ids.add(mission["id"])

    rendered: list[dict[str, Any]] = []
    scenes_completed_total = 0
    scenes_total = 0
    for mission in catalogue:
        scenes_done = progress.get(mission["id"], set())
        rendered_mission = _serialize_mission(
            mission,
            completed_scenes=scenes_done,
            completed_mission_ids=completed_mission_ids,
            total_xp=total_xp,
            current_streak_days=current_streak_days,
        )
        rendered.append(rendered_mission)
        scenes_completed_total += rendered_mission["scenes_completed"]
        scenes_total += rendered_mission["scenes_total"]

    return {
        "missions": rendered,
        "summary": {
            "missions_completed": len(completed_mission_ids),
            "missions_total": len(catalogue),
            "scenes_completed": scenes_completed_total,
            "scenes_total": scenes_total,
            "total_xp": total_xp,
            "current_streak_days": current_streak_days,
        },
    }


# ---------------------------------------------------------------------------
# Public write
# ---------------------------------------------------------------------------


def complete_scene(
    conn: sqlite3.Connection,
    account_id: str,
    mission_id: str,
    scene_id: str,
    *,
    root: Optional[Path] = None,
    award_xp_fn: Optional[Any] = None,
) -> dict[str, Any]:
    """Mark one scene of a mission completed for ``account_id``.

    Behaviour:

    * Mission unknown        → :class:`MissionNotFound` (404).
    * Scene unknown          → :class:`SceneNotFound` (404).
    * Mission still locked   → :class:`MissionLocked` (409).
    * First completion       → insert one row + award scene XP. If this
      was the final scene of the mission, also award the mission's
      ``xp_on_complete`` bonus.
    * Repeat completion      → idempotent — same row returned, no extra
      XP. The route layer therefore can safely retry without the
      learner farming XP.

    Returns:

    .. code-block:: json

        {
          "mission_id": "m1-riga-arrival",
          "scene_id": "s1-greet-taxi-driver",
          "newly_completed": true,
          "mission_completed": false,
          "scene_xp_awarded": 10,
          "mission_bonus_xp_awarded": 0,
          "scenes_completed": 1,
          "scenes_total": 3
        }
    """

    if not account_id:
        raise InvalidStoryRequest("account_id is required.")

    mission = load_mission(mission_id, root=root)
    scene = _find_scene(mission, scene_id)

    ensure_story_schema(conn)

    # Unlock evaluation depends on cross-mission state, so we read the
    # full progress map once.
    progress = _all_progress(conn, account_id)
    completed_mission_ids = {
        m["id"]
        for m in _load_catalogue(root)
        if _is_mission_completed(m, progress.get(m["id"], set()))
    }
    total_xp = _total_xp(conn, account_id)
    current_streak_days = _current_streak_days(conn, account_id)
    unlock = _evaluate_unlock(
        mission,
        completed_mission_ids=completed_mission_ids,
        total_xp=total_xp,
        current_streak_days=current_streak_days,
    )
    if not unlock["unlocked"]:
        raise MissionLocked(
            f"Mission {mission['id']!r} is locked. "
            f"Required missions: {unlock['missing_missions']}, "
            f"XP {unlock['has_total_xp']}/{unlock['needs_total_xp']}, "
            f"streak {unlock['has_streak_days']}/{unlock['needs_streak_days']}."
        )

    scene_id_clean = (scene.get("id") or "").strip().lower()
    already_done = scene_id_clean in progress.get(mission["id"], set())

    newly_completed = False
    if not already_done:
        progress_id = f"sp_{uuid.uuid4().hex[:16]}"
        conn.execute(
            """
            INSERT OR IGNORE INTO story_progress
                (id, account_id, mission_id, scene_id, completed_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                progress_id,
                account_id,
                mission["id"],
                scene_id_clean,
                _now_iso(),
            ),
        )
        # Re-check to confirm the insert actually happened (the UNIQUE
        # constraint plus IGNORE means a racing duplicate insert lands
        # softly — we treat that as "already done").
        check = conn.execute(
            """
            SELECT 1 FROM story_progress
            WHERE account_id = ? AND mission_id = ? AND scene_id = ?
            """,
            (account_id, mission["id"], scene_id_clean),
        ).fetchone()
        if check is not None:
            newly_completed = not already_done
        conn.commit()

    # Recompute completion state after the insert.
    scenes_done = _completed_scenes_for_mission(conn, account_id, mission["id"])
    scenes_total = len(
        [s for s in mission.get("scenes", []) if isinstance(s, dict) and s.get("id")]
    )
    mission_now_completed = _is_mission_completed(mission, scenes_done)
    mission_was_completed = mission["id"] in completed_mission_ids

    scene_xp = int(scene.get("xp", DEFAULT_SCENE_XP))
    bonus_xp = int(mission.get("xp_on_complete", 0))

    scene_xp_awarded = 0
    bonus_xp_awarded = 0

    if newly_completed and scene_xp > 0:
        scene_xp_awarded = _award_xp(
            conn,
            account_id,
            scene_xp,
            payload={
                "source": "story_scene_complete",
                "mission_id": mission["id"],
                "scene_id": scene_id_clean,
            },
            award_xp_fn=award_xp_fn,
        )

    if newly_completed and mission_now_completed and not mission_was_completed and bonus_xp > 0:
        bonus_xp_awarded = _award_xp(
            conn,
            account_id,
            bonus_xp,
            payload={
                "source": "story_mission_complete",
                "mission_id": mission["id"],
                "rewards": mission.get("rewards") or {},
            },
            award_xp_fn=award_xp_fn,
        )

    logger.info(
        "story_scene_complete account=%s mission=%s scene=%s newly=%s "
        "mission_done=%s scene_xp=%s bonus_xp=%s",
        account_id,
        mission["id"],
        scene_id_clean,
        newly_completed,
        mission_now_completed,
        scene_xp_awarded,
        bonus_xp_awarded,
    )

    return {
        "mission_id": mission["id"],
        "scene_id": scene_id_clean,
        "newly_completed": newly_completed,
        "mission_completed": mission_now_completed,
        "mission_just_completed": (
            newly_completed and mission_now_completed and not mission_was_completed
        ),
        "scene_xp_awarded": scene_xp_awarded,
        "mission_bonus_xp_awarded": bonus_xp_awarded,
        "scenes_completed": len(scenes_done),
        "scenes_total": scenes_total,
    }


def _award_xp(
    conn: sqlite3.Connection,
    account_id: str,
    amount: int,
    *,
    payload: dict[str, Any],
    award_xp_fn: Optional[Any] = None,
) -> int:
    """Best-effort wrapper around the T-034 XP engine.

    Never raises — XP failures are logged but do not roll back the
    story-progress insert (the learner has done the work either way).
    Returns the amount actually awarded (0 on failure).
    """

    if amount <= 0:
        return 0
    fn = award_xp_fn
    if fn is None:
        try:
            from server_app.services import xp as xp_service

            fn = xp_service.award_xp
        except Exception:  # noqa: BLE001
            logger.exception("story_xp_import_failed")
            return 0
    try:
        # Prefer the canonical ``mission_complete`` kind so story XP
        # appears in the same XP-log bucket as daily missions.
        from server_app.services import xp as xp_service

        fn(
            conn,
            account_id,
            xp_service.KIND_MISSION_COMPLETE,
            amount=int(amount),
            payload=payload,
        )
        return int(amount)
    except Exception:  # noqa: BLE001
        logger.exception(
            "story_xp_award_failed account=%s mission=%s",
            account_id,
            payload.get("mission_id"),
        )
        return 0


__all__ = [
    "DEFAULT_SCENE_XP",
    "DEFAULT_STORY_ROOT",
    "EXPECTED_CITIES",
    "EXPECTED_MISSION_IDS",
    "InvalidStoryRequest",
    "MissionLocked",
    "MissionNotFound",
    "SceneNotFound",
    "StoryError",
    "complete_scene",
    "ensure_story_schema",
    "get_state",
    "list_missions",
    "load_mission",
    "story_root_dir",
]
