# Latvian A2 Exam Simulator Roadmap

## Purpose

Build a realistic Latvian A2 state language exam simulator that helps learners practice under real exam conditions, receive useful scoring and feedback, and understand whether they are ready before exam day.

The product should become both:

- A high-trust exam preparation tool for learners.
- A monetizable product with subscriptions, paid exam packs, or paid AI scoring.

## Current State

The repository already contains a strong prototype:

- Browser exam app in `latvian-a2-exam-app/`.
- 10 generated mock exams from `codex/A2_Mock_Exam_01.md` through `codex/A2_Mock_Exam_10.md`.
- Additional `A2_Mock_Exam_11.md` content exists.
- MP3 audio assets for listening and speaking tasks.
- Image assets for writing and speaking tasks.
- Timed exam sections:
  - Listening: 25 minutes.
  - Reading: 30 minutes.
  - Writing: 35 minutes.
  - Speaking: 15 minutes.
- Objective answer capture and local scoring from Markdown answer keys.
- AI evaluation endpoint in `server.py`.
- Docker and Docker Compose support.
- Markdown, JSON, submission, TTS, image, and quality/debug views.
- Submission persistence in browser `localStorage`.

This is currently a local exam studio/prototype. The production MVP gap is mostly around accounts, payments, persistence, exam access control, content governance, reliability, legal positioning, and commercial packaging.

## Product Positioning

Core offer:

> Practice the Latvian A2 state language exam under realistic timing, get instant scoring, and know whether you are ready before exam day.

The product should not be positioned as generic Latvian exercises. The strongest value is:

- Realistic full-exam simulation.
- Time pressure similar to the real exam.
- Listening, reading, writing, and speaking coverage.
- AI feedback for writing and speaking.
- Clear pass/fail readiness based on the 9/15 per-skill rule.
- Progress history across attempts.

## Production MVP Definition

A production-ready MVP should allow a real learner to:

1. Create an account.
2. Choose a free or paid exam simulation.
3. Take the exam under realistic timing.
4. Submit answers.
5. Receive score, corrections, and feedback.
6. View attempt history and progress.
7. Pay for subscriptions, exam packs, or individual simulations.
8. Trust that the product is stable, secure, and clearly unofficial.

## Gap Analysis

| Area | Current State | Production MVP Need |
|---|---|---|
| Users | No real authentication | Email/social login and learner profile |
| Payments | No monetization | Stripe checkout, plans, entitlements |
| Storage | Browser `localStorage` | Database-backed attempts, scores, and history |
| Exam access | All local/free | Free vs paid exam access control |
| Scoring | Local objective scoring plus LLM endpoint | Server-side scoring, retries, auditability, cost controls |
| Speaking | Typed answers only | Audio recording, upload, optional transcription |
| Content | Markdown files | Versioned structured exam bank |
| Admin | No admin workflow | Draft/review/publish/archive exams |
| Security | Local prototype | Auth, rate limits, secret management, abuse protection |
| Deployment | Docker-ready | Hosted app, HTTPS, domain, monitoring |
| Legal | Not defined | Privacy policy, terms, unofficial simulator disclaimer |
| Analytics | None | Funnel, conversion, completion, retention, scoring cost |
| UX | Functional studio | Learner-facing polished exam flow |

## Business Model Options

### Option 1: Freemium Plus Paid Exam Packs

Free:

- 1 sample exam.
- Limited feedback.
- Possibly no full AI scoring.

Paid:

- 3, 5, or 10 full exam simulations.
- Paid AI correction for writing and speaking.
- Best fit for learners preparing close to an exam date.

Why it works:

- Users may only need the product for a short preparation window.
- One-off purchase has less friction than a subscription.
- Easy to connect value to a concrete exam attempt.

### Option 2: Monthly Subscription

Subscription includes:

- Access to all exams.
- Progress dashboard.
- Repeated practice.
- AI feedback within fair-use limits.
- New exams added regularly.

Why it works:

- Good for learners preparing over several weeks.
- Predictable recurring revenue.
- Supports a larger content library.

Risk:

- Learners may churn after passing the real exam.

### Option 3: Hybrid Model

Recommended MVP model:

- Free sample simulation.
- Paid exam packs.
- Monthly full-access subscription.
- Optional AI feedback credits for heavy users.

Example pricing:

- Free: 1 demo exam with limited feedback.
- Starter: EUR 7-10 for 3 full simulations.
- Exam Prep: EUR 15-25/month for all exams and AI feedback.
- Premium: EUR 29-39/month with detailed speaking/writing feedback and personalized study plan.

## Roadmap

## Phase 1: Productize The Existing Simulator

Goal: turn the current local studio into a learner-facing exam simulator.

Tasks:

- Rename learner-facing UI from "Studio" to "Exam Simulator" or similar.
- Hide developer/debug views by default:
  - Markdown.
  - JSON.
  - TTS.
  - Images.
  - Quality.
