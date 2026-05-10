# TASK-012: Document auth, billing, and AI scoring operational failure modes

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

