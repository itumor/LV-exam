# Risk Register

| Field | Value |
|---|---|
| **Document ID** | SOC2-RSK-001 |
| **Owner** | CTO |
| **Effective date** | 2026-05-23 |
| **Last review** | 2026-05-24 |
| **Next review** | 2026-06-23 |
| **Review cadence** | Monthly |
| **Parent policy** | `policy-information-security.md` |

## 1. Scoring Method

Each risk is scored on a **Likelihood × Impact** scale of 1–5; the
resulting risk score is the product (1–25). Anything ≥ 12 is escalated
to the founders at the next monthly review.

| Score | Likelihood | Score | Impact |
|---|---|---|---|
| 1 | Rare | 1 | Negligible |
| 2 | Unlikely | 2 | Minor |
| 3 | Possible | 3 | Moderate |
| 4 | Likely | 4 | Major |
| 5 | Almost certain | 5 | Severe |

## 2. Status Definitions

- **Open** — known risk, mitigation not yet in place.
- **In progress** — mitigation underway; expected close date is recorded.
- **Mitigated** — control implemented; residual risk acceptable.
- **Accepted** — risk acknowledged and accepted by founders without further mitigation, with re-review date.
- **Closed** — risk no longer applicable.

## 3. Top Risks

| # | Risk | Likelihood | Impact | Score | Owner | Mitigation | Status | Re-review |
|---|---|---|---|---|---|---|---|---|
| R-01 | SQLite-on-Fly volume corruption causes data loss > RPO | 2 | 5 | 10 | SRE Lead | T-013 6h backups to R2 + `PRAGMA integrity_check`; T-021 Postgres migration removes the single-volume failure mode | **Mitigated** (Postgres migration tracked under T-021) | 2026-08-23 |
| R-02 | Single-region Fly outage in FRA halts service beyond RTO | 3 | 4 | 12 | SRE Lead | T-028 multi-region warm standby (LHR + FRA); DNS failover documented in BC policy | **In progress** (T-028 not yet merged) | 2026-07-23 |
| R-03 | Credential leak via committed secret | 2 | 5 | 10 | Security Lead | `gitleaks` pre-commit + CI gate; secrets only in Fly secrets / GitHub Actions secrets; quarterly rotation | **Mitigated** | 2026-08-23 |
| R-04 | LLM provider (Groq / OpenAI) outage degrades exam delivery | 3 | 3 | 9 | Engineering Lead | Provider failover wired in code; cached content for the most common exam templates | **Mitigated** | 2026-08-23 |
| R-05 | Stripe webhook replay causes duplicate billing | 2 | 4 | 8 | Engineering Lead | Idempotency keys in `billing.py` (hotfix T-099 historical); contract tests verify idempotency | **Mitigated** | 2026-08-23 |
| R-06 | Server-side entitlement bypass (privilege escalation) | 2 | 5 | 10 | Security Lead | T-024 enforces every protected route server-side; pen-test (T-029) validates externally | **In progress** (T-024 merge pending) | 2026-06-23 |
| R-07 | Brute-force / credential-stuffing on `/api/auth/*` | 3 | 3 | 9 | Security Lead | T-015 rate limits (`rate_limit.py`) — 10/min/IP on auth routes with 429 + `Retry-After`; MFA required on admin accounts | **Mitigated** | 2026-08-23 |
| R-08 | Insufficient audit log for institutional disputes | 3 | 3 | 9 | Engineering Lead | T-043 audit-log export (CSV + JSON) gives institutional admins on-demand access | **In progress** (T-043 merge pending) | 2026-07-23 |
| R-09 | Sub-processor (e.g. Groq) experiences a breach exposing prompt data | 2 | 3 | 6 | CTO | Sub-processors evaluated in `policy-vendor-management.md`; no learner PII sent to LLM providers; DPA + ZDR (OpenAI) on file | **Mitigated** | 2027-05-23 |
| R-10 | Burnout / single-person dependency on Security Lead and SRE Lead during incidents | 3 | 4 | 12 | CTO | Cross-train two engineers per role; document IR runbook; rotating on-call after team grows past 4 | **Open** | 2026-06-23 |
| R-11 | Platform lock-in to Fly.io — forced migration on Fly outage / pricing change / enterprise self-host requirement | 3 | 3 | 9 | CTO | T-072 K8s evaluation merged with PoC manifests in `infra/k8s-poc/` and trigger-based reopen criteria in `docs/k8s-evaluation.md` §6; cost model re-run every 6 months | **Accepted** (residual; reviewed under T-072) | 2026-11-24 |

## 4. Risks Below the Top Bar

Tracked in the longer GitHub Issues list under the `risk` label. Items
that grow past a score of 8 are promoted into this register at the next
monthly review.

## 5. Review Workflow

1. CTO reviews the register on the first business day of each month.
2. Owners post a one-line update on every risk in their column.
3. Any risk that has been **Open** for ≥ 90 days without progress is
   escalated to the founders.
4. Risks moved to **Mitigated** or **Closed** are kept in the table for
   one additional quarter, then archived to §6.

## 6. Archive

_None yet — initial issue._

## 7. Revision History

| Date | Author | Change |
|---|---|---|
| 2026-05-23 | T-070 | Initial issue. |
| 2026-05-24 | T-072 | Added R-11 (platform lock-in to Fly.io) following K8s vs Fly evaluation. Renamed §3 from "Top-10" to "Top Risks". |
