# MVP Delivery Plan

## Purpose

This plan turns the current Latvian A2 exam prototype into a commercial learner-facing MVP with accounts, paid access, persisted attempts, scoring, monitoring, and launch-ready legal positioning.

The plan is intentionally sequenced around the current repository state:

- The browser exam app already exists in `latvian-a2-exam-app/`.
- Exam content already exists in `codex/`.
- Server-side scoring already exists in `server.py`.
- The MVP work is mostly productization, persistence, access control, and release hardening.

## Delivery Principles

- Keep learner-facing changes small enough to review and test in one sprint.
- Do not expose answer keys, scoring prompts, or provider secrets to normal users.
- Treat AI scoring as a practice estimate, never as an official exam result.
- Prefer incremental migration over a full rewrite.
- Preserve historical attempt reproducibility by versioning exam content.

## Phased Plan

### Phase 1: Productize The Learner Experience

Goal: make the prototype feel like a real exam product instead of a developer studio.

Primary issues:

- `HUM-8` Frontend product flow and debug view hiding.
- `HUM-13` Structured exam bank importer and validation pipeline.
- `HUM-14` Speaking recording, upload, playback, and PDF report.

Exit criteria:

- Learners can complete a realistic exam flow without seeing internal debug tools.
- Exam content is validated before release.
- Speaking practice can capture and review audio.

### Phase 2: Add Durable Core Platform Services

Goal: make attempts, accounts, and entitlements survive browser refreshes and device changes.

Primary issues:

- `HUM-9` Persisted attempts, server-side scoring, and exam history API.
- `HUM-10` Accounts, learner profile, dashboard, and auth webhook sync.
- `HUM-11` Stripe Checkout, subscriptions, exam packs, and entitlements.

Exit criteria:

- Attempts are stored server-side and can be reopened later.
- Users can sign in and see their own history.
- Paid access is enforced by entitlement, not by front-end hiding alone.

### Phase 3: Control Cost And Scoring Quality

Goal: keep AI scoring useful, bounded, and auditable.

Primary issue:

- `HUM-12` Rubric scoring, retries, quotas, and cost controls.

Exit criteria:

- Writing and speaking scoring is schema-validated.
- Failures, retries, and quota states are visible.
- Scoring cost stays within a controlled per-user and per-plan budget.

### Phase 4: Prepare Production Operations

Goal: make the app safe to deploy publicly with clear operational and legal boundaries.

Primary issues:

- `HUM-15` HTTPS deployment, monitoring, backups, rate limits, and legal pages.
- `HUM-16` End-to-end regression suite and release gate checklist.

Exit criteria:

- The app runs behind HTTPS with monitored health checks.
- Backups, alerts, and legal pages are in place.
- A regression gate blocks release if critical flows fail.

## Downstream Issue Breakdown

### HUM-8 - Frontend productize learner exam flow and hide debug views

- Owner: Product UX Exam Flow Agent.
- Inputs: the current static app shell, Markdown-based exam content, and the existing timer/state model.
- Outputs: learner-facing home, registration, instructions, exam, and results flow; real and practice modes; hidden debug panels.
- Tests: mode switching, timer expiry, result rendering, and basic accessibility coverage.
- Blocker handling: if content format changes, keep a thin adapter layer in the frontend rather than hard-coding new parsing logic in the UI.

### HUM-9 - Persisted attempts, server-side scoring, and exam history API

- Owner: Backend Persistence Agent.
- Inputs: the current submission model, exam content, and existing `/api/evaluate` behavior.
- Outputs: Postgres schema, attempt lifecycle API, persisted scores, and server-side objective scoring.
- Tests: lifecycle transitions, invalid transitions, scoring correctness, and rate-limit behavior.
- Blocker handling: if the database schema is not stable, gate the frontend on a compatibility layer and keep attempt writes idempotent.

### HUM-10 - Accounts, learner profile, dashboard, and auth webhook sync

