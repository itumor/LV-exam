#!/usr/bin/env bash
#
# scripts/release.sh — T-019
#
# Cut a release/<name> branch from develop, run the full regression locally,
# tag vX.Y.Z, and open a PR to main. Enforces the T-011 / T-014 / T-016
# risk-gate pre-flight (legal pages, observability, Stripe Tax) so we never
# cut a release for paid EU traffic without those merged.
#
# Usage: scripts/release.sh --name <e.g. 2026-Q1> --version <e.g. v1.0.0> [--dry-run]
#
# See docs/release-process.md for the full procedure.

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults & globals
# ---------------------------------------------------------------------------

RELEASE_NAME=""
RELEASE_VERSION=""
DRY_RUN=0
SCRIPT_NAME="$(basename "$0")"

# Risk-gate markers searched in `git log -- <paths>` on develop.
# Each marker MUST be present (as a substring in commit message) for the
# corresponding path-filtered log slice. If any marker is missing, the
# script aborts and tells the operator which T-XXX PR to merge first.
RISK_GATE_MARKERS=(
  "T-011:legal/"
  "T-014:docker/"
  "T-016:billing.py"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

usage() {
  cat <<'EOF'
Usage: scripts/release.sh --name <release-name> --version <vX.Y.Z> [--dry-run]

Cuts a release/<name> branch from develop, runs the full regression locally,
tags <version>, and opens a PR to main. Enforces T-011 (legal pages),
T-014 (observability), and T-016 (Stripe Tax) risk-gate pre-flight so we
never cut a release without those merged to develop.

Required arguments:
  --name <name>        Release-train name, e.g. 2026-Q1 (used in
                       release/<name> branch).
  --version <vX.Y.Z>   Annotated tag to apply to the release HEAD,
                       e.g. v1.0.0.

Optional:
  --dry-run            Print every action but do not push, tag, or open a
                       PR. The risk-gate pre-flight is skipped under
                       --dry-run so the script can be rehearsed without
                       real merged history.
  -h, --help           Show this message.

Examples:
  scripts/release.sh --name 2026-Q1 --version v1.0.0
  scripts/release.sh --name 2026-Q1 --version v1.0.0 --dry-run

Refer to docs/release-process.md for the full pre-cut checklist,
post-merge tag promotion, rollback guidance, and hotfix workflow.
EOF
}

log() { printf '[release] %s\n' "$*"; }
warn() { printf '[release][warn] %s\n' "$*" >&2; }
die() { printf '[release][error] %s\n' "$*" >&2; exit 1; }

run() {
  # run <cmd...> — respects --dry-run.
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    printf '[release][dry-run] %s\n' "$*"
  else
    "$@"
  fi
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

parse_args() {
  if [[ "$#" -eq 0 ]]; then
    usage
    exit 1
  fi
  while [[ "$#" -gt 0 ]]; do
    case "$1" in
      --name)
        [[ "$#" -lt 2 ]] && die "--name requires a value"
        RELEASE_NAME="$2"
        shift 2
        ;;
      --version)
        [[ "$#" -lt 2 ]] && die "--version requires a value"
        RELEASE_VERSION="$2"
        shift 2
        ;;
      --dry-run)
        DRY_RUN=1
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        usage
        die "unknown argument: $1"
        ;;
    esac
  done

  if [[ -z "${RELEASE_NAME}" ]]; then
    usage
    die "--name is required"
  fi
  if [[ -z "${RELEASE_VERSION}" ]]; then
    usage
    die "--version is required"
  fi
  if [[ ! "${RELEASE_VERSION}" =~ ^v[0-9]+\.[0-9]+\.[0-9]+(-[A-Za-z0-9.-]+)?$ ]]; then
    die "--version must look like vMAJOR.MINOR.PATCH (got: ${RELEASE_VERSION})"
  fi
}

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

check_branch_is_develop() {
  local current
  current="$(git rev-parse --abbrev-ref HEAD)"
  if [[ "${current}" != "develop" ]]; then
    die "current branch is '${current}', must be 'develop' before cutting a release"
  fi
  log "current branch: develop"
}

check_clean_worktree() {
  if [[ -n "$(git status --porcelain)" ]]; then
    die "working tree has uncommitted changes; commit, stash, or discard before cutting a release"
  fi
  log "working tree is clean"
}

check_develop_up_to_date() {
  # Refresh origin/develop, then compare local HEAD with remote.
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    log "(dry-run) skipping origin fetch + ahead/behind check"
    return 0
  fi
  log "fetching origin/develop..."
  git fetch origin develop --quiet
  local local_sha remote_sha
  local_sha="$(git rev-parse develop)"
  remote_sha="$(git rev-parse origin/develop)"
  if [[ "${local_sha}" != "${remote_sha}" ]]; then
    die "local develop (${local_sha:0:7}) differs from origin/develop (${remote_sha:0:7}); pull or push first"
  fi
  log "develop is up to date with origin"
}

