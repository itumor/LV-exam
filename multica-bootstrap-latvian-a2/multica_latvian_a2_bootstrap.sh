#!/usr/bin/env bash
# multica_latvian_a2_bootstrap.sh
#
# Bootstrap Multica agents, skills, and issues for the Latvian A2 Exam Simulator MVP.
#
# Usage:
#   chmod +x multica_latvian_a2_bootstrap.sh
#   DRY_RUN=1 ./multica_latvian_a2_bootstrap.sh   # preview
#   DRY_RUN=0 ./multica_latvian_a2_bootstrap.sh   # execute
#
# Required before execution:
#   multica login
#   multica auth status
#   jq --version
#
# Optional:
#   export WORKSPACE_ID="<workspace-id>"
#   export PROJECT_ID="<existing-project-id>"
#   export MULTICA_PAT="mul_..."                  # for headless login
#   export RUNTIME_KIND="codex"                   # codex|claude|opencode|openclaw|cursor
#
# Notes:
# - Multica CLI flags can evolve. This script uses safe wrappers and tries common variants.
# - Skills.sh imports may fail for some repository layouts. The script keeps running and creates local project skills.
# - ClawHub Stripe API skill is optional and requires MATON_API_KEY if you want managed OAuth/API access.

set -Eeuo pipefail

DRY_RUN="${DRY_RUN:-1}"
PROJECT_TITLE="${PROJECT_TITLE:-Latvian A2 Exam Simulator MVP}"
PROJECT_DESCRIPTION="${PROJECT_DESCRIPTION:-Productionize the Latvian A2 Exam Simulator: accounts, payments, persistence, server-side scoring, content governance, reliability, legal positioning, and commercial release.}"
RUNTIME_KIND="${RUNTIME_KIND:-codex}"

BOOTSTRAP_DIR="${BOOTSTRAP_DIR:-./multica-bootstrap-latvian-a2}"
SKILLS_DIR="$BOOTSTRAP_DIR/skills"
ISSUES_DIR="$BOOTSTRAP_DIR/issues"
mkdir -p "$SKILLS_DIR" "$ISSUES_DIR"

log()  { printf '\n[%s] %s\n' "$(date +%H:%M:%S)" "$*" >&2; }
warn() { printf '\n[WARN] %s\n' "$*" >&2; }

run() {
  echo "+ $*"
  if [[ "$DRY_RUN" == "0" ]]; then
    "$@"
  fi
}

try_run() {
  echo "+ $*"
  if [[ "$DRY_RUN" == "0" ]]; then
    "$@" || return 1
  fi
  return 0
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    warn "Missing command: $1"
    exit 1
  }
}

slugify() {
  printf '%s' "$1" \
    | tr '[:upper:]' '[:lower:]' \
    | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//'
}

json_get() {
  local expr="$1"
  jq -r "$expr // empty" 2>/dev/null || true
}

require_tools() {
  need_cmd multica
  need_cmd jq
}

login_if_needed() {
  log "Checking Multica authentication"
  if try_run multica auth status; then
    return 0
  fi

  if [[ -n "${MULTICA_PAT:-}" ]]; then
    log "Trying token login from MULTICA_PAT"
    run multica login --token "$MULTICA_PAT"
  else
    warn "Not authenticated. Run: multica login"
    exit 1
  fi
}

set_workspace_if_provided() {
  if [[ -n "${WORKSPACE_ID:-}" ]]; then
    log "Setting Multica workspace: $WORKSPACE_ID"
    run multica config set workspace_id "$WORKSPACE_ID"
  fi
}

start_daemon_if_requested() {
  if [[ "${START_DAEMON:-0}" == "1" ]]; then
    log "Starting Multica daemon"
    run multica daemon start
    run multica daemon status
  fi
}

create_or_get_project() {
  if [[ -n "${PROJECT_ID:-}" ]]; then
    echo "$PROJECT_ID"
    return 0
  fi

  local out=""
  log "Creating project: $PROJECT_TITLE"
  if [[ "$DRY_RUN" == "0" ]]; then
    out="$(multica project create \
      --title "$PROJECT_TITLE" \
      --description "$PROJECT_DESCRIPTION" \
      --status in_progress \
      --output json 2>/dev/null || true)"
    local id
    id="$(printf '%s' "$out" | json_get '.id // .project.id')"
    if [[ -n "$id" ]]; then
      echo "$id"
      return 0
    fi
    warn "Could not parse project id from project create output. Issues will be created without --project unless PROJECT_ID is provided."
    echo ""
  else
    echo "DRY_RUN_PROJECT_ID"
  fi
}

