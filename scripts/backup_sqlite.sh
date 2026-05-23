#!/usr/bin/env bash
# T-013: Online SQLite snapshot + gzip + upload to Cloudflare R2 (S3-compatible).
#
# Required environment variables (R2 credentials and bucket):
#   R2_ACCOUNT_ID         Cloudflare account id (used to derive endpoint URL).
#   R2_ACCESS_KEY_ID      R2 access key id.
#   R2_SECRET_ACCESS_KEY  R2 secret access key.
#   R2_BUCKET             Target bucket name.
#
# Optional:
#   DB_PATH       Path to the source SQLite database (default /app/data/lvcodex.db).
#   PREFIX        Key prefix within the bucket (default "backups").
#   RETENTION     Number of backups to keep (default 30).
#   R2_ENDPOINT   Override the derived endpoint URL.
#   AWS_BIN       Path to the aws CLI (default "aws").
#
# Flags:
#   --help        Show usage and exit.
#   --dry-run     Print the planned actions without contacting R2 or copying the DB.
#
# Exit codes:
#   0  success
#   1  usage / configuration error
#   2  backup or upload failure
#
# Source: BUSINESS_REPORT.md §9.2 #2 + App.A #8 (no-data-loss requirement).

set -euo pipefail

PROG="${0##*/}"

usage() {
  cat <<USAGE
${PROG} - online SQLite backup + gzip + upload to R2

Usage:
  ${PROG} [--dry-run]
  ${PROG} --help

Environment:
  R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET (required)
  DB_PATH (default /app/data/lvcodex.db)
  PREFIX  (default backups)
  RETENTION (default 30)
  R2_ENDPOINT (override) AWS_BIN (default aws)
USAGE
}

DRY_RUN=0
for arg in "$@"; do
  case "${arg}" in
    -h|--help)
      usage
      exit 0
      ;;
    --dry-run)
      DRY_RUN=1
      ;;
    *)
      echo "${PROG}: unknown argument: ${arg}" >&2
      usage >&2
      exit 1
      ;;
  esac
done

DB_PATH="${DB_PATH:-/app/data/lvcodex.db}"
PREFIX="${PREFIX:-backups}"
RETENTION="${RETENTION:-30}"
AWS_BIN="${AWS_BIN:-aws}"

if [[ "${DRY_RUN}" -eq 0 ]]; then
  : "${R2_ACCOUNT_ID:?R2_ACCOUNT_ID is required}"
  : "${R2_ACCESS_KEY_ID:?R2_ACCESS_KEY_ID is required}"
  : "${R2_SECRET_ACCESS_KEY:?R2_SECRET_ACCESS_KEY is required}"
  : "${R2_BUCKET:?R2_BUCKET is required}"
fi

R2_ENDPOINT="${R2_ENDPOINT:-https://${R2_ACCOUNT_ID:-DRY}.r2.cloudflarestorage.com}"

TIMESTAMP="$(date -u +%Y%m%d-%H%M%S)"
KEY="${PREFIX}/lvcodex-${TIMESTAMP}.db.gz"
TMPDIR_BASE="${TMPDIR:-/tmp}"
WORKDIR="$(mktemp -d "${TMPDIR_BASE}/lvcodex-backup.XXXXXX")"
SNAPSHOT="${WORKDIR}/lvcodex.db"
ARCHIVE="${WORKDIR}/lvcodex-${TIMESTAMP}.db.gz"

cleanup() {
  rm -rf "${WORKDIR}"
}
trap cleanup EXIT

log() {
  printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

if [[ "${DRY_RUN}" -eq 1 ]]; then
  log "dry-run: would snapshot ${DB_PATH} → ${ARCHIVE}"
  log "dry-run: would upload to s3://${R2_BUCKET:-<bucket>}/${KEY}"
  log "dry-run: would prune older than newest ${RETENTION} keys under ${PREFIX}/"
  exit 0
fi

if [[ ! -f "${DB_PATH}" ]]; then
  log "ERROR: DB_PATH '${DB_PATH}' not found" >&2
  exit 2
fi

if ! command -v sqlite3 >/dev/null 2>&1; then
  log "ERROR: sqlite3 binary is not installed" >&2
  exit 2
fi
if ! command -v gzip >/dev/null 2>&1; then
  log "ERROR: gzip is not installed" >&2
  exit 2
fi
if ! command -v "${AWS_BIN}" >/dev/null 2>&1; then
  log "ERROR: aws CLI ('${AWS_BIN}') is not installed" >&2
  exit 2
fi

log "snapshotting ${DB_PATH} → ${SNAPSHOT}"
# `.backup` is online-safe; it copies pages while the writer continues.
sqlite3 "${DB_PATH}" ".backup '${SNAPSHOT}'"

log "verifying snapshot integrity"
result="$(sqlite3 "${SNAPSHOT}" 'PRAGMA integrity_check;' | head -n 1)"
if [[ "${result}" != "ok" ]]; then
  log "ERROR: integrity_check failed on snapshot: ${result}" >&2
  exit 2
fi

log "compressing snapshot → ${ARCHIVE}"
gzip -c "${SNAPSHOT}" > "${ARCHIVE}"

export AWS_ACCESS_KEY_ID="${R2_ACCESS_KEY_ID}"
export AWS_SECRET_ACCESS_KEY="${R2_SECRET_ACCESS_KEY}"
export AWS_DEFAULT_REGION="auto"

log "uploading to s3://${R2_BUCKET}/${KEY}"
"${AWS_BIN}" s3 cp "${ARCHIVE}" "s3://${R2_BUCKET}/${KEY}" \
  --endpoint-url "${R2_ENDPOINT}" \
  --only-show-errors

log "pruning to last ${RETENTION} backups under ${PREFIX}/"
listing="$("${AWS_BIN}" s3api list-objects-v2 \
  --bucket "${R2_BUCKET}" \
  --prefix "${PREFIX}/" \
  --endpoint-url "${R2_ENDPOINT}" \
  --query 'Contents[].Key' \
  --output text 2>/dev/null || true)"

if [[ -n "${listing}" && "${listing}" != "None" ]]; then
  # Newest keys first (timestamps embedded in name sort lexicographically).
  mapfile -t keys < <(printf '%s\n' ${listing} | sort -r)
  if (( ${#keys[@]} > RETENTION )); then
    for ((i = RETENTION; i < ${#keys[@]}; i++)); do
      old_key="${keys[$i]}"
      log "  delete s3://${R2_BUCKET}/${old_key}"
      "${AWS_BIN}" s3 rm "s3://${R2_BUCKET}/${old_key}" \
        --endpoint-url "${R2_ENDPOINT}" \
        --only-show-errors || log "  warn: failed to delete ${old_key}"
    done
  else
    log "  ${#keys[@]} backups retained (≤ ${RETENTION}); nothing to prune"
  fi
fi

log "done: ${KEY}"
