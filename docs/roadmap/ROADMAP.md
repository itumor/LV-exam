# Project Roadmap

## 1. Executive Summary
Latvian A2 Exam Simulator is a browser-based exam practice application with a Python server, a static frontend, Markdown-based exam content, local media assets, auth and billing persistence, and optional AI-assisted scoring for writing and speaking. The repository already contains meaningful product capability, a containerized runtime, a Fly.io deployment configuration, a regression test suite, and a set of architecture and release documents.

The roadmap aims to turn the current MVP-style implementation into a production-ready service with clearer operational documentation, stronger automated validation, safer deployment practices, better observability, and more durable infrastructure assumptions.

## 2. Current State

### Application/runtime stack
- Python 3.12+ server in `server.py`.
- Static frontend in `latvian-a2-exam-app/` using HTML, CSS, and vanilla JavaScript.
- SQLite-backed auth and billing stores.
- Optional AI scoring integration via Groq or a Codex remote/local workflow.
- Docker-based runtime with a single container model.

### Main components
- Exam frontend and UI flow.
- Markdown exam vault in `codex/`.
- Attachment/media assets under `codex/Attachments/`.
- Auth, billing, and attempt persistence code in Python modules.
- Exam import/validation utilities in `exam_bank.py`.
- Operational scripts for backup, import, regeneration, smoke checks, and deployment.

### Repository structure
- Root-level Python application and support modules.
- `latvian-a2-exam-app/` for the browser app.
- `tests/` for Python, Node, and Playwright coverage.
- `docs/` for architecture, deployment, legal, and release guidance.
- `scripts/` for operational and content-generation workflows.
- `migrations/` for SQL schema evolution.
- `docker-compose.yml`, `Dockerfile`, and `fly.toml` for runtime/deployment.

### Build process
- `npm ci` installs the Playwright dependency set.
- `npm test` runs `scripts/run_regression_suite.sh`.
- Docker builds from the repository root and bundles the Python runtime, frontend, and content vault.
- The current repo also has GitHub Actions configured to run the regression suite on push and pull request.

### Test process
- Python unit tests for server, billing, exam import, uploads, and security behavior.
- Node contract tests for release assumptions.
- Playwright end-to-end regression covering the learner journey and UI navigation.
- The test suite is broad for the current size of the application, but coverage is still uneven around deployment, runtime health, and production failure modes.

### Deployment process
- Local: `python3 server.py`.
- Container: Docker Compose builds and runs the app.
- Cloud: Fly.io is configured via `fly.toml` and `scripts/deploy-fly.sh`.
- Health check endpoint exists at `/healthz`.

### CI/CD status
- GitHub Actions workflow exists and runs the regression suite.
- Dependabot is configured for npm and GitHub Actions updates.
- No evidence in the repo of artifact publishing, release tagging, image scanning, or automated deployment from CI.

### Infrastructure status
- Current infrastructure is minimal and mostly single-service oriented.
- Fly.io is the only explicit cloud target in the repository.
- SQLite is used for local persistence; durable storage is assumed through mounted volumes.
- No Kubernetes, Helm, Terraform, or Crossplane manifests are present.

### Documentation status
- Strong architecture and runbook documentation already exists.
- Frontend user manuals exist in English and Latvian.
- Release checklist, privacy policy, terms, and security review docs are present.
- Root-level setup documentation is still fragmented across several docs and examples.

### Security status
- Provider credentials are server-side only.
- Static asset allow-listing is tested.
- Billing and auth are server-side and backed by SQLite.
- Secrets are environment-driven, but production secret handling and runtime hardening need explicit operational validation.

### Observability status
- `/healthz` exists.
- There is no obvious metrics, tracing, or structured logging stack defined in the repo.
- Sentry configuration is supported as environment input, but there is no evidence of end-to-end monitoring wiring or alerting policy in the repository.

## 3. Target State
The target state is a small but production-ready exam practice service that is straightforward to run locally, validate in CI, deploy consistently, and operate safely.

