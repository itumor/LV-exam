from __future__ import annotations

import hashlib
import hmac
import json
import tempfile
import time
from pathlib import Path
import unittest

from billing import BillingStore, FREE_EXAM_ID


def sign_webhook(payload: dict[str, object], secret: str, timestamp: int | None = None) -> tuple[bytes, str]:
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ts = timestamp or int(time.time())
    signed = f"{ts}.{body.decode('utf-8')}".encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return body, f"t={ts},v1={digest}"


class BillingStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "billing.sqlite3"
        self.store = BillingStore(self.db_path)
        self.learner_id = "learner-test-1"
        self.store.ensure_learner(self.learner_id, email="learner@example.com")

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_free_exam_is_consumed_once(self) -> None:
        first = self.store.consume_exam_access(self.learner_id, FREE_EXAM_ID)
        second = self.store.consume_exam_access(self.learner_id, FREE_EXAM_ID)

        self.assertTrue(first["allowed"])
        self.assertFalse(first["state"]["free_exam_available"])
        self.assertFalse(second["allowed"])
        state = self.store.get_state(self.learner_id)
        self.assertFalse(state["free_exam_available"])
        self.assertEqual(state["paid_attempts_remaining"], 0)

    def test_exam_pack_grants_attempts_and_ai_credits(self) -> None:
        event = {
            "id": "evt_pack_1",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_pack_1",
                    "customer": "cus_123",
                    "payment_intent": "pi_123",
                    "metadata": {
                        "learner_id": self.learner_id,
                        "product_key": "exam_pack",
                    },
                    "customer_details": {"email": "learner@example.com"},
                }
            },
        }
        result = self.store.process_stripe_event(event)
        duplicate = self.store.process_stripe_event(event)

        state = self.store.get_state(self.learner_id)
        self.assertEqual(result["status"], "granted")
        self.assertEqual(duplicate["status"], "duplicate")
        self.assertEqual(state["paid_attempts_remaining"], 5)
        self.assertEqual(state["ai_credits_remaining"], 5)

    def test_subscription_updates_are_idempotent(self) -> None:
        created = {
            "id": "evt_sub_created",
            "type": "customer.subscription.created",
            "data": {
                "object": {
                    "id": "sub_123",
                    "customer": "cus_456",
                    "status": "active",
                    "current_period_end": int(time.time()) + 86400,
                    "metadata": {"learner_id": self.learner_id, "product_key": "monthly_subscription"},
                }
            },
        }
        updated = {
            "id": "evt_sub_updated",
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "id": "sub_123",
                    "customer": "cus_456",
                    "status": "active",
                    "current_period_end": int(time.time()) + 172800,
                    "metadata": {"learner_id": self.learner_id, "product_key": "monthly_subscription"},
                }
            },
        }
        self.store.process_stripe_event(created)
        self.store.process_stripe_event(updated)

        state = self.store.get_state(self.learner_id)
        self.assertTrue(state["subscription_active"])
        self.assertEqual(state["paid_attempts_remaining"], 30)
        self.assertEqual(state["ai_credits_remaining"], 30)

    def test_refund_freezes_customer_entitlement(self) -> None:
        self.store.process_stripe_event(
            {
                "id": "evt_pack_for_refund",
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "id": "cs_refund_1",
                        "customer": "cus_refund",
                        "payment_intent": "pi_refund",
                        "metadata": {
                            "learner_id": self.learner_id,
                            "product_key": "single_exam",
                        },
                        "customer_details": {"email": "learner@example.com"},
                    }
                },
            }
        )
        refund = {
            "id": "evt_refund_1",
            "type": "charge.refunded",
            "data": {
                "object": {
                    "id": "ch_refund_1",
                    "customer": "cus_refund",
                    "payment_intent": "pi_refund",
                    "metadata": {"learner_id": self.learner_id},
                }
            },
        }
        self.store.process_stripe_event(refund)
        state = self.store.get_state(self.learner_id)
        self.assertTrue(state["frozen"])
        self.assertEqual(state["paid_attempts_remaining"], 0)

    def test_webhook_signature_verification(self) -> None:
        secret = "whsec_test_secret"
        payload, signature = sign_webhook(
            {
                "id": "evt_webhook_1",
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "id": "cs_webhook_1",
                        "customer": "cus_sig",
                        "payment_intent": "pi_sig",
                        "metadata": {
                            "learner_id": self.learner_id,
                            "product_key": "ai_credits",
                        },
                    }
                },
            },
            secret,
        )
        self.assertTrue(self.store.verify_webhook_signature(payload, signature, secret))
        result = self.store.handle_webhook(payload, signature, secret)
        self.assertEqual(result["status"], "granted")


if __name__ == "__main__":
    unittest.main()
