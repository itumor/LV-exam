-- T-041 — Institutional seat licensing + bulk vouchers (Postgres).
-- Mirrors migrations/sqlite/003_institutional_seats.sql and the
-- runtime schema produced by
-- :func:`server_app.services.institutional.init_institutional_tables`.
-- Idempotent — safe to re-run.

-- ---------------------------------------------------------------
-- organizations: one row per institutional customer.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS organizations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    owner_account_id TEXT NOT NULL,
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_organizations_owner
    ON organizations (owner_account_id);

-- ---------------------------------------------------------------
-- org_seats: seat cap + denormalised usage counter.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS org_seats (
    org_id TEXT PRIMARY KEY REFERENCES organizations(id) ON DELETE CASCADE,
    max_seats INTEGER NOT NULL,
    used_seats INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

-- ---------------------------------------------------------------
-- org_members: account <-> org link.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS org_members (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    account_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    status TEXT NOT NULL DEFAULT 'active',
    joined_at TEXT NOT NULL,
    revoked_at TEXT,
    UNIQUE(org_id, account_id)
);

CREATE INDEX IF NOT EXISTS idx_org_members_account
    ON org_members (account_id, status);

CREATE INDEX IF NOT EXISTS idx_org_members_org
    ON org_members (org_id, status);

-- ---------------------------------------------------------------
-- vouchers: single-use redemption codes.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vouchers (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    code TEXT NOT NULL UNIQUE,
    invite_email TEXT,
    created_at TEXT NOT NULL,
    expires_at TEXT,
    redeemed_at TEXT,
    redeemed_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_vouchers_org
    ON vouchers (org_id);

CREATE INDEX IF NOT EXISTS idx_vouchers_code
    ON vouchers (code);
