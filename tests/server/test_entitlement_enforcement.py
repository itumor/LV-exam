"""T-024: Server-enforced entitlement checks on every protected route.

The Definition-of-Done line item ``8. Entitlement enforcement is
server-side, never UI-only`` is operationalised by
:mod:`server_app.services.entitlements`. This test module audits the
five risk scenarios called out in the T-024 plan:

* free-tier user cannot start a paid attempt (exam_unlock missing),
* paid user (with attempts or AI credits) passes the gate,
* admin / superadmin bypass the gate entirely,
* expired entitlement grants are ignored (and the user is rejected),
* concurrent consumption races serialise — exactly one consume wins.
"""
from __future__ import annotations

import io
import json
import tempfile
import threading
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import server  # exposes the same surface as server_app.core
from billing import FREE_EXAM_ID, BillingStore, utc_now, utc_now_iso
from server_app.services.entitlements import (
    EntitlementError,
    entitled,
    require_entitlement,
)


def _seed_paid_attempts(store: BillingStore, learner_id: str, *, quantity: int = 5) -> None:
    store.ensure_learner(learner_id, email=f"{learner_id}@example.test")
    store.grant_product(
        learner_id,
        product_key="exam_pack",
        quantity=quantity,
        grant_type="exam_attempts",
        source_reference="seed-test",
    )


def _seed_ai_credits(store: BillingStore, learner_id: str, *, quantity: int = 3) -> None:
    store.ensure_learner(learner_id, email=f"{learner_id}@example.test")
    store.grant_product(
        learner_id,
        product_key="ai_credits",
        quantity=quantity,
        grant_type="ai_credits",
        source_reference="seed-test",
    )


def _seed_expired_grant(store: BillingStore, learner_id: str) -> None:
    store.ensure_learner(learner_id, email=f"{learner_id}@example.test")
    past = (utc_now() - timedelta(days=1)).isoformat().replace("+00:00", "Z")
    store.grant_product(
        learner_id,
        product_key="exam_pack",
        quantity=5,
        grant_type="exam_attempts",
        expires_at=past,
        source_reference="seed-test-expired",
    )


def _fresh_store(tmpdir: tempfile.TemporaryDirectory) -> BillingStore:
    return BillingStore(Path(tmpdir.name) / "billing.sqlite3")


