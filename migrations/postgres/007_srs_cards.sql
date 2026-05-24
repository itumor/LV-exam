-- T-032 — Spaced-repetition (SM-2) tables.
--
-- Mirrors the SQLite-side schema created lazily by
-- :func:`server_app.services.srs.ensure_srs_schema`. Apply order: this
-- migration is additive (IF NOT EXISTS) and self-contained — it does
-- not depend on any other 0NN file beyond ``001_initial_auth_attempts``
-- (which creates the ``accounts`` table the FK below references).
--
-- All statements are idempotent so this migration is safe to re-run.

CREATE TABLE IF NOT EXISTS srs_cards (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    lemma TEXT NOT NULL,
    lv TEXT NOT NULL,
    en TEXT NOT NULL,
    ease DOUBLE PRECISION NOT NULL DEFAULT 2.5,
    interval_days INTEGER NOT NULL DEFAULT 0,
    repetitions INTEGER NOT NULL DEFAULT 0,
    next_due TEXT NOT NULL,
    last_quality INTEGER,
    last_reviewed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(account_id, lemma)
);

CREATE INDEX IF NOT EXISTS idx_srs_cards_account_due
    ON srs_cards (account_id, next_due);

CREATE TABLE IF NOT EXISTS srs_reviews (
    id TEXT PRIMARY KEY,
    card_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    quality INTEGER NOT NULL,
    ease_after DOUBLE PRECISION NOT NULL,
    interval_after INTEGER NOT NULL,
    reviewed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_srs_reviews_card_time
    ON srs_reviews (card_id, reviewed_at DESC);

CREATE INDEX IF NOT EXISTS idx_srs_reviews_account_time
    ON srs_reviews (account_id, reviewed_at DESC);
