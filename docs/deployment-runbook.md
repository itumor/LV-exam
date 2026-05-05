# Production Deployment Runbook

## Purpose

This runbook captures the minimum production setup for Latvian A2 Exam Studio: HTTPS, managed secrets, health checks, rate limits, backups, and operational monitoring.

It is written for the current single-container architecture with local SQLite auth and billing stores. Move the same data to managed Postgres before scaling beyond a single writable instance.

## Deployment Model

- Run the app behind a managed HTTPS edge or load balancer.
- Keep the container stateless except for in-memory caches.
- Store all secrets in the platform secret manager or managed environment variables.
- Expose only the web origin and do not expose provider keys to the browser.

## Environment Variable Matrix

| Variable | Required | Example | Purpose |
| --- | --- | --- | --- |
| `PORT` | Yes | `80` | HTTP listen port inside the container. |
| `LLM_PROVIDER` | Yes | `groq` | Selects `groq` or `codex` scoring mode. |
| `LLM_MODEL` | No | `llama-3.3-70b-versatile` | Overrides the Groq model. |
| `GROQ_API_KEY` | Groq only | secret | Provider credential kept server-side. |
| `GROQ_BASE_URL` | No | `https://api.groq.com/openai/v1` | Alternative Groq-compatible endpoint. |
| `CODEX_REMOTE_URL` | Codex remote mode | `https://scoring.example/api/evaluate` | Forwards scoring to a trusted host. |
| `CODEX_MODEL` | No | `gpt-5.2` | Model label used by Codex scoring. |
| `CODEX_PROFILE` | No | `prod` | Optional Codex CLI profile. |
| `CODEX_OSS` | No | `false` | Enables OSS Codex CLI defaults. |
| `CODEX_LOCAL_PROVIDER` | No | `ollama` | Local provider name for Codex OSS mode. |
| `CODEX_CLI_PATH` | No | `/usr/local/bin/codex` | Custom path to the Codex executable. |
| `CODEX_TIMEOUT_SECONDS` | No | `300` | Scoring timeout for local or remote Codex mode. |
| `EVALUATE_RATE_LIMIT_PER_MINUTE` | No | `20` | Per-IP evaluation request cap. |
| `EVALUATE_RATE_LIMIT_WINDOW_SECONDS` | No | `60` | Sliding window for the evaluation limiter. |
| `AUTH_DB_PATH` | No | `/data/auth.sqlite3` | SQLite account, profile, session, attempt, and auth webhook store. |
| `AUTH_WEBHOOK_SECRET` | Yes | secret | HMAC secret for auth sync webhooks. |
| `BILLING_DB_PATH` | No | `/data/billing.sqlite3` | SQLite learner entitlement, Stripe event, and billing activity store. |
| `STRIPE_SECRET_KEY` | Production billing | secret | Stripe API key, never exposed to the browser. |
| `STRIPE_WEBHOOK_SECRET` | Production billing | secret | Stripe webhook verification secret. |
| `STRIPE_PRICE_SINGLE_EXAM` | Production billing | `price_...` | Stripe price for one exam simulation. |
| `STRIPE_PRICE_EXAM_PACK` | Production billing | `price_...` | Stripe price for a multi-exam pack. |
| `STRIPE_PRICE_MONTHLY_SUBSCRIPTION` | Production billing | `price_...` | Stripe price for subscription access. |
| `STRIPE_PRICE_AI_CREDITS` | Production billing | `price_...` | Stripe price for AI scoring credits. |
| `SENTRY_DSN` | No | secret | Enables optional error monitoring. |
| `SENTRY_TRACES_SAMPLE_RATE` | No | `0.0` | Controls tracing volume when Sentry is enabled. |
| `APP_ENV` | No | `production` | Environment label for logs and Sentry. |
| `APP_RELEASE` | No | `git-sha` | Release label for error reporting. |

## Health Checks

- `GET /healthz` returns a compact JSON response for platform checks.
- The Docker health check should use `http://127.0.0.1:${PORT}/healthz`.
- Smoke test the learner app at `/latvian-a2-exam-app/` after each deploy.

## Monitoring

Minimum signals to alert on:

- `/api/evaluate` 5xx responses.
- `/api/evaluate` 429 responses.
- Scoring timeouts.
- Login failures on `/api/auth/login`.
- Payment webhook failures on `/api/stripe/webhook`.
- Unusual LLM cost spikes or provider retry storms.

Recommended logging shape:

- JSON access logs with method, path, status, size, and remote IP.
- Error logs with request context and a short message.
- No full answer keys or provider secrets in logs.

## Backup and Restore

Current state:

- Auth data is stored in SQLite at `AUTH_DB_PATH` or `.multica/auth.sqlite3`.
- Billing and entitlement data is stored in SQLite at `BILLING_DB_PATH` or `data/billing.sqlite3`.
- Browser localStorage is only a client cache and is not a backup source.

Backup procedure:

1. Mount the database directory on durable platform storage.
2. Run `python3 scripts/backup_sqlite.py --output-dir /backups/latvian-a2` at least daily.
3. Copy backup artifacts to platform object storage with lifecycle retention.
4. Verify the latest backup with `sqlite3 <backup-file> "PRAGMA integrity_check;"`.
5. Restore into a staging deployment and confirm login, dashboard attempts, entitlements, and Stripe event idempotency.

Restore test evidence:

- The backup script runs SQLite online backup and `PRAGMA integrity_check` on every backup it creates.
- CI or release smoke should run `python3 scripts/backup_sqlite.py --verify-only` against seeded auth and billing stores.
- Record the backup filenames and restore target in the release checklist before launch.

## Release Checklist

Before launch:

1. Confirm HTTPS is active on the production hostname.
2. Confirm secrets are only present in the platform secret manager.
3. Confirm `/healthz` is healthy.
4. Confirm rate limiting is active on `/api/evaluate`.
5. Confirm monitoring can page on provider and application failures.
6. Confirm privacy policy, terms, and disclaimer pages are linked from the UI.
7. Record the deployment revision and rollback path.