# -----------------------------
# Public skill imports
# -----------------------------
# Format:
#   key|expected_slug|source|url|why
#
# Use URLs from supported registries:
# - ClawHub: https://clawhub.ai/skills/<skill>
# - Skills.sh: https://skills.sh/<owner>/<repo>/<skill>
#
PUBLIC_SKILLS=(
  "skill_creator|skill-creator|skills.sh|https://skills.sh/openai/skills/skill-creator|Create and maintain small reusable project skills"
  "openai_docs|openai-docs|skills.sh|https://skills.sh/openai/skills/openai-docs|Current OpenAI docs for AI scoring/provider integration"
  "speech|speech|skills.sh|https://skills.sh/openai/skills/speech|Text-to-speech and audio generation workflows"
  "security_threat_model|security-threat-model|skills.sh|https://skills.sh/openai/skills/security-threat-model|Repository threat modeling and security reviews"
  "sentry_readonly|sentry|skills.sh|https://skills.sh/openai/skills/sentry|Read-only production error inspection"
  "sentry_ai_monitoring|sentry-setup-ai-monitoring|skills.sh|https://skills.sh/getsentry/sentry-agent-skills/sentry-setup-ai-monitoring|AI/LLM usage and cost monitoring"
  "sentry_logging|sentry-setup-logging|skills.sh|https://skills.sh/getsentry/sentry-agent-skills/sentry-setup-logging|Structured Sentry logging setup"
  "fastapi_python|fastapi-python|skills.sh|https://skills.sh/mindrally/skills/fastapi-python|FastAPI backend implementation"
  "microservices|microservices|skills.sh|https://skills.sh/mindrally/skills/microservices|Service boundaries, async processing, observability"
  "serverless|serverless|skills.sh|https://skills.sh/mindrally/skills/serverless|Cloud-native/serverless deployment patterns"
  "python|python|skills.sh|https://skills.sh/ahgraber/skills/python|Python design and workflow router"
  "python_testing|python-testing|skills.sh|https://skills.sh/ahgraber/skills/python-testing|Python unit/integration testing"
  "postgres_best_practices|supabase-postgres-best-practices|skills.sh|https://skills.sh/supabase/agent-skills/supabase-postgres-best-practices|Postgres schema, performance, RLS, query review"
  "react_best_practices|vercel-react-best-practices|skills.sh|https://skills.sh/vercel-labs/agent-skills/vercel-react-best-practices|React/Next.js performance and maintainability"
  "web_design_guidelines|web-design-guidelines|skills.sh|https://skills.sh/vercel-labs/agent-skills/web-design-guidelines|Learner-facing UI polish and UX quality"
  "shadcn|shadcn|skills.sh|https://skills.sh/shadcn/ui/shadcn|shadcn/ui component composition and accessibility"
  "clerk_setup|clerk-setup|skills.sh|https://skills.sh/clerk/skills/clerk-setup|Authentication setup"
  "clerk_nextjs|clerk-nextjs-patterns|skills.sh|https://skills.sh/clerk/skills/clerk-nextjs-patterns|Next.js auth patterns and API protection"
  "clerk_webhooks|clerk-webhooks|skills.sh|https://skills.sh/clerk/skills/clerk-webhooks|Auth event syncing to database"
  "clerk_testing|clerk-testing|skills.sh|https://skills.sh/clerk/skills/clerk-testing|E2E testing for authenticated flows"
  "stripe_best_practices|stripe-best-practices|skills.sh|https://skills.sh/stripe/ai/stripe-best-practices|Stripe Checkout, Billing, subscriptions, webhooks"
  "stripe_api_optional|stripe-api|clawhub|https://clawhub.ai/skills/stripe-api|Optional managed Stripe API access via ClawHub/Maton"
)

safe_var_key() {
  printf '%s' "$1" | sed -E 's/[^A-Za-z0-9_]/_/g'
}

set_skill_slug() {
  local key safe
  key="$1"
  safe="$(safe_var_key "$key")"
  eval "SKILL_SLUG_${safe}=\$2"
}

get_skill_slug() {
  local key safe value
  key="$1"
  safe="$(safe_var_key "$key")"
  eval "value=\${SKILL_SLUG_${safe}:-}"
  printf '%s' "${value:-$key}"
}

set_skill_id() {
  local key safe
  key="$1"
  safe="$(safe_var_key "$key")"
  eval "SKILL_ID_${safe}=\$2"
}

get_skill_id() {
  local key safe value
  key="$1"
  safe="$(safe_var_key "$key")"
  eval "value=\${SKILL_ID_${safe}:-}"
  printf '%s' "$value"
}

