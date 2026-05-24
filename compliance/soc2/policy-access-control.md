# Access Control Policy

| Field | Value |
|---|---|
| **Document ID** | SOC2-POL-002 |
| **Owner** | Security Lead (acting: CTO) |
| **Effective date** | 2026-05-23 |
| **Last review** | 2026-05-23 |
| **Next review** | 2027-05-23 |
| **Review cadence** | Annual + on every personnel change |
| **TSC mapping** | CC6.1, CC6.2, CC6.3, CC6.6, CC6.7 |

## 1. Purpose

Define how identities, roles, and permissions are provisioned, reviewed,
and revoked across lvcodex production systems and supporting services.

## 2. Identity Sources

| System | Identity provider | MFA | Notes |
|---|---|---|---|
| GitHub (source repos) | GitHub.com SSO | **Required** | Reviewed quarterly. |
| Fly.io (runtime) | Fly.io accounts | **Required** | Org owners limited to 2 founders + SRE Lead. |
| Cloudflare R2 (backups) | Cloudflare account | **Required** | API tokens scoped to single bucket. |
| Stripe (billing) | Stripe Dashboard | **Required** | Role: `Developer` for engineers, `Administrator` only for finance. |
| Sentry (error reporting) | Sentry SSO | **Required** | Read-only for engineers below SRE. |
| **lvcodex app** (admin console) | Email + password + session cookie | Required for `superadmin` | See `server_app/services/auth.py`. |

External user (learner) accounts are governed by the privacy notice in `legal/`, not this policy.

## 3. Role Model (RBAC)

The lvcodex application enforces three server-side roles. Enforcement is
implemented in the routes layer (see T-024 entitlement checks) — **never UI-only**.

| Role | Capabilities | Lifecycle |
|---|---|---|
| `learner` | Self-service exam attempts, view own results, manage own billing. | Self-registration; suspended on payment failure after dunning. |
| `tutor` | Read-only access to assigned learner cohort (T-042). | Provisioned by institutional admin; revoked when seat is reclaimed. |
| `institution_admin` | Manage seats (T-041), download audit-log export (T-043). | Provisioned by lvcodex sales; revoked on contract end + 30 days grace. |
| `superadmin` | Full read/write on `/admin/*` routes. | Engineering Lead only. Granted via DB migration with two-founder sign-off. |

There are **no** anonymous-write paths to the application.

## 4. Least Privilege

- Service-account tokens (Stripe webhook secret, R2 keys, Sentry DSN) are scoped to a single integration.
- No engineer has standing prod database write access; emergency access requires founder approval and is logged.
- Read-only database snapshots are derived from the T-013 backup chain; staging restores never receive raw prod data without redaction.

## 5. Account Lifecycle

The detailed onboarding and offboarding steps live in
`procedure-onboarding-offboarding.md`. At a glance:

| Event | SLA | Trigger |
|---|---|---|
| Joiner — create accounts | 1 business day after start | Signed contract + manager request |
| Mover — adjust roles | Same day | Role-change ticket |
| Leaver — revoke all access | **Within 1 business hour** of termination notification | HR + Security Lead signal |
| Quarterly access review | Within 10 business days of quarter end | Calendar reminder + ticket |

## 6. Authentication Requirements

- Minimum password length: 14 characters for any human-system account.
- TOTP / WebAuthn MFA required on every external system listed in §2.
- Application sessions expire after **24 hours of inactivity** (see `server_app/services/auth.py`).
- Failed-login rate limits enforced by `rate_limit.py` (T-015) — default 10/min on `/api/auth/*` with `Retry-After`.

## 7. Logging and Monitoring

Every privileged action logs to the centralized log stream and is exported
via T-043 audit-log export. Sample events: role grants, billing changes,
data exports, admin route access.

## 8. Revision History

| Date | Author | Change |
|---|---|---|
| 2026-05-23 | T-070 | Initial issue. |
