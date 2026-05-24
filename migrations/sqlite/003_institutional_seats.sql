-- T-041 — Institutional seat licensing + bulk vouchers (SQLite).
--
-- Mirrors :func:`server_app.services.institutional.init_institutional_tables`
-- so an operator can pre-create the tables when re-hydrating a fresh
-- database from backups. The Python service is idempotent and will
-- create the tables lazily on first request either way; this file
-- exists for parity with migrations/postgres/006_institutional_seats.sql
-- and the rest of the migrations layout.
--
-- All tables are additive (IF NOT EXISTS); safe to re-run.

-- ---------------------------------------------------------------
-- organizations: one row per institutional customer.
--
-- Owner-account is the human responsible for seat assignment and
-- billing. ``stripe_subscription_id`` (nullable) links to the
-- seat-based Stripe subscription created in T-041 step 5.
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
-- org_seats: seat cap + usage counter. Exactly one row per org.
--
-- ``used_seats`` is denormalised for cheap reads; it must always
-- equal the count of active rows in ``org_members``. The service
-- maintains the invariant inside a serialised transaction.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS org_seats (
    org_id TEXT PRIMARY KEY REFERENCES organizations(id) ON DELETE CASCADE,
    max_seats INTEGER NOT NULL,
    used_seats INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

-- ---------------------------------------------------------------
-- org_members: account <-> org link. One row per (org, account).
--
-- Status is one of {'active','revoked'}. Revoked rows are kept for
-- audit; entitlement extension only counts ``status='active'``.
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
-- vouchers: single-use redemption codes for seat invites.
--
-- ``code`` is the human-readable token displayed to the invitee.
-- ``redeemed_by`` is the account_id that consumed it. ``expires_at``
-- (nullable) limits the redemption window. Vouchers are single-use:
-- once ``redeemed_at`` is non-null the row may not be re-used.
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
