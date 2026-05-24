"""T-041 — Institutional seat licensing + bulk voucher tests.

Covers the six deliverable test categories called out in the T-041 plan:

1. ``create_org`` consumes one seat for the owner.
2. ``invite_member`` issues a single voucher; ``create_bulk_vouchers``
   issues N at once and enforces the ``MAX_BULK_COUNT`` cap.
3. Seat-cap enforcement: redemption is rejected once ``used_seats``
   equals ``max_seats``.
4. Single-use voucher: a code that has been redeemed cannot be
   redeemed a second time.
5. Expiry: ``expires_at`` in the past returns ``voucher_expired``.
6. Owner permissions: invite + bulk are rejected for non-owner.
7. T-024 entitlement extension: an active org member passes the
   ``exam_unlock`` / ``ai_credit`` gates without a personal Stripe
   grant.
"""

from __future__ import annotations

import os
import secrets
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import server  # noqa: F401  - package import side-effects
from server_app import core as _core
from server_app.services import institutional as inst_mod
from server_app.services.entitlements import (
    EntitlementError,
    require_entitlement,
)


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        )
    )


def _past_iso(*, hours: int = 1) -> str:
    return (
        (datetime.now(timezone.utc) - timedelta(hours=hours))
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _future_iso(*, hours: int = 1) -> str:
    return (
        (datetime.now(timezone.utc) + timedelta(hours=hours))
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _insert_account(conn: sqlite3.Connection, *, email: str) -> str:
    account_id = f"acct_{secrets.token_hex(6)}"
    conn.execute(
        """
        INSERT INTO accounts (
            id, email, password_salt, password_hash, status,
            created_at, deleted_at, role
        ) VALUES (?, ?, 'salt', 'hash', 'active', ?, NULL, 'user')
        """,
        (account_id, email, _now_iso()),
    )
    return account_id


class _InstitutionalTestBase(unittest.TestCase):
    """Shared fixture: isolated SQLite DB pointed at by AUTH_DB_PATH."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "auth.sqlite3"
        self.billing_path = Path(self.tmpdir.name) / "billing.sqlite3"
        self.auth_patch = patch.object(_core, "AUTH_DB_PATH", self.db_path)
        self.env_patch = patch.dict(
            os.environ,
            {
                "AUTH_DB_PATH": str(self.db_path),
                "BILLING_DB_PATH": str(self.billing_path),
            },
        )
        self.auth_patch.start()
        self.env_patch.start()
        _core.init_auth_store()
        with _core.db_connection() as conn:
            inst_mod.init_institutional_tables(conn)

    def tearDown(self) -> None:
        # Drop the cached BillingStore so the next test's BILLING_DB_PATH
        # is respected (T-041 entitlement extension would otherwise hold
        # on to this test's tmpdir handle, which gets cleaned up next).
        try:
            _core.get_billing_store.cache_clear()
        except AttributeError:  # pragma: no cover - defensive
            pass
        self.env_patch.stop()
        self.auth_patch.stop()
        try:
            _core.get_billing_store.cache_clear()
        except AttributeError:  # pragma: no cover - defensive
            pass
        self.tmpdir.cleanup()

    def _create_account(self, email: str) -> str:
        with _core.db_connection() as conn:
            return _insert_account(conn, email=email)


class CreateOrgTests(_InstitutionalTestBase):
    def test_create_org_consumes_one_seat_for_owner(self) -> None:
        owner = self._create_account("owner@example.test")
        org = inst_mod.create_org("Acme Inc", owner, max_seats=5)
        self.assertEqual(org["name"], "Acme Inc")
        self.assertEqual(org["owner_account_id"], owner)
        self.assertEqual(org["max_seats"], 5)
        self.assertEqual(org["used_seats"], 1)
        self.assertEqual(org["status"], "active")
        self.assertTrue(org["id"].startswith("org_"))

    def test_owner_is_recorded_as_active_member_with_owner_role(self) -> None:
        owner = self._create_account("owner@example.test")
        org = inst_mod.create_org("Acme Inc", owner, max_seats=2)
        seats = inst_mod.list_seats(org["id"])
        self.assertEqual(len(seats["members"]), 1)
        self.assertEqual(seats["members"][0]["account_id"], owner)
        self.assertEqual(seats["members"][0]["role"], "owner")
        self.assertEqual(seats["members"][0]["status"], "active")

    def test_create_org_rejects_zero_seats(self) -> None:
        owner = self._create_account("owner@example.test")
        with self.assertRaises(inst_mod.InstitutionalError) as ctx:
            inst_mod.create_org("Bad Org", owner, max_seats=0)
        self.assertEqual(ctx.exception.code, "org_max_seats_invalid")

    def test_create_org_rejects_missing_name(self) -> None:
        owner = self._create_account("owner@example.test")
        with self.assertRaises(inst_mod.InstitutionalError) as ctx:
            inst_mod.create_org("  ", owner, max_seats=3)
        self.assertEqual(ctx.exception.code, "org_name_required")

    def test_account_has_active_seat_returns_true_for_owner(self) -> None:
        owner = self._create_account("owner@example.test")
        inst_mod.create_org("Acme Inc", owner, max_seats=2)
        self.assertTrue(inst_mod.account_has_active_seat(owner))


class InviteAndBulkTests(_InstitutionalTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.owner = self._create_account("owner@example.test")
        self.org = inst_mod.create_org("Acme Inc", self.owner, max_seats=10)

    def test_invite_member_issues_voucher(self) -> None:
        voucher = inst_mod.invite_member(
            self.org["id"],
            actor_account_id=self.owner,
            invite_email="invitee@acme.test",
        )
        self.assertEqual(voucher["org_id"], self.org["id"])
        self.assertEqual(voucher["invite_email"], "invitee@acme.test")
        self.assertIsNone(voucher["redeemed_at"])
        self.assertIsNone(voucher["redeemed_by"])
        self.assertIn("-", voucher["code"])
        self.assertEqual(len(voucher["code"]), 13)  # 6 + 1 + 6

    def test_invite_member_rejects_invalid_email(self) -> None:
        with self.assertRaises(inst_mod.InstitutionalError) as ctx:
            inst_mod.invite_member(
                self.org["id"],
                actor_account_id=self.owner,
                invite_email="not-an-email",
            )
        self.assertEqual(ctx.exception.code, "invite_email_invalid")

    def test_create_bulk_vouchers_n_unique_codes(self) -> None:
        records = inst_mod.create_bulk_vouchers(
            self.org["id"], count=20, actor_account_id=self.owner
        )
        self.assertEqual(len(records), 20)
        codes = [r["code"] for r in records]
        self.assertEqual(len(set(codes)), 20)
        for r in records:
            self.assertIsNone(r["invite_email"])
            self.assertIsNone(r["redeemed_at"])

    def test_create_bulk_vouchers_rejects_too_large(self) -> None:
        with self.assertRaises(inst_mod.InstitutionalError) as ctx:
            inst_mod.create_bulk_vouchers(
                self.org["id"],
                count=inst_mod.MAX_BULK_COUNT + 1,
                actor_account_id=self.owner,
            )
        self.assertEqual(ctx.exception.code, "bulk_count_too_large")

    def test_create_bulk_vouchers_rejects_zero(self) -> None:
        with self.assertRaises(inst_mod.InstitutionalError) as ctx:
            inst_mod.create_bulk_vouchers(
                self.org["id"], count=0, actor_account_id=self.owner
            )
        self.assertEqual(ctx.exception.code, "bulk_count_invalid")


class OwnerPermissionTests(_InstitutionalTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.owner = self._create_account("owner@example.test")
        self.outsider = self._create_account("outsider@example.test")
        self.org = inst_mod.create_org("Acme Inc", self.owner, max_seats=5)

    def test_invite_rejected_for_non_owner(self) -> None:
        with self.assertRaises(inst_mod.InstitutionalError) as ctx:
            inst_mod.invite_member(
                self.org["id"], actor_account_id=self.outsider
            )
        self.assertEqual(ctx.exception.code, "org_owner_required")
        self.assertEqual(ctx.exception.status_code, 403)

    def test_bulk_vouchers_rejected_for_non_owner(self) -> None:
        with self.assertRaises(inst_mod.InstitutionalError) as ctx:
            inst_mod.create_bulk_vouchers(
                self.org["id"], count=5, actor_account_id=self.outsider
            )
        self.assertEqual(ctx.exception.code, "org_owner_required")

    def test_invite_rejected_for_unknown_org(self) -> None:
        with self.assertRaises(inst_mod.InstitutionalError) as ctx:
            inst_mod.invite_member(
                "org_does_not_exist", actor_account_id=self.owner
            )
        self.assertEqual(ctx.exception.code, "org_not_found")
        self.assertEqual(ctx.exception.status_code, 404)


class RedeemVoucherTests(_InstitutionalTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.owner = self._create_account("owner@example.test")
        self.alice = self._create_account("alice@example.test")
        self.bob = self._create_account("bob@example.test")
        self.org = inst_mod.create_org("Acme Inc", self.owner, max_seats=2)

    def test_redeem_voucher_consumes_seat_and_adds_member(self) -> None:
        voucher = inst_mod.invite_member(
            self.org["id"], actor_account_id=self.owner
        )
        result = inst_mod.redeem_voucher(voucher["code"], self.alice)
        self.assertEqual(result["org_id"], self.org["id"])
        self.assertEqual(result["account_id"], self.alice)
        org = inst_mod.get_org(self.org["id"])
        self.assertEqual(org["used_seats"], 2)
        self.assertTrue(inst_mod.account_has_active_seat(self.alice))

    def test_voucher_is_single_use(self) -> None:
        voucher = inst_mod.invite_member(
            self.org["id"], actor_account_id=self.owner
        )
        inst_mod.redeem_voucher(voucher["code"], self.alice)
        with self.assertRaises(inst_mod.InstitutionalError) as ctx:
            inst_mod.redeem_voucher(voucher["code"], self.bob)
        self.assertEqual(ctx.exception.code, "voucher_already_redeemed")
        self.assertEqual(ctx.exception.status_code, 409)
        # Bob has no seat as a result of the rejected redemption.
        self.assertFalse(inst_mod.account_has_active_seat(self.bob))

    def test_expired_voucher_is_rejected(self) -> None:
        voucher = inst_mod.invite_member(
            self.org["id"],
            actor_account_id=self.owner,
            expires_at=_past_iso(hours=1),
        )
        with self.assertRaises(inst_mod.InstitutionalError) as ctx:
            inst_mod.redeem_voucher(voucher["code"], self.alice)
        self.assertEqual(ctx.exception.code, "voucher_expired")
        self.assertEqual(ctx.exception.status_code, 410)
        org = inst_mod.get_org(self.org["id"])
        self.assertEqual(org["used_seats"], 1)  # only owner

    def test_voucher_with_future_expiry_succeeds(self) -> None:
        voucher = inst_mod.invite_member(
            self.org["id"],
            actor_account_id=self.owner,
            expires_at=_future_iso(hours=24),
        )
        inst_mod.redeem_voucher(voucher["code"], self.alice)
        self.assertTrue(inst_mod.account_has_active_seat(self.alice))

    def test_seat_cap_blocks_extra_redemption(self) -> None:
        # max_seats=2, owner already takes 1. Alice takes the second
        # via voucher_a; Bob's redemption of voucher_b must fail.
        voucher_a = inst_mod.invite_member(
            self.org["id"], actor_account_id=self.owner
        )
        voucher_b = inst_mod.invite_member(
            self.org["id"], actor_account_id=self.owner
        )
        inst_mod.redeem_voucher(voucher_a["code"], self.alice)
        with self.assertRaises(inst_mod.InstitutionalError) as ctx:
            inst_mod.redeem_voucher(voucher_b["code"], self.bob)
        self.assertEqual(ctx.exception.code, "org_seat_cap_reached")
        self.assertEqual(ctx.exception.status_code, 409)
        # The voucher is NOT marked redeemed on a cap failure.
        org = inst_mod.get_org(self.org["id"])
        self.assertEqual(org["used_seats"], 2)
        # voucher_b is still unused, so it remains redeemable once
        # capacity opens (or the cap is raised).

    def test_redeem_unknown_code_returns_404(self) -> None:
        with self.assertRaises(inst_mod.InstitutionalError) as ctx:
            inst_mod.redeem_voucher("DOES-NOT-EXIST", self.alice)
        self.assertEqual(ctx.exception.code, "voucher_unknown")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_double_redeem_by_same_account_is_blocked(self) -> None:
        # Use a larger org so the membership-uniqueness check fires
        # before the seat-cap check (which would otherwise mask it).
        owner2 = self._create_account("owner2@example.test")
        big_org = inst_mod.create_org("Wide Org", owner2, max_seats=10)
        v1 = inst_mod.invite_member(big_org["id"], actor_account_id=owner2)
        v2 = inst_mod.invite_member(big_org["id"], actor_account_id=owner2)
        inst_mod.redeem_voucher(v1["code"], self.alice)
        with self.assertRaises(inst_mod.InstitutionalError) as ctx:
            inst_mod.redeem_voucher(v2["code"], self.alice)
        self.assertEqual(ctx.exception.code, "member_already_active")


class EntitlementExtensionTests(_InstitutionalTestBase):
    """T-024 extension: active org member passes paid-tier gates."""

    def test_member_with_active_seat_passes_exam_unlock(self) -> None:
        owner = self._create_account("owner@example.test")
        alice = self._create_account("alice@example.test")
        org = inst_mod.create_org("Acme Inc", owner, max_seats=3)
        voucher = inst_mod.invite_member(org["id"], actor_account_id=owner)
        # Before redemption Alice has only the free attempt.
        self.assertTrue(require_entitlement(alice, "exam_unlock"))
        # Consume Alice's free attempt so the gate would normally fail.
        store = _core.get_billing_store()
        _core.get_billing_store.cache_clear()
        store = _core.get_billing_store()
        store.ensure_learner(alice)
        from billing import FREE_EXAM_ID

        store.consume_exam_access(alice, FREE_EXAM_ID)
        with self.assertRaises(EntitlementError):
            require_entitlement(alice, "ai_credit")
        # Redeem the voucher — Alice becomes an active org member.
        inst_mod.redeem_voucher(voucher["code"], alice)
        _core.get_billing_store.cache_clear()
        # Now both gates pass via the institutional extension.
        self.assertTrue(require_entitlement(alice, "exam_unlock"))
        self.assertTrue(require_entitlement(alice, "ai_credit"))

    def test_revoked_member_does_not_have_active_seat(self) -> None:
        owner = self._create_account("owner@example.test")
        alice = self._create_account("alice@example.test")
        org = inst_mod.create_org("Acme Inc", owner, max_seats=3)
        voucher = inst_mod.invite_member(org["id"], actor_account_id=owner)
        inst_mod.redeem_voucher(voucher["code"], alice)
        self.assertTrue(inst_mod.account_has_active_seat(alice))
        # Manually flip the membership to revoked; the seat helper must
        # immediately stop returning True.
        with _core.db_connection() as conn:
            conn.execute(
                "UPDATE org_members SET status = 'revoked', revoked_at = ? "
                "WHERE org_id = ? AND account_id = ?",
                (_now_iso(), org["id"], alice),
            )
            conn.commit()
        self.assertFalse(inst_mod.account_has_active_seat(alice))

    def test_inactive_org_disables_member_seat(self) -> None:
        owner = self._create_account("owner@example.test")
        alice = self._create_account("alice@example.test")
        org = inst_mod.create_org("Acme Inc", owner, max_seats=3)
        voucher = inst_mod.invite_member(org["id"], actor_account_id=owner)
        inst_mod.redeem_voucher(voucher["code"], alice)
        with _core.db_connection() as conn:
            conn.execute(
                "UPDATE organizations SET status = 'suspended', updated_at = ? "
                "WHERE id = ?",
                (_now_iso(), org["id"]),
            )
            conn.commit()
        self.assertFalse(inst_mod.account_has_active_seat(alice))


class StripeSubscriptionBuilderTests(unittest.TestCase):
    """Pure-function tests for the seat-based Stripe checkout body."""

    def test_body_contains_org_metadata_and_quantity(self) -> None:
        body = inst_mod.build_seat_subscription_body(
            org_id="org_abc",
            price_id="price_seat_42",
            quantity=25,
            success_url="https://app.example/orgs/org_abc?ok=1",
            cancel_url="https://app.example/orgs/org_abc?cancel=1",
            customer_email="owner@example.test",
        )
        self.assertEqual(body["mode"], "subscription")
        self.assertEqual(body["line_items[0][price]"], "price_seat_42")
        self.assertEqual(body["line_items[0][quantity]"], "25")
        self.assertEqual(body["metadata[org_id]"], "org_abc")
        self.assertEqual(body["metadata[seats]"], "25")
        self.assertEqual(body["client_reference_id"], "org_abc")
        self.assertEqual(body["customer_email"], "owner@example.test")
        # Stripe Tax is on by default (consistent with T-016).
        self.assertEqual(body["automatic_tax[enabled]"], "true")

    def test_body_rejects_zero_quantity(self) -> None:
        with self.assertRaises(inst_mod.InstitutionalError) as ctx:
            inst_mod.build_seat_subscription_body(
                org_id="org_abc",
                price_id="price_seat",
                quantity=0,
                success_url="https://x",
                cancel_url="https://y",
                customer_email=None,
            )
        self.assertEqual(ctx.exception.code, "quantity_invalid")

    def test_body_uses_customer_id_when_present(self) -> None:
        body = inst_mod.build_seat_subscription_body(
            org_id="org_abc",
            price_id="price_seat",
            quantity=5,
            success_url="https://x",
            cancel_url="https://y",
            customer_email="owner@example.test",
            customer_id="cus_existing",
        )
        self.assertEqual(body["customer"], "cus_existing")
        self.assertNotIn("customer_email", body)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
