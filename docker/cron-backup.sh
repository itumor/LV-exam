#!/usr/bin/env bash
# T-013: in-container cron loop. Runs scripts/backup_sqlite.sh every BACKUP_INTERVAL
# seconds (default 21600 = 6h). Designed to run as a separate Fly process group.
#
# Usage (fly.toml example):
#   [processes]
#     app    = "python server.py"
#     backup = "/app/docker/cron-backup.sh"
#
# Environment passthrough — the same R2_* / DB_PATH variables that backup_sqlite.sh
# consumes must be present in the container (set via `flyctl secrets`).
#
# This intentionally avoids cron daemons (supercronic, busybox crond) so the
# image stays minimal. If the loop crashes Fly's restart policy will respawn it.

set -euo pipefail

INTERVAL="${BACKUP_INTERVAL:-21600}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_SCRIPT="${BACKUP_SCRIPT:-${SCRIPT_DIR}/scripts/backup_sqlite.sh}"

log() {
  printf '[cron-backup %s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

if [[ ! -x "${BACKUP_SCRIPT}" ]]; then
  log "ERROR: backup script not executable: ${BACKUP_SCRIPT}" >&2
  exit 1
fi

log "starting backup loop (interval=${INTERVAL}s, script=${BACKUP_SCRIPT})"

# Optional jitter (0–60s) to avoid all machines snapshotting at the exact same
# wall-clock moment across regions.
sleep "$((RANDOM % 60))"

while true; do
  if "${BACKUP_SCRIPT}"; then
    log "backup ok"
  else
    rc=$?
    log "backup failed (exit ${rc}); will retry next cycle"
  fi
  sleep "${INTERVAL}"
done
