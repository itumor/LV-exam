[Backend] Add persisted attempts, server-side scoring, and exam history API

Tasks:
1. Replace browser-only attempt persistence with backend API.
2. Add Postgres schema and migrations for users, exams, attempts, answers, scores, AI evaluations, payments/subscriptions, entitlements.
3. Implement attempt lifecycle: started, in_progress, submitted, scored, expired.
4. Store exam content version per attempt.
5. Move objective scoring server-side.
6. Add structured API errors and rate limits for scoring endpoints.

Acceptance criteria:
- API supports start attempt, save answer, submit attempt, get scored attempt, list attempt history.
- Objective scoring works from structured answer keys.
- Historical attempt remains reproducible even after exam content changes.
- Tests cover lifecycle transitions, invalid transitions, scoring, and rate limits.
