[QA] Add end-to-end regression suite and release gate checklist

Tasks:
1. Add E2E tests for full learner journey: sign up, choose free/paid exam, take exam, submit, view results/history.
2. Add tests for real simulation restrictions and timer expiry.
3. Add tests for auth-protected routes.
4. Add tests for entitlement enforcement and Stripe webhook idempotency.
5. Add tests for AI scoring failure/retry/quota states.
6. Create release regression checklist.

Acceptance criteria:
- CI can run deterministic tests without live paid APIs.
- Test fixtures exist for exam content, auth sessions, payments, scoring responses, and media upload.
- Release checklist blocks launch if critical flows fail.
- QA summary is posted to each issue before marking ready for review.
