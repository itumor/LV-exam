# TASK-009: Tighten the regression suite guidance for Python, Node, and Playwright

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

