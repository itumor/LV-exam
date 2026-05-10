# Task Backlog

## Master List

| ID | Title | Phase | Type | Priority | Complexity | Status | Dependencies |
|---|---|---|---|---|---|---|---|
| TASK-001 | Create a root-level onboarding and environment guide | Phase 1 | docs | P1 high | M | proposed | None |
| TASK-002 | Document the current architecture and runtime boundaries | Phase 0 | docs | P1 high | M | proposed | None |
| TASK-003 | Add a documented local smoke-test workflow | Phase 1 | docs | P1 high | S | proposed | TASK-001 |
| TASK-004 | Clarify deployment and rollback steps for Fly.io | Phase 3 | docs | P1 high | M | proposed | TASK-002 |
| TASK-005 | Define a release checklist tied to repo commands | Phase 3 | docs | P1 high | M | proposed | TASK-003, TASK-004 |
| TASK-006 | Add a task index and naming convention for roadmap work | Phase 1 | docs | P2 medium | S | proposed | None |
| TASK-007 | Record the current production-readiness gaps as an explicit risk register | Phase 0 | investigation | P0 critical | S | proposed | TASK-002 |
| TASK-008 | Document the test matrix and when each suite should run | Phase 2 | docs | P1 high | M | proposed | TASK-001, TASK-002 |
| TASK-009 | Tighten the regression suite guidance for Python, Node, and Playwright | Phase 2 | test | P1 high | M | proposed | TASK-008 |
| TASK-010 | Add CI validation notes for the existing GitHub Actions workflow | Phase 3 | docs | P2 medium | S | proposed | TASK-008 |
| TASK-011 | Capture the current secret and environment-variable inventory | Phase 6 | security | P0 critical | M | proposed | TASK-001, TASK-004 |
| TASK-012 | Document auth, billing, and AI scoring operational failure modes | Phase 6 | security | P0 critical | M | proposed | TASK-011 |
| TASK-013 | Define log and alert expectations for `/api/evaluate` and billing endpoints | Phase 7 | observability | P1 high | M | proposed | TASK-011, TASK-012 |
| TASK-014 | Add an observability gap assessment for structured logs and monitoring | Phase 7 | observability | P2 medium | S | proposed | TASK-013 |
| TASK-015 | Document SQLite backup and restore procedures for auth and billing data | Phase 4 | infrastructure | P0 critical | M | proposed | TASK-004, TASK-011 |
| TASK-016 | Confirm whether Kubernetes or Helm is required for future deployment | Phase 5 | investigation | P2 medium | S | proposed | TASK-002, TASK-004 |
| TASK-017 | If Kubernetes is needed, draft a minimal deployment requirements doc | Phase 5 | infrastructure | P2 medium | M | proposed | TASK-016 |
| TASK-018 | Add a cost-control backlog for AI scoring and container hosting | Phase 8 | cost-optimization | P2 medium | M | proposed | TASK-011, TASK-013 |
| TASK-019 | Create a performance baseline plan for local and deployed runtime | Phase 8 | performance | P2 medium | M | proposed | TASK-008, TASK-013 |
| TASK-020 | Build a prioritized follow-on feature backlog from product docs | Phase 9 | docs | P2 medium | L | proposed | TASK-002, TASK-007 |

## Detailed Tasks

### TASK-001: Create a root-level onboarding and environment guide

## Summary
Create one root-level guide that explains how to clone, configure, run, and validate the project using the existing repo commands.

## Phase
Phase 1.

## Type
docs.

## Priority
P1 high.

## Complexity
M.

## Status
proposed.

## Context
The repository already has setup guidance spread across multiple docs, `.env-example`, and application-specific manuals. A single entry point would reduce onboarding ambiguity.

## Objective
Make the project easy to start locally without chasing scattered instructions.

## Scope
- Document the required runtime versions.
- Document the preferred commands from `package.json`, `README`, and `AGENTS.md`.
- Document environment variables and safe defaults.
- Document the recommended local URL and health endpoint.

## Out of Scope
- Changing application behavior.
- Introducing new tooling.
- Rewriting existing manuals.

## Files Likely Affected
- `README.md`
- `docs/roadmap/TASKS.md`
- `docs/roadmap/ROADMAP.md`

## Implementation Plan
1. Collect the current startup and test commands.
2. Summarize environment variables from `.env-example` and docs.
3. Add a concise root-level onboarding guide.
4. Cross-link the existing architecture and deployment docs.

