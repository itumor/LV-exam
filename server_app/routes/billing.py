"""Billing routes (T-020).

Covers Stripe checkout, entitlement consumption, refund (T-016), and the
Stripe webhook receiver. The endpoint bodies are implemented as methods
on :class:`server_app.core.AppHandler` (``handle_checkout_session``,
``handle_consume_exam``, etc.) — they are exposed here for ownership.
"""

from __future__ import annotations

from server_app.core import (  # noqa: F401
    get_billing_store,
    get_product_price_id,
    get_stripe_client,
    stripe_webhook_secret,
)

ROUTES: list[tuple[str, str]] = [
    ("GET", "/api/billing/config"),
    ("GET", "/api/billing/state"),
    ("GET", "/api/billing/audit"),
    ("POST", "/api/billing/checkout-session"),
    ("POST", "/api/billing/consume-exam"),
    ("POST", "/api/billing/consume-ai-credit"),
    ("POST", "/api/billing/refund"),
    ("POST", "/api/stripe/webhook"),
]

__all__ = [
    "ROUTES",
    "get_billing_store",
    "get_product_price_id",
    "get_stripe_client",
    "stripe_webhook_secret",
]
