-- T-021 — Postgres baseline schema for the auth + attempts store.
-- Mirrors the SQLite tables created by `init_auth_store()` in
-- server_app/core.py. Idempotent — safe to re-run.
--
-- Apply order: this file MUST run before 002_billing_tables.sql.

-- ---------------------------------------------------------------
-- accounts: canonical user record. Referenced by users.account_id,
-- attempts.account_id, sessions.account_id, etc.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_salt TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    role TEXT NOT NULL DEFAULT 'user',
    created_at TEXT NOT NULL,
    deleted_at TEXT
);

-- ---------------------------------------------------------------
-- users: external identity bridge (kept for compat with the
-- 20260505 migration draft). One row per account.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    account_id TEXT REFERENCES accounts(id) ON DELETE CASCADE,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    role TEXT NOT NULL DEFAULT 'user',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- ---------------------------------------------------------------
-- profiles: 1:1 with accounts, learner-facing display data.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS profiles (
    account_id TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
    full_name TEXT NOT NULL,
    native_language TEXT,
    exam_target_date TEXT,
    exam_pack_status TEXT NOT NULL DEFAULT 'free',
    updated_at TEXT NOT NULL
);

-- ---------------------------------------------------------------
-- sessions: short-lived auth tokens.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    last_seen_at TEXT NOT NULL
);

-- ---------------------------------------------------------------
-- exams: published exam catalogue.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS exams (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    content_version INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'published',
    manifest_payload TEXT NOT NULL,
    answer_key_payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- ---------------------------------------------------------------
-- attempts: top-level attempt record (per submission).
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS attempts (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    exam_id TEXT NOT NULL,
    exam_title TEXT NOT NULL,
    status TEXT NOT NULL,
    submitted_at TEXT NOT NULL,
    score_total INTEGER,
    score_payload TEXT NOT NULL,
    submission_payload TEXT NOT NULL,
    content_version INTEGER NOT NULL DEFAULT 1,
    exam_snapshot_payload TEXT NOT NULL DEFAULT '{}',
    answer_payload TEXT NOT NULL DEFAULT '{}',
    started_at TEXT,
    expires_at TEXT,
    scored_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- ---------------------------------------------------------------
-- attempt_answers: per-item answer payload.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS attempt_answers (
    id TEXT PRIMARY KEY,
    attempt_id TEXT NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    skill TEXT NOT NULL,
    task_key TEXT NOT NULL,
    item_index INTEGER NOT NULL,
    answer_payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (attempt_id, skill, task_key, item_index)
);

-- ---------------------------------------------------------------
-- attempt_scores: scored snapshots, one per (attempt, scoring_version).
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS attempt_scores (
    id TEXT PRIMARY KEY,
    attempt_id TEXT NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    scoring_version TEXT NOT NULL,
    score_total INTEGER NOT NULL,
    score_payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- ---------------------------------------------------------------
-- exam_attempt_category_score: per-category 0..15 buckets (T-017).
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS exam_attempt_category_score (
    id TEXT PRIMARY KEY,
    attempt_id TEXT NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    category TEXT NOT NULL CHECK (category IN ('listening', 'reading', 'writing', 'speaking')),
    score_0_to_15 INTEGER NOT NULL CHECK (score_0_to_15 >= 0 AND score_0_to_15 <= 15),
    passed_boolean BOOLEAN NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_exam_attempt_category_score_attempt_category
    ON exam_attempt_category_score (attempt_id, category);

CREATE INDEX IF NOT EXISTS idx_exam_attempt_category_score_account_category
    ON exam_attempt_category_score (account_id, category, created_at DESC);

-- ---------------------------------------------------------------
-- ai_evaluations: provider-side LLM scoring traces.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ai_evaluations (
    id TEXT PRIMARY KEY,
    attempt_id TEXT NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL,
    evaluation_payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- ---------------------------------------------------------------
-- payments: Stripe one-off charges.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS payments (
    id TEXT PRIMARY KEY,
    account_id TEXT REFERENCES accounts(id) ON DELETE SET NULL,
    provider TEXT NOT NULL,
    provider_reference TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    amount_cents INTEGER,
    currency TEXT,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- ---------------------------------------------------------------
-- subscriptions: Stripe recurring records.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS subscriptions (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    provider_reference TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    current_period_end TEXT,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- ---------------------------------------------------------------
-- entitlements: server-side feature gates (T-024 will enforce reads).
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS entitlements (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    entitlement_type TEXT NOT NULL,
    source_reference TEXT,
    starts_at TEXT NOT NULL,
    expires_at TEXT,
    consumed_at TEXT,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- ---------------------------------------------------------------
-- auth_webhook_events: idempotency ledger for external webhooks.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS auth_webhook_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- ---------------------------------------------------------------
-- app_settings: free-form KV bucket used by admin tooling.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- ---------------------------------------------------------------
-- Hot read paths the SQLite store also indexes.
-- ---------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_attempts_account_submitted_at
    ON attempts (account_id, submitted_at DESC);

CREATE INDEX IF NOT EXISTS idx_attempt_answers_attempt
    ON attempt_answers (attempt_id, skill, task_key, item_index);

CREATE INDEX IF NOT EXISTS idx_attempt_scores_attempt
    ON attempt_scores (attempt_id, created_at DESC);
