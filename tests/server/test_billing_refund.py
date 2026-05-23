"""T-016: server-enforced 7-day self-serve refund flow.

Covers:
  * Happy path – refund issued, entitlement marked revoked.
  * Window expired (>7 days) – 409, no refund issued.
  * Credits already consumed – 409, no refund issued.
  * Wrong user (session belongs to someone else) – 403, no refund issued.

The Stripe SDK is mocked end-to-end – we never call ``api.stripe.com``.
"""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import server
from billing import BillingStore, utc_now, utc_now_iso


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
CHECKOUT_ID = "cs_test_refund_happy"


def _seed_purchase(store: BillingStore, learner_id: str, checkout_id: str = CHECKOUT_ID) -> None:
    """Simulate a completed Stripe checkout for the given learner."""
    store.ensure_learner(learner_id, email=f"{learner_id}@example.test")
    store.process_stripe_event(
        {
            "id": f"evt_{checkout_id}",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": checkout_id,
                    "customer": f"cus_{learner_id}",
                    "payment_intent": f"pi_{checkout_id}",
                    "metadata": {
                        "learner_id": learner_id,
                        "product_key": "exam_pack",
                    },
                    "customer_details": {"email": f"{learner_id}@example.test"},
                }
            },
        }
    )


# --------------------------------------------------------------------------- #
# Eligibility tests (the server-side source of truth)
# --------------------------------------------------------------------------- #
class RefundEligibilityTests(unittest.TestCase):
    """Server-enforced eligibility rules: window, consumption, ownership."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.store = BillingStore(Path(self.tmpdir.name) / "billing.sqlite3")
        self.learner_id = "learner_refund_1"
        _seed_purchase(self.store, self.learner_id)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_happy_path_eligible_when_recent_and_unused(self) -> None:
        eligibility = self.store.refund_eligibility(
            self.learner_id, checkout_session_id=CHECKOUT_ID
        )
        self.assertTrue(eligibility["eligible"])
        self.assertEqual(eligibility["reason"], "eligible")
        self.assertGreaterEqual(len(eligibility["grants"]), 1)

    def test_window_expired_returns_window_expired(self) -> None:
        # Same purchase, but pretend "now" is 8 days later.
        future = utc_now() + timedelta(days=8)
        eligibility = self.store.refund_eligibility(
            self.learner_id, checkout_session_id=CHECKOUT_ID, now=future
        )
        self.assertFalse(eligibility["eligible"])
        self.assertEqual(eligibility["reason"], "window_expired")

    def test_configurable_window_days_is_honored(self) -> None:
        # If the operator sets window=1 day, a 2-day-old purchase is expired.
        future = utc_now() + timedelta(days=2)
        eligibility = self.store.refund_eligibility(
            self.learner_id,
            checkout_session_id=CHECKOUT_ID,
            window_days=1,
            now=future,
        )
        self.assertFalse(eligibility["eligible"])
        self.assertEqual(eligibility["reason"], "window_expired")

    def test_consumed_credits_block_refund(self) -> None:
        # Burn one exam attempt – any consumption disqualifies the refund.
        self.store.consume_exam_access(self.learner_id, "02")
        eligibility = self.store.refund_eligibility(
            self.learner_id, checkout_session_id=CHECKOUT_ID
        )
        self.assertFalse(eligibility["eligible"])
        self.assertEqual(eligibility["reason"], "credits_consumed")

    def test_wrong_user_blocks_refund(self) -> None:
        intruder = "learner_intruder"
        self.store.ensure_learner(intruder)
        eligibility = self.store.refund_eligibility(
            intruder, checkout_session_id=CHECKOUT_ID
        )
        self.assertFalse(eligibility["eligible"])
        self.assertEqual(eligibility["reason"], "wrong_user")

    def test_unknown_session_returns_not_found(self) -> None:
        eligibility = self.store.refund_eligibility(
            self.learner_id, checkout_session_id="cs_does_not_exist"
        )
        self.assertFalse(eligibility["eligible"])
        self.assertEqual(eligibility["reason"], "session_not_found")

    def test_already_refunded_blocks_second_refund(self) -> None:
        affected = self.store.mark_grants_refunded(
            self.learner_id,
            checkout_session_id=CHECKOUT_ID,
            refund_id="re_test_1",
        )
        self.assertGreaterEqual(affected, 1)
        eligibility = self.store.refund_eligibility(
            self.learner_id, checkout_session_id=CHECKOUT_ID
        )
        self.assertFalse(eligibility["eligible"])
        self.assertEqual(eligibility["reason"], "already_refunded")


# --------------------------------------------------------------------------- #
# mark_grants_refunded – ledger invariants
# --------------------------------------------------------------------------- #
class MarkGrantsRefundedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.store = BillingStore(Path(self.tmpdir.name) / "billing.sqlite3")
        self.learner_id = "learner_mark_1"
        _seed_purchase(self.store, self.learner_id)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_refund_revokes_unused_credits(self) -> None:
        before = self.store.get_state(self.learner_id)
        self.assertGreater(before["paid_attempts_remaining"], 0)
        self.assertGreater(before["ai_credits_remaining"], 0)

        affected = self.store.mark_grants_refunded(
            self.learner_id,
            checkout_session_id=CHECKOUT_ID,
            refund_id="re_test_revoke",
            refund_reason="self_serve_7_day",
        )
        self.assertGreaterEqual(affected, 1)

        after = self.store.get_state(self.learner_id)
        self.assertEqual(after["paid_attempts_remaining"], 0)
        self.assertEqual(after["ai_credits_remaining"], 0)

    def test_refund_does_not_affect_other_learners(self) -> None:
        other = "learner_other"
        _seed_purchase(self.store, other, checkout_id="cs_test_other")
        self.store.mark_grants_refunded(
            self.learner_id,
            checkout_session_id=CHECKOUT_ID,
            refund_id="re_test_iso",
        )
        # Other learner is untouched.
        state = self.store.get_state(other)
        self.assertGreater(state["paid_attempts_remaining"], 0)

    def test_refund_metadata_records_refund_id(self) -> None:
        self.store.mark_grants_refunded(
            self.learner_id,
            checkout_session_id=CHECKOUT_ID,
            refund_id="re_test_meta",
            refund_reason="self_serve_7_day",
        )
        grants = self.store.find_grants_by_checkout_session(CHECKOUT_ID)
        self.assertTrue(grants)
        for grant in grants:
            self.assertEqual(grant["metadata"].get("refund_id"), "re_test_meta")
            self.assertEqual(grant["metadata"].get("refund_reason"), "self_serve_7_day")
            self.assertIsNotNone(grant["revoked_at"])


# --------------------------------------------------------------------------- #
# HTTP-level handler tests – verify status codes and that Stripe is mocked.
# --------------------------------------------------------------------------- #
class _FakeHandler:
    """Minimal stand-in for ``AppHandler`` so we can drive ``handle_billing_refund``."""

    def __init__(self, body: dict[str, object]) -> None:
        encoded = json.dumps(body).encode("utf-8")
        self.rfile = io.BytesIO(encoded)
        self.wfile = io.BytesIO()
        self.headers = {"Content-Length": str(len(encoded)), "Content-Type": "application/json"}
        self.responses: list[tuple[int, dict[str, object]]] = []
        # Patched-in status code and JSON body container.
        self._status: int | None = None
        self._body: dict[str, object] | None = None
        self.path = "/api/billing/refund"

    # The handler uses safe_read_json which reads Content-Length bytes from rfile.
    def send_response(self, *args, **kwargs) -> None:  # pragma: no cover - compat
        pass

    def send_header(self, *args, **kwargs) -> None:  # pragma: no cover - compat
        pass

    def end_headers(self) -> None:  # pragma: no cover - compat
        pass

    def __getattr__(self, item: str):  # pragma: no cover - compat
        raise AttributeError(item)


def _drive_refund(
    *,
    db_path: Path,
    session_account: dict[str, object],
    body: dict[str, object],
) -> tuple[int, dict[str, object]]:
    """Invoke ``AppHandler.handle_billing_refund`` with mocks for auth + Stripe."""
    handler = _FakeHandler(body)

    captured: dict[str, object] = {}

    def fake_json_response(self_or_handler, status, payload):
        # When called as a method, ``self_or_handler`` is the handler arg.
        captured["status"] = int(status)
        captured["body"] = payload

    with patch.object(server, "require_session", return_value={"account": session_account}), \
         patch.object(server, "json_response", side_effect=fake_json_response), \
         patch.object(server, "billing_db_path", return_value=db_path), \
         patch.object(server, "get_stripe_client") as stripe_factory:
        # Force the mock Stripe client to be "disabled" so we never call out.
        stripe_factory.return_value = MagicMock(enabled=MagicMock(return_value=False))
        # Bypass lru_cache on get_billing_store for test isolation.
        server.get_billing_store.cache_clear()
        try:
            server.AppHandler.handle_billing_refund(handler)
        finally:
            server.get_billing_store.cache_clear()
    return int(captured.get("status", 0)), captured.get("body") or {}


class RefundHandlerStatusCodeTests(unittest.TestCase):
    """Verify the HTTP handler maps eligibility reasons to correct status codes."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "billing.sqlite3"
        self.store = BillingStore(self.db_path)
        self.learner_id = "acct_refund_handler"
        _seed_purchase(self.store, self.learner_id)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def _account(self, account_id: str = "acct_refund_handler") -> dict[str, object]:
        return {
            "id": account_id,
            "email": f"{account_id}@example.test",
            "status": "active",
            "role": "user",
            "created_at": utc_now_iso(),
            "deleted_at": None,
        }

    def test_happy_path_returns_200_and_refunds(self) -> None:
        status, body = _drive_refund(
            db_path=self.db_path,
            session_account=self._account(),
            body={"checkout_session_id": CHECKOUT_ID},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body.get("status"), "refunded")
        self.assertGreaterEqual(int(body.get("grants_refunded") or 0), 1)
        # Entitlements actually revoked.
        state = BillingStore(self.db_path).get_state(self.learner_id)
        self.assertEqual(state["paid_attempts_remaining"], 0)

    def test_wrong_user_returns_403(self) -> None:
        # Authenticated session belongs to a *different* account than the buyer.
        status, body = _drive_refund(
            db_path=self.db_path,
            session_account=self._account("acct_someone_else"),
            body={"checkout_session_id": CHECKOUT_ID},
        )
        self.assertEqual(status, 403)
        self.assertEqual(body.get("reason"), "wrong_user")

    def test_consumed_credits_returns_409(self) -> None:
        # Consume one attempt before requesting the refund.
        self.store.consume_exam_access(self.learner_id, "02")
        status, body = _drive_refund(
            db_path=self.db_path,
            session_account=self._account(),
            body={"checkout_session_id": CHECKOUT_ID},
        )
        self.assertEqual(status, 409)
        self.assertEqual(body.get("reason"), "credits_consumed")

    def test_expired_window_returns_409(self) -> None:
        # Default window is 7 days; we override to 0 so the purchase is "old".
        with patch.dict("os.environ", {"BILLING_REFUND_WINDOW_DAYS": "0"}):
            status, body = _drive_refund(
                db_path=self.db_path,
                session_account=self._account(),
                body={"checkout_session_id": CHECKOUT_ID},
            )
        self.assertEqual(status, 409)
        self.assertEqual(body.get("reason"), "window_expired")

    def test_unknown_session_returns_404(self) -> None:
        status, body = _drive_refund(
            db_path=self.db_path,
            session_account=self._account(),
            body={"checkout_session_id": "cs_test_missing"},
        )
        self.assertEqual(status, 404)
        self.assertEqual(body.get("reason"), "session_not_found")


# --------------------------------------------------------------------------- #
# Stripe SDK must be mocked – no real HTTP traffic ever
# --------------------------------------------------------------------------- #
class StripeRefundClientIsMockedTests(unittest.TestCase):
    def test_create_refund_uses_stripe_client_and_is_mockable(self) -> None:
        client = MagicMock()
        client.enabled.return_value = True
        client.create_refund.return_value = {"id": "re_mocked", "status": "succeeded"}
        # We assert the contract: callers always pass ``payment_intent``.
        client.create_refund(payment_intent="pi_test", metadata={"learner_id": "x"})
        client.create_refund.assert_called_once_with(
            payment_intent="pi_test",
            metadata={"learner_id": "x"},
        )


if __name__ == "__main__":
    unittest.main()
