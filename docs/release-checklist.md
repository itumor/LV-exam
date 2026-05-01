# Release Checklist

## Purpose

Use this checklist as the final gate before the Latvian A2 exam simulator is treated as a commercial MVP.

If any item in the must-pass sections is incomplete, the release stays blocked.

## Must-Pass Product Checks

- [ ] Learner can create or sign into an account.
- [ ] Learner can start a free or paid exam from the normal UI.
- [ ] Real simulation mode locks section order and prevents casual answer-key exposure.
- [ ] Practice mode still works for section-by-section review.
- [ ] Results page shows skill scores, pass/fail, total score, and next-practice guidance.
- [ ] Speaking flow records or uploads audio without breaking the session.
- [ ] Candidate-facing report clearly says the score is a practice estimate, not an official exam result.

## Must-Pass Data Checks

- [ ] Attempts are stored server-side.
- [ ] Attempt history is visible after refresh and on a second device.
- [ ] Exam content version is stored with each attempt.
- [ ] Objective scoring is reproducible from stored answer data.
- [ ] AI scoring records include prompt version, rubric version, model, and result status.
- [ ] Failed scoring retries are visible rather than silently discarded.

## Must-Pass Billing Checks

- [ ] Stripe Checkout works in test mode and production mode.
- [ ] Free access is enforced exactly as configured.
- [ ] Paid access is granted only after a verified entitlement event.
- [ ] Webhooks are idempotent.
- [ ] Refunds and chargebacks revoke or freeze the correct entitlement.
- [ ] Upgrade prompts appear only where they make product sense.

## Must-Pass Security And Ops Checks

- [ ] Production deployment runs behind HTTPS.
- [ ] Secrets are stored in managed environment variables or a secret store.
- [ ] Login, billing, and scoring endpoints have rate limiting.
- [ ] Logs do not leak answer keys, provider tokens, or full candidate answers.
- [ ] Monitoring covers request failures, payment failures, scoring failures, and high latency.
- [ ] Backups are configured and a restore test has been documented.
- [ ] Health checks are green in the target environment.

## Must-Pass Legal And Trust Checks

- [ ] Privacy policy is published.
- [ ] Terms of service are published.
- [ ] Unofficial simulator disclaimer is visible before payment and on results pages.
- [ ] Language around AI scoring is clearly framed as practice feedback.
- [ ] Data retention and deletion rules are documented.

## Must-Pass QA Checks

- [ ] Full learner journey passes in the regression suite.
- [ ] Real simulation timer expiry is tested.
- [ ] Auth-protected routes reject anonymous access.
- [ ] Payment webhook idempotency test passes.
- [ ] AI scoring timeout, invalid response, and quota tests pass.
- [ ] Release gate checklist has a named owner and a current run date.

## Launch Day Checks

- [ ] Production environment variables are verified against the deployment matrix.
- [ ] Rollback or previous image path is documented.
- [ ] Support contact or escalation path is visible to the team.
- [ ] Launch metrics dashboard is confirmed.
- [ ] A smoke test has been run on the live domain.

## Post-Launch Monitoring

- [ ] First-hour error rate is watched.
- [ ] Payment success rate is watched.
- [ ] AI scoring cost is watched.
- [ ] Sign-in failures are watched.
- [ ] Completion rate for the exam flow is watched.
- [ ] Any launch blockers are logged back into the issue tracker immediately.

## Source Notes

- [[Latvian A2 Exam Simulator Roadmap]]
- [[Solution Architecture]]
- [[Cloud Hosting and Improvement Architecture]]
