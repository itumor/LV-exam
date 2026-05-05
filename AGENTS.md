# AGENTS.md

## Repo Overview
Latvian A2 Exam Simulator: static frontend (`latvian-a2-exam-app/`) + Python backend (`server.py`, Python 3.12+). Node 20 required for Playwright E2E tests.

## Key Commands
- Local server: `python3 server.py` (default port 4173, set `PORT` env to override)
- All tests: `npm test` (or `./scripts/run_regression_suite.sh`)
  - Single Python test: `python3 -m unittest tests.server.test_attempt_lifecycle`
  - Single Playwright test: `npx playwright test tests/playwright/release-regression.spec.js`
- Test deps: `npm ci && npx playwright install --with-deps chromium`
- Fly.io deploy: `./scripts/deploy-fly.sh` (requires `flyctl` auth + `.env` secrets)
- Docker local: `docker compose up --build` (set `APP_PORT` to change host port)

## Configuration
- Copy `.env-example` to `.env`:
  - `LLM_PROVIDER`: `groq` (needs `GROQ_API_KEY`) or `codex` (needs `CODEX_REMOTE_URL` for Docker)
  - `STRIPE_SECRET_KEY`: Unset = Stripe mock mode
  - `A2_BOOTSTRAP_SUPERADMIN_*`: Creates first superadmin if no users exist
- Fly.io mounts: `auth_data` → `.multica/`, `billing_data` → `data/`

## Gotchas
- AI scoring requires `server.py` (browser never holds LLM/Stripe keys)
- Docker can't run macOS Codex CLI: run host server on port 4174, set `CODEX_REMOTE_URL=http://host.docker.internal:4174/api/evaluate`
- Playwright requires Chromium: `npx playwright install chromium`
- CI flow: `npm ci` → `npx playwright install chromium` → `npm test`
