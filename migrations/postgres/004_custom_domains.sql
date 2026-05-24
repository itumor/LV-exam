-- T-044 — white-label custom-domain mapping (Postgres).
--
-- Mirrors ``migrations/sqlite/002_custom_domains.sql`` modulo PG-native
-- timestamp types. The application services treat ``created_at`` /
-- ``updated_at`` as opaque ISO-8601 strings so the surface is identical
-- on both engines.
--
-- Apply order: must run AFTER 001_initial_auth_attempts.sql so the
-- ``schema_migrations`` ledger table already exists.
--
-- Idempotent (IF NOT EXISTS); safe to re-run.

CREATE TABLE IF NOT EXISTS custom_domains (
    host TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    verified BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_custom_domains_tenant
    ON custom_domains (tenant_id);
