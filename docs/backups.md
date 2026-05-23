# Backups & Restore Drill (T-013)

Source: `BUSINESS_REPORT.md` §9.2 #2 + Appendix A #8 — no-data-loss requirement.

The lvcodex app stores all durable state in SQLite on a Fly volume mounted at
`/app/data` (see `fly.toml`). This runbook explains how those databases are
snapshotted to Cloudflare R2 and how the weekly restore drill validates them.

## At a glance

| Concern              | Implementation                                                                    |
| -------------------- | --------------------------------------------------------------------------------- |
| What is backed up    | The SQLite DB at `DB_PATH` (default `/app/data/lvcodex.db`)                       |
| How                  | `sqlite3 .backup` (online safe) → `gzip` → `aws s3 cp` to R2                      |
| When                 | Every `BACKUP_INTERVAL` seconds (default 21 600 s = 6 h) inside the Fly machine   |
| Where                | Cloudflare R2, key `backups/lvcodex-YYYYMMDD-HHMMSS.db.gz`                        |
| Retention            | Last 30 snapshots; older are pruned on each run                                   |
| Drill                | GitHub Action `backup-restore-drill.yml`, every Monday 03:00 UTC                  |
| Recovery objective   | RPO ≤ 6 h, RTO ≤ 1 h                                                              |

## Required secrets

Provision these once via `flyctl secrets set …` for the production app **and** as
GitHub repository secrets so the drill workflow can run:

| Secret                  | Notes                                                  |
| ----------------------- | ------------------------------------------------------ |
| `R2_ACCOUNT_ID`         | Cloudflare account id — used to derive the endpoint   |
| `R2_ACCESS_KEY_ID`      | R2 access key (scoped, write to backup bucket only)    |
| `R2_SECRET_ACCESS_KEY`  | Matching secret                                        |
| `R2_BUCKET`             | Bucket name, e.g. `lvcodex-prod-backups`               |

Optional Fly env:

| Variable           | Default                | Purpose                                  |
| ------------------ | ---------------------- | ---------------------------------------- |
| `DB_PATH`          | `/app/data/lvcodex.db` | SQLite path to snapshot                  |
| `PREFIX`           | `backups`              | Key prefix within the bucket             |
| `RETENTION`        | `30`                   | Keep N newest backups                    |
| `BACKUP_INTERVAL`  | `21600`                | Cron loop period in seconds              |
| `R2_ENDPOINT`      | _(derived)_            | Override the endpoint URL                |

## How the backup loop runs

`docker/cron-backup.sh` is a plain shell loop that invokes
`scripts/backup_sqlite.sh` and sleeps. It is intentionally not a real cron
daemon, to keep the image minimal. Register it as a Fly process group:

```toml
# fly.toml (excerpt)
[processes]
  app    = "python server.py"
  backup = "/app/docker/cron-backup.sh"
```

Then redeploy with `flyctl deploy`. Verify with:

```sh
flyctl logs -a latvian-a2-exam | grep cron-backup
flyctl status -a latvian-a2-exam     # confirm the backup process group is healthy
```

If the loop crashes, Fly's restart policy will respawn it. The script writes
one structured log line per phase (`snapshotting`, `verifying`, `compressing`,
`uploading`, `pruning`, `done`).

## Manual backup

From inside the Fly machine, or any host that has the secrets in env:

```sh
R2_ACCOUNT_ID=…  R2_ACCESS_KEY_ID=…  R2_SECRET_ACCESS_KEY=…  R2_BUCKET=lvcodex-prod-backups \
DB_PATH=/app/data/lvcodex.db \
  scripts/backup_sqlite.sh
```

Dry-run (no R2 access required, prints planned actions):

```sh
scripts/backup_sqlite.sh --dry-run
```

## Listing existing backups

```sh
scripts/restore_sqlite.sh --list
```

Output is one key per line, newest first.

## Manual restore

To restore the most recent backup into a tmp file for inspection:

```sh
scripts/restore_sqlite.sh --latest /tmp/lvcodex-restore.db
sqlite3 /tmp/lvcodex-restore.db 'PRAGMA integrity_check;'
```

To restore a specific key:

```sh
scripts/restore_sqlite.sh --fetch backups/lvcodex-20260520-030000.db.gz /tmp/lvcodex-restore.db
```

To restore **into production** (destructive — coordinate with on-call):

1. `flyctl scale count app=0 -a latvian-a2-exam` (stop app machines).
2. SSH in: `flyctl ssh console -a latvian-a2-exam`.
3. Move the corrupt DB aside: `mv /app/data/lvcodex.db /app/data/lvcodex.db.bad`.
4. Run `scripts/restore_sqlite.sh --latest /app/data/lvcodex.db`.
5. `chown` if needed, then `flyctl scale count app=1 -a latvian-a2-exam`.
6. Tail logs and `/healthz` to confirm.

## Weekly restore drill

`.github/workflows/backup-restore-drill.yml` runs every Monday 03:00 UTC. It:

1. Installs `sqlite3` and `awscli` on the runner.
2. Calls `scripts/restore_sqlite.sh --latest` to download the newest archive
   and restore it to `${RUNNER_TEMP}/restore/lvcodex.db`.
3. Runs `PRAGMA integrity_check;` and fails the job if the result is not `ok`.
4. Asserts the restored DB has ≥ 1 table.

The job can also be triggered on demand via **Run workflow** in the Actions
tab. A failed drill should be treated as a P1 incident — the latest backup is
not restorable.

## Definition of done

- Snapshot uploaded to R2 every 6 h with a dated key.
- ≤ 30 archives retained per the prune step.
- Weekly drill green for two consecutive runs.
- Runbook reviewed by an SRE/operator.
