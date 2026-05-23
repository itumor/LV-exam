"""T-015 follow-up: ``LVCODEX_RATE_LIMIT_DISABLE`` env knob.

The Playwright regression suite runs every worker from ``127.0.0.1``, which
exhausts the production-default per-IP bucket (60 req/min, burst 30) long
before the 10th test. To unblock CI without weakening production posture,
``rate_limit.RateLimiter.check`` short-circuits to allow-all when
``LVCODEX_RATE_LIMIT_DISABLE`` is set to a truthy value. This module pins
that contract:

(a) default behavior (env not set) is unchanged — full bucket semantics.
(b) when the env var is "1" (or any truthy spelling) every check returns
    ``(True, 0.0)`` regardless of bucket state, role, or scope.
"""

from __future__ import annotations

import os
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import rate_limit


class _FakeClock:
    """Monotonic clock that only advances when ``tick`` is called."""

    def __init__(self, start: float = 1_000.0) -> None:
        self._now = float(start)
        self._lock = threading.Lock()

    def __call__(self) -> float:
        with self._lock:
            return self._now

    def tick(self, seconds: float) -> None:
        with self._lock:
            self._now += float(seconds)


def _tight_limiter(clock: _FakeClock) -> rate_limit.RateLimiter:
    """Limiter with very small buckets so reject is one or two calls away."""

    return rate_limit.RateLimiter(
        tiers={
            "ip": rate_limit.TierConfig(capacity=2, refill_per_sec=0.001),
            "session": rate_limit.TierConfig(capacity=2, refill_per_sec=0.001),
            "ip_auth": rate_limit.TierConfig(capacity=1, refill_per_sec=0.001),
        },
        time_source=clock,
    )


class DisableEnvDefaultsTests(unittest.TestCase):
    """Env knob unset — production defaults must continue to apply."""

    def setUp(self) -> None:
        # Defensive: tests in other modules MUST NOT leak the env var into
        # this module's namespace. Pop and restore around each test body.
        self._original = os.environ.pop(rate_limit.DISABLE_ENV_VAR, None)
        self.clock = _FakeClock()
        self.limiter = _tight_limiter(self.clock)

    def tearDown(self) -> None:
        if self._original is None:
            os.environ.pop(rate_limit.DISABLE_ENV_VAR, None)
        else:
            os.environ[rate_limit.DISABLE_ENV_VAR] = self._original

    def test_is_disabled_returns_false_when_unset(self) -> None:
        self.assertFalse(rate_limit.is_disabled_via_env())

    def test_ip_bucket_still_rejects_after_burst(self) -> None:
        # capacity=2, so two requests allowed, third rejected with retry > 0.
        for _ in range(2):
            allowed, retry = self.limiter.check("ip", "10.0.0.1")
            self.assertTrue(allowed)
            self.assertEqual(retry, 0.0)
        allowed, retry = self.limiter.check("ip", "10.0.0.1")
        self.assertFalse(allowed)
        self.assertGreater(retry, 0.0)

    def test_explicit_empty_string_treated_as_disabled_off(self) -> None:
        with patch.dict(os.environ, {rate_limit.DISABLE_ENV_VAR: ""}):
            self.assertFalse(rate_limit.is_disabled_via_env())
            # And the bucket still enforces.
            for _ in range(2):
                self.assertTrue(self.limiter.check("ip", "10.0.0.2")[0])
            self.assertFalse(self.limiter.check("ip", "10.0.0.2")[0])

    def test_explicit_zero_treated_as_disabled_off(self) -> None:
        with patch.dict(os.environ, {rate_limit.DISABLE_ENV_VAR: "0"}):
            self.assertFalse(rate_limit.is_disabled_via_env())
            for _ in range(2):
                self.assertTrue(self.limiter.check("ip", "10.0.0.3")[0])
            self.assertFalse(self.limiter.check("ip", "10.0.0.3")[0])

    def test_explicit_false_treated_as_disabled_off(self) -> None:
        for value in ("false", "FALSE", "no", "off"):
            with self.subTest(value=value):
                with patch.dict(os.environ, {rate_limit.DISABLE_ENV_VAR: value}):
                    self.assertFalse(rate_limit.is_disabled_via_env())

    def test_passing_explicit_env_mapping_overrides_os_environ(self) -> None:
        # is_disabled_via_env(env=...) ignores os.environ entirely.
        with patch.dict(os.environ, {rate_limit.DISABLE_ENV_VAR: "1"}):
            self.assertFalse(rate_limit.is_disabled_via_env(env={}))


