# TASK-011: Capture the current secret and environment-variable inventory

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

