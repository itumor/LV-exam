# TASK-004: Clarify deployment and rollback steps for Fly.io

## Summary
Document the current Fly.io deployment flow, expected environment variables, and rollback approach.

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
The repo includes `fly.toml` and `scripts/deploy-fly.sh`, but the operational path is only partially documented across multiple files.

## Objective
Make deployment repeatable and reduce operator guesswork.

## Scope
- Document the Fly.io deployment command.
- Document required environment and secrets assumptions.
- Document smoke checks and rollback considerations.

## Out of Scope
- Changing deployment topology.
- Replacing Fly.io.

## Files Likely Affected
- `docs/deployment-runbook.md`
- `docs/roadmap/ROADMAP.md`
- `docs/roadmap/MILESTONES.md`

## Implementation Plan
1. Read the current deployment script and Fly config.
2. Summarize the deploy flow.
3. Add rollback and verification steps.

## Acceptance Criteria
- [ ] The deployment path is documented from build to smoke check.
- [ ] Rollback considerations are explicit.
- [ ] Secret handling expectations are called out.

## Validation
Compare the document with `fly.toml` and `scripts/deploy-fly.sh`.

## Dependencies
- `TASK-002`

## Risks
Deployment docs can lag behind the actual script if the script changes.

## Rollback Plan
Update the runbook to the currently supported deploy path.

## Notes
This is operationally sensitive.

