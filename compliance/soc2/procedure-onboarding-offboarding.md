# Procedure — Admin Account Onboarding & Offboarding

| Field | Value |
|---|---|
| **Document ID** | SOC2-PRC-001 |
| **Owner** | Security Lead + HR (acting: CTO) |
| **Effective date** | 2026-05-23 |
| **Last review** | 2026-05-23 |
| **Next review** | 2027-05-23 |
| **Review cadence** | Annual + after any leaver event that exposed a gap |
| **Parent policy** | `policy-access-control.md` |
| **TSC mapping** | CC6.1, CC6.2, CC6.3 |

## 1. Scope

This procedure governs the lifecycle of accounts that hold administrative
or production access — i.e. all roles listed in `policy-access-control.md`
§2 (GitHub, Fly.io, R2, Stripe, Sentry, lvcodex `superadmin`). Learner and
institutional-user lifecycles are handled by the application itself and
are out of scope.

## 2. Onboarding (Joiners)

Trigger: signed contract + manager request ticket.

| # | Step | Owner | SLA |
|---|---|---|---|
| 1 | HR opens an onboarding ticket with start date, role, and manager. | HR | T-7 days |
| 2 | Security Lead reviews the requested role set against least-privilege baseline. | Security Lead | T-3 days |
| 3 | Hardware issued + endpoint enrolled (disk encryption verified). | HR / IT | T-1 day |
| 4 | Accounts created on each system listed in `policy-access-control.md` §2. MFA enforced before first login. | Security Lead | T+1 business day |
| 5 | Joiner completes security awareness training (acceptable use, phishing, secrets handling, IR contacts). | Joiner | T+5 business days |
| 6 | Confirm joiner has only the accounts and roles listed in their ticket; remove anything extra. | Security Lead | T+5 business days |
| 7 | Close onboarding ticket with evidence (screenshots of role grants, training completion). | Security Lead | T+10 business days |

## 3. Role Changes (Movers)

Trigger: role-change ticket from manager.

| # | Step | Owner | SLA |
|---|---|---|---|
| 1 | Manager files role-change ticket with effective date. | Manager | T-3 days |
| 2 | Security Lead grants new role and **immediately removes** roles no longer required. There is no "carry-over" grace period. | Security Lead | Effective date |
| 3 | Ticket closed with a diff of role grants. | Security Lead | T+1 business day |

## 4. Offboarding (Leavers)

Trigger: termination notification from HR, founder, or by the leaver
themselves. **Note:** termination notifications are treated as a Sev-2
event for access-revocation timing.

| # | Step | Owner | SLA |
|---|---|---|---|
| 1 | HR notifies Security Lead via the agreed paging channel. | HR | Immediately |
| 2 | Revoke MFA-protected SSO sessions on GitHub, Fly, Cloudflare, Stripe, Sentry. Delete the accounts (do not just suspend) within 24 hours unless legal hold requires retention. | Security Lead | **≤ 1 business hour** |
| 3 | Rotate all shared service-account credentials the leaver had access to (R2 keys, Stripe webhook secret, Groq / OpenAI keys, session-signing secret). | SRE Lead | ≤ 4 business hours |
| 4 | Remove leaver from `compliance/soc2/CODEOWNERS` (once added) and any GitHub teams. | Security Lead | ≤ 4 business hours |
| 5 | Collect hardware; wipe disk; mark in asset inventory. | HR / IT | ≤ 5 business days |
| 6 | Document the offboarding in the closed ticket: list of accounts revoked, secrets rotated, hardware status. | Security Lead | ≤ 5 business days |

## 5. Quarterly Access Review

Trigger: calendar reminder, 10 business days after each quarter end.

| # | Step | Owner |
|---|---|---|
| 1 | Generate role-grant report for each system in §2 above. | Security Lead |
| 2 | Each manager confirms or revokes their direct reports' grants. | Managers |
| 3 | Discrepancies opened as remediation tickets; target close within 10 business days. | Security Lead |
| 4 | Review summary archived for SOC 2 evidence. | Security Lead |

## 6. Evidence

The closed onboarding, role-change, and offboarding tickets are the
SOC 2 evidence for the **CC6 — Logical Access** controls. They are
exported to the compliance archive at each quarter end.

## 7. Revision History

| Date | Author | Change |
|---|---|---|
| 2026-05-23 | T-070 | Initial issue. |