## Acceptance Criteria
- [ ] A single root-level doc explains setup, run, and test entry points.
- [ ] Environment variables are listed with purpose and safe defaults.
- [ ] The guide points to the local health check and main app URL.

## Validation
Review the document against the repo commands and confirm it references only real files and commands.

## Dependencies
None.

## Risks
If the doc is too detailed, it can become stale quickly.

## Rollback Plan
Remove the doc or trim it back to the minimum command list.

## Notes
Keep it short and operational.

### TASK-002: Document the current architecture and runtime boundaries

## Summary
Write a repository-grounded architecture summary that reflects the actual stack, components, and runtime boundaries.

## Phase
Phase 0.

## Type
docs.

## Priority
P1 high.

## Complexity
M.

## Status
proposed.

## Context
The repo already contains architecture docs, but the roadmap should have a current baseline tied directly to present files and deployment behavior.

## Objective
Create a stable reference for platform, product, and engineering decisions.

## Scope
- Summarize the Python server, frontend, content vault, billing, auth, and AI scoring boundaries.
- Note what is and is not persisted server-side.
- Note the current deployment model.

## Out of Scope
- Refactoring architecture.
- Adding new infrastructure.

## Files Likely Affected
- `docs/roadmap/ROADMAP.md`
- `docs/roadmap/RISK_REGISTER.md`

## Implementation Plan
1. Use the repo evidence to list the current components.
2. Capture runtime boundaries and trust boundaries.
3. Call out unknowns explicitly.

## Acceptance Criteria
- [ ] The document describes the real runtime stack.
- [ ] The document distinguishes browser, server, content, and provider boundaries.
- [ ] Unknowns are labeled as unknown rather than guessed.

## Validation
Compare the text against `server.py`, `docker-compose.yml`, `Dockerfile`, `fly.toml`, and the tested modules.

## Dependencies
None.

## Risks
Architecture text can drift if it is not updated with major changes.

## Rollback Plan
Revise the doc to match the current code paths.

## Notes
This task feeds the roadmap and future milestone planning.

### TASK-003: Add a documented local smoke-test workflow

## Summary
Document a minimal local smoke test that proves the app boots and the primary route loads correctly.

## Phase
Phase 1.

## Type
docs.

## Priority
P1 high.

## Complexity
S.

## Status
proposed.

## Context
The repo has a health endpoint, a Playwright test server, and local startup commands, but the fastest manual verification path is not captured in one place.

## Objective
Make it easy to verify a clean startup before running the full suite.

## Scope
- Document the startup command.
- Document the expected URL.
- Document a simple health-check and page-load sequence.

## Out of Scope
- Adding automated smoke tests.
- Changing the server.

## Files Likely Affected
- `README.md`
- `docs/roadmap/TASKS.md`

## Implementation Plan
1. Define the minimal boot sequence.
2. Describe the expected success conditions.
3. Add troubleshooting notes for common local failures.

## Acceptance Criteria
- [ ] The smoke workflow includes boot, health, and page-load checks.
- [ ] The workflow uses existing repo commands.

## Validation
Follow the written steps on a clean local environment.

## Dependencies
- `TASK-001`

## Risks
The guide may become outdated if startup behavior changes.

## Rollback Plan
Trim the workflow to the commands still supported by the repo.

## Notes
Keep this intentionally short.

### TASK-004: Clarify deployment and rollback steps for Fly.io

## Summary
Document the current Fly.io deployment flow, expected environment variables, and rollback approach.

## Phase
Phase 3.

## Type
docs.

## Priority
P1 high.

## Complexity
M.

## Status
proposed.

## Context
The repo includes `fly.toml` and `scripts/deploy-fly.sh`, but the operational path is only partially documented across multiple files.

## Objective
Make deployment repeatable and reduce operator guesswork.

## Scope
- Document the Fly.io deployment command.
- Document required environment and secrets assumptions.
- Document smoke checks and rollback considerations.

## Out of Scope
- Changing deployment topology.
- Replacing Fly.io.

## Files Likely Affected
- `docs/deployment-runbook.md`
- `docs/roadmap/ROADMAP.md`
- `docs/roadmap/MILESTONES.md`

## Implementation Plan
1. Read the current deployment script and Fly config.
2. Summarize the deploy flow.
3. Add rollback and verification steps.

