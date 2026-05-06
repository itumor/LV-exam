# TASK-019: Create a performance baseline plan for local and deployed runtime

## Summary
Document what performance should be measured and what a healthy baseline looks like for the current app.

## Phase
Phase 8.

## Type
performance.

## Priority
P2 medium.

## Complexity
M.

## Status
proposed.

## Context
The app includes AI calls, uploads, and browser-side workflows, but there is no explicit performance baseline or load-testing plan in the repo.

## Objective
Make future performance work measurable.

## Scope
- Define the current hotspots to measure.
- Document basic latency and resource metrics.
- Describe a light-weight load-check approach.

## Out of Scope
- Implementing performance optimizations.

## Files Likely Affected
- `docs/roadmap/ROADMAP.md`
- `docs/deployment-runbook.md`

## Implementation Plan
1. Identify key user journeys and server endpoints.
2. Define a simple baseline measurement plan.
3. Record the metrics that matter most.

## Acceptance Criteria
- [ ] Key journeys and endpoints are named.
- [ ] The baseline metrics are specific enough to track later.

## Validation
Compare the plan to the current app routes and tests.

## Dependencies
- `TASK-008`
- `TASK-013`

## Risks
Performance work can drift into optimization before measurement.

## Rollback Plan
Simplify the baseline to a small set of metrics.

## Notes
Measure first, optimize later.

