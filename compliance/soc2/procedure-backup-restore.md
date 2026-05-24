# Procedure — Backup & Restore

| Field | Value |
|---|---|
| **Document ID** | SOC2-PRC-002 |
| **Owner** | SRE Lead (acting: CTO) |
| **Effective date** | 2026-05-23 |
| **Last review** | 2026-05-23 |
| **Next review** | 2027-05-23 |
| **Review cadence** | Quarterly (after each restore drill) |
| **Parent policy** | `policy-business-continuity.md` |
| **TSC mapping** | A1.2, A1.3, CC7.5 |

## 1. Scope

Defines how lvcodex production state is backed up, verified, and restored.
The supporting code lives in:

- `scripts/backup_sqlite.sh` — the production backup script (gzip + R2 upload, T-013).
- `scripts/backup_sqlite.py` — the local verify/snapshot helper used by tests and on-host drills.

If either script is modified, this procedure must be reviewed in the same
PR (enforced by CODEOWNERS once added under T-070-followup).

## 2. Backup Cadence

| Source | Cadence | Destination | Retention |
|---|---|---|---|
| `data/lvcodex.db` (primary SQLite) | Every 6h via Fly machine cron | Cloudflare R2 bucket (`PREFIX=backups`) | 30 daily + 12 weekly + 6 monthly |
| `.multica/auth.sqlite3` (auth) | Bundled in the same backup run | Same R2 bucket | Same |
| `data/billing.sqlite3` (billing) | Bundled in the same backup run | Same R2 bucket | Same |
| Configuration secrets | Out of band — `fly secrets` snapshot stored in 1Password vault | 1Password (Restricted) | Rotated quarterly |

The 6h cadence is the source of the 6h RPO in `policy-business-continuity.md`.

## 3. Backup Execution

Daily / scheduled run:

```bash
# Set on the Fly machine via fly secrets:
#   R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET
DB_PATH=/app/data/lvcodex.db scripts/backup_sqlite.sh
```

On success the script:

1. Calls SQLite `.backup` API to produce a consistent online snapshot.
2. Gzips the snapshot.
3. Uploads with a deterministic key (`backups/lvcodex-YYYYMMDDTHHMMSSZ.sqlite.gz`).
4. Emits a checksum manifest.
5. Prunes any objects older than `RETENTION`.

Failure during any step exits non-zero, which Fly machine cron surfaces
as a Prometheus alert (T-014).

## 4. Verification (Daily Automated)

Each backup is followed by a verify pass:

```bash
scripts/backup_sqlite.py --verify-only
```

This runs `PRAGMA integrity_check` against each source database and
fails loudly if the result is anything other than `ok`. The verify step
is also runnable against a downloaded R2 snapshot during the drill (§5).

## 5. Quarterly Restore Drill

The restore drill is the single most important SOC 2 availability
evidence artifact. It is executed by the on-call SRE within the first
two weeks of each quarter.

| # | Step | Pass criterion |
|---|---|---|
| 1 | Pick the most recent R2 snapshot. | Object listed in R2 within the last 6h. |
| 2 | Download to a scratch Fly volume (`drill-YYYYQX`). | Checksum matches manifest. |
| 3 | Run `scripts/backup_sqlite.py --verify-only` against the restored databases. | All return `ok`. |
| 4 | Boot a non-production Fly app pointed at the restored data. | `/healthz` returns 200 and at least one canned exam attempt round-trips end-to-end. |
| 5 | Record drill outcome in §6 below. | One new row added per drill. |

Drills that fail any step become a Sev-2 incident and trigger a
post-mortem per `policy-incident-response.md`.

## 6. Drill Log

| Quarter | Date | Operator | Snapshot used | Restore duration | Outcome | Ticket |
|---|---|---|---|---|---|---|
| _initial issue — first drill scheduled for 2026-Q3_ | — | — | — | — | — | — |

## 7. Recovery Workflow (Production Incident)

If a Sev-1 incident requires a restore:

1. The on-call SRE declares a restore is needed in the incident channel.
2. A founder or Engineering Lead authorizes the restore in writing in the channel.
3. The SRE runs the drill steps §5.1–§5.4 against **production** rather than a scratch app.
4. Application traffic is repointed (Fly app swap or DNS) only after step §5.4 passes.
5. A post-mortem is filed within 5 business days documenting:
   - Time of detection, time of restore start, time of service restoration.
   - Compared against the RTO of 8h and RPO of 6h.
   - Any data loss reconciled from application logs.

## 8. Revision History

| Date | Author | Change |
|---|---|---|
| 2026-05-23 | T-070 | Initial issue. |
