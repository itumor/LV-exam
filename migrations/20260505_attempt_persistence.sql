-- Production Postgres schema for persisted Latvian A2 exam attempts.
-- The local MVP server applies an equivalent SQLite schema in server.py.

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    external_account_id TEXT UNIQUE,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS exams (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    level TEXT NOT NULL DEFAULT 'A2',
    language TEXT NOT NULL DEFAULT 'lv',
    content_version INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'published',
    manifest_payload JSONB NOT NULL,
    answer_key_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS attempts (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    exam_id TEXT NOT NULL REFERENCES exams(id),
    exam_title TEXT NOT NULL,
    content_version INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('started', 'in_progress', 'submitted', 'scored', 'expired')),
    exam_snapshot_payload JSONB NOT NULL,
    answer_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    score_total INTEGER,
    score_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    submission_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    submitted_at TIMESTAMPTZ,
    scored_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS attempt_answers (
    id TEXT PRIMARY KEY,
    attempt_id TEXT NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    skill TEXT NOT NULL,
    task_key TEXT NOT NULL,
    item_index INTEGER NOT NULL,
    answer_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(attempt_id, skill, task_key, item_index)
);

CREATE TABLE IF NOT EXISTS attempt_scores (
    id TEXT PRIMARY KEY,
    attempt_id TEXT NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    scoring_version TEXT NOT NULL,
    score_total INTEGER NOT NULL,
    score_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ai_evaluations (
    id TEXT PRIMARY KEY,
    attempt_id TEXT NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL,
    evaluation_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS payments (
    id TEXT PRIMARY KEY,
    user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    provider TEXT NOT NULL,
    provider_reference TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    amount_cents INTEGER,
    currency TEXT,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    provider_reference TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    current_period_end TIMESTAMPTZ,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS entitlements (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    entitlement_type TEXT NOT NULL,
    source_reference TEXT,
    starts_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ,
    consumed_at TIMESTAMPTZ,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_attempts_user_submitted_at ON attempts(user_id, submitted_at DESC);
CREATE INDEX IF NOT EXISTS idx_attempt_answers_attempt ON attempt_answers(attempt_id, skill, task_key, item_index);
CREATE INDEX IF NOT EXISTS idx_attempt_scores_attempt ON attempt_scores(attempt_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_entitlements_user_type ON entitlements(user_id, entitlement_type, consumed_at, expires_at);
