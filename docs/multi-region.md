# Multi-region Fly warm standby — runbook (T-028)

Status: **planning** — configs and scripts are merged ahead of the
production rollout. No machines have been launched in `fra` yet. Promotion
of the warm standby happens in the release-train ops slot after T-021
finishes its Postgres cutover (see `docs/postgres-migration.md`).

This document is the operator's runbook for:

1. Adding `fra` as a warm standby alongside the `lhr` primary.
2. Configuring Postgres streaming replication so the standby can serve
   reads with a sub-second lag.
3. Failing over to `fra` during a DR event (or planned maintenance) and
   rolling back afterwards.

> See also: `fly.multi-region.toml` (the multi-region Fly config),
> `.github/workflows/region-health.yml` (cross-region monitoring), and
> `scripts/region-failover.sh` (interactive cutover helper).

## Topology

```
                       ┌────────────────────────────┐
                       │     Cloudflare / Fly LB    │
                       └─────────────┬──────────────┘
                                     │
                ┌────────────────────┴────────────────────┐
                ▼                                         ▼
        ┌───────────────┐                         ┌───────────────┐
        │  lhr region   │   streaming WAL         │  fra region   │
        │  PRIMARY      │ ──────────────────────► │  WARM STANDBY │
        │  app: 1-2 vm  │                         │  app: 1-2 vm  │
        │  PG: leader   │                         │  PG: replica  │
        └───────────────┘                         └───────────────┘
                ▲                                         ▲
                │  /healthz returns {"region":"lhr"}      │  /healthz returns {"region":"fra"}
                └─────────────────────────────────────────┘
                          monitored every 5 min
```

## Pre-flight checklist

- [ ] T-021 Postgres migration is at **phase 3** or later (reads on PG).
  Multi-region with mixed SQLite + PG is not supported.
- [ ] `DATABASE_URL` secret is attached to the app and points at the PG
  leader's Flycast address.
- [ ] `fly auth whoami` succeeds for the deploy operator.
- [ ] Latest snapshot in R2 is < 6 hours old (`fly logs -a latvian-a2-exam |
  grep snapshot_uploaded`).

## 1. Add `fra` as a warm standby

### 1.1 Add the region to the app

```bash
# Add fra to the app's region pool. Backup-only means the region is
# eligible for traffic but only when lhr is down — that's the warm-standby
# semantic we want before we explicitly scale.
fly regions add fra --app latvian-a2-exam
fly regions backup fra --app latvian-a2-exam
fly regions list --app latvian-a2-exam
# Expected output: Region Pool: lhr, fra; Backup Region: fra
```

### 1.2 Scale machine count per region

```bash
# 1 machine in fra (warm-standby baseline), allow burst to 2.
fly scale count 1 --region fra --max-per-region 2 --app latvian-a2-exam

# Keep lhr at 1 baseline, burst to 2.
fly scale count 1 --region lhr --max-per-region 2 --app latvian-a2-exam

fly status --app latvian-a2-exam
```

### 1.3 Deploy with the multi-region config

```bash
fly deploy --config fly.multi-region.toml --app latvian-a2-exam
```

The deploy uses the `rolling` strategy — one region at a time. Watch the
health checks pass for `lhr` first; only then will `fra` flip live.

### 1.4 Verify both regions respond

```bash
# The region-health.yml workflow does this every 5 min, but verify once
# by hand straight after deploy:
curl -s https://lhr.latvian-a2-exam.fly.dev/healthz | jq .
# {"status":"ok","region":"lhr"}

curl -s https://fra.latvian-a2-exam.fly.dev/healthz | jq .
# {"status":"ok","region":"fra"}
```

The `region` field is populated from the `FLY_REGION` env var that Fly
injects per machine. If it returns `"unknown"`, the env var is missing —
file an issue with the Fly platform team.

## 2. Postgres streaming replica

Fly Postgres clusters support streaming replication natively. The setup
is two steps: extend the cluster, then verify replication.

### 2.1 Extend the cluster into `fra`

```bash
# Add a read-replica volume in fra to the existing PG cluster (created
# in T-021 as ``lvcodex-db``):
fly volumes create pg_data \
  --region fra \
  --size 10 \
  --app lvcodex-db

# Add a replica machine in fra. Fly Postgres detects the new volume and
# bootstraps it from the leader's basebackup automatically.
fly machine clone --region fra --app lvcodex-db
```

Reference: <https://fly.io/docs/postgres/managing/scaling-replicas/>

### 2.2 Verify replication is healthy

```bash
fly ssh console --app lvcodex-db --select  # pick the leader
$ psql -U postgres -c 'SELECT client_addr, state, sync_state, replay_lag FROM pg_stat_replication;'
```

