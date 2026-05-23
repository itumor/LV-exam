# Incident Response Policy

| Field | Value |
|---|---|
| **Document ID** | SOC2-POL-003 |
| **Owner** | Security Lead (acting: CTO) |
| **Effective date** | 2026-05-23 |
| **Last review** | 2026-05-23 |
| **Next review** | 2027-05-23 |
| **Review cadence** | Annual + after every Sev-1 incident |
| **TSC mapping** | CC7.2, CC7.3, CC7.4, CC7.5 |

## 1. Purpose

Define how lvcodex detects, triages, contains, eradicates, and learns from
security and availability incidents — and how stakeholders (customers,
regulators, founders) are informed.

## 2. Definitions

| Term | Definition |
|---|---|
| **Event** | Any observed change in system state (alert, log line, user report). |
| **Incident** | An event with confirmed or suspected adverse impact on confidentiality, integrity, or availability. |
| **Breach** | An incident with confirmed unauthorized access to customer personal data. Triggers additional GDPR notification flow. |

## 3. Severity Matrix

| Sev | Definition | Page | Response start |
|---|---|---|---|
| **Sev-1** | Production down, customer data leak, payment system unavailable, or any breach. | PagerDuty all-hands | ≤ 15 min |
| **Sev-2** | Partial outage, degraded performance, one customer impacted, or recoverable data loss. | PagerDuty primary | ≤ 30 min |
| **Sev-3** | Single-feature degradation, monitoring alert without customer impact. | Slack `#oncall` | ≤ 4 business hours |
| **Sev-4** | Informational; tracked but not paged. | Ticket only | Next business day |

## 4. Detection Sources

1. **Sentry** — uncaught exceptions, performance regressions.
2. **Prometheus + Grafana Cloud (T-014)** — error-rate, latency, and saturation alerts wired to PagerDuty.
3. **Rate-limit metrics (T-015)** — anomalous `429` rates indicating brute-force.
4. **Stripe Radar** — billing fraud signals.
5. **Customer reports** — `security@` mailbox, in-app feedback.
6. **External researchers** — `security.txt` + responsible-disclosure programme.

## 5. Response Workflow

The on-call engineer follows the IR runbook stored at `docs/runbooks/incident-response.md` (created under T-070-followup). The high-level flow is:

1. **Acknowledge** the page within the SLA in §3.
2. **Triage** — assign severity, declare an incident channel.
3. **Contain** — revoke tokens, block IPs (rate limits), or scale down a malicious endpoint.
4. **Eradicate** — patch the root cause; deploy via the standard change-management process unless emergency-change criteria (§7) are met.
5. **Recover** — verify metrics return to baseline; lift any temporary controls.
6. **Communicate** — customer status page update for Sev-1/Sev-2; final post-mortem within 5 business days.

## 6. External Communication

| Audience | Trigger | Channel | SLA |
|---|---|---|---|
| Affected customers | Sev-1 or any breach | Email + in-app banner | ≤ 4 hours from confirmation |
| Status page subscribers | Any Sev-1/Sev-2 | `status.lvcodex.io` | ≤ 30 min from declaration |
| Data Protection Authority | Personal-data breach | Per GDPR Art. 33 | ≤ 72 hours from awareness |
| Auditor (SOC 2) | Any Sev-1 | Email summary | Within 5 business days |

## 7. Emergency Change Authority

A Sev-1 incident authorizes the on-call engineer to bypass the standard PR
review (`policy-change-management.md`) for a **single emergency change**,
provided that:

1. A founder or Engineering Lead is paged and acknowledges in the incident channel.
2. The change is committed on a `hotfix/T-XXX` branch (per CONTRIBUTING.md).
3. A retrospective PR review is completed within 48 hours.

## 8. Post-Mortem

Every Sev-1 and every Sev-2 incident produces a blameless post-mortem
within 5 business days. The template is in `docs/runbooks/post-mortem-template.md`.
The Security Lead tracks all action items to closure in the risk register.

## 9. Revision History

| Date | Author | Change |
|---|---|---|
| 2026-05-23 | T-070 | Initial issue. |