## Acceptance Criteria
- [ ] The deployment path is documented from build to smoke check.
- [ ] Rollback considerations are explicit.
- [ ] Secret handling expectations are called out.

## Validation
Compare the document with `fly.toml` and `scripts/deploy-fly.sh`.

## Dependencies
- `TASK-002`

## Risks
Deployment docs can lag behind the actual script if the script changes.

## Rollback Plan
Update the runbook to the currently supported deploy path.

## Notes
This is operationally sensitive.

### TASK-005: Define a release checklist tied to repo commands

## Summary
Create a release gate that maps directly to repository validation commands and deployment checks.

## Phase
Phase 3.

## Type
docs.

## Priority
P1 high.

## Complexity
M.

## Status
proposed.

## Context
The repo already has a release checklist, but the roadmap needs a practical checklist that is aligned to the current codebase and validation flow.

## Objective
Make release readiness measurable and reproducible.

## Scope
- Define must-pass checks.
- Tie checks to commands and docs.
- Capture rollback and evidence expectations.

## Out of Scope
- Changing release gating logic in code.

## Files Likely Affected
- `docs/release-checklist.md`
- `docs/roadmap/MILESTONES.md`

## Implementation Plan
1. Review the existing release checklist.
2. Map each checklist item to a concrete repo command or manual check.
3. Remove ambiguity and add evidence requirements.

## Acceptance Criteria
- [ ] The checklist references concrete commands or actions.
- [ ] The checklist includes rollback and evidence capture.

## Validation
Walk through the checklist against a sample release.

## Dependencies
- `TASK-003`
- `TASK-004`

## Risks
Too much detail can make the checklist hard to use.

## Rollback Plan
Revert to the simpler release checklist if needed.

## Notes
The goal is practical gating, not paperwork.

### TASK-006: Add a task index and naming convention for roadmap work

## Summary
Define how roadmap task IDs, titles, and statuses should be used so the backlog remains maintainable.

## Phase
Phase 1.

## Type
docs.

## Priority
P2 medium.

## Complexity
S.

## Status
proposed.

## Context
The repo needs a consistent way to keep roadmap tasks aligned as the project evolves.

## Objective
Make task files easy to find, reference, and update.

## Scope
- Define task naming rules.
- Define status vocabulary.
- Define how dependencies should be recorded.

## Out of Scope
- Changing the product backlog tool.

## Files Likely Affected
- `docs/roadmap/TASKS.md`
- `docs/roadmap/MILESTONES.md`

## Implementation Plan
1. Decide the minimum task metadata needed.
2. Document the conventions once.
3. Apply them to all roadmap task files.

## Acceptance Criteria
- [ ] Task naming and dependency conventions are documented.
- [ ] Status and priority values are standardized.

## Validation
Check that the existing task files follow the convention.

## Dependencies
None.

## Risks
If the convention is too strict, it may be ignored.

## Rollback Plan
Simplify the convention to the fields that are actually used.

## Notes
This is a backlog hygiene task.

### TASK-007: Record the current production-readiness gaps as an explicit risk register

## Summary
Create a repository-backed risk register that lists the highest-impact gaps and mitigation paths.

## Phase
Phase 0.

## Type
investigation.

## Priority
P0 critical.

## Complexity
S.

## Status
proposed.

## Context
The repo already hints at production concerns in docs, but the risks need to be consolidated into a formal register for prioritization.

## Objective
Make the highest-risk items visible and actionable.

## Scope
- List technical, security, delivery, operational, infrastructure, cost, compliance, and maintainability risks.
- Map each risk to mitigation and related tasks.

## Out of Scope
- Implementing mitigations.

## Files Likely Affected
- `docs/roadmap/RISK_REGISTER.md`

## Implementation Plan
1. Extract risks from existing docs and tests.
2. Rank them by severity and likelihood.
3. Map each risk to the roadmap tasks that address it.

## Acceptance Criteria
- [ ] Every high-risk area from the repo has an entry.
- [ ] Each risk links to one or more follow-up tasks.

## Validation
Review the register against the repo docs and test coverage.

## Dependencies
- `TASK-002`

## Risks
Risks may be underestimated if the review misses runtime details.

## Rollback Plan
Update the register when new evidence appears.

## Notes
This should remain factual and specific.

### TASK-008: Document the test matrix and when each suite should run

## Summary
Document the intended use of unit, contract, and Playwright tests and how they fit into the development workflow.