You should see one row per replica. `state` must be `streaming`,
`sync_state` is `async` for warm-standby (we don't need synchronous;
the latency hit isn't worth it). `replay_lag` should be under 1 s in
steady state.

### 2.3 App-side wiring

The app's existing `DATABASE_URL` secret points at the leader. The
`fly.multi-region.toml` config also sets `LVCODEX_MULTI_REGION=1`. The
read-side abstraction in `server_app/services/db.py` is region-aware:
machines whose `FLY_REGION != primary_region` resolve a separate
`DATABASE_REPLICA_URL` secret if set, otherwise they fall through to
`DATABASE_URL`.

Set the replica DSN once:

```bash
fly secrets set \
  DATABASE_REPLICA_URL="postgres://lvcodex:***@lvcodex-db.flycast:5433/lvcodex" \
  --app latvian-a2-exam
```

Note the **`:5433`** port — Fly Postgres exposes the read-replica port
on 5433 by convention. The leader stays on 5432.

## 3. DR failover — flip primary from `lhr` to `fra`

Use this section if `lhr` is unreachable, or as a planned drill (we run
one quarterly per `docs/release-process.md`).

> The interactive script `scripts/region-failover.sh` walks through
> these steps and is **idempotent** — re-running it after a partial
> failure is safe.

### 3.1 Confirm the standby is healthy

```bash
curl -fsS https://fra.latvian-a2-exam.fly.dev/healthz
# Must return HTTP 200 and {"status":"ok","region":"fra"}.
```

### 3.2 Pull traffic away from lhr

```bash
fly regions backup lhr --app latvian-a2-exam   # demote lhr to backup
fly regions add fra --app latvian-a2-exam      # ensure fra is in the pool
# (No need to remove lhr — leaving it as backup means we can flip back
# without redeploying the config.)
```

### 3.3 Promote the Postgres replica in `fra`

```bash
fly pg failover --app lvcodex-db
```

`fly pg failover` is the documented Fly command that promotes the
healthiest replica to leader. It updates the cluster's internal Stolon
config so subsequent connections from the app reach the new leader on
the same `lvcodex-db.flycast:5432` address — no app-side env change is
needed.

Reference: <https://fly.io/docs/postgres/managing/failover/>

### 3.4 Scale the warm standby up

```bash
fly scale count 2 --region fra --max-per-region 2 --app latvian-a2-exam
fly status --app latvian-a2-exam
# Expected: 2 healthy machines in fra; lhr machines either stopped or
# unhealthy.
```

### 3.5 Verify

```bash
curl -fsS https://latvian-a2-exam.fly.dev/healthz | jq .region
# Should be "fra" (or "lhr" if lhr is reachable — DNS still hits the
# nearest healthy region; that's fine).
```

End-to-end smoke: log in as the canary user, submit one practice
question, confirm the response writes to PG.

## 4. Rollback after the incident

Once `lhr` is healthy again:

```bash
# Re-promote PG in lhr (only if you ran step 3.3 — otherwise skip).
fly pg failover --app lvcodex-db

# Restore the original region pool.
fly regions add lhr --app latvian-a2-exam
fly regions backup fra --app latvian-a2-exam

# Re-scale to the baseline 1+1.
fly scale count 1 --region lhr --max-per-region 2 --app latvian-a2-exam
fly scale count 1 --region fra --max-per-region 2 --app latvian-a2-exam

fly status --app latvian-a2-exam
```

Verify `/healthz` returns `"region":"lhr"` from a clean cache.

## 5. Cross-region monitoring

`.github/workflows/region-health.yml` runs every 5 min and `GET`s
`/healthz` for each region. On any non-200 response (or a missing
`region` field) it posts a Slack alert via `SLACK_WEBHOOK_URL` (set as
a repo secret). The workflow is also `workflow_dispatch`-triggerable
for one-off checks.

## 6. Cost note

The warm-standby topology roughly doubles the Fly compute spend (an
extra `shared-cpu-1x` machine + 10 GB PG replica volume). Budget impact
is tracked in `BUSINESS_REPORT.md` §9. We accept the cost because the
RPO target (< 1 min) and RTO target (< 5 min) cannot be met with a
cold standby.

## References

- Fly multi-region docs: <https://fly.io/docs/reference/regions/>
- Fly Postgres replicas: <https://fly.io/docs/postgres/managing/scaling-replicas/>
- Fly PG failover: <https://fly.io/docs/postgres/managing/failover/>
- Internal: `docs/postgres-migration.md`, `docs/backups.md`,
  `docs/deployment-runbook.md`.
