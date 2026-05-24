-- T-044 — white-label custom-domain mapping (SQLite).
--
-- Maps an inbound HTTP ``Host`` header to a tenant id. The tenant
-- configuration itself lives on disk under ``tenants/<id>.json`` and is
-- loaded by ``server_app/services/tenant.py``. This table only stores the
-- many-to-one host → tenant assignment so an institution can attach
-- multiple domains (apex + ``www.`` + branded subdomain) to a single
-- tenant without re-uploading the theme.
--
-- Idempotent — safe to re-run. Mirrors
-- ``migrations/postgres/004_custom_domains.sql``.

CREATE TABLE IF NOT EXISTS custom_domains (
    host TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    verified INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_custom_domains_tenant
    ON custom_domains (tenant_id);
