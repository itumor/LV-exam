"""T-026 AI per-user quota ledger tests.

Exercises the DB-backed daily ledger in
:mod:`server_app.services.quota`:

* Reserving slots increments the ledger.
* Exceeding the daily cap raises :class:`QuotaExceededError` (status 429)
  with a reset-time hint in the message.
* The ``LVCODEX_AI_DAILY_LIMIT`` env var controls the global cap.
* The effective cap is the minimum of the per-plan cap and the global cap.
* Release decrements the ledger (idempotent — never below zero).
* The ledger persists across :class:`AIQuotaLedger` instances (DB-backed,
  not in-memory).
* Provider failure simulation: the evaluator wraps a mocked provider call
  with the retry policy and surfaces the visible 503 body after exhaustion.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import server
from server_app.services import quota as quota_service
from server_app.services.evaluator import (
    ProviderResponseError,
    build_provider_unavailable_response,
    call_with_retry,
)
from server_app.services.quota import (
    AIQuotaLedger,
    DEFAULT_AI_DAILY_LIMIT,
    QuotaExceededError,
    ai_daily_limit,
    effective_daily_limit,
    reserve_daily_ai_quota,
)


class AIQuotaLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        # Isolate to a tempfile SQLite DB so each test sees a clean ledger.
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "auth.sqlite3"
        self.auth_db_patch = patch.object(server, "AUTH_DB_PATH", self.db_path)
        self.auth_db_patch.start()
        # Reset the once-flag so the DDL re-runs for each tempfile.
        quota_service._reset_ledger_ddl_cache()
        server.init_auth_store()

        # Force a generous global cap (so per-plan caps drive most tests).
        # Individual tests can override via env patches.
        self.env_patch = patch.dict(
            os.environ,
            {
                "LVCODEX_AI_DAILY_LIMIT": "100",
                # Lift the per-plan cap so the global cap controls.
                "AI_SCORING_DAILY_REQUEST_LIMIT_FREE": "5",
                "AI_SCORING_DAILY_REQUEST_LIMIT_PRO": "12",
            },
            clear=False,
        )
        self.env_patch.start()

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.auth_db_patch.stop()
        self.tmpdir.cleanup()
        quota_service._reset_ledger_ddl_cache()

    # ------------------------------------------------------------------
    # Basic reserve / current_usage
    # ------------------------------------------------------------------

    def test_reserve_increments_usage(self) -> None:
        ledger = AIQuotaLedger()
        snapshot = ledger.reserve("learner-1", "free")
        self.assertEqual(snapshot["used"], 1)
        self.assertEqual(snapshot["limit"], 5)
        self.assertEqual(ledger.current_usage("learner-1", "free"), 1)

        snapshot2 = ledger.reserve("learner-1", "free")
        self.assertEqual(snapshot2["used"], 2)

    def test_reserve_includes_resets_at_hint(self) -> None:
        ledger = AIQuotaLedger()
        snapshot = ledger.reserve("learner-2", "free")
        self.assertIn("resets_at", snapshot)
        self.assertTrue(snapshot["resets_at"].endswith("Z"))

    def test_separate_users_have_independent_counters(self) -> None:
        ledger = AIQuotaLedger()
        ledger.reserve("alice", "free")
        ledger.reserve("alice", "free")
        ledger.reserve("bob", "free")
        self.assertEqual(ledger.current_usage("alice", "free"), 2)
        self.assertEqual(ledger.current_usage("bob", "free"), 1)

    def test_separate_plans_have_independent_counters(self) -> None:
        ledger = AIQuotaLedger()
        ledger.reserve("alice", "free")
        ledger.reserve("alice", "pro")
        self.assertEqual(ledger.current_usage("alice", "free"), 1)
        self.assertEqual(ledger.current_usage("alice", "pro"), 1)

    def test_ledger_persists_across_instances(self) -> None:
        AIQuotaLedger().reserve("durable", "free")
        AIQuotaLedger().reserve("durable", "free")
        # Fresh instance — counter must come from DB, not memory.
        self.assertEqual(AIQuotaLedger().current_usage("durable", "free"), 2)

    # ------------------------------------------------------------------
    # Cap enforcement
    # ------------------------------------------------------------------

    def test_exceeding_cap_raises_quota_exceeded(self) -> None:
        ledger = AIQuotaLedger()
        for _ in range(5):  # plan cap = 5
            ledger.reserve("heavy", "free")
        with self.assertRaises(QuotaExceededError) as ctx:
            ledger.reserve("heavy", "free")
        # 429 status with reset-time hint in message.
        self.assertEqual(ctx.exception.status_code, 429)
        message = str(ctx.exception)
        self.assertIn("quota exceeded", message.lower())
        self.assertIn("Resets at", message)
        # Counter does NOT increment on rejection.
        self.assertEqual(ledger.current_usage("heavy", "free"), 5)

    def test_reserve_daily_ai_quota_high_level_helper(self) -> None:
        ledger = AIQuotaLedger()
        snapshot = reserve_daily_ai_quota("learner-x", "free", ledger=ledger)
        self.assertEqual(snapshot["used"], 1)

    # ------------------------------------------------------------------
    # Env-var cap + effective cap
    # ------------------------------------------------------------------

    def test_global_cap_clamps_high_per_plan_caps(self) -> None:
        with patch.dict(
            os.environ,
            {
                "LVCODEX_AI_DAILY_LIMIT": "3",
                "AI_SCORING_DAILY_REQUEST_LIMIT_PRO": "50",
            },
            clear=False,
        ):
            self.assertEqual(effective_daily_limit("pro"), 3)
            ledger = AIQuotaLedger()
            for _ in range(3):
                ledger.reserve("pro-user", "pro")
            with self.assertRaises(QuotaExceededError):
                ledger.reserve("pro-user", "pro")

    def test_per_plan_cap_wins_when_lower(self) -> None:
        with patch.dict(
            os.environ,
            {
                "LVCODEX_AI_DAILY_LIMIT": "100",
                "AI_SCORING_DAILY_REQUEST_LIMIT_FREE": "2",
            },
            clear=False,
        ):
            self.assertEqual(effective_daily_limit("free"), 2)

    def test_default_global_limit_is_30(self) -> None:
        # Clear any env override.
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LVCODEX_AI_DAILY_LIMIT", None)
            self.assertEqual(ai_daily_limit(), DEFAULT_AI_DAILY_LIMIT)
            self.assertEqual(DEFAULT_AI_DAILY_LIMIT, 30)

    def test_invalid_env_value_raises_runtime_error(self) -> None:
        with patch.dict(os.environ, {"LVCODEX_AI_DAILY_LIMIT": "abc"}, clear=False):
            with self.assertRaises(RuntimeError):
                ai_daily_limit()

    # ------------------------------------------------------------------
    # Release path (refund on provider failure)
    # ------------------------------------------------------------------

    def test_release_decrements_counter(self) -> None:
        ledger = AIQuotaLedger()
        ledger.reserve("refund-me", "free")
        ledger.reserve("refund-me", "free")
        ledger.release("refund-me", "free")
        self.assertEqual(ledger.current_usage("refund-me", "free"), 1)

    def test_release_never_goes_below_zero(self) -> None:
        ledger = AIQuotaLedger()
        ledger.release("no-history", "free")  # no rows yet
        self.assertEqual(ledger.current_usage("no-history", "free"), 0)
        ledger.reserve("balanced", "free")
        ledger.release("balanced", "free")
        ledger.release("balanced", "free")  # extra release - idempotent
        self.assertEqual(ledger.current_usage("balanced", "free"), 0)


# ---------------------------------------------------------------------------
# Provider-failure → 503 with retry-later hint (visible failure mode)
# ---------------------------------------------------------------------------


class ProviderFailureVisibilityTests(unittest.TestCase):
    """Mock the provider call and verify the user-visible failure shape.

    The roadmap A P3 requirement is: when AI provider errors after retries,
    the user sees a 503 with a retry-later hint. This test composes the
    public surface (call_with_retry + build_provider_unavailable_response)
    the way the route would.
    """

    def test_provider_failure_after_retries_emits_503_body(self) -> None:
        attempts = {"count": 0}

        def always_503() -> None:
            attempts["count"] += 1
            raise ProviderResponseError("upstream 503", retriable=True)

        with self.assertRaises(ProviderResponseError):
            call_with_retry(
                always_503,
                provider="groq",
                max_attempts=3,
                sleep=lambda _delay: None,
            )

        body = build_provider_unavailable_response(
            provider="groq", attempts=attempts["count"], retry_after_seconds=30
        )
        self.assertEqual(body["code"], "ai_provider_unavailable")
        self.assertEqual(body["attempts"], 3)
        self.assertEqual(body["retry_after_seconds"], 30)
        self.assertIn("retry", body["message"].lower())

    def test_groq_then_openai_fallback_each_use_own_retry(self) -> None:
        """Simulate Groq-then-OpenAI: each provider gets its own retry budget."""

        groq_attempts = {"count": 0}
        openai_attempts = {"count": 0}

        def groq_call() -> None:
            groq_attempts["count"] += 1
            raise ProviderResponseError("groq down", retriable=True)

        def openai_call() -> str:
            openai_attempts["count"] += 1
            if openai_attempts["count"] < 2:
                raise ProviderResponseError("openai blip", retriable=True)
            return "ok"

        with self.assertRaises(ProviderResponseError):
            call_with_retry(
                groq_call, provider="groq", max_attempts=3,
                sleep=lambda _delay: None,
            )
        result = call_with_retry(
            openai_call, provider="openai", max_attempts=3,
            sleep=lambda _delay: None,
        )
        self.assertEqual(result, "ok")
        # Groq used its full retry budget; OpenAI recovered on attempt 2.
        self.assertEqual(groq_attempts["count"], 3)
        self.assertEqual(openai_attempts["count"], 2)


if __name__ == "__main__":  # pragma: no cover - manual invocation
    unittest.main()