- Stable local development workflow with one documented entry path.
- Automated unit, contract, and end-to-end test coverage with clear quality gates.
- CI/CD pipeline that validates, packages, and optionally releases the application in a deterministic way.
- Secure configuration and secrets handling with documented operational requirements.
- Containerization with repeatable build and health checks.
- Kubernetes/Helm readiness only if the deployment model later requires it; otherwise keep the platform surface intentionally small.
- Infrastructure as Code only where it brings measurable value; keep the current Fly.io path simple unless scaling demands more.
- Observability with structured logging, error reporting, and actionable alerts.
- A release process that documents rollback, backups, and smoke tests.
- Operational runbooks that cover deploy, restore, failure handling, and AI scoring incidents.

## 4. Roadmap Principles
- Small incremental changes.
- Test before refactor.
- Automate repeatable work.
- Secure by default.
- Production readiness before feature expansion.
- Observability before scale.
- Cost awareness where cloud resources or provider APIs are involved.

## 5. Roadmap Phases

### Phase 0: Discovery and Baseline
Goal:
- Establish the current state with evidence from the repository.

Expected outcomes:
- Documented architecture.
- Known risks.
- Known gaps.
- Known dependencies.

### Phase 1: Developer Experience and Project Hygiene
Goal:
- Make the project easy to understand, run, test, and contribute to.

Expected outcomes:
- Root-level setup guidance.
- Clear environment variable documentation.
- Standard scripts and commands.
- Better task and release tracking.

### Phase 2: Testing and Quality
Goal:
- Improve confidence in changes.

Expected outcomes:
- Stronger unit and contract coverage.
- Clearer integration test strategy.
- Better regression reliability.
- Quality gates in CI.

### Phase 3: CI/CD and Release Automation
Goal:
- Make builds, tests, and releases repeatable.

Expected outcomes:
- Deterministic CI pipeline.
- Build and release checks.
- Versioning and release notes flow.
- Deployment workflow documentation.

### Phase 4: Containerization and Runtime Readiness
Goal:
- Make the application deployable in a consistent runtime.

Expected outcomes:
- Container build hardening.
- Health checks and startup behavior documented.
- Runtime config validation.
- Image and dependency scan readiness.

### Phase 5: Kubernetes, Helm, and Infrastructure
Goal:
- Prepare the project for cloud-native deployment only if that becomes relevant.

Expected outcomes:
- Explicit decision on whether Kubernetes/Helm is needed.
- If needed, a small and maintainable deployment surface.
- Resource and secret strategy documented.
- IaC path defined, or explicitly deferred.

### Phase 6: Security and Compliance
Goal:
- Reduce security risk.

Expected outcomes:
- Secret scanning and dependency scanning.
- Safer runtime defaults.
- Auth and billing hardening notes.
- Production trust artifacts reviewed.

### Phase 7: Observability and Operations
Goal:
- Make the system measurable and operable.

Expected outcomes:
- Structured logging guidance.
- Metrics and alerting plan.
- Runbooks.
- Incident response notes.

### Phase 8: Performance, Cost, and Scalability
Goal:
- Optimize for efficient and reliable operation.

Expected outcomes:
- Performance baseline.
- Resource optimization.
- Cost controls for AI scoring and hosting.
- Scalability recommendations.

### Phase 9: Feature Expansion
Goal:
- Expand product functionality after the foundation is stable.

Expected outcomes:
- Prioritized feature backlog.
- User-facing improvements.
- API improvements.
- Integration opportunities.

## 6. Milestone Overview

