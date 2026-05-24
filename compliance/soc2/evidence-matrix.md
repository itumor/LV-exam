# SOC 2 Trust Service Criteria — Evidence Matrix

| Field | Value |
|---|---|
| **Document ID** | SOC2-EVD-001 |
| **Owner** | Security Lead (acting: CTO) |
| **Effective date** | 2026-05-23 |
| **Last review** | 2026-05-24 |
| **Next review** | 2026-08-24 |
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
| CC2.3 — Whistleblower channel | `security@` mailbox; founder direct line; documented in `policy-incident-response.md`. |

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
| CC4.1 — Ongoing monitoring | Prometheus metrics (T-014): [`server_app/metrics.py`](../../server_app/metrics.py), [`server_app/routes/metrics.py`](../../server_app/routes/metrics.py); weekly CI-runs evidence in `compliance/soc2/evidence/<YYYY-WW>/ci_runs.json`. |
| CC4.2 — Independent assessment | External pen-test (T-029): [`schemas/openapi.yaml`](../../schemas/openapi.yaml) + [`docs/pentest-scope-of-work.md`](../../docs/pentest-scope-of-work.md); remediation tickets tracked in `risk-register.md`. |

### CC5 — Control Activities

| Control | Evidence artifact |
|---|---|
| CC5.1 — Control selection | This evidence matrix (`compliance/soc2/evidence-matrix.md`). |
| CC5.2 — Technology general controls | `policy-change-management.md` + CI configuration: [`.github/workflows/ci-pr.yml`](../../.github/workflows/ci-pr.yml), [`.github/workflows/ci-develop.yml`](../../.github/workflows/ci-develop.yml), [`.github/workflows/soc2-evidence.yml`](../../.github/workflows/soc2-evidence.yml), and the orchestrator at [`compliance/soc2/automation/orchestrator.py`](automation/orchestrator.py). |
| CC5.3 — Policy deployment | `compliance/soc2/` directory under version control; pre-flight gate [`scripts/soc2_preflight.py`](../../scripts/soc2_preflight.py) blocks releases when an artifact is missing. |

### CC6 — Logical & Physical Access

| Control | Evidence artifact |
|---|---|
| CC6.1 — Logical access | `policy-access-control.md` + `procedure-onboarding-offboarding.md`; rate-limit enforcement at [`rate_limit.py`](../../rate_limit.py); weekly access summary in `compliance/soc2/evidence/<YYYY-WW>/access_audit.json`. |
| CC6.2 — Account provisioning | Joiner tickets, role grants in each system; T-043 audit ledger rows (`account.created`, `admin.invited`, `sso.user.provisioned`) — see [`server_app/services/audit_export.py`](../../server_app/services/audit_export.py); weekly aggregate in `access_audit.json` (`joiner_count`). |
| CC6.3 — Account de-provisioning | Leaver tickets (≤1h SLA); T-043 audit ledger rows (`account.deleted`, `account.deactivated`, `session.revoked`); weekly aggregate in `access_audit.json` (`leaver_count`). |
| CC6.5 — Data classification | `policy-data-classification.md`. |
| CC6.6 — External access | T-024 server-side entitlement enforcement on every protected route; contract tests in [`tests/server/test_entitlement_enforcement.py`](../../tests/server/test_entitlement_enforcement.py). |
| CC6.7 — Data transmission protection | TLS 1.2+ everywhere; cert managed by Fly; configured in `fly.toml`. |
| CC6.8 — Malware protection | Endpoint EDR (vendor in `docs/vendors/`); `pip-audit` on every PR via [`.github/workflows/reusable-security.yml`](../../.github/workflows/reusable-security.yml). |

### CC7 — System Operations

| Control | Evidence artifact |
|---|---|
| CC7.1 — System monitoring | T-014 metrics ([`server_app/metrics.py`](../../server_app/metrics.py)) + alert rules; T-043 audit export ([`server_app/services/audit_export.py`](../../server_app/services/audit_export.py)). |
| CC7.2 — Anomaly detection | T-015 rate-limit metrics ([`rate_limit.py`](../../rate_limit.py)) + Sentry release health; `failed_login_count` in weekly `access_audit.json`. |
| CC7.3 — Incident evaluation | `policy-incident-response.md` triage workflow. |
| CC7.4 — Incident response | Post-mortems in `docs/incidents/`; triage runbook in `policy-incident-response.md`. |
| CC7.5 — Recovery | `policy-business-continuity.md` + `procedure-backup-restore.md`; weekly restore-drill summary in `compliance/soc2/evidence/<YYYY-WW>/backup_drills.json` (sourced from [`.github/workflows/backup-restore-drill.yml`](../../.github/workflows/backup-restore-drill.yml)). |

### CC8 — Change Management

