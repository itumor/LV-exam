> Last updated: 2026-05-23
>
> Note: This document is currently available in English only. A Latvian
> translation is forthcoming and will be filed as a follow-up to T-011.

# Data Processing Agreement (DPA)

This Data Processing Agreement ("DPA") forms part of the agreement
between **the Customer** ("Controller") and **Latvian A2 Exam Studio**
("Processor"), and reflects the parties' agreement with regard to the
Processing of Personal Data, in accordance with the requirements of
the EU General Data Protection Regulation 2016/679 ("GDPR").

This document is a template intended for institutional / B2B
customers. Individual consumers do not need to sign a DPA; their
processing is governed by the Privacy Policy at `legal/privacy.md`.

## 1. Definitions

Terms used in this DPA have the meanings given in Art. 4 GDPR, in
particular: "personal data", "processing", "data subject",
"controller", "processor", and "sub-processor".

## 2. Subject matter and duration

| Item | Value |
| --- | --- |
| Subject matter | Provision of the Latvian A2 Exam Studio service |
| Duration | For the term of the underlying service agreement, and after termination as required for legal retention |
| Nature and purpose | Hosting, scoring, and analytics for language-exam practice |
| Type of personal data | Account, attempt, billing, audio, and operational data (see Privacy Policy section 1) |
| Categories of data subjects | Customer's learners, instructors, and administrators |

## 3. Processor obligations

The Processor shall:

1. Process Personal Data only on documented instructions from the
   Controller (Art. 28(3)(a) GDPR).
2. Ensure that persons authorised to process the Personal Data are
   bound by confidentiality.
3. Implement appropriate technical and organisational measures
   (Art. 32 GDPR) — see Annex 2.
4. Engage sub-processors only with the Controller's prior written
   authorisation, which may be granted via the list in Annex 1.
5. Assist the Controller in responding to data-subject requests
   (Art. 15-22) and notifications of personal-data breaches.
6. At the Controller's choice, delete or return all Personal Data
   after termination (subject to retention required by law).

## 4. International transfers

Where Personal Data is transferred outside the European Economic Area,
the parties incorporate the **EU Standard Contractual Clauses (SCCs)**
adopted by the European Commission in Decision 2021/914 (Module 2:
Controller-to-Processor). Annex 3 sets out the docking and
implementation details.

## 5. Sub-processors

The Controller authorises the Processor to engage the sub-processors
listed in Annex 1. The Processor will notify the Controller of any
intended changes at least 30 days in advance. The Controller may
object on reasonable grounds; if the objection cannot be resolved, the
Controller may terminate the underlying service agreement.

## 6. Audit

The Controller may, no more than once per calendar year and on
30 days' written notice, audit the Processor's compliance with this
DPA, subject to reasonable confidentiality and access limits.

## 7. Liability

Liability under this DPA is subject to the limitations in the
underlying service agreement and to mandatory provisions of Art. 82
GDPR.

---

## Annex 1 — Authorised sub-processors

> Placeholder list. The live list is maintained at
> https://lvexam.example/sub-processors (to be published before paid
> launch) and is incorporated by reference into this DPA.

| Sub-processor | Service | Location |
| --- | --- | --- |
| Fly.io, Inc. | Application hosting | US / EU |
| Stripe Payments Europe Ltd. | Payments | EEA + US |
| Groq, Inc. | AI scoring (primary) | US |
| OpenAI Ireland Ltd. | AI scoring (fallback) | EEA + US |
| Sentry (Functional Software, Inc.) | Error monitoring | US |
| Cloudflare, Inc. | CDN and DDoS mitigation | Global |

## Annex 2 — Technical and organisational measures

- TLS 1.2+ for all in-transit traffic.
- PBKDF2-SHA256 password hashing with per-user salt.
- Database encryption at rest (Fly.io volume-level).
- Access control: least-privilege IAM, MFA for engineers.
- Logging and monitoring: structured access logs (30 days), Sentry
  error capture (90 days).
- Backups: daily snapshots, 14-day retention, tested quarterly.
- Incident response: 72-hour breach notification per Art. 33 GDPR.
- Pen-test / security review: annual, summary report available on
  request under NDA.

## Annex 3 — Standard Contractual Clauses (Module 2)

The parties incorporate Commission Implementing Decision (EU)
2021/914, Module 2 (Controller to Processor), with the docking clause
enabled. The information required by Annexes I, II, and III of the
SCCs is supplied by Annexes 1 and 2 of this DPA and by the underlying
service order form.

In the event of conflict between this DPA and the SCCs, the SCCs
prevail.

---

## Signatures

| Party | Name | Title | Date |
| --- | --- | --- | --- |
| Controller (Customer) | __________________ | __________________ | __________________ |
| Processor (Latvian A2 Exam Studio) | __________________ | __________________ | __________________ |
