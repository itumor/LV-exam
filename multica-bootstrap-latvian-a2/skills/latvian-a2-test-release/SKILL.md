---
name: latvian-a2-test-release
description: Own QA, Playwright flows, API tests, payment/auth/scoring reliability tests, release readiness, and regression prevention.
---

# Latvian A2 Test Release

Test complete exam flow from account creation to paid attempt result history. Cover real simulation timer expiry, practice mode review, auth protected routes, Stripe webhook idempotency, entitlement enforcement, server-side scoring, AI scoring failure/retry states, content validation, speaking upload, and PDF report generation. Prefer deterministic tests and avoid relying on live payment/AI calls in CI.
