> Last updated: 2026-05-23
>
> Note: This document is currently available in English only. A Latvian
> translation is forthcoming and will be filed as a follow-up to T-011.

# Privacy Policy

Latvian A2 Exam Studio ("we", "us") is the data controller for personal
data processed through the Service. This Privacy Policy explains what
we collect, why, on what legal basis, how long we keep it, and the
rights you have under the EU General Data Protection Regulation 2016/679
("GDPR") and the Latvian Personal Data Processing Law.

## 1. Data we collect

| Category | Examples | Source |
| --- | --- | --- |
| Account data | Email address, hashed password, locale | You |
| Attempt data | Exam selections, answers (text and audio), objective scores, AI scoring metadata | You |
| Audio recordings | Speaking-task uploads (audio/webm, audio/ogg, audio/wav, audio/mp4, audio/mpeg) | You |
| Billing data | Stripe customer ID, payment status, invoice records (we do NOT store card numbers) | Stripe |
| Operational data | IP address, user-agent, request logs, error reports | Automatic |

We do not knowingly collect special categories of personal data
(Art. 9 GDPR). Do not upload such data unless absolutely necessary; if
you do, we will treat it under the lawful basis you select.

## 2. Purposes and lawful basis

| Purpose | Lawful basis (GDPR) |
| --- | --- |
| Provide the exam, score answers, save progress | Art. 6(1)(b) — performance of a contract |
| Process payments and issue invoices | Art. 6(1)(b) + Art. 6(1)(c) — legal obligation (tax/accounting) |
| AI scoring via third-party providers (Groq, OpenAI, etc.) | Art. 6(1)(b) — contract, plus your in-product consent before audio upload |
| Operational logs, fraud and abuse prevention | Art. 6(1)(f) — legitimate interests |
| Service announcements and product updates | Art. 6(1)(a) — consent (opt-in at signup, revocable) |
| Compliance with court orders or supervisory requests | Art. 6(1)(c) — legal obligation |

## 3. Retention

| Data | Retention |
| --- | --- |
| Account record (active) | Until you delete the account |
| Attempt and scoring history | 24 months from last activity, then anonymised |
| Speaking audio uploads | 90 days from upload, or sooner on request |
| Billing records (invoices, Stripe events) | 6 years (Latvian Accounting Law) |
| Web server / access logs | 30 days |
| Error and security telemetry (Sentry) | 90 days |

After the retention period, data is deleted or irreversibly anonymised.

## 4. Sub-processors and international transfers

We use the following sub-processors. Transfers outside the European
Economic Area ("EEA") rely on Standard Contractual Clauses (SCCs) and,
where applicable, supplementary measures (encryption in transit, IP
filtering, no log retention beyond what is necessary).

- Fly.io, Inc. — application hosting (US/EU regions).
- Stripe Payments Europe Ltd. — payment processing (EEA + US).
- Groq, Inc. — AI scoring inference (US).
- OpenAI Ireland Ltd. — fallback AI scoring (EEA + US).
- Sentry (Functional Software, Inc.) — error monitoring (US).
- Cloudflare, Inc. — CDN and DDoS mitigation (global).

A current and machine-readable sub-processor list is published at the
URL in your Data Processing Agreement (see `legal/dpa.md`). Material
changes are notified at least 30 days in advance.

## 5. Your rights

Under GDPR you have the right to:

- **Access** (Art. 15) — request a copy of your data. Self-service
  export is available at `/api/account/export`.
- **Rectification** (Art. 16) — correct inaccurate data.
- **Erasure / "right to be forgotten"** (Art. 17) — delete your
  account; billing records that we are legally required to retain
  will be kept for the statutory period.
- **Restriction** (Art. 18) — temporarily stop processing.
- **Portability** (Art. 20) — receive your data in JSON via the export
  endpoint above.
- **Object** (Art. 21) — object to processing based on legitimate
  interests or direct marketing.
- **Withdraw consent** (Art. 7) — without affecting prior lawful
  processing.
- **Lodge a complaint** (Art. 77) — with the Latvian Data State
  Inspectorate (Datu valsts inspekcija, www.dvi.gov.lv) or your local
  supervisory authority.

## 6. Cookies and similar technologies

See `legal/cookie-policy.md` for the cookies we set and your choices.

## 7. Security

Data in transit is encrypted with TLS 1.2+. Passwords are hashed with
PBKDF2-SHA256 with a per-user salt. Audio uploads are scanned for size
and content-type. Production access to the database is restricted to
on-call engineers and is audit-logged.

## 8. Data Protection Officer (DPO)

DPO contact (placeholder): dpo@lvexam.example. We will replace this
with a verified address (and, where required, a formal DPO appointment
under Art. 37 GDPR) before opening paid traffic in the EU.

## 9. Children

The Service is not directed at children under 16. If you believe a
child has provided us personal data, contact dpo@lvexam.example and we
will delete it.

## 10. Changes

We will announce material changes at least 30 days before they take
effect via in-app notice or email.

## 11. Contact

Privacy questions: privacy@lvexam.example (placeholder until launch).