## Phase
Phase 2.

## Type
docs.

## Priority
P1 high.

## Complexity
M.

## Status
proposed.

## Context
The repository has a broad test suite, but the intended layering and trigger points are not fully captured in one place.

## Objective
Make test execution decisions easier and more consistent.

## Scope
- Describe the test layers.
- Document what each suite validates.
- Document when to run targeted vs full regression checks.

## Out of Scope
- Adding new tests.

## Files Likely Affected
- `README.md`
- `docs/roadmap/ROADMAP.md`

## Implementation Plan
1. Inventory current test commands.
2. Group them by purpose.
3. Document the intended sequence for local and CI use.

## Acceptance Criteria
- [ ] The document distinguishes unit, contract, and Playwright coverage.
- [ ] The document states the smallest relevant validation for common changes.

## Validation
Compare the doc to `package.json`, `playwright.config.js`, and the tests folder.

## Dependencies
- `TASK-001`
- `TASK-002`

## Risks
The matrix can become stale if the test suite changes often.

## Rollback Plan
Reduce the description to the currently stable commands.

## Notes
Focus on practical developer decision-making.

### TASK-009: Tighten the regression suite guidance for Python, Node, and Playwright

## Summary
Document the minimum regression requirements and the environment needed to run them reliably.

## Phase
Phase 2.

## Type
test.

## Priority
P1 high.

## Complexity
M.

## Status
proposed.

## Context
The CI workflow depends on Python, Node 20, and Playwright Chromium. The repo should explain this clearly and consistently.

## Objective
Reduce test setup errors and flaky execution.

## Scope
- Document the required runtime versions.
- Document Chromium installation assumptions.
- Document the primary regression command.

## Out of Scope
- Modifying test code.

## Files Likely Affected
- `docs/release-checklist.md`
- `docs/roadmap/TASKS.md`

## Implementation Plan
1. Capture the exact commands from the repo.
2. Note the required runtimes and browser installation step.
3. Add failure triage notes for common setup issues.

## Acceptance Criteria
- [ ] The guidance names Python, Node, and Playwright requirements.
- [ ] The guidance includes the canonical regression command.

## Validation
Run the documented command on a fresh environment or clean virtualenv.

## Dependencies
- `TASK-008`

## Risks
If browser dependencies drift, the doc may need frequent updates.

## Rollback Plan
Restore the guidance to the simplest supported command list.

## Notes
Keep the troubleshooting notes brief.

### TASK-010: Add CI validation notes for the existing GitHub Actions workflow

## Summary
Document the current CI workflow and the expectations around it.

## Phase
Phase 3.

## Type
docs.

## Priority
P2 medium.

## Complexity
S.

## Status
proposed.

## Context
The repository has a GitHub Actions workflow, but the docs do not yet present the CI path as a first-class operational artifact.

## Objective
Make CI behavior visible to contributors and release reviewers.

## Scope
- Summarize the CI job sequence.
- Note the required runtime versions.
- Note how Dependabot updates are handled.

## Out of Scope
- Editing the workflow itself.

## Files Likely Affected
- `docs/roadmap/ROADMAP.md`
- `.github/workflows/ci.yml`

## Implementation Plan
1. Describe the existing workflow steps.
2. Identify the supported validation gates.
3. Cross-link the command references.

## Acceptance Criteria
- [ ] The CI flow is documented from checkout to regression suite.
- [ ] The dependency update policy is mentioned.

## Validation
Compare the doc to the existing workflow file.

## Dependencies
- `TASK-008`

## Risks
CI docs can become stale if the workflow changes.

## Rollback Plan
Update the notes to match the workflow.

## Notes
This is documentation only.

### TASK-011: Capture the current secret and environment-variable inventory

## Summary
Create a single inventory of the runtime environment variables and their security sensitivity.

## Phase
Phase 6.

## Type
security.

## Priority
P0 critical.

## Complexity
M.

## Status
proposed.

## Context
The repo uses many environment variables across auth, billing, AI scoring, deploy, and local tooling. The production posture depends on clearly separating secret, non-secret, and optional values.

## Objective
Make secret handling explicit and reviewable.

## Scope
- Inventory the env vars from `.env-example`, docs, Docker, and Fly config.
- Classify values by sensitivity.
- Note which values must never reach the browser.

## Out of Scope
- Rotating secrets.
- Changing secret handling in code.

