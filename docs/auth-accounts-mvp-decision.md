# Auth Accounts MVP Decision

The commercial MVP keeps the current server-managed email/password session flow in `server.py` instead of wiring a third-party identity provider into the browser app.

## Why this is the MVP choice

- The repository already has durable account, profile, dashboard, and webhook-sync endpoints that keep secrets server-side.
- The browser never receives `AUTH_WEBHOOK_SECRET`, provider API keys, or any other auth secret.
- The current goal is a launchable learner product, not a full identity-platform migration.
- Deferring an external IdP keeps the MVP smaller while still supporting sign-up, sign-in, sign-out, recovery-oriented account export, and account deletion.

## What remains true for production

- Auth webhooks must stay signature-verified and idempotent.
- Protected routes must remain server-enforced, not just hidden in the client.
- Learner profile and attempt history must remain tied to the authenticated account.
- Any future external IdP can be added behind the same account/session contract without exposing secrets to the browser.

## Operational notes

- Set `AUTH_WEBHOOK_SECRET` only in the server environment.
- Keep provider-specific secrets in managed environment variables or a secret store.
- Never copy provider secrets into `latvian-a2-exam-app/app.js`, `index.html`, or other browser assets.
