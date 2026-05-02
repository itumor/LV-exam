# Security Review

## Scope

This review covers the current exam runner, server-side scoring endpoint, and the planned production deployment for the Latvian A2 Exam Studio MVP.

## Key Risks

### 1. Secret Exposure

Risk:

- Provider API keys or future payment credentials could leak to the browser or logs.

Mitigations:

- Keep all secrets in server environment variables or a secret manager.
- Never ship provider keys in frontend code.
- Avoid logging full request bodies or provider responses.

### 2. Answer-Key Exposure

Risk:

- Learners could access answer keys or internal scoring prompts.

Mitigations:

- Keep scoring server-side.
- Treat Markdown content as internal exam source, not a public API contract.
- Hide internal debug views from ordinary users.

### 3. Abuse And Cost Growth

Risk:

- Repeated scoring calls can create provider cost and availability issues.

Mitigations:

- Rate limit `/api/evaluate`.
- Enforce request size limits.
- Cap retries and timeouts.
- Add per-plan and per-user quotas once accounts exist.

### 4. Missing Persistence Or Backups

Risk:

- Attempts and entitlements can be lost if state is only in memory or browser storage.

Mitigations:

- Store durable data in Postgres when the platform is added.
- Back up the database.
- Test restore paths before launch.

### 5. Unsafe Content Or Rendering

Risk:

- Rendered Markdown or generated content could produce broken layout or script injection if not constrained.

Mitigations:

- Keep Markdown parsing strict.
- Sanitize any HTML injection paths.
- Validate exam structure before publishing content.

### 6. Weak Operational Visibility

Risk:

- Failures in scoring, billing, or login can be missed until users report them.

Mitigations:

- Emit structured JSON logs.
- Add Sentry or equivalent error monitoring.
- Alert on 5xx errors, 429s, webhook failures, and elevated latency.

## Launch Readiness Notes

- The current repository is still pre-database and pre-billing.
- The production launch should not proceed until HTTPS, monitoring, legal pages, and backup verification are in place.
- AI scoring must always be labeled as practice feedback, not an official exam result.
