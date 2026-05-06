# TASK-005: Define a release checklist tied to repo commands

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

