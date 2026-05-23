-- T-021 — Postgres schema for the billing.py SQLite store.
-- Mirrors the tables created by BillingStore._initialize_schema() in
-- billing.py. Idempotent — safe to re-run.

-- ---------------------------------------------------------------
-- learners: billing-side identity. NOT the same row as accounts;
-- the two are joined by learner_id == account.id at the app layer.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS learners (
    learner_id TEXT PRIMARY KEY,
    email TEXT,
    name TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- ---------------------------------------------------------------
-- stripe_events: idempotent Stripe webhook ledger.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS stripe_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    learner_id TEXT,
    created_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

-- ---------------------------------------------------------------
-- entitlement_grants: every credit/exam/AI grant issued.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS entitlement_grants (
    grant_id TEXT PRIMARY KEY,
    learner_id TEXT NOT NULL REFERENCES learners (learner_id) ON DELETE CASCADE,
    grant_type TEXT NOT NULL,
    product_key TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    exam_id TEXT,
    customer_id TEXT,
    source_reference TEXT,
    expires_at TEXT,
    revoked_at TEXT,
    source_event_id TEXT,
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL
);

-- ---------------------------------------------------------------
-- entitlement_consumptions: every grant consumption (1:N with grants).
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS entitlement_consumptions (
    consumption_id TEXT PRIMARY KEY,
    learner_id TEXT NOT NULL REFERENCES learners (learner_id) ON DELETE CASCADE,
    consumption_type TEXT NOT NULL,
    product_key TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    exam_id TEXT,
    customer_id TEXT,
    source_reference TEXT,
    source_event_id TEXT,
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL
);

-- ---------------------------------------------------------------
-- Indexes mirror the BillingStore SQLite ones.
-- ---------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_entitlement_grants_learner
    ON entitlement_grants (learner_id, grant_type, revoked_at, expires_at);

CREATE INDEX IF NOT EXISTS idx_entitlement_consumptions_learner
    ON entitlement_consumptions (learner_id, consumption_type, exam_id);

CREATE INDEX IF NOT EXISTS idx_stripe_events_learner
    ON stripe_events (learner_id, created_at DESC);
