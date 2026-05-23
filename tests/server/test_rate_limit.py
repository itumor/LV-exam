"""Unit tests for T-015 rate-limit module and the server.py middleware hook."""

from __future__ import annotations

import io
import json
import sys
import threading
import unittest
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any
from unittest.mock import patch

# Ensure repo root is on sys.path when running ``python -m unittest`` from
# arbitrary cwd (CI uses ``-s tests/server``, which already prepends cwd, but
# being explicit keeps the test self-contained).
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import rate_limit
import server


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class FakeClock:
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


class StubHeaders:
    """Minimal Mapping-like header bag matching what BaseHTTPRequestHandler exposes."""

    def __init__(self, mapping: dict[str, str] | None = None) -> None:
        self._data = {k.lower(): v for k, v in (mapping or {}).items()}

    def get(self, key: str, default: str = "") -> str:
        return self._data.get(key.lower(), default)

    def __iter__(self):  # pragma: no cover - not used by hook
        return iter(self._data)


class StubHandler:
    """Just enough of SimpleHTTPRequestHandler for the middleware hook."""

    def __init__(
        self,
        *,
        path: str,
        headers: dict[str, str] | None = None,
        client_address: tuple[str, int] = ("127.0.0.1", 0),
    ) -> None:
        self.path = path
        self.command = "GET"
        self.headers = StubHeaders(headers)
        self.client_address = client_address
        self._response_status: int | None = None
        self._response_headers: dict[str, str] = {}
        self.wfile = io.BytesIO()

    # mirror the BaseHTTPRequestHandler surface used by the hook ------------
    def send_response(self, status: int) -> None:
        self._response_status = int(status)

    def send_header(self, name: str, value: str) -> None:
        self._response_headers[name] = str(value)

    def end_headers(self) -> None:  # pragma: no cover - no extra logic needed
        pass

    @property
    def status(self) -> int | None:
        return self._response_status

    @property
    def response_headers(self) -> dict[str, str]:
        return dict(self._response_headers)

    @property
    def body(self) -> bytes:
        return self.wfile.getvalue()


# ---------------------------------------------------------------------------
# TokenBucket
# ---------------------------------------------------------------------------


class TokenBucketTests(unittest.TestCase):
    def test_initial_state_is_full(self) -> None:
        clock = FakeClock()
        bucket = rate_limit.TokenBucket(capacity=5, refill_per_sec=1.0, time_source=clock)
        tokens, capacity = bucket.snapshot()
        self.assertEqual(capacity, 5.0)
        self.assertEqual(tokens, 5.0)

    def test_consume_drains_then_rejects(self) -> None:
        clock = FakeClock()
        bucket = rate_limit.TokenBucket(capacity=3, refill_per_sec=1.0, time_source=clock)
        for _ in range(3):
            allowed, retry = bucket.consume()
            self.assertTrue(allowed)
            self.assertEqual(retry, 0.0)
        allowed, retry = bucket.consume()
        self.assertFalse(allowed)
        # missing 1 token at 1 tok/s -> retry_after ~1.0
        self.assertAlmostEqual(retry, 1.0, places=5)

    def test_refill_replenishes_over_time(self) -> None:
        clock = FakeClock()
        bucket = rate_limit.TokenBucket(capacity=4, refill_per_sec=2.0, time_source=clock)
        for _ in range(4):
            self.assertTrue(bucket.consume()[0])
        # Drained — next call rejected
        self.assertFalse(bucket.consume()[0])
        # Advance 1s -> 2 tokens added
        clock.tick(1.0)
        self.assertTrue(bucket.consume()[0])
        self.assertTrue(bucket.consume()[0])
        self.assertFalse(bucket.consume()[0])
        # Advance fully — should saturate at capacity, not exceed it
        clock.tick(100.0)
        # Drain capacity again to confirm cap held
        for _ in range(4):
            self.assertTrue(bucket.consume()[0])
        self.assertFalse(bucket.consume()[0])

    def test_rejects_invalid_construction(self) -> None:
        with self.assertRaises(ValueError):
            rate_limit.TokenBucket(capacity=0, refill_per_sec=1.0)
        with self.assertRaises(ValueError):
            rate_limit.TokenBucket(capacity=1, refill_per_sec=0)


# ---------------------------------------------------------------------------
# RateLimiter registry
# ---------------------------------------------------------------------------