class DisableEnvActiveTests(unittest.TestCase):
    """Env knob truthy — every check must allow regardless of bucket state."""

    def setUp(self) -> None:
        self._original = os.environ.pop(rate_limit.DISABLE_ENV_VAR, None)
        self.clock = _FakeClock()
        self.limiter = _tight_limiter(self.clock)

    def tearDown(self) -> None:
        if self._original is None:
            os.environ.pop(rate_limit.DISABLE_ENV_VAR, None)
        else:
            os.environ[rate_limit.DISABLE_ENV_VAR] = self._original

    def test_is_disabled_returns_true_for_one(self) -> None:
        with patch.dict(os.environ, {rate_limit.DISABLE_ENV_VAR: "1"}):
            self.assertTrue(rate_limit.is_disabled_via_env())

    def test_is_disabled_accepts_common_truthy_spellings(self) -> None:
        for value in ("1", "true", "TRUE", "yes", "on", "  1 ", " True "):
            with self.subTest(value=value):
                with patch.dict(os.environ, {rate_limit.DISABLE_ENV_VAR: value}):
                    self.assertTrue(rate_limit.is_disabled_via_env())

    def test_check_allows_through_drained_bucket(self) -> None:
        with patch.dict(os.environ, {rate_limit.DISABLE_ENV_VAR: "1"}):
            # Even calling 20x on a capacity=2 bucket must all succeed.
            for _ in range(20):
                allowed, retry = self.limiter.check("ip", "10.0.0.10")
                self.assertTrue(allowed)
                self.assertEqual(retry, 0.0)

    def test_check_allows_through_all_scopes(self) -> None:
        with patch.dict(os.environ, {rate_limit.DISABLE_ENV_VAR: "1"}):
            for scope in ("ip", "session", "ip_auth"):
                for _ in range(10):
                    allowed, retry = self.limiter.check(scope, f"key-{scope}")
                    self.assertTrue(allowed, f"scope={scope!r}")
                    self.assertEqual(retry, 0.0)

    def test_check_allows_through_when_role_is_not_admin(self) -> None:
        with patch.dict(os.environ, {rate_limit.DISABLE_ENV_VAR: "1"}):
            for _ in range(10):
                allowed, _ = self.limiter.check("ip", "10.0.0.20", role="user")
                self.assertTrue(allowed)

    def test_disable_takes_effect_after_bucket_already_drained(self) -> None:
        # Drain first without the env (production posture)…
        for _ in range(2):
            self.assertTrue(self.limiter.check("ip", "10.0.0.30")[0])
        self.assertFalse(self.limiter.check("ip", "10.0.0.30")[0])
        # …then flip the env. The limiter must reverse to allow-all
        # immediately, *without* requiring re-instantiation.
        with patch.dict(os.environ, {rate_limit.DISABLE_ENV_VAR: "1"}):
            for _ in range(5):
                allowed, retry = self.limiter.check("ip", "10.0.0.30")
                self.assertTrue(allowed)
                self.assertEqual(retry, 0.0)
        # Removing the env restores production behavior on the same bucket.
        # Bucket is still drained (we never refilled the clock), so reject.
        self.assertFalse(self.limiter.check("ip", "10.0.0.30")[0])

    def test_disable_does_not_consume_tokens(self) -> None:
        # If the disable path accidentally consumed tokens we would see a
        # smaller post-disable allowance. Verify by inspecting the bucket
        # snapshot before and after a disabled-mode burst.
        bucket = self.limiter._bucket_for("ip", "10.0.0.40")  # noqa: SLF001
        before_tokens, before_capacity = bucket.snapshot()
        with patch.dict(os.environ, {rate_limit.DISABLE_ENV_VAR: "1"}):
            for _ in range(50):
                self.assertTrue(self.limiter.check("ip", "10.0.0.40")[0])
        after_tokens, after_capacity = bucket.snapshot()
        self.assertEqual(before_tokens, after_tokens)
        self.assertEqual(before_capacity, after_capacity)


if __name__ == "__main__":
    unittest.main()
