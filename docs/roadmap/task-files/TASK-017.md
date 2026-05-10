# TASK-017: If Kubernetes is needed, draft a minimal deployment requirements doc

## Summary
If Kubernetes becomes necessary, document the smallest viable requirements before any manifest work.

## Phase
Phase 5.

## Type
infrastructure.

## Priority
P2 medium.

## Complexity
M.

## Status
proposed.

## Context
There is no Kubernetes configuration in the repo, so any future K8s effort should start with a requirements doc rather than assumptions.

## Objective
Prevent overbuilt manifests and unsupported operational expectations.

## Scope
- Define the required runtime and configuration objects.
- Define resource and health-check expectations.
- Define secret and config management assumptions.

## Out of Scope
- Writing manifests unless the decision from TASK-016 says to do so.

## Files Likely Affected
- `docs/roadmap/MILESTONES.md`
- `docs/roadmap/ROADMAP.md`

## Implementation Plan
1. Capture the runtime requirements.
2. Capture operational constraints.
3. Convert them into minimal deployment requirements.

## Acceptance Criteria
- [ ] Requirements are written before manifests.
- [ ] The doc avoids assuming cluster-specific extras.

## Validation
Review the requirements against the app's single-container model.

## Dependencies
- `TASK-016`

## Risks
If Kubernetes is not needed, this task should remain deferred.

## Rollback Plan
Do not create Kubernetes artifacts unless the decision requires them.

## Notes
Only execute this if justified.

