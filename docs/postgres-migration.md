# Postgres migration playbook (T-021)

Status: **planning** — dual-write hook landed in T-021. Cutover dates
are tracked in the release-train calendar (`docs/release-process.md`).

## Goal

Move the lvcodex backend from `data/auth.sqlite3` + `data/billing.sqlite3`
on a single Fly volume to a managed Fly Postgres cluster, with **no
read-side downtime** and a fully reversible cutover.

## Approach: dual-write + backfill + flip-reads

```
┌─────────┐    write     ┌──────────┐    mirror    ┌────────────┐
│ caller  │ ───────────► │ SQLite   │ ───────────► │ Postgres   │
│         │              │ (primary)│  dual-write  │ (replica)  │
│         │ ◄─────────── │          │              │            │
└─────────┘    read      └──────────┘              └────────────┘
                              ↑
                              │ backfill_to_postgres.py
                              │ (one-shot, idempotent)
                              ▼
                         historical rows
```

Phases:

| # | Phase | Flags | Reads | Writes | Reversible? |
| - | --- | --- | --- | --- | --- |
| 0 | Pre-cut | none | SQLite | SQLite | n/a |
| 1 | Dual-write on | `LVCODEX_DB_DUAL_WRITE=1`, `DATABASE_URL=…` | SQLite | SQLite + PG (best-effort) | yes — drop the env vars |
| 2 | Backfill | (same) | SQLite | SQLite + PG | yes — drop the env vars |
| 3 | Reads on PG | `LVCODEX_DB_READ_FROM=postgres` | Postgres | SQLite + PG | yes — clear the read flag |
| 4 | SQLite retire | drop `LVCODEX_DB_DUAL_WRITE` | Postgres | Postgres | hard — restore from snapshot |

Each phase change is a **single env-var flip + redeploy** — no code
ships between phases.

## Pre-flight checklist

* [ ] `DATABASE_URL` secret attached to the Fly app (see "Provisioning"
  below). Test with `fly ssh console -C "echo $DATABASE_URL"`.
* [ ] `migrations/postgres/*.sql` applied. Run
  `python3 scripts/backfill_to_postgres.py --dry-run` to verify
  connectivity; the script auto-applies migrations on first non-dry run.
* [ ] SQLite snapshot taken via `scripts/backup_sqlite.sh` and uploaded
  to R2 (T-013). The backup is the rollback path for phase 4.
* [ ] Grafana dashboard panel for the `DUAL_WRITE_STATS` counters
  exposed (T-027 will plumb these into `/metrics`).

## Phase 1 — enable dual-write

1. Set the secrets:
   ```bash
   fly secrets set \
     DATABASE_URL="postgres://lvcodex:***@<cluster>.flycast:5432/lvcodex" \
     LVCODEX_DB_DUAL_WRITE=1 \
     -a latvian-a2-exam
   ```
2. Deploy. Fly will rolling-restart the machines. New writes start
   mirroring to PG immediately.
3. Confirm: tail logs for `dual_write_failed` — should be zero. The
   `DUAL_WRITE_STATS["ok"]` counter increments per successful mirror;
   `DUAL_WRITE_STATS["fail"]` stays at zero.

If failures appear, **the SQLite write still succeeded** — the
dual-write hook is best-effort by design. You can leave the app running
while you investigate.

## Phase 2 — backfill historical rows

```bash
fly ssh console -a latvian-a2-exam
$ python3 scripts/backfill_to_postgres.py \
    --auth-db /app/data/auth.sqlite3 \
    --billing-db /app/data/billing.sqlite3
```

The script is **idempotent** (uses `INSERT … ON CONFLICT DO NOTHING`).
Safe to re-run on partial failure. Expected output:

```
applied migrations: 001_initial_auth_attempts.sql, 002_billing_tables.sql
backfilling auth tables...
  [accounts] 1241 read → 1241 inserted
  [sessions] 87 read → 87 inserted
  …
backfilling billing tables...
  [learners] 1241 read → 1241 inserted
  …
{"read": 12480, "inserted": 12480}
```

### Verification queries

Compare row counts to confirm the backfill is complete before flipping
reads:

```bash
fly ssh console -a latvian-a2-exam
$ sqlite3 /app/data/auth.sqlite3 'SELECT count(*) FROM accounts;'
$ psql "$DATABASE_URL" -c 'SELECT count(*) FROM accounts;'

$ sqlite3 /app/data/auth.sqlite3 'SELECT count(*) FROM attempts;'
$ psql "$DATABASE_URL" -c 'SELECT count(*) FROM attempts;'
```

Both pairs must match. Differences indicate a dual-write gap — re-run
the backfill until they converge.

## Phase 3 — switch reads to Postgres

```bash
fly secrets set LVCODEX_DB_READ_FROM=postgres -a latvian-a2-exam
```

Redeploy. From this point, every read path checks
`server_app.services.db.read_from_postgres()` and routes to PG instead
of SQLite. Writes still go to **both** stores — the dual-write window
is still open.

### Smoke tests

After redeploy:

* Log in with the seed superadmin → confirm session restored.
* Submit a test attempt → confirm it appears in PG and SQLite.
* Inspect a billing event in the admin console.

### Rollback

Clear the read flag and redeploy:

```bash
fly secrets unset LVCODEX_DB_READ_FROM -a latvian-a2-exam
```

Reads flip back to SQLite. No data loss — dual-write was still active
the whole time.

## Phase 4 — retire SQLite

Only after at least 7 calendar days of clean phase 3 operation:

```bash
fly secrets unset LVCODEX_DB_DUAL_WRITE -a latvian-a2-exam
```

Writes now go to Postgres only. Keep the SQLite volume mounted for at
least one more release cycle so an emergency rollback can be performed
by re-enabling the read flag.

Tear down the SQLite volume in the **next** release after the volume is
no longer needed:

```bash
fly volume destroy <volume-id> -a latvian-a2-exam
```

## Provisioning a Fly Postgres cluster

```bash
fly postgres create \
  --name lvcodex-db \
  --region lhr \
  --vm-size shared-cpu-1x \
  --volume-size 10 \
  --initial-cluster-size 1
fly postgres attach lvcodex-db -a latvian-a2-exam
```

`fly postgres attach` automatically writes `DATABASE_URL` to the app's
secrets. Verify with `fly secrets list -a latvian-a2-exam`.

For multi-region readiness (T-028) follow the Fly Postgres
streaming-replica docs.

## Disaster recovery

If Postgres is corrupted mid-cutover:

1. Roll back: `fly secrets unset LVCODEX_DB_READ_FROM` so reads use
   SQLite.
2. Investigate. The SQLite primary is intact — no data loss.
3. Restore PG from the Fly daily backup (`fly postgres backup list`).
4. Re-run `scripts/backfill_to_postgres.py` to close any gap that opened
   while PG was offline.

## Operational metrics

The dual-write hook exports counters in
`server_app.services.db.DUAL_WRITE_STATS`:

| Key | Meaning |
| --- | --- |
| `ok` | Mirror succeeded |
| `fail` | Mirror failed (logged at WARNING) |
| `skipped` | Dual-write disabled / DSN absent |

Wire these into `/metrics` (T-027) once the hook is in production.

## Open questions

* Should we use `psycopg.pool.ConnectionPool` instead of opening a new
  connection per mirror? Not in T-021 — defer until traffic hits the
  level where it matters (pgBouncer is in the Fly stack anyway).
* When to drop the SQLite read code paths? Tracked as **T-021c** — only
  after one full release in phase 4.
