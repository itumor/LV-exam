---
name: latvian-a2-auth-accounts
description: Implement authentication, learner profiles, account dashboard, privacy flows, and auth webhook sync for the exam simulator.
---

# Latvian A2 Auth Accounts

Support account creation/login, learner profile fields, exam target date, attempt dashboard, latest score, skill progress, billing/entitlement status, account deletion/export, and protected API routes. Never expose secret keys client-side. Webhooks must verify signatures and be idempotent. Keep public marketing/pricing pages accessible while protecting paid exam and dashboard routes.
