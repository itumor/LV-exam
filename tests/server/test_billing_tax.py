"""T-016: verify Stripe Tax + B2B invoice fields on every checkout session.

These tests exercise the body builder used by ``StripeClient.create_checkout_session``
and the mock session helper. The Stripe SDK is **never** contacted – we assert on
the form-encoded payload that would have been sent to Stripe so EU VAT and B2B
invoicing requirements remain wired up regardless of mode (live or mock).
"""
from __future__ import annotations

import unittest

from billing import DEFAULT_PRODUCTS, StripeClient


def _product(key: str):
    for product in DEFAULT_PRODUCTS:
        if product.key == key:
            return product
    raise AssertionError(f"Unknown product key {key}")


class CheckoutSessionTaxTests(unittest.TestCase):
    """Stripe Tax must be enabled on every checkout session we create."""

    def setUp(self) -> None:
        # Secret value is irrelevant – we only build the request body.
        self.client = StripeClient(secret_key="sk_test_dummy")

    def test_b2c_checkout_enables_automatic_tax_and_customer_update(self) -> None:
        body = self.client.build_checkout_session_body(
            product=_product("single_exam"),
            price_id="price_single",
            learner_id="learner_eu_1",
            email="buyer@example.eu",
            success_url="https://app.test/success",
            cancel_url="https://app.test/cancel",
            metadata={"learner_id": "learner_eu_1", "product_key": "single_exam"},
        )
        self.assertEqual(body["automatic_tax[enabled]"], "true")
        self.assertEqual(body["customer_update[address]"], "auto")
        self.assertEqual(body["customer_update[name]"], "auto")
        # Customer must be created so customer_update can resolve fields.
        self.assertEqual(body["customer_creation"], "always")
        self.assertEqual(body["customer_email"], "buyer@example.eu")
        # B2B fields must NOT be present on a plain B2C checkout.
        self.assertNotIn("invoice_creation[enabled]", body)
        self.assertNotIn("tax_id_collection[enabled]", body)

    def test_b2c_checkout_without_email_still_enables_tax(self) -> None:
        body = self.client.build_checkout_session_body(
            product=_product("exam_pack"),
            price_id="price_pack",
            learner_id="learner_eu_2",
            email=None,
            success_url="https://app.test/success",
            cancel_url="https://app.test/cancel",
            metadata={"learner_id": "learner_eu_2", "product_key": "exam_pack"},
        )
        self.assertEqual(body["automatic_tax[enabled]"], "true")
        # The customer_update pair must still be present so Stripe can populate
        # the buyer address once collected at checkout.
        self.assertEqual(body["customer_update[address]"], "auto")

    def test_subscription_checkout_enables_automatic_tax(self) -> None:
        body = self.client.build_checkout_session_body(
            product=_product("monthly_subscription"),
            price_id="price_sub",
            learner_id="learner_sub",
            email="sub@example.eu",
            success_url="https://app.test/success",
            cancel_url="https://app.test/cancel",
            metadata={"learner_id": "learner_sub", "product_key": "monthly_subscription"},
        )
        self.assertEqual(body["mode"], "subscription")
        self.assertEqual(body["automatic_tax[enabled]"], "true")
        self.assertEqual(body["customer_update[address]"], "auto")

    def test_b2b_checkout_enables_invoice_and_tax_id_collection(self) -> None:
        body = self.client.build_checkout_session_body(
            product=_product("exam_pack"),
            price_id="price_pack",
            learner_id="learner_b2b_1",
            email="finance@acme.lv",
            success_url="https://app.test/success",
            cancel_url="https://app.test/cancel",
            metadata={"learner_id": "learner_b2b_1", "product_key": "exam_pack", "b2b": "true"},
            b2b=True,
            business_address={"line1": "Brivibas 1", "city": "Riga", "country": "LV", "company": "Acme SIA"},
            vat_id="LV40000000000",
        )
        # B2B always preserves tax fields.
        self.assertEqual(body["automatic_tax[enabled]"], "true")
        # B2B-specific fields.
        self.assertEqual(body["invoice_creation[enabled]"], "true")
        self.assertEqual(body["tax_id_collection[enabled]"], "true")
        # Pre-filled VAT/Tax ID via customer_data.
        self.assertEqual(body["customer_data[tax_id_data][0][type]"], "eu_vat")
        self.assertEqual(body["customer_data[tax_id_data][0][value]"], "LV40000000000")
        # Business address echoed into metadata for audit / invoice ref.
        self.assertEqual(body["metadata[b2b]"], "true")
        self.assertEqual(body["metadata[business_address_line1]"], "Brivibas 1")
        self.assertEqual(body["metadata[business_address_city]"], "Riga")
        self.assertEqual(body["metadata[business_address_country]"], "LV")
        self.assertEqual(body["metadata[business_address_company]"], "Acme SIA")

    def test_b2b_checkout_without_vat_id_still_collects_via_checkout(self) -> None:
        body = self.client.build_checkout_session_body(
            product=_product("single_exam"),
            price_id="price_single",
            learner_id="learner_b2b_2",
            email="ops@school.lv",
            success_url="https://app.test/success",
            cancel_url="https://app.test/cancel",
            metadata={"learner_id": "learner_b2b_2", "product_key": "single_exam", "b2b": "true"},
            b2b=True,
            business_address={"line1": "Skola iela 5", "country": "LV"},
        )
        # tax_id_collection is what asks the buyer for their VAT/Tax ID on the
        # Stripe-hosted checkout page when we don't pre-fill it.
        self.assertEqual(body["tax_id_collection[enabled]"], "true")
        self.assertNotIn("customer_data[tax_id_data][0][value]", body)
        self.assertEqual(body["invoice_creation[enabled]"], "true")


class MockCheckoutSessionTests(unittest.TestCase):
    """Mock-mode checkout sessions must mirror the real Stripe payload shape."""

    def setUp(self) -> None:
        self.client = StripeClient(secret_key="")  # mock mode

    def test_mock_session_includes_automatic_tax_and_customer_update(self) -> None:
        session = self.client.create_mock_checkout_session(
            product=_product("single_exam"),
            learner_id="learner_mock_1",
            email="mock@example.eu",
            success_url="https://app.test/success",
            cancel_url="https://app.test/cancel",
        )
        self.assertTrue(session["automatic_tax"]["enabled"])
        self.assertEqual(session["customer_update"]["address"], "auto")
        self.assertEqual(session["customer_update"]["name"], "auto")
        # Sanity: no B2B fields on B2C.
        self.assertNotIn("invoice_creation", session)
        self.assertNotIn("tax_id_collection", session)

    def test_mock_b2b_session_includes_invoice_and_vat_fields(self) -> None:
        session = self.client.create_mock_checkout_session(
            product=_product("exam_pack"),
            learner_id="learner_mock_b2b",
            email="ops@firm.lv",
            success_url="https://app.test/success",
            cancel_url="https://app.test/cancel",
            b2b=True,
            business_address={"line1": "Centra 12", "country": "LV"},
            vat_id="LV40000000000",
        )
        self.assertEqual(session["metadata"]["b2b"], "true")
        self.assertTrue(session["invoice_creation"]["enabled"])
        self.assertTrue(session["tax_id_collection"]["enabled"])
        self.assertEqual(
            session["customer_data"]["tax_id_data"][0]["value"],
            "LV40000000000",
        )
        self.assertEqual(session["business_address"], {"line1": "Centra 12", "country": "LV"})


if __name__ == "__main__":
    unittest.main()
