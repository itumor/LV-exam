# TASK-002: Document the current architecture and runtime boundaries

## Summary
Write a repository-grounded architecture summary that reflects the actual stack, components, and runtime boundaries.

## Phase
Phase 0.

## Type
docs.

## Priority
P1 high.

## Complexity
M.

## Status
proposed.

## Context
The repo already contains architecture docs, but the roadmap should have a current baseline tied directly to present files and deployment behavior.

## Objective
Create a stable reference for platform, product, and engineering decisions.

## Scope
- Summarize the Python server, frontend, content vault, billing, auth, and AI scoring boundaries.
- Note what is and is not persisted server-side.
- Note the current deployment model.

## Out of Scope
- Refactoring architecture.
- Adding new infrastructure.

## Files Likely Affected
- `docs/roadmap/ROADMAP.md`
- `docs/roadmap/RISK_REGISTER.md`

## Implementation Plan
1. Use the repo evidence to list the current components.
2. Capture runtime boundaries and trust boundaries.
3. Call out unknowns explicitly.

## Acceptance Criteria
- [ ] The document describes the real runtime stack.
- [ ] The document distinguishes browser, server, content, and provider boundaries.
- [ ] Unknowns are labeled as unknown rather than guessed.

## Validation
Compare the text against `server.py`, `docker-compose.yml`, `Dockerfile`, `fly.toml`, and the tested modules.

## Dependencies
None.

## Risks
Architecture text can drift if it is not updated with major changes.

## Rollback Plan
Revise the doc to match the current code paths.

## Notes
This task feeds the roadmap and future milestone planning.