class RateLimiterTests(unittest.TestCase):
    def _limiter(self, clock: FakeClock | None = None) -> rate_limit.RateLimiter:
        return rate_limit.RateLimiter(
            tiers={
                "ip": rate_limit.TierConfig(capacity=3, refill_per_sec=1.0),
                "session": rate_limit.TierConfig(capacity=5, refill_per_sec=1.0),
                "ip_auth": rate_limit.TierConfig(capacity=2, refill_per_sec=0.5),
            },
            time_source=clock or FakeClock(),
        )

    def test_per_ip_exceed_returns_retry_after(self) -> None:
        limiter = self._limiter()
        for _ in range(3):
            allowed, _ = limiter.check("ip", "1.2.3.4")
            self.assertTrue(allowed)
        allowed, retry = limiter.check("ip", "1.2.3.4")
        self.assertFalse(allowed)
        self.assertGreater(retry, 0)

    def test_per_ip_independent_keys(self) -> None:
        limiter = self._limiter()
        for _ in range(3):
            limiter.check("ip", "1.1.1.1")
        # other IP still has full burst
        allowed, _ = limiter.check("ip", "2.2.2.2")
        self.assertTrue(allowed)

    def test_per_session_exceed(self) -> None:
        limiter = self._limiter()
        for _ in range(5):
            self.assertTrue(limiter.check("session", "sid-abc")[0])
        self.assertFalse(limiter.check("session", "sid-abc")[0])

    def test_auth_scope_stricter_than_ip(self) -> None:
        limiter = self._limiter()
        # ip_auth capacity = 2 in the fixture
        self.assertTrue(limiter.check("ip_auth", "9.9.9.9")[0])
        self.assertTrue(limiter.check("ip_auth", "9.9.9.9")[0])
        allowed, retry = limiter.check("ip_auth", "9.9.9.9")
        self.assertFalse(allowed)
        # 1 missing token at 0.5 tok/s -> 2.0s
        self.assertAlmostEqual(retry, 2.0, places=4)

    def test_admin_role_bypass(self) -> None:
        limiter = self._limiter()
        # exhaust per-ip first
        for _ in range(3):
            limiter.check("ip", "10.0.0.1")
        self.assertFalse(limiter.check("ip", "10.0.0.1")[0])
        # admin role bypass returns allowed=True regardless
        allowed, retry = limiter.check("ip", "10.0.0.1", role="admin")
        self.assertTrue(allowed)
        self.assertEqual(retry, 0.0)
        allowed, retry = limiter.check("session", "sid-admin", role="superadmin")
        self.assertTrue(allowed)
        self.assertEqual(retry, 0.0)

    def test_unknown_scope_raises(self) -> None:
        limiter = self._limiter()
        with self.assertRaises(KeyError):
            limiter.check("not-a-scope", "k")

    def test_empty_key_is_allowed_passthrough(self) -> None:
        limiter = self._limiter()
        # Empty key (e.g. unauthenticated session id) is a no-op
        allowed, _ = limiter.check("session", "")
        self.assertTrue(allowed)

    def test_concurrent_threads_do_not_exceed_limit(self) -> None:
        limiter = rate_limit.RateLimiter(
            tiers={
                "ip": rate_limit.TierConfig(capacity=20, refill_per_sec=0.001),
                "session": rate_limit.TierConfig(capacity=5, refill_per_sec=0.001),
                "ip_auth": rate_limit.TierConfig(capacity=2, refill_per_sec=0.001),
            },
            time_source=FakeClock(),
        )
        successes = []
        successes_lock = threading.Lock()

        def hammer() -> None:
            for _ in range(10):
                allowed, _ = limiter.check("ip", "race-key")
                if allowed:
                    with successes_lock:
                        successes.append(1)

        threads = [threading.Thread(target=hammer) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # capacity=20 with negligible refill — must never exceed capacity
        self.assertEqual(sum(successes), 20)

    def test_from_env_overrides(self) -> None:
        env = {
            "RATE_LIMIT_IP_BURST": "7",
            "RATE_LIMIT_IP_PER_MIN": "30",
            "RATE_LIMIT_AUTH_BURST": "2",
            "RATE_LIMIT_BYPASS_ROLES": "superadmin",
        }
        limiter = rate_limit.RateLimiter.from_env(env=env, time_source=FakeClock())
        self.assertEqual(limiter.tier("ip").capacity, 7)
        self.assertAlmostEqual(limiter.tier("ip").refill_per_sec, 0.5, places=5)
        self.assertEqual(limiter.tier("ip_auth").capacity, 2)
        self.assertEqual(limiter.bypass_roles, frozenset({"superadmin"}))


# ---------------------------------------------------------------------------
# Server middleware hook
# ---------------------------------------------------------------------------


class _LimiterFixture:
    """Context manager that swaps in a clean limiter for the duration of a test."""

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self._original: rate_limit.RateLimiter | None = None

    def __enter__(self) -> rate_limit.RateLimiter:
        self._original = rate_limit.LIMITER
        rate_limit.LIMITER = rate_limit.RateLimiter(**self.kwargs)
        return rate_limit.LIMITER

    def __exit__(self, *exc: Any) -> None:
        if self._original is not None:
            rate_limit.LIMITER = self._original


class ServerHookTests(unittest.TestCase):
    def setUp(self) -> None:
        # Tight limits so we can exercise reject quickly
        self.clock = FakeClock()
        self.limiter_ctx = _LimiterFixture(
            tiers={
                "ip": rate_limit.TierConfig(capacity=2, refill_per_sec=1.0),
                "session": rate_limit.TierConfig(capacity=2, refill_per_sec=1.0),
                "ip_auth": rate_limit.TierConfig(capacity=1, refill_per_sec=0.5),
            },
            time_source=self.clock,
        )
        self.limiter_ctx.__enter__()

    def tearDown(self) -> None:
        self.limiter_ctx.__exit__(None, None, None)

    def _enforce(self, handler: StubHandler, *, role: str = "user") -> bool:
        with patch.object(server, "get_session_user_role", return_value=role):
            return server._t015_enforce(handler)

    def test_non_api_path_skips_limiter(self) -> None:
        handler = StubHandler(path="/latvian-a2-exam-app/index.html")
        self.assertFalse(self._enforce(handler))
        self.assertIsNone(handler.status)

    def test_healthz_is_not_limited(self) -> None:
        handler = StubHandler(path="/healthz")
        for _ in range(20):
            self.assertFalse(self._enforce(handler))
        self.assertIsNone(handler.status)

    def test_api_per_ip_returns_429_with_retry_after(self) -> None:
        # capacity=2 so two requests allowed, third rejected
        for _ in range(2):
            h = StubHandler(path="/api/exams/catalog")
            self.assertFalse(self._enforce(h))
        h = StubHandler(path="/api/exams/catalog")
        self.assertTrue(self._enforce(h))
        self.assertEqual(h.status, int(HTTPStatus.TOO_MANY_REQUESTS))
        self.assertIn("Retry-After", h.response_headers)
        self.assertGreaterEqual(int(h.response_headers["Retry-After"]), 1)
        payload = json.loads(h.body.decode("utf-8"))
        self.assertEqual(payload["error"], "rate_limited")
        self.assertIn("retry_after", payload)

    def test_x_forwarded_for_is_used_as_client_ip(self) -> None:
        # Two different XFFs share the same socket peer but get independent buckets
        for _ in range(2):
            h = StubHandler(
                path="/api/exams/catalog",
                headers={"X-Forwarded-For": "203.0.113.10, 10.0.0.1"},
            )
            self.assertFalse(self._enforce(h))
        # Third from same XFF rejected
        h = StubHandler(
            path="/api/exams/catalog",
            headers={"X-Forwarded-For": "203.0.113.10"},
        )
        self.assertTrue(self._enforce(h))
        # But a fresh XFF is allowed (same TCP peer though)
        h2 = StubHandler(
            path="/api/exams/catalog",
            headers={"X-Forwarded-For": "198.51.100.7"},
        )
        self.assertFalse(self._enforce(h2))

    def test_session_scope_engaged_when_cookie_present(self) -> None:
        cookies = f"{server.AUTH_SESSION_COOKIE}=sid-zzz"
        # capacity_session = 2 — third with same cookie is rejected even
        # though per-ip is reset by a new IP each call.
        for i in range(2):
            h = StubHandler(
                path="/api/profile",
                headers={
                    "Cookie": cookies,
                    "X-Forwarded-For": f"10.0.0.{i+1}",
                },
            )
            self.assertFalse(self._enforce(h))
        h = StubHandler(
            path="/api/profile",
            headers={"Cookie": cookies, "X-Forwarded-For": "10.0.0.99"},
        )
        self.assertTrue(self._enforce(h))
        self.assertEqual(h.status, int(HTTPStatus.TOO_MANY_REQUESTS))

    def test_auth_path_uses_stricter_bucket(self) -> None:
        # ip_auth capacity=1 in fixture, so the second auth call is rejected
        # *before* the broader ip bucket runs out.
        h = StubHandler(path="/api/auth/login")
        self.assertFalse(self._enforce(h))
        h = StubHandler(path="/api/auth/login")
        self.assertTrue(self._enforce(h))
        self.assertEqual(h.status, int(HTTPStatus.TOO_MANY_REQUESTS))
        # Non-auth path on same IP should still be allowed (ip bucket has
        # capacity=2 in this fixture, and we have not consumed from it yet).
        h2 = StubHandler(path="/api/exams/catalog")
        self.assertFalse(self._enforce(h2))

    def test_admin_role_bypasses_middleware(self) -> None:
        # Burn through the per-ip bucket using a normal user first.
        for _ in range(2):
            self.assertFalse(self._enforce(StubHandler(path="/api/exams/catalog")))
        self.assertTrue(self._enforce(StubHandler(path="/api/exams/catalog")))
        # Admin from the same IP must still pass.
        h = StubHandler(path="/api/exams/catalog")
        self.assertFalse(self._enforce(h, role="admin"))
        self.assertIsNone(h.status)
        h = StubHandler(path="/api/exams/catalog")
        self.assertFalse(self._enforce(h, role="superadmin"))
        self.assertIsNone(h.status)

    def test_retry_after_header_value_helper(self) -> None:
        self.assertEqual(rate_limit.retry_after_header_value(0.1), "1")
        self.assertEqual(rate_limit.retry_after_header_value(0.0), "1")
        self.assertEqual(rate_limit.retry_after_header_value(1.0), "1")
        self.assertEqual(rate_limit.retry_after_header_value(1.01), "2")
        self.assertEqual(rate_limit.retry_after_header_value(4.6), "5")


if __name__ == "__main__":
    unittest.main()