- Keep debug tools behind admin/dev mode.
- Add a clear exam flow:
  - Welcome.
  - Candidate registration/details.
  - Instructions.
  - Listening.
  - Reading.
  - Writing.
  - Speaking.
  - Results.
- Add two modes:
  - Real simulation mode.
  - Practice mode.
- Real simulation mode should:
  - Lock section order.
  - Prevent answer key exposure.
  - Prevent casual section switching.
  - Auto-submit when timers end.
  - Save one attempt record.
- Practice mode should:
  - Allow section-by-section practice.
  - Allow review after completion.
  - Support immediate correction where possible.
- Improve the results page:
  - Score by skill.
  - Pass/fail for each skill.
  - Total score out of 60.
  - Weak areas.
  - Suggested next practice.

Deliverable:

- A polished single-user MVP flow that feels like a real exam simulator rather than a developer tool.

## Phase 2: Backend And Persistence

Goal: replace browser-only state with durable server-side records.

Tasks:

- Add a production backend API.
- Add database storage for:
  - Users.
  - Exams.
  - Attempts.
  - Answers.
  - Scores.
  - AI evaluations.
  - Payments/subscriptions.
- Add attempt lifecycle:
  - `started`.
  - `in_progress`.
  - `submitted`.
  - `scored`.
  - `expired`.
- Persist every submitted attempt server-side.
- Store exam content version per attempt so historical results remain reproducible.
- Move objective scoring server-side.
- Keep LLM scoring focused on writing, speaking, and other free-text answers.
- Add AI evaluation retry and failure states.
- Add rate limits for scoring endpoints.
- Add structured API errors.

Suggested stack:

- Backend: FastAPI or similar Python API.
- Database: Postgres.
- Object storage: S3-compatible storage such as S3, R2, or equivalent for audio/image/speaking uploads.

Deliverable:

- Users can start, submit, and later reopen scored attempts from a database.

## Phase 3: Authentication And User Accounts

Goal: make the product usable by real paying learners.

Tasks:

- Add account creation and login.
- Support email/password, magic link, or social login.
- Add learner profile:
  - Name.
  - Email.
  - Native language if useful.
  - Exam target date.
- Add account dashboard:
  - Attempts taken.
  - Latest score.
  - Skill-level progress.
  - Subscription or exam pack status.
- Add password/account recovery if using password auth.
- Add account deletion/export flow for privacy compliance.

Suggested providers:

- Supabase Auth.
- Clerk.
- Auth0.
- Custom auth only if there is a strong reason.

Deliverable:

- Users have persistent accounts and can track progress across sessions/devices.

## Phase 4: Monetization

Goal: users can pay and receive controlled access.

Tasks:

- Add Stripe Checkout.
- Define products:
  - Single exam simulation.
  - Exam pack.
  - Monthly subscription.
  - AI scoring credits if needed.
- Add entitlements:
  - Free exam access.
  - Paid exam access.
  - Remaining attempts.
  - Remaining AI-scored submissions.
- Add Stripe webhook handling:
  - Payment succeeded.
  - Subscription created.
  - Subscription renewed.
  - Subscription canceled.
  - Refund or chargeback.
- Add billing page:
  - Current plan.
  - Attempts remaining.
  - Manage subscription.
  - Payment history if needed.
- Add pricing page.
- Add upgrade prompts after free exam completion.

Deliverable:

- A working paid access model that can sell exam simulations or subscriptions.

## Phase 5: Exam Realism

Goal: make the simulation feel close enough to the real exam experience to justify payment.

Tasks:

- Validate timing and section structure against the real A2 exam format.
- Add stricter real simulation controls:
  - No pause in real simulation mode.
  - Auto-submit on timeout.
  - One final submit per section or attempt.
  - Locked results until completion.
- Add optional audio playback constraints for listening tasks:
  - Limited replays if this matches the desired exam realism.
  - Playback count tracking.
- Add speaking task recording:
  - Browser microphone permission.
  - Audio recording.
  - Upload to server.
  - Playback for review.
  - Optional speech-to-text.
  - AI scoring based on transcript and/or audio-derived transcript.
- Add candidate-style result report:
  - Total score.
  - Skill scores.
  - Pass/fail status.
  - Corrections.
  - Recommendations.
- Add PDF export for results.

Deliverable:

- A paid learner can take a full realistic simulation and get a credible readiness report.

## Phase 6: Content System And Quality

Goal: make exam content scalable, validated, and safe to publish.

Tasks:

- Convert or mirror Markdown exams into structured JSON.
- Build a parser/importer from current Markdown format.
- Define an exam schema:
  - Metadata.
  - Sections.
  - Tasks.
  - Questions.
  - Answer options.
  - Correct answers.
  - Audio assets.
  - Image assets.
  - Scoring rules.