| Control | Evidence artifact |
|---|---|
| CC8.1 — Change management process | `policy-change-management.md` + GitHub PR history + CI logs; weekly run summary in `compliance/soc2/evidence/<YYYY-WW>/ci_runs.json` (workflow conclusions, last-failure SHAs). |

### CC9 — Risk Mitigation

| Control | Evidence artifact |
|---|---|
| CC9.1 — Risk mitigation activities | `risk-register.md`. |
| CC9.2 — Vendor risk | `policy-vendor-management.md` sub-processor table + DPAs on file. |

## C. Availability (A1)

| Control | Evidence artifact |
|---|---|
| A1.1 — Capacity planning | Fly autoscaling config; Prometheus saturation alerts ([`server_app/metrics.py`](../../server_app/metrics.py)). |
| A1.2 — Environmental protection | Fly.io SOC 2 report (vendor evidence); sub-processor table in `policy-vendor-management.md`. |
| A1.3 — Recovery | `procedure-backup-restore.md` drill log §6; automated weekly summary in `compliance/soc2/evidence/<YYYY-WW>/backup_drills.json` (drill success rate, R2 snapshot age). |

## D. Confidentiality (C1)

| Control | Evidence artifact |
|---|---|
| C1.1 — Identifies confidential information | `policy-data-classification.md` §2.3 + inventory in §A. |
| C1.2 — Disposes of confidential information | Retention table in `policy-data-classification.md` §5; account-deletion endpoint logs. |

## E. Processing Integrity (PI1)

| Control | Evidence artifact |
|---|---|
| PI1.1 — Process inputs | Server-side request validation in `server_app/` — see [`server_app/core.py`](../../server_app/core.py) and the route modules under [`server_app/routes/`](../../server_app/routes). |
| PI1.2 — Process integrity | T-024 entitlement enforcement; [`tests/server/test_entitlement_enforcement.py`](../../tests/server/test_entitlement_enforcement.py) + contract tests. |
| PI1.3 — Output integrity | 9/15 per-skill A2 pass-rule preserved (CONTRIBUTING.md DoD #7); contract tests in [`tests/contracts/release-contracts.test.cjs`](../../tests/contracts/release-contracts.test.cjs). |
| PI1.4 — Output review | T-043 audit-log export accessible to institutional admins — [`server_app/services/audit_export.py`](../../server_app/services/audit_export.py), tested by [`tests/server/test_audit_export.py`](../../tests/server/test_audit_export.py). |
| PI1.5 — Stored data integrity | T-013 backups + `PRAGMA integrity_check` in [`scripts/backup_sqlite.py`](../../scripts/backup_sqlite.py); weekly restore-drill outcome captured in `compliance/soc2/evidence/<YYYY-WW>/backup_drills.json`. |

## F. Evidence Refresh Cadence

| Evidence type | Refresh cadence | Automated? | Owner |
|---|---|---|---|
| Policy docs | Annual | No (manual) | Document owner |
| Access review | Quarterly | Weekly aggregate via `access_audit.json` | Security Lead |
| Restore drill | Quarterly | Weekly aggregate via `backup_drills.json` | SRE Lead |
| Vendor SOC reports | Annual | No | CTO |
| Pen-test (external) | Annual | No | Security Lead |
| Risk register | Monthly | No | CTO |
| CI-run history | Weekly | Yes (`ci_runs.json`) | Engineering Lead |

## G. Automated Evidence Pipeline (T-070-final)

The orchestrator at [`compliance/soc2/automation/orchestrator.py`](automation/orchestrator.py)
runs every Monday at 04:00 UTC via [`.github/workflows/soc2-evidence.yml`](../../.github/workflows/soc2-evidence.yml)
and writes:

| Artifact | Source | Maps to |
|---|---|---|
| `compliance/soc2/evidence/<YYYY-WW>/ci_runs.json` | `gh run list` over `develop` + `main` | CC4.1, CC7.1, CC8.1 |
| `compliance/soc2/evidence/<YYYY-WW>/backup_drills.json` | `Backup restore drill` workflow + R2 listing | A1.3, CC7.5, PI1.5 |
| `compliance/soc2/evidence/<YYYY-WW>/access_audit.json` | T-043 `audit_events` ledger (aggregated, no PII) | CC6.1, CC6.2, CC6.3, CC7.2 |
| `compliance/soc2/evidence/<YYYY-WW>/manifest.json` | Orchestrator index | CC5.2 |

The pre-flight gate [`scripts/soc2_preflight.py`](../../scripts/soc2_preflight.py)
enumerates every required artifact and exits non-zero if any are
missing — wired into the same weekly workflow and run locally by the
Security Lead before the auditor engagement.

## H. Revision History

| Date | Author | Change |
|---|---|---|
| 2026-05-23 | T-070 | Initial issue. |
| 2026-05-24 | T-070-final | Linked concrete artifact paths after T-014, T-029, T-043 merged; added §G automation pipeline; bumped review cadence to quarterly. |
