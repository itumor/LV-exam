"""A2 exam schema service (T-025).

Provides the canonical CEFR-level → skill → task-type → exam-part data
model used by:

* the readiness dashboard (T-030),
* daily-mission generator (T-031),
* mock-exam runner (T-033),
* B1/B2 follow-ups (T-060).

The service is intentionally thin — it owns:

* schema bootstrapping (``init_a2_schema_tables``),
* idempotent seeding of the canonical A2/B1/B2 catalog,
* read helpers consumed by ``GET /api/admin/schema``,
* the **9/15-per-skill A2 pass rule** (:func:`is_passing`) that is also
  surfaced on the learner dashboard as a ``would_pass_exam`` flag.

The 9/15 rule comes from the official Latvian A2 exam regulations
(Naturalizācijas pārvalde) and is reflected in
``docs/exam-content-schema.md`` and the existing scoring code in
``server_app.core.compute_objective_score`` (``minimum_to_pass = 9``).
This module makes that rule a first-class, reusable predicate so the
dashboard and the mock-exam runner do not re-implement it.

The same SQL schema works on Postgres (see
``migrations/postgres/003_a2_schema.sql``) — the service uses only
ANSI-portable SQL and parameter placeholders that
``server_app.services.db.translate_sql_to_pg`` rewrites on the
dual-write path.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Mapping

__all__ = [
    "A2_LEVEL_CODE",
    "A2_MIN_PER_SKILL",
    "A2_TOTAL_POINTS",
    "A2_SKILL_MAX_POINTS",
    "A2_SKILLS",
    "build_schema_response",
    "ensure_seed_data",
    "get_level_by_code",
    "get_skills_for_level",
    "get_task_types_for_skill",
    "init_a2_schema_tables",
    "is_passing",
    "list_levels",
    "would_pass_exam",
]


_LOGGER = logging.getLogger("server_app.schema_a2")


# ---------------------------------------------------------------------------
# Canonical constants — the 9/15 rule lives here.
# ---------------------------------------------------------------------------

# CEFR code for the level this module models. The other levels (B1, B2)
# are seeded too but only A2 has battle-tested scoring code today.
A2_LEVEL_CODE = "A2"

# Maximum points per skill on the official A2 exam (15 each).
A2_SKILL_MAX_POINTS = 15

# Minimum points per skill required to pass — the 9/15 rule.
A2_MIN_PER_SKILL = 9

# Total points across all four skills (60 = 4 × 15).
A2_TOTAL_POINTS = 60

# Skill codes in the canonical order they are administered.
A2_SKILLS: tuple[str, ...] = ("listening", "reading", "writing", "speaking")


# ---------------------------------------------------------------------------
# Schema bootstrapping
# ---------------------------------------------------------------------------

_CREATE_EXAM_LEVELS = """
CREATE TABLE IF NOT EXISTS exam_levels (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    total_points INTEGER NOT NULL CHECK (total_points > 0),
    min_per_skill INTEGER NOT NULL CHECK (min_per_skill >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

_CREATE_SKILLS = """
CREATE TABLE IF NOT EXISTS skills (
    id TEXT PRIMARY KEY,
    level_id TEXT NOT NULL REFERENCES exam_levels(id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    max_points INTEGER NOT NULL CHECK (max_points > 0),
    ordinal INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (level_id, code)
)
"""

_CREATE_TASK_TYPES = """
CREATE TABLE IF NOT EXISTS task_types (
    id TEXT PRIMARY KEY,
    skill_id TEXT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    format TEXT NOT NULL,
    max_points INTEGER NOT NULL CHECK (max_points >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (skill_id, code)
)
"""

_CREATE_EXAM_PARTS = """
CREATE TABLE IF NOT EXISTS exam_parts (
    id TEXT PRIMARY KEY,
    exam_id TEXT NOT NULL,
    skill_id TEXT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL DEFAULT 0,
    duration_seconds INTEGER NOT NULL CHECK (duration_seconds > 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (exam_id, skill_id)
)
"""

_CREATE_INDEX_SKILLS = (
    "CREATE INDEX IF NOT EXISTS idx_skills_level_ordinal "
    "ON skills (level_id, ordinal)"
)
_CREATE_INDEX_TASK_TYPES = (
    "CREATE INDEX IF NOT EXISTS idx_task_types_skill "
    "ON task_types (skill_id)"
)
_CREATE_INDEX_EXAM_PARTS = (
    "CREATE INDEX IF NOT EXISTS idx_exam_parts_exam_ordinal "
    "ON exam_parts (exam_id, ordinal)"
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def init_a2_schema_tables(conn: sqlite3.Connection) -> None:
    """Create the four A2-schema tables if they do not already exist.

    Idempotent. Safe to call from ``init_auth_store`` at app boot or from
    individual entry points (the seed script, tests).
    """

    conn.execute(_CREATE_EXAM_LEVELS)
    conn.execute(_CREATE_SKILLS)
    conn.execute(_CREATE_TASK_TYPES)
    conn.execute(_CREATE_EXAM_PARTS)
    conn.execute(_CREATE_INDEX_SKILLS)
    conn.execute(_CREATE_INDEX_TASK_TYPES)
    conn.execute(_CREATE_INDEX_EXAM_PARTS)


# ---------------------------------------------------------------------------
# Seed data — the canonical A2 + skeleton B1/B2 rows.
# ---------------------------------------------------------------------------

# (level_id, code, name, total_points, min_per_skill)
_SEED_LEVELS: tuple[tuple[str, str, str, int, int], ...] = (
    ("lvl_a2", "A2", "CEFR A2 (Latvian — naturalization)", 60, 9),
    ("lvl_b1", "B1", "CEFR B1 (Latvian)", 60, 12),
    ("lvl_b2", "B2", "CEFR B2 (Latvian)", 60, 15),
)

# (skill_id, level_code, code, name, max_points, ordinal)
_SEED_SKILLS: tuple[tuple[str, str, str, str, int, int], ...] = (
    # A2 — official 4 skills × 15 points each.
    ("skl_a2_listening", "A2", "listening", "Klausīšanās", 15, 1),
    ("skl_a2_reading", "A2", "reading", "Lasīšana", 15, 2),
    ("skl_a2_writing", "A2", "writing", "Rakstīšana", 15, 3),
    ("skl_a2_speaking", "A2", "speaking", "Runāšana", 15, 4),
    # B1 — same shape, higher threshold (encoded on the level row).
    ("skl_b1_listening", "B1", "listening", "Klausīšanās", 15, 1),
    ("skl_b1_reading", "B1", "reading", "Lasīšana", 15, 2),
    ("skl_b1_writing", "B1", "writing", "Rakstīšana", 15, 3),
    ("skl_b1_speaking", "B1", "speaking", "Runāšana", 15, 4),
    # B2 — placeholder; content lands in T-060.
    ("skl_b2_listening", "B2", "listening", "Klausīšanās", 15, 1),
    ("skl_b2_reading", "B2", "reading", "Lasīšana", 15, 2),
    ("skl_b2_writing", "B2", "writing", "Rakstīšana", 15, 3),
    ("skl_b2_speaking", "B2", "speaking", "Runāšana", 15, 4),
)

# (task_type_id, skill_code (A2 only), code, format, max_points)
_SEED_TASK_TYPES: tuple[tuple[str, str, str, str, int], ...] = (
    # Listening — short audio + comprehension prompts.
    ("tt_a2_listen_mc", "listening", "multiple_choice", "multiple_choice", 1),
    ("tt_a2_listen_match", "listening", "matching", "matching", 1),
    ("tt_a2_listen_tf", "listening", "true_false", "true_false", 1),
    # Reading — short texts, signs, advertisements.
    ("tt_a2_read_mc", "reading", "multiple_choice", "multiple_choice", 1),
    ("tt_a2_read_gap", "reading", "fill_blank", "fill_blank", 1),
    ("tt_a2_read_match", "reading", "matching", "matching", 1),
    # Writing — short note + short letter.
    ("tt_a2_write_note", "writing", "short_note", "short_text", 5),
    ("tt_a2_write_letter", "writing", "informal_letter", "essay", 10),
    # Speaking — monologue + dialogue + picture description.
    ("tt_a2_speak_monologue", "speaking", "monologue", "recording", 5),
    ("tt_a2_speak_dialogue", "speaking", "dialogue", "recording", 5),
    ("tt_a2_speak_picture", "speaking", "picture_description", "recording", 5),
)

# Per-skill duration in seconds for the canonical A2 mock exam, used to
# seed exam_parts for the built-in ``a2-builtin`` exam id. The 35/25/35/15
# split mirrors the official Naturalizācijas pārvalde sitting and is also
# reflected in the existing ``exam_bank.py`` content.
_SEED_EXAM_PARTS: tuple[tuple[str, str, str, int, int], ...] = (
    # (exam_part_id, exam_id, skill_code (A2 only), ordinal, duration_seconds)
    ("part_a2_builtin_listening", "a2-builtin", "listening", 1, 35 * 60),
    ("part_a2_builtin_reading", "a2-builtin", "reading", 2, 25 * 60),
    ("part_a2_builtin_writing", "a2-builtin", "writing", 3, 35 * 60),
    ("part_a2_builtin_speaking", "a2-builtin", "speaking", 4, 15 * 60),
)


def ensure_seed_data(conn: sqlite3.Connection) -> dict[str, int]:
    """Idempotently seed the A2/B1/B2 catalog.

    Inserts only rows that are missing — every statement uses
    ``INSERT OR IGNORE`` so re-running the seed is a no-op. Returns a
    dict of {"levels": int, "skills": int, "task_types": int,
    "exam_parts": int} counting rows inserted on this call (zero on
    second and subsequent calls).
    """

    init_a2_schema_tables(conn)
    now = _now_iso()
    counts: dict[str, int] = {
        "levels": 0,
        "skills": 0,
        "task_types": 0,
        "exam_parts": 0,
    }

    # ---- exam_levels --------------------------------------------------
    for level_id, code, name, total, min_per in _SEED_LEVELS:
        cur = conn.execute(
            "INSERT OR IGNORE INTO exam_levels "
            "(id, code, name, total_points, min_per_skill, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (level_id, code, name, total, min_per, now, now),
        )
        if cur.rowcount > 0:
            counts["levels"] += 1

    # Resolve code -> id for the seeded levels (handles the case where
    # the row already existed under a different id).
    level_ids: dict[str, str] = {}
    for row in conn.execute(
        "SELECT id, code FROM exam_levels WHERE code IN ('A2','B1','B2')"
    ).fetchall():
        level_ids[row["code"]] = row["id"]

    # ---- skills -------------------------------------------------------
    for skill_id, level_code, code, name, max_pts, ordinal in _SEED_SKILLS:
        lvl_id = level_ids.get(level_code)
        if lvl_id is None:
            continue
        cur = conn.execute(
            "INSERT OR IGNORE INTO skills "
            "(id, level_id, code, name, max_points, ordinal, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (skill_id, lvl_id, code, name, max_pts, ordinal, now, now),
        )
        if cur.rowcount > 0:
            counts["skills"] += 1

    a2_skill_ids: dict[str, str] = {}
    for row in conn.execute(
        "SELECT s.id, s.code FROM skills s "
        "JOIN exam_levels l ON l.id = s.level_id WHERE l.code = 'A2'"
    ).fetchall():
        a2_skill_ids[row["code"]] = row["id"]

    # ---- task_types (A2 only for now) --------------------------------
    for tt_id, skill_code, code, fmt, max_pts in _SEED_TASK_TYPES:
        skl_id = a2_skill_ids.get(skill_code)
        if skl_id is None:
            continue
        cur = conn.execute(
            "INSERT OR IGNORE INTO task_types "
            "(id, skill_id, code, format, max_points, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (tt_id, skl_id, code, fmt, max_pts, now, now),
        )
        if cur.rowcount > 0:
            counts["task_types"] += 1

    # ---- exam_parts (A2 built-in exam) -------------------------------
    for part_id, exam_id, skill_code, ordinal, duration in _SEED_EXAM_PARTS:
        skl_id = a2_skill_ids.get(skill_code)
        if skl_id is None:
            continue
        cur = conn.execute(
            "INSERT OR IGNORE INTO exam_parts "
            "(id, exam_id, skill_id, ordinal, duration_seconds, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (part_id, exam_id, skl_id, ordinal, duration, now, now),
        )
        if cur.rowcount > 0:
            counts["exam_parts"] += 1

    return counts


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------


def _row_to_level(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "code": row["code"],
        "name": row["name"],
        "total_points": int(row["total_points"]),
        "min_per_skill": int(row["min_per_skill"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _row_to_skill(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "level_id": row["level_id"],
        "code": row["code"],
        "name": row["name"],
        "max_points": int(row["max_points"]),
        "ordinal": int(row["ordinal"]),
    }


def _row_to_task_type(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "skill_id": row["skill_id"],
        "code": row["code"],
        "format": row["format"],
        "max_points": int(row["max_points"]),
    }


def list_levels(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    init_a2_schema_tables(conn)
    rows = conn.execute(
        "SELECT * FROM exam_levels ORDER BY code"
    ).fetchall()
    return [_row_to_level(r) for r in rows]


def get_level_by_code(
    conn: sqlite3.Connection, code: str
) -> dict[str, Any] | None:
    init_a2_schema_tables(conn)
    row = conn.execute(
        "SELECT * FROM exam_levels WHERE code = ?", (code,)
    ).fetchone()
    return _row_to_level(row) if row is not None else None


def get_skills_for_level(
    conn: sqlite3.Connection, level_id: str
) -> list[dict[str, Any]]:
    init_a2_schema_tables(conn)
    rows = conn.execute(
        "SELECT * FROM skills WHERE level_id = ? ORDER BY ordinal, code",
        (level_id,),
    ).fetchall()
    return [_row_to_skill(r) for r in rows]


def get_task_types_for_skill(
    conn: sqlite3.Connection, skill_id: str
) -> list[dict[str, Any]]:
    init_a2_schema_tables(conn)
    rows = conn.execute(
        "SELECT * FROM task_types WHERE skill_id = ? ORDER BY code",
        (skill_id,),
    ).fetchall()
    return [_row_to_task_type(r) for r in rows]


def build_schema_response(
    conn: sqlite3.Connection, level_code: str = A2_LEVEL_CODE
) -> dict[str, Any]:
    """Return the level + skills + task_types payload for the admin route.

    Shape:

    .. code-block:: json

        {
          "level": {"id": "...", "code": "A2", ...},
          "skills": [
            {
              "id": "...", "code": "listening", "name": "...",
              "max_points": 15, "ordinal": 1,
              "task_types": [{"id": "...", "code": "multiple_choice", ...}]
            },
            ...
          ]
        }

    Returns ``{"level": None, "skills": []}`` if the level is unseeded —
    the admin UI will then prompt the operator to run ``ensure_seed_data``.
    """

    level = get_level_by_code(conn, level_code)
    if level is None:
        return {"level": None, "skills": []}
    skills = get_skills_for_level(conn, level["id"])
    out: list[dict[str, Any]] = []
    for skill in skills:
        skill_view = dict(skill)
        skill_view["task_types"] = get_task_types_for_skill(conn, skill["id"])
        out.append(skill_view)
    return {"level": level, "skills": out}


# ---------------------------------------------------------------------------
# The 9/15 pass rule
# ---------------------------------------------------------------------------


def is_passing(
    skill_scores: Mapping[str, Any],
    *,
    min_per_skill: int = A2_MIN_PER_SKILL,
    required_skills: tuple[str, ...] = A2_SKILLS,
) -> bool:
    """Return ``True`` when ``skill_scores`` clears the 9/15-per-skill rule.

    Parameters
    ----------
    skill_scores
        Mapping of ``skill_code -> points``. Both the canonical
        ``{"listening": 12, "reading": 11, ...}`` shape and the
        ``compute_objective_score`` shape (``{"listening": {"points": 12}}``
        or ``{"listening": {"objective_correct": 12}}``) are accepted. Any
        skill missing from the mapping is treated as ``0`` points and
        therefore fails.
    min_per_skill
        Threshold each skill must clear. Defaults to ``A2_MIN_PER_SKILL``
        (9) — pass an explicit value when scoring a B1/B2 attempt.
    required_skills
        The skills required to pass. Defaults to all four A2 skills.
        Pass a subset when scoring a partial mock that only covers
        some skills (the caller is then telling us "do not enforce
        readiness for skills not yet attempted").

    Returns
    -------
    bool
        True iff every required skill has at least ``min_per_skill``
        points. False if any skill is below threshold or missing.

    Notes
    -----
    The rule is the official Latvian-A2 naturalization threshold; see
    ``docs/exam-content-schema.md`` and the ``minimum_to_pass`` field on
    every ``compute_objective_score`` skill bucket. This function is the
    single source of truth — the dashboard, the mock-exam result page,
    and the readiness UI all funnel through here.
    """

    if not isinstance(skill_scores, Mapping):
        return False
    for skill in required_skills:
        raw = skill_scores.get(skill)
        points = _extract_points(raw)
        if points is None or points < min_per_skill:
            return False
    return True


def _extract_points(value: Any) -> int | None:
    """Coerce a learner-side score shape into an integer point total.

    Accepts:

    * plain ``int`` / ``float`` (rounded to int);
    * ``{"points": int}`` (canonical compact form);
    * ``{"objective_correct": int}`` (the
      ``compute_objective_score`` per-skill bucket — we treat objective
      correctness as the lower-bound pre-AI score, which is exactly the
      "minimum guaranteed points" we want the dashboard to gate on);
    * ``{"score": int}`` (a legacy shape used by ``exam_bank.py``).

    Returns ``None`` when nothing usable is present.
    """

    if value is None:
        return None
    if isinstance(value, bool):
        # ``bool`` is a subclass of int — reject explicitly so a stray
        # ``True``/``False`` doesn't masquerade as 1/0 points.
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, Mapping):
        for key in ("points", "objective_correct", "score", "score_0_to_15"):
            if key in value:
                inner = value[key]
                if isinstance(inner, bool):
                    return None
                if isinstance(inner, (int, float)):
                    return int(inner)
    return None


def would_pass_exam(
    skill_progress: Mapping[str, Any] | None,
    *,
    min_per_skill: int = A2_MIN_PER_SKILL,
) -> bool:
    """Dashboard-friendly wrapper around :func:`is_passing`.

    ``skill_progress`` is the structure ``build_dashboard`` already emits
    on the learner dashboard (``{"listening": {"objective_correct": 12,
    "objective_possible": 15}, ...}``). Returns ``False`` for ``None`` /
    empty / partial data so the UI defaults to "not yet passing".
    """

    if not skill_progress:
        return False
    return is_passing(skill_progress, min_per_skill=min_per_skill)
