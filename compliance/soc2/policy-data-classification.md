# Data Classification Policy

| Field | Value |
|---|---|
| **Document ID** | SOC2-POL-004 |
| **Owner** | Security Lead (acting: CTO) |
| **Effective date** | 2026-05-23 |
| **Last review** | 2026-05-23 |
| **Next review** | 2027-05-23 |
| **Review cadence** | Annual |
| **TSC mapping** | C1.1, C1.2, CC6.5 |

## 1. Purpose

Define data sensitivity tiers and the minimum handling controls required
for each. Every dataset, log stream, and backup must be classified at the
time of creation; the data owner is responsible for the classification.

## 2. Classification Tiers

### 2.1 Public

- **Definition.** Information explicitly approved for unrestricted disclosure.
- **Examples.** Marketing site copy, public API documentation, the SOC 2
  policy excerpts published to prospects, the open-source portions of the
  exam-bank schema.
- **Handling.** No special controls; integrity controls (signed releases,
  CDN cache invalidation) still apply.

### 2.2 Internal

- **Definition.** Non-sensitive operational data that should not be
  disclosed externally but whose accidental leak is low impact.
- **Examples.** Aggregated usage metrics, internal architecture diagrams,
  CI logs without secrets, design documents.
- **Handling.** Access limited to employees and contractors under NDA.
  Stored only in approved systems (GitHub private repos, internal Drive).

### 2.3 Confidential

- **Definition.** Sensitive customer or business data whose disclosure
  would harm trust, reputation, or finances.
- **Examples.** Learner profiles, exam attempts and scores, audio
  submissions (`audio_uploads.py`), institutional rosters, billing
  metadata (excluding raw card numbers — those never reach lvcodex),
  Stripe customer IDs, audit-log exports (T-043).
- **Handling.**
  - Encrypted in transit (TLS 1.2+) and at rest (Fly volumes + R2 SSE).
  - Access logged via the application audit log.
  - Backups restricted to the R2 bucket configured in `scripts/backup_sqlite.sh`.
  - Never logged to stdout, Sentry, or any third-party tool.
  - Must be redacted from any dataset used for staging restores.

### 2.4 Restricted

- **Definition.** Data whose disclosure would result in regulatory
  action, contractual breach, or material business harm.
- **Examples.** Service-account credentials (R2 keys, Stripe webhook
  secret, Groq/OpenAI API keys), session-signing secrets, root admin
  TOTP seeds, government-tender contractual terms.
- **Handling.**
  - Stored only in the secrets vault (Fly secrets / GitHub Actions
    secrets, never in plaintext files).
  - Access requires founder approval and is logged.
  - Rotated at least every 90 days **and** on any leaver event.
  - Any leak triggers Sev-1 incident response.

## 3. Default Classification

Any new dataset whose tier is not explicitly recorded is treated as
**Confidential** until the owner classifies it. This is the safe default.

## 4. Data Inventory

The current data inventory is maintained in `evidence-matrix.md` §A and
is updated whenever a new persistent store or sub-processor is introduced.

## 5. Retention

| Tier | Default retention | Notes |
|---|---|---|
| Public | Indefinite | — |
| Internal | 3 years | CI logs auto-pruned at 90 days. |
| Confidential | Per legal/contractual obligations — typically 2 years post-account-closure | Exam attempts retained for academic dispute window. |
| Restricted | Only as long as required; rotated quarterly | Secrets never retained beyond rotation overlap. |

## 6. Revision History

| Date | Author | Change |
|---|---|---|
| 2026-05-23 | T-070 | Initial issue. |
