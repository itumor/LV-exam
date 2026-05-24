-- T-025 — A2 exam schema tables (Postgres).
--
-- Mirrors migrations/sqlite/001_a2_schema.sql verbatim, modulo PG-native
-- types (TIMESTAMPTZ vs TEXT for created_at). The application services
-- treat both as opaque ISO-8601 strings so the surface is identical.
--
-- Apply order: this file MUST run AFTER 001_initial_auth_attempts.sql so
-- that the schema_migrations ledger table already exists.
--
-- Tables: exam_levels, skills, task_types, exam_parts.
-- All idempotent (IF NOT EXISTS); safe to re-run.

-- ---------------------------------------------------------------
-- exam_levels: CEFR level catalogue (A2/B1/B2).
-- The 9/15-per-skill A2 pass rule is stored as min_per_skill.
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
-- skills: one row per (level, skill). Four rows for A2 @ 15 points.
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
-- task_types: catalog of task formats per skill.
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
-- exam_parts: per-exam ordering + durations.
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
