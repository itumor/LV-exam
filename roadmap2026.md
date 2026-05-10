# Latvian A2 Exam Simulator Roadmap 2026

## Purpose

This roadmap turns the current Latvian A2 Exam Simulator prototype into a production-ready commercial MVP.

The product already has a browser exam flow, generated content, audio and image assets, timed sections, local scoring, AI evaluation, Docker support, debug views, and local storage persistence. The next step is to harden the product for commercial use with accounts, payments, durable persistence, access control, monitoring, legal positioning, and a release process that can be operated safely.

## Source Of Truth

This roadmap is aligned with the existing planning docs in the repository:

- `docs/roadmap/ROADMAP.md`
- `docs/roadmap/MILESTONES.md`
- `docs/mvp-delivery-plan.md`
- `docs/mvp-dependency-map.md`
- `docs/release-checklist.md`

If these documents diverge, the more specific downstream planning docs should be updated to match this roadmap.

## Current State

- Static frontend lives in `latvian-a2-exam-app/`.
- Python backend handles server-side logic, auth, billing, uploads, and scoring.
- Exam content and media are already present in the repository.
- SQLite-backed persistence is in use for local and packaged workflows.
- Docker and Fly.io deployment paths already exist.
- Regression coverage exists across Python tests, contract tests, and Playwright flows.

## Product Goal

Deliver a commercial learner-facing MVP with:

- Account creation and login
- Free sample access and paid exam packs
- Persisted attempt history
- Objective scoring plus AI feedback for writing and speaking
- Stripe payment flow and entitlement enforcement
- Results dashboard and learner history
- Legal disclaimer, privacy, and terms pages
- HTTPS production deployment with monitoring and backups

## Delivery Principles

- Keep changes small and reviewable.
- Preserve answer-key secrecy and provider secrets.
- Never present AI scoring as an official exam result.
- Prefer incremental migration over a rewrite.
- Verify each milestone with tests and acceptance evidence.
- Keep the deployment surface as small as possible unless scaling needs prove otherwise.

## 2026 Roadmap Phases

### Phase 1: Productize The Learner Flow

Goal: make the exam app feel like a real product rather than a developer prototype.

Focus:

- Hide internal debug views from normal users.
- Improve the learner journey across home, instructions, exam, and results.
- Stabilize exam-bank import and content validation.
- Add speaking capture, upload, playback, and review behavior where needed.

Exit criteria:

- A learner can complete a realistic exam flow without seeing internal tooling.
- Content validation prevents broken or incomplete exam revisions from shipping.

### Phase 2: Add Durable Core Services

Goal: make user progress and exam attempts survive refreshes, devices, and deployment cycles.

Focus:

- Persist attempts server-side.
- Keep scoring and history retrievable from the backend.
- Add accounts and learner profile views.
- Enforce access through server-side entitlements, not UI hiding alone.

Exit criteria:

- Attempts are durable and reopenable.
- Learners can sign in and see their own history.
- Paid access is enforced on the server.

### Phase 3: Control AI Scoring Cost And Quality

Goal: keep AI evaluation bounded, predictable, and auditable.

Focus:

- Validate scoring payloads and responses.
- Add retry and quota handling.
- Make failures visible instead of silent.
- Track cost-sensitive paths.

Exit criteria:

- Writing and speaking scoring has explicit failure modes.
- Quota and retry states are visible to operators and users.

### Phase 4: Prepare Production Operations

Goal: make the service safe to launch publicly.

Focus:

- HTTPS deployment.
- Monitoring and alerting.
- Backup and restore guidance.
- Rate limits and operational safeguards.
- Legal pages and disclaimer positioning.
- Release checklist and regression gate.

Exit criteria:

- The app is deployable behind HTTPS.
- Operators have a repeatable release and rollback path.
- The public legal surface is in place.

## Milestone Sequence

1. Document baseline architecture and risk.
2. Finish learner-flow productization.
3. Add server-side persistence and account flows.
4. Add payment and entitlement enforcement.
5. Stabilize AI scoring and quotas.
6. Harden deployment, monitoring, backups, and legal pages.
7. Gate release with a full regression and checklist.

## Major Dependencies

- Content validation must stay ahead of user-facing product polish where content integrity is at risk.
- Backend persistence must exist before dashboard and history features can be trusted.
- Accounts and payments must be server-controlled before launch.
- AI scoring needs schema validation and quota controls before commercial traffic.
- Production deployment should not be considered complete without backup, monitoring, and legal coverage.

## Top Risks

- Answer keys or internal scoring logic becoming visible to users.
- AI scoring failures causing silent or misleading results.
- Paid access being enforced only in the frontend.
- Attempt history being lost across refreshes or redeploys.
- Release process drifting away from the actual deployment and test tooling.
- Legal and privacy pages being incomplete at launch.

## Release Readiness Checklist

- Free sample exam works end to end.
- Paid pack access is enforced by entitlement.
- Accounts can be created and used to recover progress.
- Attempts are persisted server-side.
- Objective scoring works for supported items.
- AI feedback returns bounded, schema-validated results.
- Stripe payment flow works in test mode and webhook handling is idempotent.
- Results dashboard shows the correct learner data.
- Legal disclaimer, privacy policy, and terms are published.
- Production deployment uses HTTPS and has health checks.
- Backups, logs, and failure recovery steps are documented.

## Next Planning Artifacts

- Convert this roadmap into sprint-sized issues with clear owners and acceptance criteria.
- Keep the dependency map current as platform decisions change.
- Update the release checklist whenever auth, billing, scoring, or deployment behavior changes.