find_skill_id_by_name() {
  local name="$1"
  multica skill list --output json 2>/dev/null | jq -r --arg name "$name" '
    .[]?
    | select((.name // .slug // .title // "") == $name)
    | .id
  ' | sed -n '1p'
}

import_skill_url() {
  local key="$1" expected="$2" source="$3" url="$4" why="$5"

  if [[ "$key" == "stripe_api_optional" && -z "${MATON_API_KEY:-}" ]]; then
    warn "Skipping optional ClawHub Stripe API skill because MATON_API_KEY is not set: $url"
    set_skill_slug "$key" "$expected"
    return 0
  fi

  log "Importing skill [$key] from $source: $url"
  local out="" slug="" id=""
  if [[ "$DRY_RUN" == "0" ]]; then
    out="$(multica skill import --url "$url" --output json 2>&1 || true)"
    printf '%s\n' "$out" > "$SKILLS_DIR/import-${key}.log"
    slug="$(printf '%s' "$out" | jq -r '.slug // .skill.slug // .name // .skill.name // empty' 2>/dev/null || true)"
    id="$(printf '%s' "$out" | jq -r '.id // .skill.id // empty' 2>/dev/null || true)"
    if [[ -z "$slug" ]]; then
      slug="$expected"
      warn "Could not parse imported skill slug for $key; using expected slug: $expected"
      warn "Import output saved to $SKILLS_DIR/import-${key}.log"
    fi
    if [[ -z "$id" ]]; then
      id="$(find_skill_id_by_name "$expected")"
    fi
    if [[ -z "$id" ]]; then
      warn "Could not determine skill id for $key; agent assignment may skip this skill."
    fi
  else
    slug="$expected"
    id="DRY_RUN_SKILL_ID_$key"
  fi
  set_skill_slug "$key" "$slug"
  set_skill_id "$key" "$id"
}

import_public_skills() {
  log "Importing public skills from Skills.sh and ClawHub"
  local rec key expected source url why
  for rec in "${PUBLIC_SKILLS[@]}"; do
    IFS='|' read -r key expected source url why <<< "$rec"
    import_skill_url "$key" "$expected" "$source" "$url" "$why"
  done
}

# -----------------------------
# Local project skills
# -----------------------------
create_local_skill() {
  local slug="$1" name="$2" description="$3" body="$4"
  local dir="$SKILLS_DIR/$slug"
  mkdir -p "$dir/references" "$dir/scripts"
  cat > "$dir/SKILL.md" <<EOF
---
name: $slug
description: $description
---

# $name

$body
EOF
}

create_project_skills() {
  log "Creating local project-specific skills"

  create_local_skill \
    "latvian-a2-program-management" \
    "Latvian A2 Program Management" \
    "Plan, sequence, and coordinate delivery for the Latvian A2 Exam Simulator MVP. Use for backlog grooming, issue decomposition, acceptance criteria, cross-agent handoffs, and release readiness." \
    "Use the product roadmap as the source of truth. Break work into small Multica issues with explicit acceptance criteria, dependencies, risks, and verification steps. Keep a release checklist covering free sample exam, paid pack, account creation, persisted attempts, objective scoring, AI feedback, Stripe payment, result dashboard, legal disclaimer, and production HTTPS. Never assign implementation tasks without clear inputs, expected files, and test requirements."

  create_local_skill \
    "latvian-a2-product-flow" \
    "Latvian A2 Product Flow" \
    "Design and implement learner-facing exam simulation UX for the Latvian A2 product. Use for hiding debug panels, real simulation mode, practice mode, timed flows, and results pages." \
    "Optimize for a realistic learner experience, not a developer studio. Hide Markdown, JSON, TTS, Images, Quality, and debug views from normal users. Real simulation mode must lock section order, prevent answer key exposure, block casual switching, auto-submit on timer expiry, and produce a single attempt record. Practice mode can allow section practice and review. Results must show score by skill, pass/fail per skill, total out of 60, weak areas, and suggested next practice."

  create_local_skill \
    "latvian-a2-backend-api" \
    "Latvian A2 Backend API" \
    "Build the FastAPI/Postgres production backend for attempts, scoring, exam content, AI evaluations, payments, and history." \
    "Model users, exams, attempts, answers, scores, AI evaluations, payments/subscriptions, and entitlements. Attempt lifecycle must include started, in_progress, submitted, scored, and expired. Store exam content version per attempt. Move objective scoring server-side. Implement structured API errors, rate limits, idempotency for external webhooks, and auditable scoring records. Prefer async DB access, migrations, and tests for all business rules."

  create_local_skill \
    "latvian-a2-auth-accounts" \
    "Latvian A2 Auth Accounts" \
    "Implement authentication, learner profiles, account dashboard, privacy flows, and auth webhook sync for the exam simulator." \
    "Support account creation/login, learner profile fields, exam target date, attempt dashboard, latest score, skill progress, billing/entitlement status, account deletion/export, and protected API routes. Never expose secret keys client-side. Webhooks must verify signatures and be idempotent. Keep public marketing/pricing pages accessible while protecting paid exam and dashboard routes."

  create_local_skill \
    "latvian-a2-monetization" \
    "Latvian A2 Monetization" \
    "Implement Stripe Checkout, products, exam packs, subscription access, AI scoring credits, billing page, and payment webhooks." \
    "Products: free sample simulation, 3-5 exam pack, monthly full access, optional AI scoring credits. Entitlements must track free exam access, paid exam access, remaining attempts, and remaining AI-scored submissions. Webhooks must handle payment_succeeded, subscription_created, subscription_renewed, subscription_canceled, refund, and chargeback with idempotent event processing and audit logs. Add upgrade prompts after free exam completion."

  create_local_skill \
    "latvian-a2-ai-scoring" \
    "Latvian A2 AI Scoring" \
    "Build reliable AI scoring for writing and speaking answers with rubrics, retries, quotas, cost controls, and auditability." \
    "Keep LLM scoring focused on writing, speaking, and free-text answers. Use deterministic rubric prompts, schema-validated outputs, retries with failure states, per-user/per-plan limits, retry caps, request size limits, and cost telemetry. Store prompt version, model, token/cost estimate, rubric version, raw provider status, and final normalized score. Never present AI score as official exam result."

  create_local_skill \
    "latvian-a2-content-quality" \
    "Latvian A2 Content Quality" \
    "Create and validate the structured exam bank from Markdown exams, audio assets, images, answer keys, and scoring rules." \
    "Convert or mirror Markdown exams into structured JSON. Define schema metadata, sections, tasks, questions, answer options, correct answers, audio assets, image assets, scoring rules, and content version. Validate missing answer keys, broken audio links, broken image links, duplicate options, unexpected point totals, and missing scoring metadata. Support draft, review, published, and archived states."

  create_local_skill \
    "latvian-a2-devops-security" \
    "Latvian A2 DevOps Security" \
    "Deploy and operate the paid exam simulator safely with HTTPS, secrets, monitoring, backups, rate limits, and legal pages." \
    "Use platform-managed environment variables. Add structured logs, Sentry monitoring, alerts for API errors, scoring failures, payment webhook failures, login failures, and high LLM cost. Add database backups, admin-only access controls, rate limiting, abuse protection, privacy policy, terms of service, and unofficial simulator disclaimer."

  create_local_skill \
    "latvian-a2-test-release" \
    "Latvian A2 Test Release" \
    "Own QA, Playwright flows, API tests, payment/auth/scoring reliability tests, release readiness, and regression prevention." \
    "Test complete exam flow from account creation to paid attempt result history. Cover real simulation timer expiry, practice mode review, auth protected routes, Stripe webhook idempotency, entitlement enforcement, server-side scoring, AI scoring failure/retry states, content validation, speaking upload, and PDF report generation. Prefer deterministic tests and avoid relying on live payment/AI calls in CI."
}

import_local_skill() {
  local slug="$1"
  local dir="$SKILLS_DIR/$slug"
  log "Importing local project skill: $slug"

  if [[ "$DRY_RUN" == "0" ]]; then
    local out="" id="" content=""
    id="$(find_skill_id_by_name "$slug")"
    content="$(sed '1,/^---$/d; 1,/^---$/d' "$dir/SKILL.md")"
    if [[ -n "$id" ]]; then
      out="$(multica skill update "$id" \
        --name "$slug" \
        --description "$(sed -n 's/^description: //p' "$dir/SKILL.md" | sed -n '1p')" \
        --content "$content" \
        --output json 2>&1 || true)"
    else
      out="$(multica skill create \
        --name "$slug" \
        --description "$(sed -n 's/^description: //p' "$dir/SKILL.md" | sed -n '1p')" \
        --content "$content" \
        --output json 2>&1 || true)"
    fi
    printf '%s\n' "$out" > "$SKILLS_DIR/import-local-${slug}.log"
    id="$(printf '%s' "$out" | jq -r '.id // .skill.id // empty' 2>/dev/null || true)"
    if [[ -z "$id" ]]; then
      id="$(find_skill_id_by_name "$slug")"
    fi
    if [[ -z "$id" ]]; then
      warn "Could not determine local skill id for $slug; agent assignment may skip this skill."
    fi
  else
    id="DRY_RUN_SKILL_ID_$slug"
    echo "+ multica skill create --name $slug --description <from SKILL.md> --content <from SKILL.md> --output json"
  fi
  set_skill_slug "$slug" "$slug"
  set_skill_id "$slug" "$id"
}

import_project_skills() {
  local slug
  for slug in \
    latvian-a2-program-management \
    latvian-a2-product-flow \
    latvian-a2-backend-api \
    latvian-a2-auth-accounts \
    latvian-a2-monetization \
    latvian-a2-ai-scoring \
    latvian-a2-content-quality \
    latvian-a2-devops-security \
    latvian-a2-test-release
  do
    import_local_skill "$slug"
  done
}

# -----------------------------
# Agent definitions
# -----------------------------
# Format:
# key|display_name|description|local_skill|public_skill_keys_csv|priority|custom_args
#
# custom_args are intentionally conservative. Override these env vars if your runtime expects different flags.
READ_ONLY_ARGS="${READ_ONLY_ARGS:---sandbox read-only}"
BUILD_ARGS="${BUILD_ARGS:---sandbox workspace-write}"
REVIEW_ARGS="${REVIEW_ARGS:---sandbox read-only}"
SECURITY_ARGS="${SECURITY_ARGS:---sandbox read-only}"

AGENTS=(
  "program_manager|MVP Program Manager|Coordinates the Latvian A2 Exam Simulator MVP, decomposes work into issues, tracks dependencies, and keeps release scope aligned to commercial MVP.|latvian-a2-program-management|skill_creator|high|$READ_ONLY_ARGS"
  "product_ux|Product UX Exam Flow Agent|Builds the learner-facing exam flow, practice/real modes, hidden debug panels, result screens, and polished UX.|latvian-a2-product-flow|react_best_practices,web_design_guidelines,shadcn|high|$BUILD_ARGS"
  "backend_api|Backend Persistence Agent|Builds the FastAPI/Postgres backend for users, exams, attempts, answers, scores, AI evaluations, payments, and history.|latvian-a2-backend-api|fastapi_python,postgres_best_practices,microservices,python_testing|high|$BUILD_ARGS"
  "auth_accounts|Auth Accounts Agent|Implements auth, profiles, dashboard, protected routes, account recovery, deletion/export, and auth webhook sync.|latvian-a2-auth-accounts|clerk_setup,clerk_nextjs,clerk_webhooks,clerk_testing|high|$BUILD_ARGS"
  "payments_entitlements|Payments Entitlements Agent|Implements Stripe products, Checkout, billing page, entitlements, paid exam access, credits, and webhooks.|latvian-a2-monetization|stripe_best_practices,stripe_api_optional,postgres_best_practices|high|$BUILD_ARGS"
  "ai_scoring|AI Scoring Reliability Agent|Implements writing/speaking AI scoring with rubrics, retries, quotas, failure states, cost controls, and audit logs.|latvian-a2-ai-scoring|openai_docs,sentry_ai_monitoring,fastapi_python,postgres_best_practices|high|$BUILD_ARGS"
  "content_quality|Content Bank QA Agent|Converts Markdown exams to structured JSON, validates schema/assets/scoring, and creates content governance workflow.|latvian-a2-content-quality|python,python_testing,openai_docs|medium|$BUILD_ARGS"
  "devops_security|DevOps Security Ops Agent|Deploys and operates the paid product with HTTPS, secrets, monitoring, backups, rate limits, and legal pages.|latvian-a2-devops-security|security_threat_model,sentry_readonly,sentry_logging,serverless|high|$SECURITY_ARGS"
  "qa_release|QA Release Agent|Owns regression tests, E2E flows, CI readiness, release checklist, and production acceptance validation.|latvian-a2-test-release|python_testing,clerk_testing,sentry_readonly|high|$REVIEW_ARGS"
)

AGENT_KEYS=()

set_agent_slug() {
  local key safe
  key="$1"
  safe="$(safe_var_key "$key")"
  eval "AGENT_SLUG_${safe}=\$2"
}

get_agent_slug() {
  local key safe value
  key="$1"
  safe="$(safe_var_key "$key")"
  eval "value=\${AGENT_SLUG_${safe}:-}"
  printf '%s' "$value"
}

set_agent_name() {
  local key safe
  key="$1"
  safe="$(safe_var_key "$key")"
  eval "AGENT_NAME_${safe}=\$2"
}

get_agent_name() {
  local key safe value
  key="$1"
  safe="$(safe_var_key "$key")"
  eval "value=\${AGENT_NAME_${safe}:-}"
  printf '%s' "$value"
}

set_agent_id() {
  local key safe
  key="$1"
  safe="$(safe_var_key "$key")"
  eval "AGENT_ID_${safe}=\$2"
}

get_agent_id() {
  local key safe value
  key="$1"
  safe="$(safe_var_key "$key")"
  eval "value=\${AGENT_ID_${safe}:-}"
  printf '%s' "$value"
}

find_agent_id_by_name() {
  local name="$1"
  multica agent list --output json 2>/dev/null | jq -r --arg name "$name" '
    .[]?
    | select((.name // "") == $name and ((.archived_at // "") == ""))
    | .id
  ' | sed -n '1p'
}

resolve_runtime_id() {
  if [[ -n "${RUNTIME_ID:-}" ]]; then
    printf '%s' "$RUNTIME_ID"
    return 0
  fi

  if [[ "$DRY_RUN" == "0" ]]; then
    multica runtime list --output json 2>/dev/null | jq -r --arg kind "$RUNTIME_KIND" '
      .[]?
      | select((.name // "" | ascii_downcase) | contains($kind | ascii_downcase))
      | .id
    ' | sed -n '1p'
  else
    printf '%s' "DRY_RUN_RUNTIME_ID"
  fi
}

custom_args_json() {
  local args="$1"
  if printf '%s' "$args" | grep -Eq '^[[:space:]]*\['; then
    printf '%s' "$args"
  else
    jq -cn --arg args "$args" '$args | split(" ") | map(select(length > 0))'
  fi
}

agent_instruction_text() {
  local key="$1" display="$2" desc="$3" local_skill="$4"
  cat <<EOF
You are $display for the Latvian A2 Exam Simulator MVP.

Mission:
$desc

Project context:
- Existing prototype includes browser app, generated mock exams, audio/image assets, timed listening/reading/writing/speaking sections, local scoring, AI endpoint, Docker support, debug views, and localStorage persistence.
- Production MVP needs accounts, payments, database persistence, exam access control, content governance, reliability, legal positioning, monitoring, and commercial packaging.
- Use your dedicated project skill: $local_skill.
- Produce small, reviewable changes with tests and clear acceptance evidence.
- Prefer practical implementation over broad research.
- Never expose answer keys or secrets to normal users.
- Never claim AI scoring is an official exam result.
- Comment on your assigned issue with blockers, assumptions, files changed, tests run, and next steps.
EOF
}

create_agent() {
  local key="$1" display="$2" desc="$3" local_skill="$4" public_keys="$5" priority="$6" custom_args="$7"
  local slug
  slug="$(slugify "$display")"
  set_agent_slug "$key" "$slug"
  set_agent_name "$key" "$display"
  AGENT_KEYS+=("$key")

  local instructions_file="$BOOTSTRAP_DIR/agent-${slug}-instructions.md"
  agent_instruction_text "$key" "$display" "$desc" "$local_skill" > "$instructions_file"

  log "Creating/updating agent: $display ($slug)"

  if [[ "$DRY_RUN" == "0" ]]; then
    local runtime_id agent_id args_json instructions out_file err_file
    runtime_id="$(resolve_runtime_id)"
    if [[ -z "$runtime_id" ]]; then
      warn "Could not resolve runtime id for RUNTIME_KIND=$RUNTIME_KIND. Set RUNTIME_ID and rerun."
      return 1
    fi
    agent_id="$(find_agent_id_by_name "$display")"
    args_json="$(custom_args_json "$custom_args")"
    instructions="$(cat "$instructions_file")"
    if [[ -n "$agent_id" ]]; then
      out_file="$BOOTSTRAP_DIR/agent-${slug}-update.json"
      err_file="$BOOTSTRAP_DIR/agent-${slug}-update.err"
      multica agent update "$agent_id" \
        --description "$desc" \
        --instructions "$instructions" \
        --custom-args "$args_json" \
        --runtime-id "$runtime_id" \
        --output json > "$out_file" 2>"$err_file" || \
        warn "Could not update agent $display. Check $err_file"
    else
      out_file="$BOOTSTRAP_DIR/agent-${slug}-create.json"
      err_file="$BOOTSTRAP_DIR/agent-${slug}-create.err"
      multica agent create \
        --name "$display" \
        --description "$desc" \
        --instructions "$instructions" \
        --custom-args "$args_json" \
        --runtime-id "$runtime_id" \
        --output json > "$out_file" 2>"$err_file" || \
        warn "Could not create agent $display. Check $err_file"
      agent_id="$(jq -r '.id // .agent.id // empty' "$out_file" 2>/dev/null || true)"
    fi
    if [[ -z "$agent_id" ]]; then
      agent_id="$(find_agent_id_by_name "$display")"
    fi
    set_agent_id "$key" "$agent_id"
  else
    set_agent_id "$key" "DRY_RUN_AGENT_ID_$key"
    echo "+ multica agent create --name \"$display\" --description \"$desc\" --instructions <from $instructions_file> --custom-args \"$(custom_args_json "$custom_args")\" --runtime-id \"$(resolve_runtime_id)\" --output json"
  fi
}

apply_agent_env() {
  local agent_id="$1"
  local env_file="$2"

  if [[ -z "$agent_id" || ! -s "$env_file" ]]; then
    return 0
  fi

  if [[ "$DRY_RUN" == "0" ]]; then
    if [[ "$(jq 'length' "$env_file" 2>/dev/null || echo 0)" == "0" ]]; then
      return 0
    fi
    chmod 600 "$env_file"
    multica agent update "$agent_id" --custom-env-file "$env_file" >/dev/null 2>&1 || \
      warn "Could not set custom env on agent $agent_id from $env_file"
  else
    echo "+ multica agent update \"$agent_id\" --custom-env-file \"$env_file\""
  fi
}

write_env_json() {
  local out_file="$1"
  shift
  printf '%s\n' "$@" | jq -Rn '
    [inputs
     | select(length > 0)
     | capture("^(?<key>[^=]+)=(?<value>.*)$")
     | select(.value != "")
    ] | from_entries
  ' > "$out_file"
}

attach_skill() {
  local agent_id="$1"
  local skill_ref="$2"
  [[ -z "$skill_ref" || -z "$agent_id" ]] && return 0

  local skill_id skill_name
  skill_id="$(get_skill_id "$skill_ref")"
  skill_name="$(get_skill_slug "$skill_ref")"
  if [[ -z "$skill_id" && "$DRY_RUN" == "0" ]]; then
    skill_id="$(find_skill_id_by_name "$skill_name")"
  fi
  if [[ -z "$skill_id" ]]; then
    warn "Skipping skill assignment for $skill_name; no skill id was found."
    return 0
  fi

  log "Attaching skill $skill_name to agent $agent_id"
  if [[ "$DRY_RUN" == "0" ]]; then
    local ids
    ids="$(multica agent skills list "$agent_id" --output json 2>/dev/null | jq -r --arg id "$skill_id" '
      ([.[]?.id] + [$id]) | unique | join(",")
    ' 2>/dev/null || true)"
    ids="${ids:-$skill_id}"
    multica agent skills set "$agent_id" --skill-ids "$ids" >/dev/null 2>&1 || \
      warn "Could not attach skill $skill_name to $agent_id. Check 'multica agent skills --help'."
  else
    echo "+ multica agent skills set \"$agent_id\" --skill-ids \"$skill_id\""
  fi
}

create_agents_and_attach_skills() {
  log "Creating agents and attaching dedicated skills"

  local rec key display desc local_skill public_keys priority custom_args
  for rec in "${AGENTS[@]}"; do
    IFS='|' read -r key display desc local_skill public_keys priority custom_args <<< "$rec"
    create_agent "$key" "$display" "$desc" "$local_skill" "$public_keys" "$priority" "$custom_args"
    local agent_id
    agent_id="$(get_agent_id "$key")"

    attach_skill "$agent_id" "$local_skill"

    IFS=',' read -ra keys <<< "$public_keys"
    local pk
    for pk in "${keys[@]}"; do
      attach_skill "$agent_id" "$pk"
    done
  done
}

apply_environment_variables() {
  log "Applying agent environment variables where supported by your Multica CLI"

  # Global app/runtime variables. Only non-empty values are pushed.
  local common_env=(
    "APP_ENV=${APP_ENV:-development}"
    "APP_BASE_URL=${APP_BASE_URL:-}"
    "PUBLIC_SITE_URL=${PUBLIC_SITE_URL:-}"
    "DATABASE_URL=${DATABASE_URL:-}"
    "DIRECT_URL=${DIRECT_URL:-}"
    "REDIS_URL=${REDIS_URL:-}"
    "RATE_LIMIT_REDIS_URL=${RATE_LIMIT_REDIS_URL:-${REDIS_URL:-}}"
    "OPENAI_API_KEY=${OPENAI_API_KEY:-}"
    "AI_MODEL=${AI_MODEL:-}"
    "AI_SCORING_RETRY_LIMIT=${AI_SCORING_RETRY_LIMIT:-3}"
    "AI_MAX_TOKENS_PER_ATTEMPT=${AI_MAX_TOKENS_PER_ATTEMPT:-}"
    "AI_MONTHLY_BUDGET_EUR=${AI_MONTHLY_BUDGET_EUR:-}"
    "SENTRY_DSN=${SENTRY_DSN:-}"
    "SENTRY_AUTH_TOKEN=${SENTRY_AUTH_TOKEN:-}"
    "SENTRY_ORG=${SENTRY_ORG:-}"
    "SENTRY_PROJECT=${SENTRY_PROJECT:-}"
    "RESEND_API_KEY=${RESEND_API_KEY:-}"
    "AWS_REGION=${AWS_REGION:-}"
    "S3_ENDPOINT=${S3_ENDPOINT:-}"
    "S3_BUCKET=${S3_BUCKET:-}"
    "AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID:-}"
    "AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY:-}"
  )

  local auth_env=(
    "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=${NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY:-}"
    "CLERK_SECRET_KEY=${CLERK_SECRET_KEY:-}"
    "CLERK_WEBHOOK_SIGNING_SECRET=${CLERK_WEBHOOK_SIGNING_SECRET:-}"
  )

  local stripe_env=(
    "STRIPE_SECRET_KEY=${STRIPE_SECRET_KEY:-}"
    "STRIPE_WEBHOOK_SECRET=${STRIPE_WEBHOOK_SECRET:-}"
    "STRIPE_PRICE_STARTER=${STRIPE_PRICE_STARTER:-}"
    "STRIPE_PRICE_MONTHLY=${STRIPE_PRICE_MONTHLY:-}"
    "STRIPE_PRICE_PREMIUM=${STRIPE_PRICE_PREMIUM:-}"
    "MATON_API_KEY=${MATON_API_KEY:-}"
  )

  local agent_key agent_slug agent_id env_file
  for agent_key in "${AGENT_KEYS[@]}"; do
    agent_slug="$(get_agent_slug "$agent_key")"
    agent_id="$(get_agent_id "$agent_key")"
    env_file="$BOOTSTRAP_DIR/agent-${agent_slug}-env.json"
    write_env_json "$env_file" "${common_env[@]}"
    apply_agent_env "$agent_id" "$env_file"
  done

  for agent_key in auth_accounts qa_release; do
    agent_slug="$(get_agent_slug "$agent_key")"
    agent_id="$(get_agent_id "$agent_key")"
    env_file="$BOOTSTRAP_DIR/agent-${agent_slug}-env.json"
    write_env_json "$env_file" "${common_env[@]}" "${auth_env[@]}"
    apply_agent_env "$agent_id" "$env_file"
  done

  for agent_key in payments_entitlements qa_release; do
    agent_slug="$(get_agent_slug "$agent_key")"
    agent_id="$(get_agent_id "$agent_key")"
    env_file="$BOOTSTRAP_DIR/agent-${agent_slug}-env.json"
    if [[ "$agent_key" == "qa_release" ]]; then
      write_env_json "$env_file" "${common_env[@]}" "${auth_env[@]}" "${stripe_env[@]}"
    else
      write_env_json "$env_file" "${common_env[@]}" "${stripe_env[@]}"
    fi
    apply_agent_env "$agent_id" "$env_file"
  done
}

write_issue_file() {
  local key="$1" title="$2" desc="$3"
  cat > "$ISSUES_DIR/${key}.md" <<EOF
$title

$desc
EOF
}

create_issue() {
  local project_id="$1"
  local key="$2"
  local title="$3"
  local desc="$4"
  local priority="$5"
  local assignee="$6"

  write_issue_file "$key" "$title" "$desc"

  log "Creating issue: $title -> $assignee"
  if [[ "$DRY_RUN" == "0" ]]; then
    if [[ -n "$project_id" && "$project_id" != "DRY_RUN_PROJECT_ID" ]]; then
      multica issue create \
        --title "$title" \
        --description "$desc" \
        --priority "$priority" \
        --status todo \
        --assignee "$assignee" \
        --project "$project_id" \
        --output json > "$ISSUES_DIR/${key}.json" 2>"$ISSUES_DIR/${key}.err" || \
        warn "Issue create failed: $title. Check $ISSUES_DIR/${key}.err"
    else
      multica issue create \
        --title "$title" \
        --description "$desc" \
        --priority "$priority" \
        --status todo \
        --assignee "$assignee" \
        --output json > "$ISSUES_DIR/${key}.json" 2>"$ISSUES_DIR/${key}.err" || \
        warn "Issue create failed: $title. Check $ISSUES_DIR/${key}.err"
    fi
  else
    echo "+ multica issue create --title \"$title\" --priority \"$priority\" --status todo --assignee \"$assignee\" ${project_id:+--project \"$project_id\"}"
  fi
}

issue_text_pm_plan() {
  cat <<'EOF'
Context:
The current prototype is a local exam studio. The MVP target is a commercial learner-facing product with account creation, free/paid exam access, persisted attempt history, objective and AI scoring, Stripe payment, results dashboard, legal disclaimer, and HTTPS production deployment.

Tasks:
1. Create a phased implementation plan from current prototype to first commercial release.
2. Convert roadmap into sprint-sized issues with dependencies and acceptance criteria.
3. Identify sequencing constraints between frontend, backend, auth, payment, scoring, content validation, and DevOps.
4. Create a release-readiness checklist.

Acceptance criteria:
- Delivery plan exists in docs/mvp-delivery-plan.md.
- Dependency map exists in docs/mvp-dependency-map.md.
- Release checklist exists in docs/release-checklist.md.
- Each downstream issue has owner, inputs, outputs, tests, and blocker handling.
EOF
}

issue_text_product_flow() {
  cat <<'EOF'
Tasks:
1. Rename learner-facing UI from Studio to Exam Simulator.
2. Hide developer/debug panels by default: Markdown, JSON, TTS, Images, Quality.
3. Add learner flow: welcome, candidate details, instructions, listening, reading, writing, speaking, results.
4. Add real simulation mode and practice mode.
5. Implement real mode restrictions: locked order, no answer key exposure, no casual section switching, auto-submit on timer end.
6. Improve result page with skill scores, pass/fail per skill, total out of 60, weak areas, next-practice suggestions.

Acceptance criteria:
- Normal learner cannot access answer keys or debug panels.
- Real simulation mode creates exactly one attempt flow.
- Practice mode allows section-level practice/review.
- UI has basic accessibility labels and keyboard navigation.
- Include tests for mode switching, timer expiry, and results rendering.
EOF
}

issue_text_backend() {
  cat <<'EOF'
Tasks:
1. Replace browser-only attempt persistence with backend API.
2. Add Postgres schema and migrations for users, exams, attempts, answers, scores, AI evaluations, payments/subscriptions, entitlements.
3. Implement attempt lifecycle: started, in_progress, submitted, scored, expired.
4. Store exam content version per attempt.
5. Move objective scoring server-side.
6. Add structured API errors and rate limits for scoring endpoints.

Acceptance criteria:
- API supports start attempt, save answer, submit attempt, get scored attempt, list attempt history.
- Objective scoring works from structured answer keys.
- Historical attempt remains reproducible even after exam content changes.
- Tests cover lifecycle transitions, invalid transitions, scoring, and rate limits.
EOF
}

issue_text_auth() {
  cat <<'EOF'
Tasks:
1. Add account creation and login.
2. Add learner profile: name, email, native language if useful, exam target date.
3. Add dashboard: attempts taken, latest score, skill progress, subscription/exam pack status.
4. Add account recovery if password auth is used.
5. Add account deletion/export flow.
6. Add auth webhook sync to local database.

Acceptance criteria:
- Protected routes cannot be accessed anonymously.
- Learner can view attempt history across sessions/devices.
- Auth webhooks verify signatures and are idempotent.
- Secret keys are never exposed to client bundle.
- Tests cover sign-in, protected route, webhook verification, and dashboard data.
EOF
}

issue_text_payments() {
  cat <<'EOF'
Tasks:
1. Define Stripe products: single exam simulation, exam pack, monthly subscription, optional AI scoring credits.
2. Implement Stripe Checkout.
3. Implement entitlements: free exam access, paid exam access, remaining attempts, remaining AI-scored submissions.
4. Implement Stripe webhooks: payment succeeded, subscription created, renewed, canceled, refund, chargeback.
5. Add billing page and upgrade prompts after free exam completion.

Acceptance criteria:
- Free user can take exactly the configured free exam.
- Paid user gets correct exam pack/subscription entitlement.
- Webhook handling is idempotent and auditable.
- Refund/chargeback removes or freezes relevant entitlement.
- Tests use Stripe test mode fixtures or mocked webhook signatures.
EOF
}

issue_text_ai_scoring() {
  cat <<'EOF'
Tasks:
1. Build provider abstraction for AI scoring.
2. Implement writing and speaking scoring rubrics with deterministic prompt templates.
3. Store prompt version, rubric version, model, input hash, provider status, score, feedback, retry/failure state, and estimated cost.
4. Add quotas by user/plan and retry caps.
5. Add request size limits and cost telemetry.
6. Clearly label scores as practice estimates, not official results.

Acceptance criteria:
- AI scoring only applies to writing/speaking/free text.
- Scoring output is schema validated.
- Retries and failure states are visible to user/admin.
- Quotas prevent unbounded LLM spend.
- Tests cover successful scoring, invalid model response, provider timeout, quota exceeded, and retry exhaustion.
EOF
}

issue_text_content() {
  cat <<'EOF'
Tasks:
1. Define structured exam JSON schema.
2. Build parser/importer from current Markdown mock exam format.
3. Include metadata, sections, tasks, questions, options, correct answers, audio/image assets, scoring rules.
4. Add validation checks: missing answer keys, broken audio/image links, duplicate options, unexpected point totals, missing scoring metadata.
5. Add content workflow statuses: draft, review, published, archived.

Acceptance criteria:
- Current mock exams can be imported into structured JSON.
- Validator fails clearly on broken assets or scoring inconsistencies.
- Published exams are versioned and immutable for historical attempts.
- Tests include valid exam fixture and multiple invalid fixtures.
EOF
}

issue_text_media_realism() {
  cat <<'EOF'
Tasks:
1. Add stricter real simulation controls: no pause, auto-submit on timeout, one final submit per section/attempt.
2. Add optional listening playback count tracking.
3. Add browser microphone recording for speaking tasks.
4. Upload speaking audio to object storage.
5. Add playback for review and optional speech-to-text path.
6. Add candidate-style report and PDF export.

Acceptance criteria:
- Real simulation timer behavior is deterministic.
- Speaking recording works with permission handling and failure states.
- Audio upload uses signed URLs or secure server-mediated upload.
- Candidate report includes total score, skill scores, pass/fail, corrections, recommendations, and disclaimer.
- Tests cover timeout, upload failure, and report generation.
EOF
}

issue_text_ops() {
  cat <<'EOF'
Tasks:
1. Prepare production deployment with HTTPS and custom domain.
2. Store secrets in platform-managed environment variables.
3. Add structured logs and Sentry monitoring.
4. Alert on API errors, scoring failures, payment webhook failures, login failures, and high LLM cost.
5. Configure database backups.
6. Add admin-only access controls, rate limiting, and abuse protection.
7. Add privacy policy, terms of service, and clear unofficial simulator disclaimer.

Acceptance criteria:
- Deployment docs exist with env var matrix.
- Health checks and monitoring are configured.
- Backups are documented and tested.
- Legal pages and disclaimer are visible before payment and on results.
- Security review documents key risks and mitigations.
EOF
}

issue_text_qa_release() {
  cat <<'EOF'
Tasks:
1. Add E2E tests for full learner journey: sign up, choose free/paid exam, take exam, submit, view results/history.
2. Add tests for real simulation restrictions and timer expiry.
3. Add tests for auth-protected routes.
4. Add tests for entitlement enforcement and Stripe webhook idempotency.
5. Add tests for AI scoring failure/retry/quota states.
6. Create release regression checklist.

Acceptance criteria:
- CI can run deterministic tests without live paid APIs.
- Test fixtures exist for exam content, auth sessions, payments, scoring responses, and media upload.
- Release checklist blocks launch if critical flows fail.
- QA summary is posted to each issue before marking ready for review.
EOF
}

create_issues() {
  local project_id="$1"
  log "Creating issues and assigning to agents"

  create_issue "$project_id" "001-program-plan" \
    "[MVP] Create delivery plan, dependency map, and release checklist" \
    "$(issue_text_pm_plan)" "high" "$(get_agent_name program_manager)"

  create_issue "$project_id" "002-product-flow" \
    "[Frontend] Productize learner exam flow and hide debug views" \
    "$(issue_text_product_flow)" "high" "$(get_agent_name product_ux)"

  create_issue "$project_id" "003-backend-persistence" \
    "[Backend] Add persisted attempts, server-side scoring, and exam history API" \
    "$(issue_text_backend)" "high" "$(get_agent_name backend_api)"

  create_issue "$project_id" "004-auth-accounts" \
    "[Auth] Add accounts, learner profile, dashboard, and webhook sync" \
    "$(issue_text_auth)" "high" "$(get_agent_name auth_accounts)"

  create_issue "$project_id" "005-payments-entitlements" \
    "[Payments] Add Stripe Checkout, subscriptions, exam packs, and entitlements" \
    "$(issue_text_payments)" "high" "$(get_agent_name payments_entitlements)"

  create_issue "$project_id" "006-ai-scoring" \
    "[AI Scoring] Add rubric scoring, retries, quotas, and cost controls" \
    "$(issue_text_ai_scoring)" "high" "$(get_agent_name ai_scoring)"

  create_issue "$project_id" "007-content-quality" \
    "[Content] Build structured exam bank importer and validation pipeline" \
    "$(issue_text_content)" "medium" "$(get_agent_name content_quality)"

  create_issue "$project_id" "008-exam-realism-media" \
    "[Exam Realism] Add speaking recording, upload, playback controls, and PDF report" \
    "$(issue_text_media_realism)" "medium" "$(get_agent_name product_ux)"

  create_issue "$project_id" "009-ops-security" \
    "[Ops] Deploy with HTTPS, monitoring, backups, rate limits, and legal pages" \
    "$(issue_text_ops)" "high" "$(get_agent_name devops_security)"

  create_issue "$project_id" "010-qa-release" \
    "[QA] Add end-to-end regression suite and release gate checklist" \
    "$(issue_text_qa_release)" "high" "$(get_agent_name qa_release)"
}

write_env_template() {
  cat > "$BOOTSTRAP_DIR/.env.multica-latvian-a2.example" <<'EOF'
# Multica authentication/workspace
MULTICA_PAT=mul_REPLACE_ME
WORKSPACE_ID=
PROJECT_ID=

# Daemon/runtime tuning
MULTICA_AGENT_TIMEOUT=3h
MULTICA_DAEMON_MAX_CONCURRENT_TASKS=4
MULTICA_WORKSPACES_ROOT=~/multica_workspaces
RUNTIME_KIND=codex
READ_ONLY_ARGS=--sandbox read-only
BUILD_ARGS=--sandbox workspace-write
REVIEW_ARGS=--sandbox read-only
SECURITY_ARGS=--sandbox read-only

# App URLs
APP_ENV=development
APP_BASE_URL=http://localhost:3000
PUBLIC_SITE_URL=http://localhost:3000

# Database/cache
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/latvian_a2
DIRECT_URL=postgresql://postgres:postgres@localhost:5432/latvian_a2
REDIS_URL=redis://localhost:6379/0
RATE_LIMIT_REDIS_URL=redis://localhost:6379/1

# Auth: Clerk by default in this bootstrap
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_REPLACE_ME
CLERK_SECRET_KEY=sk_test_REPLACE_ME
CLERK_WEBHOOK_SIGNING_SECRET=whsec_REPLACE_ME

# Payments: Stripe
STRIPE_SECRET_KEY=sk_test_REPLACE_ME
STRIPE_WEBHOOK_SECRET=whsec_REPLACE_ME
STRIPE_PRICE_STARTER=price_REPLACE_ME
STRIPE_PRICE_MONTHLY=price_REPLACE_ME
STRIPE_PRICE_PREMIUM=price_REPLACE_ME

# Optional ClawHub Stripe API skill
MATON_API_KEY=

# AI scoring
OPENAI_API_KEY=sk-REPLACE_ME
AI_MODEL=
AI_SCORING_RETRY_LIMIT=3
AI_MAX_TOKENS_PER_ATTEMPT=12000
AI_MONTHLY_BUDGET_EUR=100

# Object storage for speaking uploads/assets
AWS_REGION=eu-north-1
S3_ENDPOINT=
S3_BUCKET=latvian-a2-media
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=

# Observability/email
SENTRY_DSN=
SENTRY_AUTH_TOKEN=
SENTRY_ORG=
SENTRY_PROJECT=
RESEND_API_KEY=
EOF
}

write_summary() {
  cat > "$BOOTSTRAP_DIR/README.md" <<EOF
# Latvian A2 Multica Bootstrap

Generated by multica_latvian_a2_bootstrap.sh.

## Agents

$(for rec in "${AGENTS[@]}"; do IFS='|' read -r key display desc local_skill public_keys priority custom_args <<< "$rec"; printf -- "- %s: %s\n" "$display" "$desc"; done)

## Public skills requested for import

$(for rec in "${PUBLIC_SKILLS[@]}"; do IFS='|' read -r key expected source url why <<< "$rec"; printf -- "- %s (%s): %s — %s\n" "$expected" "$source" "$url" "$why"; done)

## Local project skills

- latvian-a2-program-management
- latvian-a2-product-flow
- latvian-a2-backend-api
- latvian-a2-auth-accounts
- latvian-a2-monetization
- latvian-a2-ai-scoring
- latvian-a2-content-quality
- latvian-a2-devops-security
- latvian-a2-test-release

## Next commands

\`\`\`bash
cp .env.multica-latvian-a2.example .env.multica-latvian-a2
# edit values
set -a && source .env.multica-latvian-a2 && set +a
DRY_RUN=0 ./multica_latvian_a2_bootstrap.sh
\`\`\`
EOF
}

main() {
  require_tools
  write_env_template
  write_summary
  login_if_needed
  set_workspace_if_provided
  start_daemon_if_requested

  local project_id
  project_id="$(create_or_get_project)"

  import_public_skills
  create_project_skills
  import_project_skills
  create_agents_and_attach_skills
  apply_environment_variables
  create_issues "$project_id"
  write_summary

  log "Bootstrap complete"
  log "Output directory: $BOOTSTRAP_DIR"
  if [[ "$DRY_RUN" != "0" ]]; then
    warn "This was a dry run. Execute with DRY_RUN=0 after reviewing $BOOTSTRAP_DIR/.env.multica-latvian-a2.example"
  fi
}

main "$@"
