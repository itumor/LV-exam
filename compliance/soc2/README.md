# SOC 2 Type I Compliance Package — lvcodex

> Task ID: **T-070 (docs portion)** — policy + evidence document set.
> Owner: **Security & Compliance Lead** (currently the CTO until role is filled).
> Review cadence: **annual**, with ad-hoc updates on material control changes.
> Last review: 2026-05-23.

This directory is the canonical source for the SOC 2 Type I audit-prep
artifacts of the Latvian A2 exam platform (**lvcodex**). It is referenced by
the master delivery plan (`/Users/eramadan/.claude/plans/create-a-detailed-delivery-robust-candle.md`)
and by the B2G procurement track in `BUSINESS_REPORT.md` §7.1 P6.

The audit scope is the Trust Service Criteria selected for our offering:

| TSC group | In scope |
|---|---|
| **Security (CC1–CC9)** | Yes — required baseline |
| **Availability (A1)** | Yes — uptime SLA in customer contracts |
| **Confidentiality (C1)** | Yes — institutional and personal data |
| **Processing Integrity (PI1)** | Yes — exam scoring (9/15 rule) is load-bearing |
| Privacy (P1–P8) | **Out of scope for Type I** — covered separately by the GDPR programme |

## Document Index

### Policies

| # | Document | Purpose | Owner |
|---|---|---|---|
| 1 | [policy-information-security.md](policy-information-security.md) | Overarching infosec policy, ownership, review cadence | CTO |
| 2 | [policy-access-control.md](policy-access-control.md) | RBAC, least-privilege, account lifecycle | Security Lead |
| 3 | [policy-incident-response.md](policy-incident-response.md) | Detection, triage, escalation, post-mortem | Security Lead |
| 4 | [policy-data-classification.md](policy-data-classification.md) | Public / Internal / Confidential / Restricted tiers | Security Lead |
| 5 | [policy-vendor-management.md](policy-vendor-management.md) | Sub-processor list + due diligence | CTO |
| 6 | [policy-business-continuity.md](policy-business-continuity.md) | RTO/RPO, DR runbook, dependency on T-013 backups | SRE Lead |
| 7 | [policy-change-management.md](policy-change-management.md) | GitFlow + PR review + CI gates as change control | Engineering Lead |

### Procedures

| # | Document | Purpose | Owner |
|---|---|---|---|
| 8 | [procedure-onboarding-offboarding.md](procedure-onboarding-offboarding.md) | Admin account lifecycle | HR + Security Lead |
| 9 | [procedure-backup-restore.md](procedure-backup-restore.md) | Backup execution + quarterly restore drill | SRE Lead |

### Evidence

| # | Document | Purpose | Owner |
|---|---|---|---|
| 10 | [evidence-matrix.md](evidence-matrix.md) | Maps each TSC (CC1–CC9, A1, C1, PI1) to evidence artifacts | Security Lead |
| 11 | [risk-register.md](risk-register.md) | Top-10 risks with owner, mitigation, status | CTO |

## Audit-Prep Checklist (T-minus-90 days)

The following gates must all be green before the SOC 2 Type I auditor engagement
begins. Each item links to the controlling document or task ID.

- [ ] All 7 policies and 2 procedures in this directory are reviewed in the last 12 months (`git log` per file).
- [ ] Each policy lists a **named owner** (not a role alias) and a **next-review-date** within the next 12 months.
- [ ] The evidence matrix has **at least one artifact** per TSC control.
- [ ] T-013 backup script (`scripts/backup_sqlite.sh`) has run successfully every 6h for the prior 90 days (R2 listing).
- [ ] At least one **restore drill** has been executed and documented in the last 90 days (`procedure-backup-restore.md`).
- [ ] T-014 Prometheus metrics endpoint (`/metrics`) is reachable from the monitoring host and Grafana alerts have fired in test.
- [ ] T-015 rate limits are active in production (verify `429` responses on synthetic burst).
- [ ] T-024 server-side entitlement checks are merged and the test suite (`tests/server/test_entitlements*.py`) is green.
- [ ] T-029 pen-test prep (OpenAPI spec + SoW) is complete and the external pen-test is either scheduled or its remediation tickets are closed.
- [ ] T-043 audit-log export endpoint is reachable by an institutional admin test account.
- [ ] No `gitleaks` finding is open on `develop` or `main`.
- [ ] All access reviews (quarterly) are documented for the prior 4 quarters.
- [ ] All risks in `risk-register.md` are either `Mitigated`, `Accepted`, or have an open Jira/GitHub ticket.
- [ ] Sub-processor list in `policy-vendor-management.md` matches the privacy notice in `legal/`.
- [ ] CI history shows zero unaddressed `pip-audit` HIGH/CRITICAL findings on `main` for the prior 90 days.

## Cross-Reference: Plan Tasks That Generate Evidence

| Task | Generates evidence for |
|---|---|
| **T-013** (`scripts/backup_sqlite.sh`, `scripts/backup_sqlite.py`) | A1 — Availability |
| **T-014** (`server_app/metrics.py`, `server_app/routes/metrics.py`) | A1, CC7 — Monitoring |
| **T-015** (`rate_limit.py`) | CC6 — Logical access controls |
| **T-024** (server-side entitlement checks) | CC6, PI1 — Authorization + processing integrity |
| **T-029** (OpenAPI + pen-test SoW) | CC4 — Independent assessment |
| **T-043** (audit-log export) | CC7 — Monitoring activities |
| **T-070** (this directory) | CC1 — Control environment |

## How to Update This Package

1. Open a `docs/T-070-...` or `chore/T-070-...` branch off `develop`.
2. Edit the relevant policy / procedure.
3. Bump the `Last review` date and `Next review` date in the document header.
4. Note the change in the "Revision history" table at the bottom of the file.
5. Open a PR; the **Security Lead** is the required reviewer for any file in `compliance/soc2/`.
6. CODEOWNERS will be configured under T-070-followup to enforce this automatically.
