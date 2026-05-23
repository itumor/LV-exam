#!/usr/bin/env bash
# T-013: Restore an lvcodex SQLite backup from Cloudflare R2.
#
# Required environment variables:
#   R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET
#
# Optional:
#   PREFIX        Key prefix within the bucket (default "backups").
#   R2_ENDPOINT   Override the derived endpoint URL.
#   AWS_BIN       Path to the aws CLI (default "aws").
#
# Subcommands:
#   --list                       Print all keys under ${PREFIX}/ sorted newest-first.
#   --latest <local-path>        Fetch the newest backup and restore to <local-path>.
#   --fetch <key> <local-path>   Fetch a specific key and restore to <local-path>.
#   --help                       Show usage.
#
# Source: BUSINESS_REPORT.md §9.2 #2 + App.A #8.

set -euo pipefail

PROG="${0##*/}"

usage() {
  cat <<USAGE
${PROG} - restore an lvcodex SQLite backup from R2

Usage:
  ${PROG} --list
  ${PROG} --latest <local-path>
  ${PROG} --fetch  <key> <local-path>
  ${PROG} --help

Environment:
  R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET (required)
  PREFIX (default backups)
  R2_ENDPOINT (override) AWS_BIN (default aws)
USAGE
}

if (( $# == 0 )); then
  usage >&2
  exit 1
fi

PREFIX="${PREFIX:-backups}"
AWS_BIN="${AWS_BIN:-aws}"

require_env() {
  : "${R2_ACCOUNT_ID:?R2_ACCOUNT_ID is required}"
  : "${R2_ACCESS_KEY_ID:?R2_ACCESS_KEY_ID is required}"
  : "${R2_SECRET_ACCESS_KEY:?R2_SECRET_ACCESS_KEY is required}"
  : "${R2_BUCKET:?R2_BUCKET is required}"
  R2_ENDPOINT="${R2_ENDPOINT:-https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com}"
  export AWS_ACCESS_KEY_ID="${R2_ACCESS_KEY_ID}"
  export AWS_SECRET_ACCESS_KEY="${R2_SECRET_ACCESS_KEY}"
  export AWS_DEFAULT_REGION="auto"
}

log() {
  printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

cmd_list() {
  require_env
  "${AWS_BIN}" s3api list-objects-v2 \
    --bucket "${R2_BUCKET}" \
    --prefix "${PREFIX}/" \
    --endpoint-url "${R2_ENDPOINT}" \
    --query 'Contents[].Key' \
    --output text \
    | tr '\t' '\n' \
    | grep -v '^None$' \
    | sort -r
}

restore_archive() {
  local archive="$1"
  local target="$2"

  mkdir -p "$(dirname "${target}")"

  log "decompressing ${archive} → ${target}"
  gunzip -c "${archive}" > "${target}"

  log "verifying ${target}"
  local result
  result="$(sqlite3 "${target}" 'PRAGMA integrity_check;' | head -n 1)"
  if [[ "${result}" != "ok" ]]; then
    log "ERROR: integrity_check failed on restored DB: ${result}" >&2
    exit 2
  fi
  log "restore complete: ${target} (integrity_check=ok)"
}

cmd_fetch() {
  local key="$1"
  local target="$2"
  require_env

  local tmp
  tmp="$(mktemp "${TMPDIR:-/tmp}/lvcodex-restore.XXXXXX.gz")"
  trap 'rm -f "${tmp}"' EXIT

  log "downloading s3://${R2_BUCKET}/${key} → ${tmp}"
  "${AWS_BIN}" s3 cp "s3://${R2_BUCKET}/${key}" "${tmp}" \
    --endpoint-url "${R2_ENDPOINT}" \
    --only-show-errors

  restore_archive "${tmp}" "${target}"
}

cmd_latest() {
  local target="$1"
  require_env
  local latest
  latest="$(cmd_list | head -n 1)"
  if [[ -z "${latest}" ]]; then
    log "ERROR: no backups found under ${PREFIX}/ in bucket ${R2_BUCKET}" >&2
    exit 2
  fi
  log "latest backup: ${latest}"
  cmd_fetch "${latest}" "${target}"
}

case "$1" in
  -h|--help)
    usage
    ;;
  --list)
    cmd_list
    ;;
  --latest)
    if (( $# != 2 )); then
      echo "${PROG}: --latest requires <local-path>" >&2
      usage >&2
      exit 1
    fi
    cmd_latest "$2"
    ;;
  --fetch)
    if (( $# != 3 )); then
      echo "${PROG}: --fetch requires <key> <local-path>" >&2
      usage >&2
      exit 1
    fi
    cmd_fetch "$2" "$3"
    ;;
  *)
    echo "${PROG}: unknown subcommand: $1" >&2
    usage >&2
    exit 1
    ;;
esac
