"""Billing routes (T-020 / T-020b).

Owns the billing + Stripe endpoint **handler bodies**. The dispatch
(``self.path == "/api/billing/..."`` branches in
:class:`server_app.core.AppHandler.do_POST`) still calls into this
module so the route literals remain visible to the modularisation
audit, but every byte of business logic for these endpoints lives
here.

Routes owned (POST handler bodies live in this module):

* ``POST /api/billing/checkout-session`` — Stripe / mock checkout session
* ``POST /api/billing/consume-exam``     — entitlement consumption (exam unlock)
* ``POST /api/billing/consume-ai-credit``— entitlement consumption (AI credit)
* ``POST /api/billing/refund``           — self-serve refund (T-016)
* ``POST /api/stripe/webhook``           — Stripe webhook receiver

The GET routes (`/api/billing/config`, `/api/billing/state`,
`/api/billing/audit`) remain dispatched inline in
:meth:`AppHandler.do_GET` for now — they were not in the T-020b
scope of "route bodies" because they fit in <30 lines each. They are
still listed in ``ROUTES`` below so the audit list stays accurate.

Each handler function takes a single ``handler`` parameter (the live
``AppHandler`` instance) and returns ``None`` — they write the HTTP
response via the same ``json_response`` helpers the inline versions
used. The signature mirrors the pattern established by the T-037 /
T-043 monkey-patch hooks in :mod:`server_app.core`.
"""

from __future__ import annotations

import os
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

# Import the module (not symbols) so that
# ``patch.object(server_app.core, "json_response", ...)`` — i.e. the same
# pattern used by every existing test under tests/server/ — reaches the
# reference site here. Direct ``from server_app.core import json_response``
# binds a *local* name at import time and bypasses unittest.mock patches.
from server_app import core as _core

# Re-export the legacy-named symbols for code that imports them from this
# module (e.g. ``from server_app.routes.billing import get_billing_store``).
# These names mirror the names also re-exported via __all__ below.
DEFAULT_PRODUCTS = _core.DEFAULT_PRODUCTS
get_billing_store = _core.get_billing_store
get_product_price_id = _core.get_product_price_id
get_stripe_client = _core.get_stripe_client
stripe_webhook_secret = _core.stripe_webhook_secret

if TYPE_CHECKING:  # pragma: no cover - typing only
    from server_app.core import AppHandler


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


# ---------------------------------------------------------------------------
# POST handler bodies (peeled from server_app/core.py — T-020b).
# ---------------------------------------------------------------------------


def handle_checkout_session(handler: "AppHandler") -> None:
    """POST ``/api/billing/checkout-session``.

    Validates payload, ensures the redirect URLs stay on-site, then
    delegates to either the real Stripe client or the mock client
    depending on whether Stripe is configured.
    """

    try:
        payload = _core.safe_read_json(handler)
        learner_id = str(payload.get("learner_id", "")).strip()
        product_key = str(payload.get("product_key", "")).strip()
        email = str(payload.get("email", "")).strip() or None
        # T-016: B2B invoicing flag.
        b2b = bool(payload.get("b2b"))
        business_address_raw = payload.get("business_address") or {}
        business_address: dict[str, str] = {}
        if isinstance(business_address_raw, dict):
            for key in ("line1", "line2", "city", "postal_code", "country", "company"):
                value = business_address_raw.get(key)
                if value:
                    business_address[key] = str(value).strip()
        vat_id_raw = payload.get("vat_id")
        vat_id = str(vat_id_raw).strip() if vat_id_raw else None
        _base = _core.request_base_url(handler)
        success_url = (
            str(payload.get("success_url", "")).strip()
            or f"{_base}/latvian-a2-exam-app/?view=billing&checkout=success"
        )
        cancel_url = (
            str(payload.get("cancel_url", "")).strip()
            or f"{_base}/latvian-a2-exam-app/?view=billing&checkout=cancel"
        )
        for _url in (success_url, cancel_url):
            if not _url.startswith(_base + "/") and _url != _base:
                raise ValueError("Redirect URL must be on this site.")
        if not learner_id:
            raise ValueError("learner_id is required.")
        if not product_key:
            raise ValueError("product_key is required.")
        if b2b and not business_address:
            raise ValueError("business_address is required for B2B checkouts.")
        store = _core.get_billing_store()
        learner = store.ensure_learner(learner_id, email=email)
        product = next(
            (item for item in _core.DEFAULT_PRODUCTS if item.key == product_key), None
        )
        if not product:
            raise ValueError("Unknown product_key.")
        price_id = _core.get_product_price_id(product_key)
        extra_metadata: dict[str, str] = {
            "learner_id": learner_id,
            "product_key": product_key,
        }
        if b2b:
            extra_metadata["b2b"] = "true"
        client = _core.get_stripe_client()
        if client.enabled():
            if not price_id:
                raise ValueError(f"Missing Stripe price ID for {product_key}.")
            session = client.create_checkout_session(
                product=product,
                price_id=price_id,
                learner_id=learner_id,
                email=email,
                success_url=success_url,
                cancel_url=cancel_url,
                metadata=extra_metadata,
                b2b=b2b,
                business_address=business_address or None,
                vat_id=vat_id,
            )
            _core.json_response(
                handler,
                HTTPStatus.OK,
                {
                    "mode": "stripe",
                    "learner": learner,
                    "product": product.key,
                    "b2b": b2b,
                    "checkout_url": session.get("url"),
                    "session": session,
                },
            )
            return

        session = client.create_mock_checkout_session(
            product=product,
            learner_id=learner_id,
            email=email,
            success_url=success_url,
            cancel_url=cancel_url,
            b2b=b2b,
            business_address=business_address or None,
            vat_id=vat_id,
        )
        _core.json_response(
            handler,
            HTTPStatus.OK,
            {
                "mode": "mock",
                "learner": learner,
                "product": product.key,
                "b2b": b2b,
                "checkout_url": session.get("url"),
                "session": session,
            },
        )
    except Exception as error:  # noqa: BLE001 - keep API responses JSON.
        _core.capture_exception(error)
        _core.log_event("error", "checkout_session_error", error=type(error).__name__)
        _core.json_response(handler, HTTPStatus.BAD_REQUEST, {"error": str(error)})