| Milestone | Phase | Goal | Priority | Dependencies | Definition of Done |
|---|---|---|---|---|---|
| M1. Baseline documented | Phase 0 | Capture the current architecture and operational assumptions | P0 | Repo inspection complete | Roadmap, risk register, milestone plan, and tasks exist and match repository evidence |
| M2. Developer onboarding cleared | Phase 1 | Make setup and repo conventions easy to follow | P1 | M1 | Root setup docs and task backlog are actionable and current |
| M3. Regression coverage stabilized | Phase 2 | Make test behavior reliable and repeatable | P1 | M1, M2 | Unit, contract, and Playwright flows run predictably in CI and locally |
| M4. CI/release workflow defined | Phase 3 | Make build and release steps deterministic | P1 | M3 | CI and release steps are documented and validated against repo tooling |
| M5. Runtime hardened | Phase 4 | Make container behavior safe and predictable | P1 | M4 | Container startup, health checks, and runtime settings are explicit |
| M6. Deployment strategy settled | Phase 5 | Decide whether Kubernetes/Helm/IaC are needed | P2 | M4, M5 | The team has a confirmed deployment strategy or an explicit decision not to add platform complexity |
| M7. Security controls validated | Phase 6 | Reduce production and privacy risk | P0 | M5 | Secret handling, scanning, auth, and billing assumptions are documented with validation paths |
| M8. Observability added | Phase 7 | Make failures visible and debuggable | P1 | M5, M7 | Logging, metrics, and alerting expectations are documented and testable |
| M9. Cost and performance baseline | Phase 8 | Control AI and runtime cost growth | P2 | M7, M8 | Cost-sensitive endpoints and resource assumptions are measured or at least baselined |
| M10. Feature backlog ready | Phase 9 | Enable product growth on a stable foundation | P2 | M1-M9 | New features are prioritized after platform and operational work are stable |

## 7. Delivery Timeline

| Timeframe | Focus Area | Expected Output |
|---|---|---|
| Week 1 | Baseline and documentation | Final roadmap, risk register, milestone plan, and task backlog |
| Weeks 2-3 | Developer experience and testing | Better setup docs, tighter test descriptions, and a stable local/CI validation path |
| Month 1 | CI/CD and release process | Confirmed CI workflow, release checklist alignment, and clearer rollback expectations |
| Months 2-3 | Runtime, security, and observability | Hardened container/runtime guidance, security checks, logs, and alerting plan |
| Months 4-6 | Cost, scale, and feature backlog | Performance baseline, cost controls, and a prioritized next-feature queue |

## 8. Success Metrics
- Local setup time under 15 minutes from a clean clone using documented steps.
- `npm test` passes consistently in local and CI environments.
- Regression suite duration stays predictable and within an agreed ceiling.
- Zero critical security findings in the repository-scoped dependency and secret review process.
- Health check success rate remains near 100 percent in deployment environments.
- Deployment rollback procedure is documented and can be executed without guesswork.
- AI scoring failures are visible through logs or monitoring instead of silent retries.
- Backup and restore procedures are documented and validated on a schedule.
- Cloud runtime cost is tracked for the container and AI scoring provider usage.

## 9. Risks and Assumptions
- The repository is currently suitable for a small production deployment, but not yet for broad scale or multi-tenant growth.
- SQLite is assumed to remain acceptable for the near term if durable storage is configured; beyond that, a database migration may be necessary.
- AI scoring cost and provider availability are material operational risks.
- The repo does not show Kubernetes, Helm, or IaC beyond Fly.io, so those should be treated as optional rather than assumed requirements.
- Existing docs suggest production intent, but some operational details still need confirmation in the code and deploy environment.

## 10. Next 10 Actions
1. Consolidate setup, runtime, and environment-variable guidance into one root-level onboarding doc.
2. Confirm the current deploy target and whether Fly.io remains the primary production path.
3. Add a documented local smoke-test sequence that mirrors production startup behavior.
4. Validate the full regression suite from a clean environment and record the exact commands.
5. Review auth, billing, and AI scoring secrets handling against the deployment environment.
6. Add structured logging and error-reporting expectations to the operational docs.
7. Confirm backup/restore assumptions for SQLite persistence and mounted storage.
8. Document release rollback steps for the current Docker/Fly.io deployment model.
9. Decide whether Kubernetes/Helm or a managed container platform is the long-term target.
10. Create a tracked backlog of implementation tasks from this roadmap and prioritize the production-risk items first.
