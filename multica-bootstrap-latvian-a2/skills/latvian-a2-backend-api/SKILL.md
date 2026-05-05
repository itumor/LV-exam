---
name: latvian-a2-backend-api
description: Build the FastAPI/Postgres production backend for attempts, scoring, exam content, AI evaluations, payments, and history.
---

# Latvian A2 Backend API

Model users, exams, attempts, answers, scores, AI evaluations, payments/subscriptions, and entitlements. Attempt lifecycle must include started, in_progress, submitted, scored, and expired. Store exam content version per attempt. Move objective scoring server-side. Implement structured API errors, rate limits, idempotency for external webhooks, and auditable scoring records. Prefer async DB access, migrations, and tests for all business rules.
