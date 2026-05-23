-- T-025 — A2 exam schema tables (SQLite).
--
-- Introduces the canonical CEFR-level → skill → task-type hierarchy that
-- the readiness dashboard (T-030), daily missions (T-031), and mock exam
-- (T-033) consume. Mirrors migrations/postgres/003_a2_schema.sql.
--
-- Tables:
--   exam_levels(id PK, code UNIQUE, name, total_points, min_per_skill)
--   skills(id PK, level_id FK, code, name, max_points, ordinal)
--   task_types(id PK, skill_id FK, code, format, max_points)
--   exam_parts(id PK, exam_id, skill_id, ordinal, duration_seconds)
--
-- Idempotent — safe to re-run. Seeding is performed by the application
-- layer (server_app/services/schema_a2.py::ensure_seed_data) so the SQL
-- file remains a pure DDL contract.

-- ---------------------------------------------------------------
-- exam_levels: CEFR level catalogue (A2/B1/B2). The 9/15-per-skill
-- A2 rule is encoded as a row property (min_per_skill = 9) so future
-- B1/B2 packs can declare their own thresholds without code change.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS exam_levels (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    total_points INTEGER NOT NULL CHECK (total_points > 0),
    min_per_skill INTEGER NOT NULL CHECK (min_per_skill >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- ---------------------------------------------------------------
-- skills: one row per (level, skill). A2 has 4 rows (listening,
-- reading, writing, speaking @ 15 points each). max_points is the
-- ceiling for a single skill; aggregating all rows for a level must
-- equal exam_levels.total_points (enforced by seed assertion, not DDL).
-- ---------------------------------------------------------------
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
);

CREATE INDEX IF NOT EXISTS idx_skills_level_ordinal
    ON skills (level_id, ordinal);

-- ---------------------------------------------------------------
-- task_types: catalog of task formats per skill (multiple_choice,
-- fill_blank, essay, recording, etc.). max_points is the maximum the
-- task format can award for a single instance — used by the readiness
-- dashboard to compute weak-skill repair queues.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS task_types (
    id TEXT PRIMARY KEY,
    skill_id TEXT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    format TEXT NOT NULL,
    max_points INTEGER NOT NULL CHECK (max_points >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (skill_id, code)
);

CREATE INDEX IF NOT EXISTS idx_task_types_skill
    ON task_types (skill_id);

-- ---------------------------------------------------------------
-- exam_parts: per-exam ordering of skill sections + their proctored
-- durations. exam_id is a free-form TEXT (intentionally no FK to the
-- exams table — exams.id is also TEXT but the column may not exist in
-- environments where T-021 has not yet been applied; the app layer
-- joins logically).
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS exam_parts (
    id TEXT PRIMARY KEY,
    exam_id TEXT NOT NULL,
    skill_id TEXT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL DEFAULT 0,
    duration_seconds INTEGER NOT NULL CHECK (duration_seconds > 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (exam_id, skill_id)
);

CREATE INDEX IF NOT EXISTS idx_exam_parts_exam_ordinal
    ON exam_parts (exam_id, ordinal);
