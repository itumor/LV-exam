# Billing — Stripe Tax, B2B invoicing, and self-serve refund

Owner: Platform / Billing
Last reviewed: 2026-05-23
Task: T-016 (EU paid-traffic risk gate for `release/2026-Q1`).

This document covers the EU VAT, B2B invoicing, and self-serve refund flows
that ship with [`billing.py`](../billing.py) and the
`/api/billing/*` endpoints in [`server.py`](../server.py).

## 1. Stripe Tax (EU VAT) on every checkout

Every checkout session — B2C or B2B, payment or subscription — is created
with Stripe Tax enabled. We never compute VAT ourselves.

The request body always includes:

```
automatic_tax[enabled]=true
customer_update[address]=auto
customer_update[name]=auto
customer_creation=always         # payment-mode sessions
```

* `automatic_tax[enabled]=true` makes Stripe resolve the buyer's country
  from the billing address Stripe collects during checkout and apply the
  correct EU VAT rate (or reverse-charge for valid B2B VAT IDs).
* `customer_update[address]=auto` / `customer_update[name]=auto` lets
  Stripe save the captured billing address/name on the resulting Customer,
  which is required for accurate cross-border tax determination and for
  hosted invoice generation.
* `customer_creation=always` is set on `payment` mode sessions so that a
  Customer object exists for `customer_update` to act on. Subscription
  mode always creates a Customer.

The mock-mode payload (`StripeClient.create_mock_checkout_session`)
mirrors this shape so frontend code and tests can rely on the same fields.

### Where it's enforced

* `billing.StripeClient.build_checkout_session_body` — the canonical
  builder used by every live or mock session.
* `tests/server/test_billing_tax.py` — asserts that the tax fields are
  present on every product/mode combination.

## 2. B2B invoicing (hosted PDF invoices)

When the client sets `metadata.b2b=true` and supplies a `business_address`
(and optionally a pre-collected `vat_id`), the checkout session is
extended with:

```
invoice_creation[enabled]=true
tax_id_collection[enabled]=true
customer_data[tax_id_data][0][type]=eu_vat   # only when vat_id is supplied
customer_data[tax_id_data][0][value]=<VAT>
metadata[b2b]=true
metadata[business_address_*]=<…>
```

* `invoice_creation` instructs Stripe to issue a **Stripe Hosted Invoice**
  (URL + PDF) as part of completing the session. We do **not** generate
  PDFs ourselves.
* `tax_id_collection` either pre-fills the buyer's VAT/Tax ID (when we
  already have it) or asks for it on the Stripe-hosted checkout page,
  enabling reverse-charge.
* When the webhook for `checkout.session.completed` arrives, the grant
  metadata stored in `entitlement_grants.metadata_json` includes:
  * `b2b: true`
  * `hosted_invoice_url` — link the buyer's finance team can open
  * `invoice_pdf` — direct download URL from Stripe
  * `invoice_id` — Stripe invoice object id

The frontend can render a "Download invoice" link from
`recent_activity[].metadata.hosted_invoice_url`.

### Required API payload (B2B)

`POST /api/billing/checkout-session`:

```json
{
  "learner_id": "acct_xxx",
  "product_key": "exam_pack",
  "email": "finance@firm.lv",
  "b2b": true,
  "business_address": {
    "company": "Acme SIA",
    "line1": "Brivibas 1",
    "city": "Riga",
    "postal_code": "LV-1010",
    "country": "LV"
  },
  "vat_id": "LV40000000000"   // optional; otherwise collected at checkout
}
```

`business_address` is **required** for B2B; the server rejects with
`400 Bad Request` otherwise.

## 3. Self-serve refund (EU 7-day window)

`POST /api/billing/refund` (authenticated):

```json
{ "checkout_session_id": "cs_test_..." }
```

The server **always** re-runs the eligibility checks. UI affordances are
convenience-only.

| Check | Source of truth | Failure response |
|---|---|---|
| Session belongs to the requesting account | `BillingStore.refund_eligibility` (`reason=wrong_user`) | `403 Forbidden` |
| Session exists in our ledger | (`reason=session_not_found`) | `404 Not Found` |
| Purchase is within `BILLING_REFUND_WINDOW_DAYS` (default `7`) | (`reason=window_expired`) | `409 Conflict` |
| No credits from this purchase have been consumed | (`reason=credits_consumed`) | `409 Conflict` |
| Not already refunded | (`reason=already_refunded`) | `409 Conflict` |

On success:

1. The server calls `StripeClient.create_refund(payment_intent=…)` for the
   full amount. If Stripe is in mock mode (no `STRIPE_SECRET_KEY`), a
   synthetic `re_mock_*` id is recorded but the ledger is still updated.
2. Every grant linked to the checkout session is marked revoked and the
   `refund_id` + `refund_reason` are stamped into `metadata_json`.
3. `200 OK` returns the new `billing_state` so the client can refresh.

If Stripe returns an error, no entitlement is changed and the client
receives `502 Bad Gateway`.

### Environment variables

| Name | Default | Purpose |
|---|---|---|
| `STRIPE_SECRET_KEY` | — | Live key; unset = mock mode (refund still revokes locally) |
| `BILLING_REFUND_WINDOW_DAYS` | `7` | Override the consumer refund window |

### Frontend behavior

The "Request refund" card on the billing page is rendered only when:

* The most recent non-free grant is < `REFUND_WINDOW_DAYS` (7) old, AND
* The learner still has unused paid attempts or AI credits.

The button POSTs to `/api/billing/refund`. The server re-validates every
condition, so UI tampering cannot bypass any of the rules above.

## 4. Tests

* `tests/server/test_billing_tax.py` — tax + B2B fields on every checkout.
* `tests/server/test_billing_refund.py` — eligibility, ledger revocation,
  HTTP status codes (200 / 403 / 404 / 409), Stripe SDK fully mocked.

## 5. Operator playbook (refund disputes)

1. Look up the checkout session id from the buyer's purchase confirmation
   email or from the `recent_activity` list in `/api/billing/state`.
2. Run `BillingStore.refund_eligibility` against the buyer's `learner_id`
   to confirm why the self-serve flow refused. The `reason` code is the
   audit trail.
3. If the buyer is outside the 7-day window or has consumed credits, the
   refund becomes a manual decision in Stripe Dashboard. **Always** mirror
   any manual Dashboard refund by running `BillingStore.mark_grants_refunded`
   so the ledger stays consistent.
