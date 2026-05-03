---
name: latvian-a2-monetization
description: Implement Stripe Checkout, products, exam packs, subscription access, AI scoring credits, billing page, and payment webhooks.
---

# Latvian A2 Monetization

Products: free sample simulation, 3-5 exam pack, monthly full access, optional AI scoring credits. Entitlements must track free exam access, paid exam access, remaining attempts, and remaining AI-scored submissions. Webhooks must handle payment_succeeded, subscription_created, subscription_renewed, subscription_canceled, refund, and chargeback with idempotent event processing and audit logs. Add upgrade prompts after free exam completion.