## Files Likely Affected
- `docs/roadmap/RISK_REGISTER.md`
- `docs/deployment-runbook.md`

## Implementation Plan
1. Collect every runtime variable from the repo.
2. Mark required, optional, and secret values.
3. Capture the trusted storage location for each secret.

## Acceptance Criteria
- [ ] The inventory covers auth, billing, AI scoring, and deployment variables.
- [ ] Secret and non-secret values are clearly separated.
- [ ] Browser-exposed values are explicitly excluded.

## Validation
Cross-check the inventory against `.env-example`, `docker-compose.yml`, `fly.toml`, and `server.py`.

## Dependencies
- `TASK-001`
- `TASK-004`

## Risks
Incomplete inventory can hide production secret leakage paths.

## Rollback Plan
Update the inventory as the runtime surface changes.

## Notes
Treat this as a production-sensitive task.

### TASK-012: Document auth, billing, and AI scoring operational failure modes

## Summary
Write a failure-mode reference for the three most production-sensitive flows: auth, billing, and AI scoring.

## Phase
Phase 6.

## Type
security.

## Priority
P0 critical.

## Complexity
M.

## Status
proposed.

## Context
The app now has persistent auth and billing plus server-side AI evaluation. These flows introduce risk around idempotency, lockout, timeouts, and provider errors.

## Objective
Make the highest-risk operational failures visible before release.

## Scope
- Describe what can fail.
- Describe user-facing and operator-visible symptoms.
- Describe the safest response or rollback path.

## Out of Scope
- Changing retry or reconciliation logic.

## Files Likely Affected
- `docs/security-review.md`
- `docs/roadmap/RISK_REGISTER.md`

## Implementation Plan
1. Review the existing tests around auth, billing, and scoring.
2. Summarize failure modes in operator language.
3. Tie each failure mode to a mitigation or task.

## Acceptance Criteria
- [ ] Failure modes are documented for auth, billing, and AI scoring.
- [ ] Each mode has a practical mitigation note.

## Validation
Check the doc against the tested code paths and current deployment assumptions.

## Dependencies
- `TASK-011`

## Risks
If the document is too abstract, it will not help operators during incidents.

## Rollback Plan
Revise the section with concrete symptoms and commands.

## Notes
Do not change logic; only describe it.

### TASK-013: Define log and alert expectations for `/api/evaluate` and billing endpoints

## Summary
Document the minimum operational signals needed to detect scoring and billing failures.

## Phase
Phase 7.

## Type
observability.

## Priority
P1 high.

## Complexity
M.

## Status
proposed.

## Context
The repo supports Sentry and has a health endpoint, but there is no defined observability contract for the high-value endpoints.

## Objective
Make the most important failures visible quickly.

## Scope
- Define log fields and event types.
- Define alert-worthy conditions.
- Call out what must not be logged.

## Out of Scope
- Implementing telemetry code.

## Files Likely Affected
- `docs/deployment-runbook.md`
- `docs/security-review.md`

## Implementation Plan
1. List the critical endpoints and their failure modes.
2. Define the smallest useful log and alert set.
3. Document privacy-safe logging constraints.

## Acceptance Criteria
- [ ] Log expectations are defined for scoring and billing.
- [ ] Alert-worthy conditions are listed.
- [ ] Sensitive payloads are excluded from logs.

## Validation
Review the doc against the current server routes and production risks.

## Dependencies
- `TASK-011`
- `TASK-012`

## Risks
Observability guidance can be ignored if it is too verbose.

## Rollback Plan
Trim the guidance to the few highest-value signals.

## Notes
This should be minimal and operational.

### TASK-014: Add an observability gap assessment for structured logs and monitoring

## Summary
Document what is missing today in logs, metrics, tracing, and alerting.

## Phase
Phase 7.

## Type
observability.

## Priority
P2 medium.

## Complexity
S.

## Status
proposed.

## Context
The current repo exposes health checks and optional Sentry input, but the observability stack is otherwise unspecified.

## Objective
Give the team a concrete gap list to close later.

## Scope
- Identify missing structured logging.
- Identify missing metrics and dashboards.
- Identify missing alerting and tracing.

## Out of Scope
- Adding telemetry implementation.

## Files Likely Affected
- `docs/roadmap/ROADMAP.md`
- `docs/roadmap/RISK_REGISTER.md`

