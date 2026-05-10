# TASK-013: Define log and alert expectations for `/api/evaluate` and billing endpoints

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

