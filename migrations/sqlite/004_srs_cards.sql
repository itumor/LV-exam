-- T-032 — Spaced-repetition (SM-2) tables (SQLite).
--
-- Mirrors the schema applied lazily by
-- :func:`server_app.services.srs.ensure_srs_schema`. The service is
-- still the authoritative DDL applier (so tests that swap in a tmp DB
-- get the tables created on first request); this migration exists for
-- environments that prefer to materialise the schema up-front.

CREATE TABLE IF NOT EXISTS srs_cards (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    lemma TEXT NOT NULL,
    lv TEXT NOT NULL,
    en TEXT NOT NULL,
    ease REAL NOT NULL DEFAULT 2.5,
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
    ON srs_cards(account_id, next_due);

CREATE TABLE IF NOT EXISTS srs_reviews (
    id TEXT PRIMARY KEY,
    card_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    quality INTEGER NOT NULL,
    ease_after REAL NOT NULL,
    interval_after INTEGER NOT NULL,
    reviewed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_srs_reviews_card_time
    ON srs_reviews(card_id, reviewed_at DESC);

CREATE INDEX IF NOT EXISTS idx_srs_reviews_account_time
    ON srs_reviews(account_id, reviewed_at DESC);