def handle_consume_exam(handler: "AppHandler") -> None:
    """POST ``/api/billing/consume-exam`` — exam-unlock entitlement burn."""

    try:
        payload = _core.safe_read_json(handler)
        learner_id = str(payload.get("learner_id", "")).strip()
        exam_id = str(payload.get("exam_id", "")).strip()
        if not learner_id:
            raise ValueError("learner_id is required.")
        if not exam_id:
            raise ValueError("exam_id is required.")
        store = _core.get_billing_store()
        store.ensure_learner(learner_id)
        result = store.consume_exam_access(
            learner_id,
            exam_id,
            source_reference=str(payload.get("source_reference", "")).strip()
            or None,
            source_event_id=str(payload.get("source_event_id", "")).strip() or None,
        )
        status = HTTPStatus.OK if result["allowed"] else HTTPStatus.PAYMENT_REQUIRED
        _core.json_response(handler, status, result)
    except Exception as error:  # noqa: BLE001 - keep API responses JSON.
        _core.capture_exception(error)
        _core.log_event("error", "consume_exam_error", error=type(error).__name__)
        _core.json_response(handler, HTTPStatus.BAD_REQUEST, {"error": str(error)})


def handle_consume_ai_credit(handler: "AppHandler") -> None:
    """POST ``/api/billing/consume-ai-credit`` — AI-credit entitlement burn."""

    try:
        payload = _core.safe_read_json(handler)
        learner_id = str(payload.get("learner_id", "")).strip()
        if not learner_id:
            raise ValueError("learner_id is required.")
        store = _core.get_billing_store()
        store.ensure_learner(learner_id)
        result = store.consume_ai_credit(
            learner_id,
            source_reference=str(payload.get("source_reference", "")).strip()
            or None,
            source_event_id=str(payload.get("source_event_id", "")).strip() or None,
        )
        status = HTTPStatus.OK if result["allowed"] else HTTPStatus.PAYMENT_REQUIRED
        _core.json_response(handler, status, result)
    except Exception as error:  # noqa: BLE001 - keep API responses JSON.
        _core.capture_exception(error)
        _core.log_event("error", "consume_ai_credit_error", error=type(error).__name__)
        _core.json_response(handler, HTTPStatus.BAD_REQUEST, {"error": str(error)})


