# Vendor Management Policy

| Field | Value |
|---|---|
| **Document ID** | SOC2-POL-005 |
| **Owner** | CTO |
| **Effective date** | 2026-05-23 |
| **Last review** | 2026-05-23 |
| **Next review** | 2027-05-23 |
| **Review cadence** | Annual + on every new sub-processor |
| **TSC mapping** | CC9.1, CC9.2 |

## 1. Purpose

Govern how third-party sub-processors are selected, contracted, monitored,
and offboarded. Every sub-processor with access to Confidential or
Restricted data (per `policy-data-classification.md`) is listed in §3.

## 2. Selection Criteria

Before a new sub-processor is engaged, the CTO confirms:

1. **Compliance posture** — current SOC 2 / ISO 27001 / GDPR DPA available.
2. **Data residency** — supports EU data residency if Confidential learner data is involved.
3. **Sub-processor chain** — the vendor's own sub-processor list is reviewed.
4. **Exit plan** — there is a documented way to extract or delete our data.
5. **Operational footprint** — incident reporting commitments meet our IR policy SLAs.

A short risk-assessment memo is filed alongside the signed DPA in the
vendor folder.

## 3. Current Sub-Processor Register

| Vendor | Purpose | Data accessed | Data classification | Region | DPA on file | Contract owner |
|---|---|---|---|---|---|---|
| **Stripe** | Payment processing, Stripe Tax (T-016) | Customer ID, billing address, payment method | Confidential | Ireland (EU) | Yes — Stripe DPA v2024 | Finance Lead |
| **Groq** | LLM inference for content generation and scoring assistance | Anonymous exam prompts; no learner PII | Internal | US (via region-pinned endpoint) | Yes — Groq DPA | CTO |
| **OpenAI** | Backup LLM inference + TTS (where Groq is unavailable) | Anonymous exam prompts; no learner PII | Internal | US | Yes — OpenAI DPA + ZDR | CTO |
| **Fly.io** | Application + database runtime hosting | All Confidential data at rest on Fly volumes | Confidential | Frankfurt (FRA) primary, London (LHR) standby (T-028) | Yes — Fly DPA | SRE Lead |
| **Cloudflare R2** | Encrypted backup storage (T-013) | Database snapshots | Confidential | EU bucket | Yes — Cloudflare DPA | SRE Lead |
| **Sentry** | Error monitoring | Stack traces, request IDs (PII scrubbed) | Internal | EU region (`sentry.io` EU) | Yes — Sentry DPA | Engineering Lead |

Vendors used **only** for marketing, analytics on the public site, or
internal collaboration (and that never touch Confidential data) are
tracked separately in `docs/vendors/marketing-tools.md` and are out of
scope for this policy.

## 4. Ongoing Monitoring

| Activity | Cadence | Owner |
|---|---|---|
| Review vendor SOC 2 / ISO 27001 reports | Annual | CTO |
| Confirm DPA is still in force | Annual | CTO |
| Re-confirm sub-processor list matches privacy notice | Annual | CTO |
| Spot-check vendor status pages during incidents | Per incident | On-call |

## 5. Vendor Offboarding

When a vendor is replaced or removed:

1. The CTO opens a removal ticket and notifies the data owner.
2. Data is extracted (if required for continuity) or deleted in place.
3. Credentials and tokens for that vendor are revoked.
4. The privacy notice is updated and customers are notified per GDPR.
5. The entry in §3 is moved to an "Archived" appendix with the offboarding date.

## 6. Customer Notification

The current sub-processor register in §3 is mirrored in the public
privacy notice in `legal/`. Material changes (new sub-processor, change
of region) are announced via email at least 30 days before activation
for institutional customers, per their contract terms.

## 7. Revision History

| Date | Author | Change |
|---|---|---|
| 2026-05-23 | T-070 | Initial issue. |
