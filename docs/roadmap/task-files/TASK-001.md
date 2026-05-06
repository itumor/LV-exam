# TASK-001: Create a root-level onboarding and environment guide

## Summary
Create one root-level guide that explains how to clone, configure, run, and validate the project using the existing repo commands.

## Phase
Phase 1.

## Type
docs.

## Priority
P1 high.

## Complexity
M.

## Status
proposed.

## Context
The repository already has setup guidance spread across multiple docs, `.env-example`, and application-specific manuals. A single entry point would reduce onboarding ambiguity.

## Objective
Make the project easy to start locally without chasing scattered instructions.

## Scope
- Document the required runtime versions.
- Document the preferred commands from `package.json`, `README`, and `AGENTS.md`.
- Document environment variables and safe defaults.
- Document the recommended local URL and health endpoint.

## Out of Scope
- Changing application behavior.
- Introducing new tooling.
- Rewriting existing manuals.

## Files Likely Affected
- `README.md`
- `docs/roadmap/TASKS.md`
- `docs/roadmap/ROADMAP.md`

## Implementation Plan
1. Collect the current startup and test commands.
2. Summarize environment variables from `.env-example` and docs.
3. Add a concise root-level onboarding guide.
4. Cross-link the existing architecture and deployment docs.

## Acceptance Criteria
- [ ] A single root-level doc explains setup, run, and test entry points.
- [ ] Environment variables are listed with purpose and safe defaults.
- [ ] The guide points to the local health check and main app URL.

## Validation
Review the document against the repo commands and confirm it references only real files and commands.

## Dependencies
None.

## Risks
If the doc is too detailed, it can become stale quickly.

## Rollback Plan
Remove the doc or trim it back to the minimum command list.

## Notes
Keep it short and operational.

