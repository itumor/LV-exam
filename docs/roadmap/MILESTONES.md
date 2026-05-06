# Milestones

## Milestone 1: Baseline and Backlog

- Goal
  - Establish the current state, risks, and backlog structure.
- Why it matters
  - The repo has many good pieces, but the team needs one consistent planning surface.
- Scope
  - Roadmap, risk register, milestone plan, and task backlog.
- Out of scope
  - Code changes and runtime changes.
- Tasks included
  - TASK-002
  - TASK-006
  - TASK-007
- Dependencies
  - None.
- Acceptance criteria
  - The roadmap is rooted in repo evidence.
  - The top risks are explicitly recorded.
- Validation plan
  - Compare the planning docs against the repository contents.
- Rollback considerations
  - Update the docs if new evidence changes the assessment.
- Expected impact
  - Better prioritization and fewer planning gaps.

## Milestone 2: Onboarding and Local Validation

- Goal
  - Make the project easy to run and verify locally.
- Why it matters
  - Contributors should be able to validate the app without reverse-engineering the repo.
- Scope
  - Root onboarding, smoke-test workflow, and test matrix guidance.
- Out of scope
  - Changing the application logic.
- Tasks included
  - TASK-001
  - TASK-003
  - TASK-008
  - TASK-009
- Dependencies
  - Milestone 1.
- Acceptance criteria
  - A new contributor can find setup, run, and test instructions in one place.
- Validation plan
  - Follow the documented steps from a clean clone.
- Rollback considerations
  - Remove or shorten any guidance that does not match the repo.
- Expected impact
  - Faster onboarding and lower validation friction.

## Milestone 3: Release and Deployment Clarity

- Goal
  - Make deployment and release behavior predictable.
- Why it matters
  - The app is production-sensitive and relies on correct deploy and rollback behavior.
- Scope
  - Fly.io deployment docs, release checklist, and CI notes.
- Out of scope
  - Replacing the current platform.
- Tasks included
  - TASK-004
  - TASK-005
  - TASK-010
- Dependencies
  - Milestone 2.
- Acceptance criteria
  - The release path is documented end to end.
  - Operators know how to verify and rollback.
- Validation plan
  - Compare docs with `fly.toml`, `scripts/deploy-fly.sh`, and GitHub Actions.
- Rollback considerations
  - Keep rollback steps tied to the current container deployment model.
- Expected impact
  - Lower release risk.

## Milestone 4: Security and Operational Safety

- Goal
  - Reduce production risk around secrets, auth, billing, and scoring.
- Why it matters
  - These are the most sensitive flows in the repository.
- Scope
  - Secret inventory, failure modes, and release safety constraints.
- Out of scope
  - Altering business logic or provider flows.
- Tasks included
  - TASK-011
  - TASK-012
  - TASK-015
- Dependencies
  - Milestone 3.
- Acceptance criteria
  - Secret boundaries are documented.
  - High-risk failure modes and backup/restore procedures are clear.
- Validation plan
  - Cross-check docs against server, billing, and deployment files.
- Rollback considerations
  - Update docs if runtime assumptions change.
- Expected impact
  - Safer production operation and faster incident response.

## Milestone 5: Observability and Control

- Goal
  - Make runtime behavior measurable and supportable.
- Why it matters
  - The current repo has health checks and optional monitoring inputs, but no explicit observability contract.
- Scope
  - Logging, alerting, and observability gap analysis.
- Out of scope
  - Implementing a full telemetry stack.
- Tasks included
  - TASK-013
  - TASK-014
- Dependencies
  - Milestone 4.
- Acceptance criteria
  - Critical endpoints have defined signals and alert expectations.
- Validation plan
  - Review the documentation against current routes and failure modes.
- Rollback considerations
  - Keep the guidance minimal and privacy-safe.
- Expected impact
  - Faster detection of scoring, billing, and deployment issues.

## Milestone 6: Platform Direction and Growth Readiness

- Goal
  - Decide how far the project should go on Kubernetes/IaC and prepare the next product backlog.
- Why it matters
  - The repo should not accumulate platform complexity without a clear need.
- Scope
  - Deployment direction decision, optional K8s requirements, cost/performance planning, and feature backlog.
- Out of scope
  - Actual feature implementation.
- Tasks included
  - TASK-016
  - TASK-017
  - TASK-018
  - TASK-019
  - TASK-020
- Dependencies
  - Milestones 1 through 5.
- Acceptance criteria
  - The deployment direction is explicit.
  - Feature work only starts after the foundation is stable.
- Validation plan
  - Check that each follow-on item is supported by repo evidence.
- Rollback considerations
  - Defer platform expansion if the need is not proven.
- Expected impact
  - Clearer long-term technical direction and controlled growth.
