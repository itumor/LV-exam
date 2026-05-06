# TASK-016: Confirm whether Kubernetes or Helm is required for future deployment

## Summary
Make an explicit decision on whether Kubernetes or Helm should be introduced, based on the current repo and deployment needs.

## Phase
Phase 5.

## Type
investigation.

## Priority
P2 medium.

## Complexity
S.

## Status
proposed.

## Context
There are no Kubernetes or Helm artifacts in the repo, so adding them would be a new operational surface that should be justified rather than assumed.

## Objective
Avoid unnecessary platform complexity.

## Scope
- Assess whether existing deployment targets are sufficient.
- Decide if Kubernetes/Helm should remain out of scope.

## Out of Scope
- Creating cluster manifests unless the decision requires it.

## Files Likely Affected
- `docs/roadmap/ROADMAP.md`
- `docs/roadmap/MILESTONES.md`

## Implementation Plan
1. Review the current runtime and hosting docs.
2. Compare operational needs to current deployment options.
3. Record a clear yes/no decision with rationale.

## Acceptance Criteria
- [ ] The repo has a documented deployment direction.
- [ ] Kubernetes/Helm are explicitly either justified or deferred.

## Validation
Review the decision against the current codebase and ops requirements.

## Dependencies
- `TASK-002`
- `TASK-004`

## Risks
Premature platform expansion can increase maintenance burden.

## Rollback Plan
Keep the deployment surface limited to Docker/Fly.io if no need is proven.

## Notes
This is a decision task, not an implementation task.

