-- T-040 — SSO (OIDC) provider table + nonce ledger (Postgres).
--
-- Mirrors migrations/sqlite/002_sso_providers.sql modulo PG-native
-- types. The Python service layer treats timestamps as opaque
-- ISO-8601 strings so the surface is identical across engines.
--
-- Apply order: this file MUST run AFTER 001_initial_auth_attempts.sql
-- so the schema_migrations ledger table already exists.
--
-- Tables: sso_providers, sso_nonces. Additive (IF NOT EXISTS).

-- ---------------------------------------------------------------
-- sso_providers: one row per org/tenant.
--
-- Sensitive columns (client_id, issuer_url) are Fernet-encrypted at
-- rest using SSO_ENCRYPTION_KEY. The client *secret value* is NEVER
-- stored — only the *name* of the env var that holds it
-- (client_secret_env), so a DB dump alone cannot impersonate the org.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sso_providers (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL DEFAULT 'oidc',
    client_id_encrypted TEXT NOT NULL,
    client_secret_env TEXT NOT NULL,
    issuer_url_encrypted TEXT NOT NULL,
    scopes TEXT NOT NULL DEFAULT 'openid email profile',
    redirect_path TEXT NOT NULL DEFAULT '/sso/oidc/callback',
    auto_provision INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sso_providers_org
    ON sso_providers (org_id);

-- ---------------------------------------------------------------
-- sso_nonces: short-lived ledger to prevent replay of (state, nonce)
-- pairs across the IdP round-trip. Rows are consumed (marked
-- consumed_at) on the callback and purged after expires_at.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sso_nonces (
    state TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    nonce TEXT NOT NULL,
    return_to TEXT,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    consumed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_sso_nonces_expires
    ON sso_nonces (expires_at);