check_risk_gates() {
  # Verifies T-011, T-014, T-016 PRs are merged to develop. For each
  # marker "T-XXX:<path>", searches `git log --oneline develop -- <path>`
  # for the T-XXX token. Missing markers abort the cut.
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    log "(dry-run) skipping risk-gate pre-flight (T-011 / T-014 / T-016)"
    return 0
  fi
  log "running risk-gate pre-flight (T-011 legal, T-014 observability, T-016 Stripe Tax)..."
  local missing=()
  for entry in "${RISK_GATE_MARKERS[@]}"; do
    local task="${entry%%:*}"
    local path="${entry#*:}"
    if ! git log --oneline develop -- "${path}" 2>/dev/null | grep -E -q "${task}"; then
      missing+=("${task} (expected commit referencing ${task} touching ${path})")
    fi
  done
  if [[ "${#missing[@]}" -gt 0 ]]; then
    warn "risk-gate pre-flight FAILED. The following PRs must be merged to develop before this release can be cut:"
    for item in "${missing[@]}"; do
      warn "  - ${item}"
    done
    die "merge the missing risk-gate PR(s) into develop, then re-run scripts/release.sh"
  fi
  log "risk-gate pre-flight passed"
}

# ---------------------------------------------------------------------------
# Release steps
# ---------------------------------------------------------------------------

cut_release_branch() {
  local branch="release/${RELEASE_NAME}"
  log "creating ${branch} from develop..."
  run git checkout -b "${branch}" develop
  log "pushing ${branch} to origin..."
  run git push -u origin "${branch}"
}

run_full_regression() {
  log "running full regression (npm test)..."
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    printf '[release][dry-run] npm test\n'
    return 0
  fi
  if ! npm test; then
    die "npm test failed; release aborted. Fix on develop, re-cut release branch."
  fi
  log "full regression passed"
}

tag_release() {
  local branch="release/${RELEASE_NAME}"
  log "tagging ${RELEASE_VERSION} on ${branch}..."
  run git tag -a "${RELEASE_VERSION}" -m "Release ${RELEASE_VERSION} (${RELEASE_NAME})"
  log "pushing tag ${RELEASE_VERSION}..."
  run git push origin "${RELEASE_VERSION}"
}

previous_tag() {
  # Most recent annotated tag reachable from HEAD, or empty string if none.
  git describe --tags --abbrev=0 --exclude="${RELEASE_VERSION}" 2>/dev/null || true
}

build_pr_body() {
  local prev
  prev="$(previous_tag)"
  local range
  if [[ -n "${prev}" ]]; then
    range="${prev}..HEAD"
  else
    range="HEAD"
  fi
  local log_block
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    log_block="(dry-run: would list git log ${range} --oneline here)"
  else
    log_block="$(git log "${range}" --oneline 2>/dev/null || true)"
    [[ -z "${log_block}" ]] && log_block="(no commits in range ${range})"
  fi

  cat <<EOF
## Release ${RELEASE_VERSION} — ${RELEASE_NAME}

Cut from develop via \`scripts/release.sh --name ${RELEASE_NAME} --version ${RELEASE_VERSION}\`.

### Merged tasks since ${prev:-<initial>}

\`\`\`
${log_block}
\`\`\`

### Pre-merge gates

- [x] Risk-gate pre-flight passed (T-011 legal, T-014 observability, T-016 Stripe Tax merged to develop).
- [x] Full regression (\`npm test\`) green locally on \`release/${RELEASE_NAME}\`.
- [x] Annotated tag \`${RELEASE_VERSION}\` created on release HEAD.

### Required before merging to main

- [ ] Manual QA checklist signed off (see \`docs/release-checklist.md\`).
- [ ] Fly preview app for this release verified.
- [ ] No outstanding bugfix-only commits expected on \`release/${RELEASE_NAME}\`.
- [ ] CI green on this PR (release pipeline incl. full regression + load smoke).

### Rollback

Revert this PR's merge commit on main, then re-deploy the previous tag. See \`docs/release-process.md\`.

---

Generated by \`scripts/release.sh\` for task **T-019**.
EOF
}

open_release_pr() {
  local branch="release/${RELEASE_NAME}"
  local title="Release ${RELEASE_VERSION} (${RELEASE_NAME})"
  local body
  body="$(build_pr_body)"
  log "opening PR ${branch} → main via gh..."
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    printf '[release][dry-run] gh pr create --base main --head %s --title %q\n' "${branch}" "${title}"
    printf '[release][dry-run] body preview:\n%s\n' "${body}"
    return 0
  fi
  if ! command -v gh >/dev/null 2>&1; then
    warn "gh CLI not found; skipping automated PR creation. Open the PR manually."
    return 0
  fi
  gh pr create \
    --base main \
    --head "${branch}" \
    --title "${title}" \
    --body "${body}"
}

print_next_steps() {
  cat <<EOF

[release] Next steps for ${RELEASE_VERSION} (${RELEASE_NAME}):

  1. Verify the Fly preview app for release/${RELEASE_NAME} is healthy.
  2. Walk docs/release-checklist.md end-to-end (manual QA).
  3. Only bugfix commits onto release/${RELEASE_NAME} after this cut.
  4. When QA signs off, merge the release PR to main (NO squash — preserve
     the tag commit). CI will deploy main to production.
  5. After merge, back-merge main into develop so the tag and any release
     bugfixes are reflected there.
  6. If anything goes wrong, see "Rollback" in docs/release-process.md.

EOF
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
  parse_args "$@"

  log "release name:    ${RELEASE_NAME}"
  log "release version: ${RELEASE_VERSION}"
  log "dry-run:         $([[ "${DRY_RUN}" -eq 1 ]] && echo yes || echo no)"

  check_branch_is_develop
  check_clean_worktree
  check_develop_up_to_date
  check_risk_gates

  cut_release_branch
  run_full_regression
  tag_release
  open_release_pr
  print_next_steps

  log "done."
}

main "$@"
