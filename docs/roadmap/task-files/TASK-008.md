# TASK-008: Document the test matrix and when each suite should run

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

