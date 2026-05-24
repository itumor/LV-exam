-- T-042 — Tutor dashboard: ``organizations.plan_tier`` column.
-- Mirrors the runtime schema produced by
-- :func:`server_app.services.tutor.init_tutor_extensions`. Idempotent.

ALTER TABLE organizations
    ADD COLUMN IF NOT EXISTS plan_tier TEXT NOT NULL DEFAULT 'standard';

-- Backfill any legacy rows (the DEFAULT clause covers new rows, but
-- existing rows on Postgres < 11 may not have inherited the default).
UPDATE organizations SET plan_tier = 'standard' WHERE plan_tier IS NULL;
