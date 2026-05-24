# Information Security Policy

| Field | Value |
|---|---|
| **Document ID** | SOC2-POL-001 |
| **Owner** | CTO (acting Security Lead until role is filled) |
| **Approver** | Founders |
| **Effective date** | 2026-05-23 |
| **Last review** | 2026-05-23 |
| **Next review** | 2027-05-23 |
| **Review cadence** | Annual + on any material control change |
| **TSC mapping** | CC1.1, CC1.2, CC1.3, CC1.4, CC2.1, CC2.2 |

## 1. Purpose

This policy establishes the management direction, principles, and
responsibilities for protecting the confidentiality, integrity, and
availability of lvcodex information assets — including learner accounts,
exam content, audio submissions, payment records, and institutional rosters.

## 2. Scope

This policy applies to:

- All employees, contractors, and founders of the operating entity behind lvcodex.
- All production and pre-production systems hosted on Fly.io, Cloudflare R2, and any sub-processor listed in `policy-vendor-management.md`.
- All source code repositories under the `lvcodex` GitHub organisation, including but not limited to `lvcodex` itself.
- All endpoint devices used to access production systems or repositories.

## 3. Guiding Principles

1. **Least privilege.** Access is granted on a need-to-know basis and reviewed quarterly (see `policy-access-control.md`).
2. **Defense in depth.** No single control failure should result in a breach. Network, application, and identity layers each have independent controls.
3. **Secure by default.** New features ship with the most restrictive setting; broader access requires explicit configuration.
4. **Transparency with customers.** Material security incidents affecting customer data are disclosed per `policy-incident-response.md` §6.
5. **Continuous improvement.** Every incident produces a written post-mortem with action items tracked to closure.

## 4. Roles and Responsibilities

| Role | Responsibility |
|---|---|
| **CTO / Security Lead** | Owns this policy, chairs quarterly security review, approves exceptions. |
| **Engineering Lead** | Enforces change-management policy on PR reviews. Ensures CI gates remain enabled. |
| **SRE Lead** | Owns backup, restore, monitoring, and DR procedures. |
| **All Engineers** | Complete annual security awareness training; report suspected incidents within 1 business hour of detection. |

## 5. Control Framework

The lvcodex security control set is built on:

- **AICPA Trust Service Criteria** (Security, Availability, Confidentiality, Processing Integrity) — primary framework for SOC 2 Type I.
- **OWASP ASVS Level 2** — used as the application security baseline.
- **CIS Benchmarks** for the Fly.io / Docker runtime configuration.

Mapping of TSC controls to evidence artifacts is maintained in `evidence-matrix.md`.

## 6. Enforcement

Violation of this policy may result in revocation of access, contractual
remedies (for contractors), or termination (for employees). Every quarter,
the Security Lead presents to the founders an exception register and an
open-finding register; any item open more than 90 days is escalated.

## 7. Exceptions

Exceptions require a written request to the Security Lead, a documented
risk acceptance, and a review-by date no later than 90 days from issuance.
All open exceptions are listed in `risk-register.md` under the `Accepted`
status.

## 8. Revision History

| Date | Author | Change |
|---|---|---|
| 2026-05-23 | T-070 | Initial issue. |
