-- T-051 — Avatar unlock ledger + currently-equipped table (SQLite).
--
-- Mirrors the schema applied lazily by
-- :func:`server_app.services.avatars.ensure_avatar_schema`. The service
-- remains the authoritative DDL applier (tests that swap in a tmp DB
-- still get the tables created on first request); this migration
-- exists for environments that prefer to materialise the schema
-- up-front.

CREATE TABLE IF NOT EXISTS avatar_unlocks (
    account_id   TEXT NOT NULL,
    avatar_id    TEXT NOT NULL,
    unlocked_at  TEXT NOT NULL,
    source       TEXT NOT NULL,
    PRIMARY KEY (account_id, avatar_id)
);

CREATE INDEX IF NOT EXISTS idx_avatar_unlocks_account
    ON avatar_unlocks(account_id);

CREATE TABLE IF NOT EXISTS account_avatars (
    account_id  TEXT PRIMARY KEY,
    avatar_id   TEXT NOT NULL,
    equipped_at TEXT NOT NULL
);
