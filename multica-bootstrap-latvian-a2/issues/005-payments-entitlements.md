[Payments] Add Stripe Checkout, subscriptions, exam packs, and entitlements

Tasks:
1. Define Stripe products: single exam simulation, exam pack, monthly subscription, optional AI scoring credits.
2. Implement Stripe Checkout.
3. Implement entitlements: free exam access, paid exam access, remaining attempts, remaining AI-scored submissions.
4. Implement Stripe webhooks: payment succeeded, subscription created, renewed, canceled, refund, chargeback.
5. Add billing page and upgrade prompts after free exam completion.

Acceptance criteria:
- Free user can take exactly the configured free exam.
- Paid user gets correct exam pack/subscription entitlement.
- Webhook handling is idempotent and auditable.
- Refund/chargeback removes or freezes relevant entitlement.
- Tests use Stripe test mode fixtures or mocked webhook signatures.
