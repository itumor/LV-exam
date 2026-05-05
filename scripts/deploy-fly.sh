#!/bin/bash
set -euo pipefail

echo "=== Latvian A2 Exam - Fly.io Deploy ==="

# Check flyctl is installed
if ! command -v flyctl &>/dev/null; then
  echo "ERROR: flyctl not installed. Run: brew install flyctl"
  exit 1
fi

# Load env
if [ -f .env ]; then
  set -a && source .env && set +a
fi

# Check auth - use token from env if available
if [ -n "${FLY_API_TOKEN:-}" ]; then
  echo "Using FLY_API_TOKEN from environment."
  export FLY_API_TOKEN
else
  if ! flyctl auth whoami &>/dev/null; then
    echo "ERROR: Not logged in and FLY_API_TOKEN not set. Run: flyctl auth login"
    exit 1
  fi
fi

echo ""
echo "1/5 Checking app status..."
flyctl status --app latvian-a2-exam 2>/dev/null || true

echo ""
echo "2/5 Ensuring volumes exist..."
flyctl volumes list --app latvian-a2-exam 2>/dev/null || true

# Create volumes if they don't exist
if ! flyctl volumes list --app latvian-a2-exam 2>/dev/null | grep -q auth_data; then
  echo "Creating auth_data volume..."
  flyctl volumes create auth_data --region lhr --size 1 --app latvian-a2-exam
fi

if ! flyctl volumes list --app latvian-a2-exam 2>/dev/null | grep -q billing_data; then
  echo "Creating billing_data volume..."
  flyctl volumes create billing_data --region lhr --size 1 --app latvian-a2-exam
fi

echo ""
echo "3/5 Setting secrets..."
flyctl secrets set \
  LLM_PROVIDER="${LLM_PROVIDER:-groq}" \
  LLM_MODEL="${LLM_MODEL:-llama-3.3-70b-versatile}" \
  --app latvian-a2-exam

if [ -n "${GROQ_API_KEY:-}" ]; then
  flyctl secrets set GROQ_API_KEY="$GROQ_API_KEY" --app latvian-a2-exam
fi

echo ""
echo "4/5 Building and deploying..."
flyctl deploy --app latvian-a2-exam --remote-only

echo ""
echo "5/5 Verifying deployment..."
sleep 5
APP_URL=$(flyctl status --app latvian-a2-exam --json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'https://{d[\"Hostname\"]}')" 2>/dev/null || echo "https://latvian-a2-exam.fly.dev")
echo "App URL: $APP_URL"
echo "Health:  $APP_URL/healthz"
echo "App:     $APP_URL/latvian-a2-exam-app/"
