-- T-051 — Avatar unlock ledger + equipped-avatar table.
--
-- Mirrors the SQLite-side schema created lazily by
-- :func:`server_app.services.avatars.ensure_avatar_schema`. Apply
-- order: this migration is additive (IF NOT EXISTS) and self-contained
-- — it does not depend on any other 0NN file beyond
-- ``001_initial_auth_attempts`` (which creates the ``accounts`` table
-- referenced as the natural foreign key target). All statements are
-- idempotent so this migration is safe to re-run.

CREATE TABLE IF NOT EXISTS avatar_unlocks (
    account_id   TEXT NOT NULL,
    avatar_id    TEXT NOT NULL,
    unlocked_at  TEXT NOT NULL,
    source       TEXT NOT NULL,
    PRIMARY KEY (account_id, avatar_id)
);

CREATE INDEX IF NOT EXISTS idx_avatar_unlocks_account
    ON avatar_unlocks (account_id);

CREATE TABLE IF NOT EXISTS account_avatars (
    account_id  TEXT PRIMARY KEY,
    avatar_id   TEXT NOT NULL,
    equipped_at TEXT NOT NULL
);
