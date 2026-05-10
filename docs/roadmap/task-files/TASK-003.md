# TASK-003: Add a documented local smoke-test workflow

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