- Owner: Auth and Profiles Agent.
- Inputs: the persisted attempt API, candidate identity fields, and the chosen auth provider.
- Outputs: login, account recovery if needed, learner profile, progress dashboard, and auth sync into the database.
- Tests: sign-in, protected route access, webhook verification, and dashboard data visibility.
- Blocker handling: if auth provider setup is delayed, build the profile and dashboard contract against mocked identity data first.
- MVP auth decision: keep the current server-managed email/password session flow as the launch path and defer an external IdP migration until the product needs it. See [[Auth Accounts MVP Decision]].
- Deterministic smoke coverage: `scripts/smoke_auth_accounts.py` exercises register, login, logout, dashboard visibility, webhook rejection, export, delete, and secret-leak checks against a throwaway server instance.

### HUM-11 - Stripe Checkout, subscriptions, exam packs, and entitlements

- Owner: Payments Agent.
- Inputs: authenticated users, product catalog decisions, and the attempt history API.
- Outputs: Stripe products, checkout flow, webhook handling, entitlement enforcement, and upgrade prompts.
- Tests: Stripe test mode, webhook idempotency, entitlement grants, and entitlement revocation on refund or chargeback.
- Blocker handling: if live billing is not ready, keep the entitlement layer testable with mocked payment events and feature flags.

### HUM-12 - Rubric scoring, retries, quotas, and cost controls

- Owner: AI Scoring Agent.
- Inputs: persisted attempts, writing and speaking responses, and the scoring prompt/rubric version.
- Outputs: validated scoring records, retry handling, quota tracking, and cost telemetry.
- Tests: valid scoring, invalid model output, timeout, quota exceeded, and retry exhaustion.
- Blocker handling: if a provider is unstable, fail safely into a visible pending or retry state rather than producing silent partial scores.

### HUM-13 - Structured exam bank importer and validation pipeline

- Owner: Content Bank QA Agent.
- Inputs: the Markdown exam vault, audio/image attachments, and the current answer-key structure.
- Outputs: structured exam JSON, validation rules, draft/review/published/archive workflow, and import tooling.
- Tests: valid import fixtures and invalid fixtures for broken assets, duplicate options, missing answers, and score inconsistencies.
- Blocker handling: if import validation finds broken content, freeze publication of that exam revision until the fixture is corrected.

### HUM-14 - Speaking recording, upload, playback controls, and PDF report

- Owner: Product UX Exam Flow Agent.
- Inputs: the speaking section flow, media storage strategy, and scoring output.
- Outputs: microphone capture, upload path, playback review, and a candidate-facing report.
- Tests: timer expiry, upload failure, permission handling, and report generation.
- Blocker handling: if upload infrastructure is delayed, keep the local review flow working while the storage integration is isolated behind an interface.

### HUM-15 - Deploy with HTTPS, monitoring, backups, rate limits, and legal pages

- Owner: DevOps Security Ops Agent.
- Inputs: the app, API, auth, billing, and scoring services.
- Outputs: production deployment, secrets handling, monitoring, backup guidance, rate limiting, privacy policy, terms, and disclaimer pages.
- Tests: health checks, alerting, backup verification, and access-control checks.
- Blocker handling: if production infra is not yet approved, keep the app deployable in a staging environment with the same config contract.

### HUM-16 - End-to-end regression suite and release gate checklist

- Owner: QA Release Agent.
- Inputs: stable app flows, mocked auth and billing fixtures, scoring responses, and media assets.
- Outputs: regression suite, release gate checklist, and launch verification evidence.
- Tests: full learner journey, real simulation restrictions, auth-protected routes, payment webhooks, scoring failure states, and release checklist coverage.
- Blocker handling: if a critical dependency is missing, mark the gate blocked and document the exact missing fixture or environment prerequisite.

## Recommended Sequencing

1. Finish `HUM-13` so the exam content has a stable contract.
2. Finish `HUM-9` so attempts and scoring are durable.
3. Finish `HUM-8` and `HUM-14` so the learner experience is product-ready.
4. Finish `HUM-10` and `HUM-11` so access control and billing are enforceable.
5. Finish `HUM-12` so AI scoring is bounded and auditable.
6. Finish `HUM-15` and `HUM-16` so the release is production-safe.

## Source Notes

- [[Latvian A2 Exam Simulator Roadmap]]
- [[Solution Architecture]]
- [[Cloud Hosting and Improvement Architecture]]