def handle_stripe_webhook(handler: "AppHandler") -> None:
    """POST ``/api/stripe/webhook`` — verifies the Stripe signature."""

    try:
        payload = _core.safe_read_raw_body(handler)
        secret = _core.stripe_webhook_secret()
        if not secret:
            _core.json_response(handler, HTTPStatus.BAD_REQUEST, {"error": "Webhook not configured."})
            return
        signature = handler.headers.get("Stripe-Signature")
        store = _core.get_billing_store()
        result = store.handle_webhook(payload, signature, secret)
        _core.json_response(handler, HTTPStatus.OK, {"status": "ok", "result": result})
    except ValueError as error:
        _core.log_event("warning", "stripe_webhook_bad_signature", error=str(error))
        _core.json_response(handler, HTTPStatus.BAD_REQUEST, {"error": str(error)})
    except Exception as error:  # noqa: BLE001 - keep API responses JSON.
        _core.capture_exception(error)
        _core.log_event("error", "stripe_webhook_error", error=type(error).__name__)
        _core.json_response(handler, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Internal error."})


def handle_billing_refund(handler: "AppHandler") -> None:
    """POST ``/api/billing/refund`` — T-016 self-serve 7-day refund.

    Authenticated POST: validates ownership, window, and unused-credits
    server-side, then issues a Stripe refund and revokes the linked
    entitlement grants. UI affordances are convenience-only; the source
    of truth is this endpoint.
    """

    try:
        session = _core.require_session(handler)
    except PermissionError:
        _core.json_response(handler, HTTPStatus.UNAUTHORIZED, {"error": "Authentication required."})
        return
    try:
        payload = _core.safe_read_json(handler)
        checkout_session_id = str(payload.get("checkout_session_id", "")).strip()
        if not checkout_session_id:
            raise ValueError("checkout_session_id is required.")
        learner_id = session["account"]["id"]
        window_days = int(os.getenv("BILLING_REFUND_WINDOW_DAYS", "7"))
        store = _core.get_billing_store()
        eligibility = store.refund_eligibility(
            learner_id,
            checkout_session_id=checkout_session_id,
            window_days=window_days,
        )
        if not eligibility["eligible"]:
            if eligibility["reason"] == "wrong_user":
                _core.json_response(handler, HTTPStatus.FORBIDDEN, eligibility)
            elif eligibility["reason"] == "session_not_found":
                _core.json_response(handler, HTTPStatus.NOT_FOUND, eligibility)
            elif eligibility["reason"] in {"window_expired", "credits_consumed", "already_refunded"}:
                _core.json_response(handler, HTTPStatus.CONFLICT, eligibility)
            else:
                _core.json_response(handler, HTTPStatus.CONFLICT, eligibility)
            _core.log_event(
                "warning",
                "billing_refund_rejected",
                reason=eligibility["reason"],
                learner_id=learner_id,
            )
            return

        client = _core.get_stripe_client()
        payment_reference = eligibility.get("payment_reference")
        refund_payload: dict[str, Any] = {}
        if client.enabled() and payment_reference:
            try:
                refund_payload = client.create_refund(
                    payment_intent=payment_reference,
                    metadata={"checkout_session_id": checkout_session_id, "learner_id": learner_id},
                )
            except Exception as stripe_error:  # noqa: BLE001 - surface as 502.
                _core.capture_exception(stripe_error)
                _core.log_event(
                    "error",
                    "billing_refund_stripe_error",
                    error=type(stripe_error).__name__,
                    learner_id=learner_id,
                )
                _core.json_response(
                    handler,
                    HTTPStatus.BAD_GATEWAY,
                    {"error": "Stripe refund failed. No entitlements changed."},
                )
                return
        else:
            # Mock/test mode: still revoke entitlements so the DoD holds.
            refund_payload = {
                "id": f"re_mock_{checkout_session_id}",
                "status": "mock_succeeded",
                "amount_refunded": None,
            }

        affected = store.mark_grants_refunded(
            learner_id,
            checkout_session_id=checkout_session_id,
            refund_id=refund_payload.get("id"),
            refund_reason="self_serve_7_day",
        )
        _core.log_event(
            "info",
            "billing_refund_issued",
            learner_id=learner_id,
            checkout_session_id=checkout_session_id,
            grants_refunded=affected,
            stripe_refund_id=refund_payload.get("id"),
        )
        _core.json_response(
            handler,
            HTTPStatus.OK,
            {
                "status": "refunded",
                "checkout_session_id": checkout_session_id,
                "grants_refunded": affected,
                "refund": refund_payload,
                "billing_state": store.get_state(learner_id),
            },
        )
    except ValueError as error:
        _core.json_response(handler, HTTPStatus.BAD_REQUEST, {"error": str(error)})
    except Exception as error:  # noqa: BLE001 - keep API responses JSON.
        _core.capture_exception(error)
        _core.log_event("error", "billing_refund_error", error=type(error).__name__)
        _core.json_response(handler, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Internal error."})


__all__ = [
    "ROUTES",
    "get_billing_store",
    "get_product_price_id",
    "get_stripe_client",
    "handle_billing_refund",
    "handle_checkout_session",
    "handle_consume_ai_credit",
    "handle_consume_exam",
    "handle_stripe_webhook",
    "stripe_webhook_secret",
]