- Add schema validation for every exam.
- Add content quality checks:
  - Missing answer keys.
  - Broken audio links.
  - Broken image links.
  - Duplicate options.
  - Unexpected point totals.
  - Missing scoring metadata.
- Add admin workflow:
  - Draft.
  - Review.
  - Published.
  - Archived.
- Add more paid content:
  - 20-30 full exam simulations.
  - Topic-specific mini drills.
  - Weak-skill practice sets.

Deliverable:

- A maintainable exam bank that can grow without breaking the app.

## Phase 7: Reliability, Security, And Operations

Goal: operate the app safely as a paid product.

Tasks:

- Deploy with HTTPS and a custom domain.
- Store secrets in platform-managed environment variables.
- Add structured logs.
- Add monitoring and alerts for:
  - API errors.
  - Scoring failures.
  - Payment webhook failures.
  - Login failures.
  - High LLM cost.
- Add backups for the database.
- Add admin-only access controls.
- Add rate limiting and abuse protection.
- Add AI cost limits:
  - Per-user limits.
  - Per-plan limits.
  - Retry caps.
  - Request size limits.
- Add privacy policy.
- Add terms of service.
- Add clear legal disclaimer:
  - This is an unofficial practice simulator.
  - It is not affiliated with the official examination authority.
  - Scores are estimates for preparation, not official results.

Deliverable:

- A stable, secure, production-hosted MVP that can accept paying users.

## Suggested Technical Architecture

Lean production MVP:

- Frontend: existing app initially, cleaned up into learner-facing flow.
- Backend: FastAPI or equivalent production API.
- Database: Postgres.
- Auth: Supabase Auth, Clerk, Auth0, or similar.
- Payments: Stripe.
- Storage: S3-compatible object storage for media and speaking uploads.
- AI scoring: server-side provider abstraction with cost/rate controls.
- Deployment: Render, Fly.io, Railway, Cloud Run, or similar.
- Monitoring: Sentry plus platform logs.
- Email: Resend or Postmark.

Recommended sequence:

1. Keep the existing frontend initially.
2. Replace `server.py` with a production API when persistence/auth/payment work begins.
3. Add Postgres, auth, and Stripe.
4. Migrate to a frontend framework later only if the current app becomes hard to maintain.

## High-Priority MVP Backlog

1. Hide debug panels for normal users.
2. Add learner-facing exam flow.
3. Add real simulation mode.
4. Add persisted attempts.
5. Add user accounts.
6. Add server-side scoring.
7. Add AI scoring quotas and retry handling.
8. Add Stripe checkout.
9. Add free vs paid exam access.
10. Add results history.
11. Add legal/privacy pages.
12. Deploy production app with HTTPS.
13. Add monitoring and error tracking.
14. Add content validation.
15. Add speaking audio recording.

## Risks And Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| AI scoring inconsistency | Users may lose trust | Use rubrics, deterministic scoring prompts, retries, and manual QA samples |
| LLM cost growth | Profit margin risk | Quotas, paid credits, caching, and per-plan limits |
| Legal confusion | Reputational/legal risk | Clear unofficial simulator disclaimer |
| Content errors | Users may churn or complain | Schema validation and content QA pipeline |
| Weak speaking simulation | Product feels incomplete | Add recording and speech-to-text after core MVP |
| Too much free usage | Poor conversion | Limit free exam and AI feedback |
| Payment/webhook bugs | Revenue/access issues | Idempotent Stripe webhook handling and audit logs |
| Data privacy issues | Compliance and trust risk | Minimal data collection, clear privacy policy, secure storage |

## Validation Plan

Before building a large platform, validate demand with a focused launch:

1. Publish one free sample exam.
2. Offer a paid pack of 3-5 full simulations.
3. Include AI feedback for paid users.
4. Track funnel metrics:
   - Visitor to exam start.
   - Exam start to submit.
   - Submit to result view.
   - Result view to payment.
   - Payment to repeated use.
5. Interview early users:
   - Did it feel like the real exam?
   - Was the feedback useful?
   - Would they pay before their actual exam?
   - What felt missing or unrealistic?

## Success Metrics

Product metrics:

- Free exam completion rate.
- Paid conversion rate after free result.
- Average attempts per paid user.
- Writing/speaking feedback usage.
- User-reported usefulness.

Business metrics:

- Revenue per user.
- AI cost per paid user.
- Gross margin after AI costs.
- Refund rate.
- Subscription retention if using monthly plans.

Learning metrics:

- Score improvement across attempts.
- Weak-skill practice completion.
- Percentage of users reaching 9/15 in all skills.

## Recommended First Release

The first commercial release should include:

- 1 free full simulation.
- 5-10 paid full simulations.
- Account creation.
- Persisted attempt history.
- Objective scoring.
- AI correction for writing and speaking.
- Stripe payment.
- Results dashboard.
- Clear unofficial simulator disclaimer.
- Production deployment with HTTPS.

This is enough to test whether learners will pay for realistic exam preparation without overbuilding the platform.

