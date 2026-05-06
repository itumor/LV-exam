# TASK-015: Document SQLite backup and restore procedures for auth and billing data

## Summary
Create a practical backup and restore guide for the SQLite-backed auth and billing stores.

## Phase
Phase 4.

## Type
infrastructure.

## Priority
P0 critical.

## Complexity
M.

## Status
proposed.

## Context
The deployment model depends on SQLite persistence and mounted storage. A production posture requires a tested backup and restore path.

## Objective
Reduce data-loss risk for auth and billing state.

## Scope
- Document the database files and their locations.
- Document backup execution.
- Document integrity and restore verification.

## Out of Scope
- Migrating to a different database engine.

## Files Likely Affected
- `docs/deployment-runbook.md`
- `scripts/backup_sqlite.py`

## Implementation Plan
1. Identify the auth and billing files in current config.
2. Document backup creation and verification.
3. Add a restore checklist and failure notes.

## Acceptance Criteria
- [ ] Backup scope and file locations are documented.
- [ ] Restore verification steps are documented.
- [ ] The doc states the operational frequency assumption.

## Validation
Review the procedure against the current backup script and storage paths.

## Dependencies
- `TASK-004`
- `TASK-011`

## Risks
Inadequate restore testing can give false confidence.

## Rollback Plan
Revert to a simpler backup note if the procedure is not yet stable.

## Notes
This is a high-priority operational safeguard.