## Implementation Plan
1. Compare the current runtime to the target state.
2. Note the gaps in plain language.
3. Prioritize them by operational impact.

## Acceptance Criteria
- [ ] The observability gaps are listed explicitly.
- [ ] The gaps are ranked by practical impact.

## Validation
Read the assessment alongside the server and deployment docs.

## Dependencies
- `TASK-013`

## Risks
The gap list may grow as new operational needs appear.

## Rollback Plan
Update the gap list as the platform evolves.

## Notes
Use this as a future implementation input.

### TASK-015: Document SQLite backup and restore procedures for auth and billing data

## Summary
Create a practical backup and restore guide for the SQLite-backed auth and billing stores.

## Phase
Phase 4.

## Type
infrastructure.

## Priority
P0 critical.

## Complexity
M.

## Status
proposed.

## Context
The deployment model depends on SQLite persistence and mounted storage. A production posture requires a tested backup and restore path.

## Objective
Reduce data-loss risk for auth and billing state.

## Scope
- Document the database files and their locations.
- Document backup execution.
- Document integrity and restore verification.

## Out of Scope
- Migrating to a different database engine.

## Files Likely Affected
- `docs/deployment-runbook.md`
- `scripts/backup_sqlite.py`

## Implementation Plan
1. Identify the auth and billing files in current config.
2. Document backup creation and verification.
3. Add a restore checklist and failure notes.

## Acceptance Criteria
- [ ] Backup scope and file locations are documented.
- [ ] Restore verification steps are documented.
- [ ] The doc states the operational frequency assumption.

## Validation
Review the procedure against the current backup script and storage paths.

## Dependencies
- `TASK-004`
- `TASK-011`

## Risks
Inadequate restore testing can give false confidence.

## Rollback Plan
Revert to a simpler backup note if the procedure is not yet stable.

## Notes
This is a high-priority operational safeguard.

### TASK-016: Confirm whether Kubernetes or Helm is required for future deployment

## Summary
Make an explicit decision on whether Kubernetes or Helm should be introduced, based on the current repo and deployment needs.

## Phase
Phase 5.

## Type
investigation.

## Priority
P2 medium.

## Complexity
S.

## Status
proposed.

## Context
There are no Kubernetes or Helm artifacts in the repo, so adding them would be a new operational surface that should be justified rather than assumed.

## Objective
Avoid unnecessary platform complexity.

## Scope
- Assess whether existing deployment targets are sufficient.
- Decide if Kubernetes/Helm should remain out of scope.

## Out of Scope
- Creating cluster manifests unless the decision requires it.

## Files Likely Affected
- `docs/roadmap/ROADMAP.md`
- `docs/roadmap/MILESTONES.md`

## Implementation Plan
1. Review the current runtime and hosting docs.
2. Compare operational needs to current deployment options.
3. Record a clear yes/no decision with rationale.

## Acceptance Criteria
- [ ] The repo has a documented deployment direction.
- [ ] Kubernetes/Helm are explicitly either justified or deferred.

## Validation
Review the decision against the current codebase and ops requirements.

## Dependencies
- `TASK-002`
- `TASK-004`

## Risks
Premature platform expansion can increase maintenance burden.

## Rollback Plan
Keep the deployment surface limited to Docker/Fly.io if no need is proven.

## Notes
This is a decision task, not an implementation task.

### TASK-017: If Kubernetes is needed, draft a minimal deployment requirements doc

## Summary
If Kubernetes becomes necessary, document the smallest viable requirements before any manifest work.

## Phase
Phase 5.

## Type
infrastructure.

## Priority
P2 medium.

## Complexity
M.

## Status
proposed.

## Context
There is no Kubernetes configuration in the repo, so any future K8s effort should start with a requirements doc rather than assumptions.

## Objective
Prevent overbuilt manifests and unsupported operational expectations.

## Scope
- Define the required runtime and configuration objects.
- Define resource and health-check expectations.
- Define secret and config management assumptions.

## Out of Scope
- Writing manifests unless the decision from TASK-016 says to do so.

## Files Likely Affected
- `docs/roadmap/MILESTONES.md`
- `docs/roadmap/ROADMAP.md`

## Implementation Plan
1. Capture the runtime requirements.
2. Capture operational constraints.
3. Convert them into minimal deployment requirements.

## Acceptance Criteria
- [ ] Requirements are written before manifests.
- [ ] The doc avoids assuming cluster-specific extras.

