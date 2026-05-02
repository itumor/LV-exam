[Auth] Add accounts, learner profile, dashboard, and webhook sync

Tasks:
1. Add account creation and login.
2. Add learner profile: name, email, native language if useful, exam target date.
3. Add dashboard: attempts taken, latest score, skill progress, subscription/exam pack status.
4. Add account recovery if password auth is used.
5. Add account deletion/export flow.
6. Add auth webhook sync to local database.

Acceptance criteria:
- Protected routes cannot be accessed anonymously.
- Learner can view attempt history across sessions/devices.
- Auth webhooks verify signatures and are idempotent.
- Secret keys are never exposed to client bundle.
- Tests cover sign-in, protected route, webhook verification, and dashboard data.
