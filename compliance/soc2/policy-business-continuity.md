# Business Continuity & Disaster Recovery Policy

| Field | Value |
|---|---|
| **Document ID** | SOC2-POL-006 |
| **Owner** | SRE Lead (acting: CTO) |
| **Effective date** | 2026-05-23 |
| **Last review** | 2026-05-23 |
| **Next review** | 2027-05-23 |
| **Review cadence** | Annual + after every restore drill |
| **TSC mapping** | A1.1, A1.2, A1.3, CC7.5 |

## 1. Purpose

Define recovery objectives, dependencies, and the exercised playbooks that
restore lvcodex service after a disruptive event — from a process crash
through to a full region outage.

## 2. Recovery Objectives

| Objective | Target | Source of truth |
|---|---|---|
| **RTO** — Recovery Time Objective | **8 hours** from declaration of a Sev-1 outage to restoration of customer-facing service. | This policy + DR runbook |
| **RPO** — Recovery Point Objective | **6 hours** of data loss maximum, aligned with the T-013 backup cadence. | `scripts/backup_sqlite.sh` cron schedule (every 6h) |
| **Restore drill** | Quarterly, full restore from R2 to a scratch Fly volume. | `procedure-backup-restore.md` |
| **Backup retention** | 30 daily snapshots + 12 weekly snapshots + 6 monthly snapshots in Cloudflare R2. | `scripts/backup_sqlite.sh` `RETENTION` env var |

The 6h RPO is feasible because T-013 produces an online SQLite snapshot
every 6 hours, gzips it, and uploads it to R2 with a checksum manifest.

## 3. Dependencies (BIA Summary)

| Dependency | Tier | Loss tolerance | Mitigation |
|---|---|---|---|
| Fly.io application runtime | Critical | < 1h before SLA breach | Multi-region warm standby (T-028: `lhr` + `fra`) |
| Fly.io / volume storage | Critical | < 6h (RPO) | T-013 backups to R2 |
| Cloudflare R2 (backups) | Critical | Cannot lose; geo-redundant by default | Cloudflare R2 SLA + monthly evidence of object presence |
| Stripe | High | Hours; degrades billing only, not exam delivery | Webhook idempotency (`billing.py`) + dunning catch-up |
| Groq / OpenAI | High | Hours; runtime fallback between the two | Provider failover in code; cached content for exams |
| Sentry | Low | Days | Logs persist locally; alerts fall back to Prometheus |

## 4. Recovery Scenarios

### 4.1 Pod crash / single-instance failure

- **Detection.** Fly health check + Prometheus pod-up alert.
- **Response.** Fly auto-restarts. If repeated, on-call rolls back the deploy via the standard GitFlow `hotfix/` path.
- **RTO/RPO.** Both within seconds. No data loss.

### 4.2 Region outage (primary FRA)

- **Detection.** Multi-region health checks fail in FRA.
- **Response.** Promote LHR standby (T-028); update DNS via Cloudflare. Customer status page update within 30 min.
- **RTO.** ≤ 1 hour. **RPO.** ≤ replication lag (target ≤ 1 min).

### 4.3 Database corruption / accidental deletion

- **Detection.** Application errors + integrity-check failures from `scripts/backup_sqlite.py --verify-only`.
- **Response.** Follow `procedure-backup-restore.md`. Restore most recent valid R2 snapshot. Diff against last known-good and reconcile any in-flight writes from application logs.
- **RTO.** ≤ 8 hours (this policy's target). **RPO.** ≤ 6 hours.

### 4.4 Backup storage compromise (R2)

- **Detection.** Cloudflare audit log + manifest checksum mismatch.
- **Response.** Rotate R2 API tokens, restore from a secondary archive (monthly off-R2 cold copy maintained by SRE Lead), open Sev-1.

## 5. Exercises

The DR runbook is exercised quarterly. Evidence of execution
(timestamp, operator, dataset hash, restore duration) is recorded in
`procedure-backup-restore.md` §5 and presented at each quarterly
security review.

## 6. Communication During DR

A Sev-1 DR event invokes `policy-incident-response.md` §5–6.
Customer-facing communication is owned by the founder on point;
technical updates flow via the incident channel.

## 7. Revision History

| Date | Author | Change |
|---|---|---|
| 2026-05-23 | T-070 | Initial issue. |
