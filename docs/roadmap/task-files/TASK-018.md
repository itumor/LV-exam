# TASK-018: Add a cost-control backlog for AI scoring and container hosting

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

