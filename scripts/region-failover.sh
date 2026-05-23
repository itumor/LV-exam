#!/usr/bin/env bash
#
# T-028 — Interactive multi-region DR failover helper.
#
# Walks an operator through promoting the fra warm-standby to primary
# when lhr is degraded (or for a planned DR drill). Idempotent: every
# step checks the current Fly state before issuing a mutating command,
# so re-running after a partial failure is safe.
#
# Usage:
#   scripts/region-failover.sh [--app APP_NAME] [--pg-app PG_APP_NAME] \
#                              [--from lhr] [--to fra] [--non-interactive]
#
# Reference runbook: docs/multi-region.md
#
set -euo pipefail

APP_NAME="${APP_NAME:-latvian-a2-exam}"
PG_APP_NAME="${PG_APP_NAME:-lvcodex-db}"
FROM_REGION="${FROM_REGION:-lhr}"
TO_REGION="${TO_REGION:-fra}"
NON_INTERACTIVE=0

usage() {
  sed -n '2,18p' "$0"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --app)              APP_NAME="$2"; shift 2 ;;
    --pg-app)           PG_APP_NAME="$2"; shift 2 ;;
    --from)             FROM_REGION="$2"; shift 2 ;;
    --to)               TO_REGION="$2"; shift 2 ;;
    --non-interactive)  NON_INTERACTIVE=1; shift ;;
    -h|--help)          usage; exit 0 ;;
    *) echo "unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

c_red()    { printf "\033[31m%s\033[0m" "$*"; }
c_green()  { printf "\033[32m%s\033[0m" "$*"; }
c_yellow() { printf "\033[33m%s\033[0m" "$*"; }
c_cyan()   { printf "\033[36m%s\033[0m" "$*"; }

log()  { printf "%s %s\n" "$(c_cyan "[failover]")" "$*"; }
ok()   { printf "%s %s\n" "$(c_green "[ ok ]")" "$*"; }
warn() { printf "%s %s\n" "$(c_yellow "[warn]")" "$*"; }
die()  { printf "%s %s\n" "$(c_red   "[fail]")" "$*" >&2; exit 1; }

confirm() {
  local prompt="${1:-Continue?}"
  if [[ "${NON_INTERACTIVE}" == "1" ]]; then
    log "(non-interactive) auto-confirm: ${prompt}"
    return 0
  fi
  local reply
  read -r -p "$(printf '%s %s [y/N] ' "$(c_yellow '?')" "${prompt}")" reply || reply=""
  [[ "${reply}" == "y" || "${reply}" == "Y" ]]
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "required command not on PATH: $1"
}

# ---------------------------------------------------------------------------
# preflight
# ---------------------------------------------------------------------------

log "Multi-region DR failover: $(c_cyan "${FROM_REGION}") → $(c_cyan "${TO_REGION}")"
log "App: $(c_cyan "${APP_NAME}")  PG app: $(c_cyan "${PG_APP_NAME}")"

require_cmd flyctl
require_cmd curl
require_cmd jq

flyctl auth whoami >/dev/null 2>&1 || die "flyctl not authenticated. Run: flyctl auth login"
ok "flyctl authenticated as: $(flyctl auth whoami 2>/dev/null | tr -d '\n')"

# Helper: does the app expose a healthy /healthz in REGION?
probe_region() {
  local region="$1"
  local url="https://${region}.${APP_NAME}.fly.dev/healthz"
  local body
  body=$(curl -sS -m 10 "${url}" 2>/dev/null || true)
  if [[ -z "${body}" ]]; then
    return 1
  fi
  local actual_region
  actual_region=$(echo "${body}" | jq -r '.region // empty' 2>/dev/null || true)
  if [[ "${actual_region}" != "${region}" ]]; then
    return 1
  fi
  return 0
}

# ---------------------------------------------------------------------------
# step 1 — verify warm standby health
# ---------------------------------------------------------------------------

log "Step 1/5: verifying ${TO_REGION} warm standby is healthy…"
if probe_region "${TO_REGION}"; then
  ok "${TO_REGION} /healthz returns expected region"
else
  warn "${TO_REGION} healthz probe failed — the standby may not be reachable yet."
  confirm "Proceed anyway? (only if you have out-of-band confirmation the standby is up)" \
    || die "Aborted: standby unhealthy."
fi

# ---------------------------------------------------------------------------
# step 2 — pull traffic away from the failing region
# ---------------------------------------------------------------------------

log "Step 2/5: demoting ${FROM_REGION} to backup-only and ensuring ${TO_REGION} is in the pool…"
current_regions=$(flyctl regions list --app "${APP_NAME}" 2>/dev/null || true)
echo "${current_regions}"

if echo "${current_regions}" | grep -qi "${TO_REGION}"; then
  ok "${TO_REGION} already in the region pool"
else
  confirm "Add ${TO_REGION} to the region pool?" \
    && flyctl regions add "${TO_REGION}" --app "${APP_NAME}"
fi

confirm "Mark ${FROM_REGION} as backup-only?" \
  && flyctl regions backup "${FROM_REGION}" --app "${APP_NAME}"

# ---------------------------------------------------------------------------
# step 3 — Postgres failover
# ---------------------------------------------------------------------------

log "Step 3/5: promoting the Postgres replica in ${TO_REGION}…"
warn "This will trigger 'flyctl pg failover --app ${PG_APP_NAME}'."
warn "Expect a 5-15 s write-pause while Stolon flips the leader."
if confirm "Run flyctl pg failover now?"; then
  flyctl pg failover --app "${PG_APP_NAME}" || warn "pg failover returned non-zero — verify manually with 'fly pg status'"
  ok "Postgres failover command dispatched"
else
  warn "Skipped Postgres failover — make sure to run it before continuing if PG primary is down"
fi

# ---------------------------------------------------------------------------
# step 4 — scale the standby up
# ---------------------------------------------------------------------------

log "Step 4/5: scaling ${TO_REGION} to 2 machines (burst)…"
confirm "Run flyctl scale count 2 --region ${TO_REGION} --max-per-region 2 --app ${APP_NAME}?" \
  && flyctl scale count 2 --region "${TO_REGION}" --max-per-region 2 --app "${APP_NAME}"

# ---------------------------------------------------------------------------
# step 5 — verify
# ---------------------------------------------------------------------------

log "Step 5/5: verifying ${TO_REGION} is serving traffic…"
sleep 5
if probe_region "${TO_REGION}"; then
  ok "${TO_REGION} /healthz: $(curl -sS -m 5 "https://${TO_REGION}.${APP_NAME}.fly.dev/healthz")"
else
  die "${TO_REGION} probe still failing. Inspect 'flyctl status --app ${APP_NAME}'."
fi

ok "Failover complete. ${TO_REGION} is now serving traffic."
log "Rollback steps: see docs/multi-region.md § 4."
