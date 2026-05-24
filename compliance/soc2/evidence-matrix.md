# SOC 2 Trust Service Criteria — Evidence Matrix

| Field | Value |
|---|---|
| **Document ID** | SOC2-EVD-001 |
| **Owner** | Security Lead (acting: CTO) |
| **Effective date** | 2026-05-23 |
| **Last review** | 2026-05-23 |
| **Next review** | 2027-05-23 |
| **Review cadence** | Quarterly |

This matrix maps each in-scope SOC 2 Trust Service Criterion to one or
more concrete evidence artifacts. Every TSC has at least one piece of
evidence; gaps must be opened as remediation items in `risk-register.md`.

## A. Data Inventory (referenced by C1)

| Dataset | Store | Owner | Classification | Backed up? |
|---|---|---|---|---|
| Learner accounts + sessions | `.multica/auth.sqlite3` | Engineering Lead | Confidential | Yes (T-013) |
| Exam attempts + scores | `data/lvcodex.db` | Engineering Lead | Confidential | Yes (T-013) |
| Billing + Stripe customer mapping | `data/billing.sqlite3` | Finance Lead | Confidential | Yes (T-013) |
| Audio submissions (T-018) | Fly volume | Engineering Lead | Confidential | Yes (T-013) |
| CI/CD logs | GitHub Actions | Engineering Lead | Internal | No (90-day default) |
| Production runtime logs | Fly + Sentry | SRE Lead | Internal (PII scrubbed) | Sentry-side retention |
| Backup snapshots | Cloudflare R2 | SRE Lead | Confidential | Geo-redundant by R2 |

## B. Common Criteria (CC1 — CC9)

### CC1 — Control Environment

| Control | Evidence artifact |
|---|---|
| CC1.1 — Commitment to integrity and ethics | `policy-information-security.md`; founder sign-off recorded in commit log on initial issue. |
| CC1.2 — Board oversight | Quarterly security review minutes (filed by Security Lead, T-070-followup). |
| CC1.3 — Organizational structure | `policy-information-security.md` §4 roles table. |
| CC1.4 — Commitment to competence | Annual security training completion, tracked by `procedure-onboarding-offboarding.md` §2 step 5. |

### CC2 — Communication & Information

| Control | Evidence artifact |
|---|---|
| CC2.1 — Internal communication | `compliance/soc2/README.md` index; policy circulation in onboarding. |
| CC2.2 — External communication | Customer-facing privacy notice in `legal/`, status page (T-012). |
| CC2.3 — Whistleblower channel | `security@` mailbox; founder direct line. |

### CC3 — Risk Assessment

| Control | Evidence artifact |
|---|---|
| CC3.1 — Specifies objectives | Delivery plan at `/Users/eramadan/.claude/plans/create-a-detailed-delivery-robust-candle.md`. |
| CC3.2 — Identifies risks | `risk-register.md`. |
| CC3.3 — Considers fraud risk | `policy-incident-response.md` Stripe Radar integration. |
| CC3.4 — Manages change | `policy-change-management.md`. |

### CC4 — Monitoring Activities

| Control | Evidence artifact |
|---|---|
| CC4.1 — Ongoing monitoring | Prometheus metrics (T-014) + Grafana Cloud dashboards. |
| CC4.2 — Independent assessment | External pen-test (T-029) results + remediation tickets. |

### CC5 — Control Activities

| Control | Evidence artifact |
|---|---|
| CC5.1 — Control selection | This evidence matrix. |
| CC5.2 — Technology general controls | `policy-change-management.md` + CI configuration. |
| CC5.3 — Policy deployment | `compliance/soc2/` directory under version control. |

### CC6 — Logical & Physical Access

| Control | Evidence artifact |
|---|---|
| CC6.1 — Logical access | `policy-access-control.md` + `procedure-onboarding-offboarding.md`. |
| CC6.2 — Account provisioning | Joiner tickets, role grants in each system. |
| CC6.3 — Account de-provisioning | Leaver tickets (≤1h SLA). |
| CC6.5 — Data classification | `policy-data-classification.md`. |
| CC6.6 — External access | T-024 server-side entitlement enforcement on every protected route. |
| CC6.7 — Data transmission protection | TLS 1.2+ everywhere; cert managed by Fly. |
| CC6.8 — Malware protection | Endpoint EDR (vendor in `docs/vendors/`); `pip-audit` on every PR. |

### CC7 — System Operations

| Control | Evidence artifact |
|---|---|
| CC7.1 — System monitoring | T-014 metrics + alert rules. |
| CC7.2 — Anomaly detection | T-015 rate-limit metrics (`rate_limit.py`) + Sentry release health. |
| CC7.3 — Incident evaluation | `policy-incident-response.md` triage workflow. |
| CC7.4 — Incident response | Post-mortems in `docs/incidents/`. |
| CC7.5 — Recovery | `policy-business-continuity.md` + `procedure-backup-restore.md`. |

### CC8 — Change Management

| Control | Evidence artifact |
|---|---|
| CC8.1 — Change management process | `policy-change-management.md` + GitHub PR history + CI logs. |

### CC9 — Risk Mitigation

| Control | Evidence artifact |
|---|---|
| CC9.1 — Risk mitigation activities | `risk-register.md`. |
| CC9.2 — Vendor risk | `policy-vendor-management.md` sub-processor table + DPAs on file. |

## C. Availability (A1)

| Control | Evidence artifact |
|---|---|
| A1.1 — Capacity planning | Fly autoscaling config; Prometheus saturation alerts. |
| A1.2 — Environmental protection | Fly.io SOC 2 report (vendor evidence). |
| A1.3 — Recovery | `procedure-backup-restore.md` drill log §6. |

## D. Confidentiality (C1)

| Control | Evidence artifact |
|---|---|
| C1.1 — Identifies confidential information | `policy-data-classification.md` §2.3 + inventory in §A. |
| C1.2 — Disposes of confidential information | Retention table in `policy-data-classification.md` §5; account-deletion endpoint logs. |

## E. Processing Integrity (PI1)

| Control | Evidence artifact |
|---|---|
| PI1.1 — Process inputs | Server-side request validation in `server_app/`. |
| PI1.2 — Process integrity | T-024 entitlement enforcement; `tests/server/` unit + contract tests. |
| PI1.3 — Output integrity | 9/15 per-skill A2 pass-rule preserved (CONTRIBUTING.md DoD #7); contract tests in `tests/contracts/release-contracts.test.cjs`. |
| PI1.4 — Output review | T-043 audit-log export accessible to institutional admins. |
| PI1.5 — Stored data integrity | T-013 backups + `PRAGMA integrity_check` in `scripts/backup_sqlite.py`. |

## F. Evidence Refresh Cadence

| Evidence type | Refresh cadence | Owner |
|---|---|---|
| Policy docs | Annual | Document owner |
| Access review | Quarterly | Security Lead |
| Restore drill | Quarterly | SRE Lead |
| Vendor SOC reports | Annual | CTO |
| Pen-test (external) | Annual | Security Lead |
| Risk register | Monthly | CTO |

## G. Revision History

| Date | Author | Change |
|---|---|---|
| 2026-05-23 | T-070 | Initial issue. |