## Validation
Review the requirements against the app's single-container model.

## Dependencies
- `TASK-016`

## Risks
If Kubernetes is not needed, this task should remain deferred.

## Rollback Plan
Do not create Kubernetes artifacts unless the decision requires them.

## Notes
Only execute this if justified.

### TASK-018: Add a cost-control backlog for AI scoring and container hosting

## Summary
Document the cost-sensitive parts of the system and the actions that can keep them under control.

## Phase
Phase 8.

## Type
cost-optimization.

## Priority
P2 medium.

## Complexity
M.

## Status
proposed.

## Context
AI scoring and container hosting are the two clear recurring cost centers in the repo.

## Objective
Make cost management part of the roadmap instead of an afterthought.

## Scope
- Identify the main recurring cost drivers.
- List practical guardrails and measurement ideas.
- Link cost work to AI scoring and runtime choices.

## Out of Scope
- Changing pricing logic.

## Files Likely Affected
- `docs/roadmap/RISK_REGISTER.md`
- `docs/roadmap/MILESTONES.md`

## Implementation Plan
1. Identify cost sources from the current architecture.
2. Describe current unknowns.
3. Add actionable cost guardrails.

## Acceptance Criteria
- [ ] Cost drivers are documented.
- [ ] Guardrails are tied to specific runtime paths.

## Validation
Review against billing, AI scoring, and deployment docs.

## Dependencies
- `TASK-011`
- `TASK-013`

## Risks
Cost work can be too vague if it is not tied to measurable endpoints.

## Rollback Plan
Reduce the backlog to only the two highest-cost paths if needed.

## Notes
Keep the focus on actual cost drivers.

### TASK-019: Create a performance baseline plan for local and deployed runtime

## Summary
Document what performance should be measured and what a healthy baseline looks like for the current app.

## Phase
Phase 8.

## Type
performance.

## Priority
P2 medium.

## Complexity
M.

## Status
proposed.

## Context
The app includes AI calls, uploads, and browser-side workflows, but there is no explicit performance baseline or load-testing plan in the repo.

## Objective
Make future performance work measurable.

## Scope
- Define the current hotspots to measure.
- Document basic latency and resource metrics.
- Describe a light-weight load-check approach.

## Out of Scope
- Implementing performance optimizations.

## Files Likely Affected
- `docs/roadmap/ROADMAP.md`
- `docs/deployment-runbook.md`

## Implementation Plan
1. Identify key user journeys and server endpoints.
2. Define a simple baseline measurement plan.
3. Record the metrics that matter most.

## Acceptance Criteria
- [ ] Key journeys and endpoints are named.
- [ ] The baseline metrics are specific enough to track later.

## Validation
Compare the plan to the current app routes and tests.

## Dependencies
- `TASK-008`
- `TASK-013`

## Risks
Performance work can drift into optimization before measurement.

## Rollback Plan
Simplify the baseline to a small set of metrics.

## Notes
Measure first, optimize later.

### TASK-020: Build a prioritized follow-on feature backlog from product docs

## Summary
Convert the existing product and architecture docs into a focused feature backlog that can be tackled after the foundation is stable.

## Phase
Phase 9.

## Type
docs.

## Priority
P2 medium.

## Complexity
L.

## Status
proposed.

## Context
The repo already describes product intentions, but the next feature set is not yet organized into an execution backlog.

## Objective
Create a clear handoff from platform work to product growth.

## Scope
- Extract supported future work from existing docs.
- Prioritize features that follow from the established platform foundation.
- Separate product features from platform maintenance.

## Out of Scope
- Implementing features.

## Files Likely Affected
- `docs/roadmap/ROADMAP.md`
- `docs/roadmap/MILESTONES.md`

## Implementation Plan
1. Review the current product and architecture docs.
2. Pull out only feature ideas that are already supported by repo context.
3. Rank them after the production-readiness tasks.

## Acceptance Criteria
- [ ] The backlog only includes features supported by the repo context.
- [ ] The backlog is prioritized after foundation work.

## Validation
Check that every feature item is traceable to an existing doc or repo capability.

## Dependencies
- `TASK-002`
- `TASK-007`

## Risks
Feature ideas can become speculative if not anchored to existing docs.

## Rollback Plan
Remove any item that is not clearly supported by the repository evidence.

## Notes
Treat this as a post-foundation backlog.