class RequireEntitlementTests(unittest.TestCase):
    """Service contract: free reject, paid pass, admin bypass, expired."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.store = _fresh_store(self.tmpdir)
        server.get_billing_store.cache_clear()
        self.patcher = patch.object(server, "billing_db_path", lambda: self.store.db_path)
        self.patcher.start()
        server.get_billing_store.cache_clear()

    def tearDown(self) -> None:
        self.patcher.stop()
        server.get_billing_store.cache_clear()
        self.tmpdir.cleanup()

    def test_free_user_rejected_for_paid_kinds_after_free_used(self) -> None:
        learner_id = "acct_free_user"
        self.store.ensure_learner(learner_id)
        self.store.consume_exam_access(learner_id, FREE_EXAM_ID)
        with self.assertRaises(EntitlementError) as ctx:
            require_entitlement(learner_id, "ai_credit")
        self.assertEqual(ctx.exception.kind, "ai_credit")
        self.assertEqual(ctx.exception.reason, "missing")
        with self.assertRaises(EntitlementError) as ctx2:
            require_entitlement(learner_id, "exam_unlock")
        self.assertEqual(ctx2.exception.reason, "missing")
        with self.assertRaises(EntitlementError):
            require_entitlement(learner_id, "subscription")

    def test_free_user_passes_exam_unlock_when_free_attempt_available(self) -> None:
        learner_id = "acct_free_with_attempt"
        self.store.ensure_learner(learner_id)
        self.assertTrue(require_entitlement(learner_id, "exam_unlock"))

    def test_paid_user_passes_exam_unlock(self) -> None:
        learner_id = "acct_paid"
        _seed_paid_attempts(self.store, learner_id, quantity=3)
        self.assertTrue(require_entitlement(learner_id, "exam_unlock"))

    def test_paid_user_passes_ai_credit(self) -> None:
        learner_id = "acct_paid_ai"
        _seed_ai_credits(self.store, learner_id, quantity=2)
        self.assertTrue(require_entitlement(learner_id, "ai_credit"))

    def test_admin_role_bypasses_all_kinds(self) -> None:
        learner_id = "acct_admin"
        self.assertTrue(
            require_entitlement(learner_id, "exam_unlock", user_role="admin")
        )
        self.assertTrue(
            require_entitlement(learner_id, "ai_credit", user_role="superadmin")
        )
        self.assertTrue(
            require_entitlement(learner_id, "subscription", user_role="admin")
        )

    def test_expired_grant_is_ignored(self) -> None:
        learner_id = "acct_expired"
        _seed_expired_grant(self.store, learner_id)
        self.store.consume_exam_access(learner_id, FREE_EXAM_ID)
        with self.assertRaises(EntitlementError) as ctx:
            require_entitlement(learner_id, "exam_unlock")
        self.assertEqual(ctx.exception.kind, "exam_unlock")
        self.assertEqual(ctx.exception.reason, "missing")
        self.assertEqual(ctx.exception.state.get("paid_attempts_remaining"), 0)

    def test_frozen_account_is_rejected(self) -> None:
        learner_id = "acct_frozen"
        _seed_paid_attempts(self.store, learner_id, quantity=5)
        with self.store._connect() as conn:
            conn.execute(
                "UPDATE learners SET status = 'frozen', updated_at = ? WHERE learner_id = ?",
                (utc_now_iso(), learner_id),
            )
        with self.assertRaises(EntitlementError) as ctx:
            require_entitlement(learner_id, "exam_unlock")
        self.assertEqual(ctx.exception.reason, "frozen")

    def test_unknown_kind_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            require_entitlement("acct_x", "wat")  # type: ignore[arg-type]

    def test_empty_account_id_raises_entitlement_error(self) -> None:
        with self.assertRaises(EntitlementError) as ctx:
            require_entitlement("", "ai_credit")
        self.assertEqual(ctx.exception.reason, "account_unknown")


class ConcurrentConsumptionTests(unittest.TestCase):
    """N threads racing the consume - at most ``granted`` win."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.store = _fresh_store(self.tmpdir)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_two_threads_racing_consume_ai_credit_only_one_wins(self) -> None:
        learner_id = "acct_race"
        _seed_ai_credits(self.store, learner_id, quantity=1)
        results: list[dict] = []
        barrier = threading.Barrier(2)

        def consume() -> None:
            barrier.wait()
            result = self.store.consume_ai_credit(learner_id)
            results.append(result)

        threads = [threading.Thread(target=consume) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        allowed = [r for r in results if r["allowed"]]
        denied = [r for r in results if not r["allowed"]]
        self.assertEqual(len(allowed), 1)
        self.assertEqual(len(denied), 1)
        self.assertEqual(denied[0]["reason"], "no_ai_credits_left")

    def test_n_threads_racing_consume_exam_access_overshoot_is_zero(self) -> None:
        learner_id = "acct_race_exam"
        _seed_paid_attempts(self.store, learner_id, quantity=3)
        self.store.consume_exam_access(learner_id, FREE_EXAM_ID)

        results: list[dict] = []
        lock = threading.Lock()
        barrier = threading.Barrier(8)

        def consume(idx: int) -> None:
            barrier.wait()
            result = self.store.consume_exam_access(
                learner_id, f"exam_race_{idx:02d}"
            )
            with lock:
                results.append(result)

        threads = [threading.Thread(target=consume, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        allowed = [r for r in results if r["allowed"]]
        denied = [r for r in results if not r["allowed"]]
        self.assertEqual(len(allowed), 3, f"overshoot: {[r['reason'] for r in results]}")
        self.assertEqual(len(denied), 5)


class _StubSession(dict):
    """Minimal session shape used by current_session_record returns."""


class _StubHandler:
    """Hand-rolled stub for AppHandler so we can drive _t024_patched_do_post."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.command = "POST"
        self._status: int | None = None
        self._headers: list[tuple[str, str]] = []
        self._body = io.BytesIO()
        self.wfile = self._body  # type: ignore[assignment]
        self.headers = {}

    def send_response(self, code: int) -> None:
        self._status = code

    def send_header(self, key: str, value: str) -> None:
        self._headers.append((key, value))

    def end_headers(self) -> None:
        pass

    def status(self) -> int | None:
        return self._status

    def body_json(self) -> dict:
        return json.loads(self._body.getvalue().decode("utf-8") or "{}")


class HookEnforcementTests(unittest.TestCase):
    """The end-of-core hook block must reject free users + pass paid ones."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.store = _fresh_store(self.tmpdir)
        server.get_billing_store.cache_clear()
        self.patcher = patch.object(server, "billing_db_path", lambda: self.store.db_path)
        self.patcher.start()
        server.get_billing_store.cache_clear()

    def tearDown(self) -> None:
        self.patcher.stop()
        server.get_billing_store.cache_clear()
        self.tmpdir.cleanup()

    def _call_enforce(self, path: str, *, role: str, account_id: str) -> _StubHandler:
        from server_app.core import _t024_enforce, _T024_GATES

        handler = _StubHandler(path)
        kind = _T024_GATES[path]
        session = _StubSession(account={"id": account_id, "role": role})
        with patch("server_app.core.current_session_record", return_value=session):
            blocked = _t024_enforce(handler, kind)
        handler._blocked = blocked  # type: ignore[attr-defined]
        return handler

    def test_attempts_start_blocks_free_user_with_no_attempts(self) -> None:
        learner_id = "acct_hook_free"
        self.store.ensure_learner(learner_id)
        self.store.consume_exam_access(learner_id, FREE_EXAM_ID)
        h = self._call_enforce(
            "/api/attempts/start", role="user", account_id=learner_id
        )
        self.assertTrue(getattr(h, "_blocked"))
        self.assertEqual(h.status(), 402)
        body = h.body_json()
        self.assertEqual(body["kind"], "exam_unlock")
        self.assertEqual(body["reason"], "missing")
        self.assertIn("billing_state", body)

    def test_attempts_start_passes_paid_user(self) -> None:
        learner_id = "acct_hook_paid"
        _seed_paid_attempts(self.store, learner_id, quantity=2)
        h = self._call_enforce(
            "/api/attempts/start", role="user", account_id=learner_id
        )
        self.assertFalse(getattr(h, "_blocked"))
        self.assertIsNone(h.status(), "no 4xx must be emitted for paid user")

    def test_evaluate_blocks_user_without_ai_credit(self) -> None:
        learner_id = "acct_hook_no_credit"
        self.store.ensure_learner(learner_id)
        h = self._call_enforce(
            "/api/evaluate", role="user", account_id=learner_id
        )
        self.assertTrue(getattr(h, "_blocked"))
        self.assertEqual(h.status(), 402)
        self.assertEqual(h.body_json()["kind"], "ai_credit")

    def test_evaluate_passes_user_with_ai_credit(self) -> None:
        learner_id = "acct_hook_with_credit"
        _seed_ai_credits(self.store, learner_id, quantity=1)
        h = self._call_enforce(
            "/api/evaluate", role="user", account_id=learner_id
        )
        self.assertFalse(getattr(h, "_blocked"))

    def test_uploads_speaking_blocks_user_with_no_attempt(self) -> None:
        learner_id = "acct_hook_speak"
        self.store.ensure_learner(learner_id)
        self.store.consume_exam_access(learner_id, FREE_EXAM_ID)
        h = self._call_enforce(
            "/api/uploads/speaking", role="user", account_id=learner_id
        )
        self.assertTrue(getattr(h, "_blocked"))
        self.assertEqual(h.status(), 402)

    def test_admin_bypasses_all_gates(self) -> None:
        learner_id = "acct_hook_admin"
        for path in ("/api/attempts/start", "/api/evaluate", "/api/uploads/speaking"):
            h = self._call_enforce(path, role="admin", account_id=learner_id)
            self.assertFalse(
                getattr(h, "_blocked"),
                f"admin must bypass entitlement gate on {path}",
            )

    def test_superadmin_bypasses_all_gates(self) -> None:
        learner_id = "acct_hook_super"
        for path in ("/api/attempts/start", "/api/evaluate", "/api/uploads/speaking"):
            h = self._call_enforce(path, role="superadmin", account_id=learner_id)
            self.assertFalse(getattr(h, "_blocked"))

    def test_expired_entitlement_is_rejected_via_hook(self) -> None:
        learner_id = "acct_hook_expired"
        _seed_expired_grant(self.store, learner_id)
        self.store.consume_exam_access(learner_id, FREE_EXAM_ID)
        h = self._call_enforce(
            "/api/attempts/start", role="user", account_id=learner_id
        )
        self.assertTrue(getattr(h, "_blocked"))
        self.assertEqual(h.body_json()["reason"], "missing")


class EntitledDecoratorTests(unittest.TestCase):
    """The @entitled decorator must guard arbitrary AppHandler methods."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.store = _fresh_store(self.tmpdir)
        server.get_billing_store.cache_clear()
        self.patcher = patch.object(server, "billing_db_path", lambda: self.store.db_path)
        self.patcher.start()
        server.get_billing_store.cache_clear()

    def tearDown(self) -> None:
        self.patcher.stop()
        server.get_billing_store.cache_clear()
        self.tmpdir.cleanup()

    def test_decorator_blocks_free_user_without_running_wrapped_method(self) -> None:
        called: list[bool] = []

        @entitled(kind="ai_credit")
        def fake_handler(self) -> None:  # noqa: ANN001
            called.append(True)

        learner_id = "acct_dec_free"
        self.store.ensure_learner(learner_id)
        handler = _StubHandler("/api/some-route")
        session = _StubSession(account={"id": learner_id, "role": "user"})
        with patch(
            "server_app.services.entitlements.current_session_record",
            return_value=session,
        ):
            fake_handler(handler)

        self.assertEqual(called, [])
        self.assertEqual(handler.status(), 402)
        self.assertEqual(handler.body_json()["kind"], "ai_credit")

    def test_decorator_calls_wrapped_method_for_paid_user(self) -> None:
        called: list[bool] = []

        @entitled(kind="ai_credit")
        def fake_handler(self) -> None:  # noqa: ANN001
            called.append(True)

        learner_id = "acct_dec_paid"
        _seed_ai_credits(self.store, learner_id, quantity=1)
        handler = _StubHandler("/api/some-route")
        session = _StubSession(account={"id": learner_id, "role": "user"})
        with patch(
            "server_app.services.entitlements.current_session_record",
            return_value=session,
        ):
            fake_handler(handler)

        self.assertEqual(called, [True])
        self.assertIsNone(handler.status())

    def test_decorator_admin_bypass(self) -> None:
        called: list[bool] = []

        @entitled(kind="exam_unlock")
        def fake_handler(self) -> None:  # noqa: ANN001
            called.append(True)

        handler = _StubHandler("/api/some-route")
        session = _StubSession(account={"id": "acct_admin", "role": "admin"})
        with patch(
            "server_app.services.entitlements.current_session_record",
            return_value=session,
        ):
            fake_handler(handler)
        self.assertEqual(called, [True])

    def test_decorator_rejects_unauthenticated_request_with_401(self) -> None:
        called: list[bool] = []

        @entitled(kind="ai_credit")
        def fake_handler(self) -> None:  # noqa: ANN001
            called.append(True)

        handler = _StubHandler("/api/some-route")
        with patch(
            "server_app.services.entitlements.current_session_record",
            return_value=None,
        ):
            with self.assertRaises(server.ApiError) as ctx:
                fake_handler(handler)
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertEqual(called, [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
