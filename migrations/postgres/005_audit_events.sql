-- T-043 — Audit-event ledger for institutional export (Postgres).
--
-- Mirrors the SQLite-side schema created by
-- :func:`server_app.services.audit_export.init_audit_events_table`.
-- Apply order: this file MUST run AFTER
-- ``001_initial_auth_attempts.sql`` because it ALTER-adds ``org_id`` to
-- the ``accounts`` table created there.
--
-- All statements are additive (IF NOT EXISTS / DO $$ guards) so this
-- migration is safe to re-run.

-- ---------------------------------------------------------------
-- accounts.org_id — membership column read by the export endpoint.
-- ---------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = 'accounts'
           AND column_name = 'org_id'
    ) THEN
        ALTER TABLE accounts ADD COLUMN org_id TEXT;
    END IF;
END$$;

CREATE INDEX IF NOT EXISTS idx_accounts_org_id
    ON accounts (org_id);

-- ---------------------------------------------------------------
-- audit_events — append-only ledger keyed by org_id.
--
-- ``payload_json`` is stored as TEXT (not JSONB) intentionally — the
-- export endpoint hands the column back to the operator verbatim. The
-- caller of :func:`record_audit_event` is responsible for redacting
-- secrets before insert.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_events (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    account_id TEXT,
    event TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    source_ip TEXT NOT NULL DEFAULT '',
    user_agent TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_audit_events_org_time
    ON audit_events (org_id, occurred_at);
