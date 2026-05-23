"""Thread-safe token-bucket rate limiter for the lvcodex API surface.

T-015 — per-IP and per-session rate limits with 429 + Retry-After.

This module is intentionally standalone (no imports from ``server``) so that
the unit tests can exercise the limiter without spinning up the HTTP server.
The :class:`RateLimiter` registry exposes three default scopes that the
``server.py`` middleware hook wires into request handling:

* ``ip``         — per-IP global cap (default 60 req/min, burst 30).
* ``session``    — per-authenticated-session cap (default 120 req/min, burst 60).
* ``ip_auth``    — stricter per-IP cap applied to ``/api/auth/*`` endpoints
  (default 10 req/min, burst 5) to slow credential stuffing.

All defaults are env-overridable; see :func:`RateLimiter.from_env` and
``docs/rate-limits.md``. Admin/superadmin roles can bypass entirely via
``RateLimiter.bypass_roles``.

The bucket is a classic continuous token bucket: ``capacity`` tokens are
available at start, each successful ``consume`` removes one token, and
tokens regenerate at ``refill_per_sec`` until ``capacity`` is reached again.
The ``time_source`` argument lets tests inject a deterministic clock.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, Optional, Tuple

TimeSource = Callable[[], float]


@dataclass
class TokenBucket:
    """Continuous token bucket guarded by a per-bucket lock.

    Parameters
    ----------
    capacity:
        Maximum tokens (burst). Must be >= 1.
    refill_per_sec:
        Tokens regenerated per second. Must be > 0.
    time_source:
        Callable returning a monotonic float. Defaults to ``time.monotonic``.
        Override in tests to make timing deterministic.
    """

    capacity: float
    refill_per_sec: float
    time_source: TimeSource = field(default=time.monotonic)
    _tokens: float = field(init=False)
    _last_refill: float = field(init=False)
    _lock: threading.Lock = field(init=False, default_factory=threading.Lock)

    def __post_init__(self) -> None:
        if self.capacity < 1:
            raise ValueError("TokenBucket capacity must be >= 1")
        if self.refill_per_sec <= 0:
            raise ValueError("TokenBucket refill_per_sec must be > 0")
        self._tokens = float(self.capacity)
        self._last_refill = float(self.time_source())

    def _refill(self, now: float) -> None:
        delta = now - self._last_refill
        if delta <= 0:
            return
        self._tokens = min(self.capacity, self._tokens + delta * self.refill_per_sec)
        self._last_refill = now

    def consume(self, cost: float = 1.0) -> Tuple[bool, float]:
        """Try to consume ``cost`` tokens.

        Returns ``(allowed, retry_after_seconds)``. When ``allowed`` is True,
        ``retry_after_seconds`` is 0.0. When False, ``retry_after_seconds`` is
        the time the caller should wait before the bucket can satisfy the
        request again.
        """

        if cost <= 0:
            return True, 0.0
        with self._lock:
            now = float(self.time_source())
            self._refill(now)
            if self._tokens >= cost:
                self._tokens -= cost
                return True, 0.0
            missing = cost - self._tokens
            retry_after = missing / self.refill_per_sec
            return False, retry_after

    def snapshot(self) -> Tuple[float, float]:
        """Return ``(tokens, capacity)`` — diagnostic helper."""

        with self._lock:
            return self._tokens, float(self.capacity)


@dataclass(frozen=True)
class TierConfig:
    """Configuration for one named rate-limit scope."""

    capacity: int
    refill_per_sec: float


class RateLimiter:
    """Thread-safe registry of named tiers, each holding a per-key bucket map.

    Use one shared :class:`RateLimiter` instance per process. The HTTP
    middleware in ``server.py`` calls :meth:`check` with the scope name and a
    key (IP address or session id). The limiter lazily creates a fresh bucket
    per unseen key and never deletes them (the working set is naturally
    bounded by unique clients; see :meth:`reset` for tests).
    """

    DEFAULT_TIERS: Dict[str, TierConfig] = {
        # 60 req / min sustained, burst 30
        "ip": TierConfig(capacity=30, refill_per_sec=60.0 / 60.0),
        # 120 req / min sustained, burst 60
        "session": TierConfig(capacity=60, refill_per_sec=120.0 / 60.0),
        # 10 req / min sustained, burst 5 — /api/auth/*
        "ip_auth": TierConfig(capacity=5, refill_per_sec=10.0 / 60.0),
    }

    DEFAULT_BYPASS_ROLES: frozenset[str] = frozenset({"admin", "superadmin"})

    def __init__(
        self,
        tiers: Optional[Dict[str, TierConfig]] = None,
        *,
        bypass_roles: Optional[Iterable[str]] = None,
        time_source: TimeSource = time.monotonic,
    ) -> None:
        self._tiers: Dict[str, TierConfig] = dict(tiers or self.DEFAULT_TIERS)
        self._buckets: Dict[str, Dict[str, TokenBucket]] = {
            scope: {} for scope in self._tiers
        }
        self._tier_lock = threading.Lock()
        self._time_source = time_source
        self.bypass_roles: frozenset[str] = frozenset(
            bypass_roles if bypass_roles is not None else self.DEFAULT_BYPASS_ROLES
        )

    # ------------------------------------------------------------------ setup
    @classmethod
    def from_env(
        cls,
        *,
        env: Optional[Dict[str, str]] = None,
        time_source: TimeSource = time.monotonic,
    ) -> "RateLimiter":
        """Build a limiter, allowing env overrides for each tier.

        Supported variables (all optional; defaults listed in
        :attr:`DEFAULT_TIERS`)::

            RATE_LIMIT_IP_BURST                 -> ip.capacity
            RATE_LIMIT_IP_PER_MIN               -> ip.refill (per minute)
            RATE_LIMIT_SESSION_BURST            -> session.capacity
            RATE_LIMIT_SESSION_PER_MIN          -> session.refill (per minute)
            RATE_LIMIT_AUTH_BURST               -> ip_auth.capacity
            RATE_LIMIT_AUTH_PER_MIN             -> ip_auth.refill (per minute)
            RATE_LIMIT_BYPASS_ROLES             -> comma-separated role list
        """

        source = os.environ if env is None else env

        def _int(name: str, fallback: int) -> int:
            raw = source.get(name)
            if not raw:
                return fallback
            try:
                value = int(raw)
            except ValueError:
                return fallback
            return value if value > 0 else fallback

        def _float_per_min(name: str, fallback_per_min: float) -> float:
            raw = source.get(name)
            if not raw:
                return fallback_per_min / 60.0
            try:
                value = float(raw)
            except ValueError:
                return fallback_per_min / 60.0
            return (value / 60.0) if value > 0 else (fallback_per_min / 60.0)

        tiers = {
            "ip": TierConfig(
                capacity=_int("RATE_LIMIT_IP_BURST", 30),
                refill_per_sec=_float_per_min("RATE_LIMIT_IP_PER_MIN", 60.0),
            ),
            "session": TierConfig(
                capacity=_int("RATE_LIMIT_SESSION_BURST", 60),
                refill_per_sec=_float_per_min("RATE_LIMIT_SESSION_PER_MIN", 120.0),
            ),
            "ip_auth": TierConfig(
                capacity=_int("RATE_LIMIT_AUTH_BURST", 5),
                refill_per_sec=_float_per_min("RATE_LIMIT_AUTH_PER_MIN", 10.0),
            ),
        }

        bypass_raw = source.get("RATE_LIMIT_BYPASS_ROLES")
        if bypass_raw is not None:
            bypass_roles = {
                role.strip() for role in bypass_raw.split(",") if role.strip()
            }
        else:
            bypass_roles = cls.DEFAULT_BYPASS_ROLES

        return cls(tiers, bypass_roles=bypass_roles, time_source=time_source)

    # ------------------------------------------------------------------- core
    def _bucket_for(self, scope: str, key: str) -> TokenBucket:
        try:
            tier = self._tiers[scope]
        except KeyError as exc:
            raise KeyError(f"Unknown rate-limit scope: {scope!r}") from exc
        scope_map = self._buckets[scope]
        bucket = scope_map.get(key)
        if bucket is not None:
            return bucket
        with self._tier_lock:
            bucket = scope_map.get(key)
            if bucket is None:
                bucket = TokenBucket(
                    capacity=tier.capacity,
                    refill_per_sec=tier.refill_per_sec,
                    time_source=self._time_source,
                )
                scope_map[key] = bucket
        return bucket

    def check(
        self, scope: str, key: str, *, role: Optional[str] = None
    ) -> Tuple[bool, float]:
        """Consume one token from ``(scope, key)``.

        Returns ``(allowed, retry_after_seconds)``. If ``role`` is in
        :attr:`bypass_roles`, always returns ``(True, 0.0)`` without
        touching the bucket.

        Empty/None ``key`` is treated as "no client to bill" and allowed
        through — callers should only invoke ``check`` with a meaningful key
        (e.g. don't call the ``session`` scope for anonymous traffic).

        Short-circuits to ``(True, 0.0)`` when the env var
        ``LVCODEX_RATE_LIMIT_DISABLE`` is set to a truthy value (``1``,
        ``true``, ``yes``, ``on``). This is intended for E2E test suites
        that share a single client IP — production deployments must leave
        the variable unset (the default).
        """

        if is_disabled_via_env():
            return True, 0.0
        if role and role in self.bypass_roles:
            return True, 0.0
        if not key:
            return True, 0.0
        bucket = self._bucket_for(scope, key)
        return bucket.consume()

    def tier(self, scope: str) -> TierConfig:
        return self._tiers[scope]

    def scopes(self) -> Iterable[str]:
        return tuple(self._tiers.keys())

    def reset(self) -> None:
        """Drop all per-key buckets — test helper."""

        with self._tier_lock:
            for scope in self._buckets:
                self._buckets[scope] = {}


# Module-level singleton used by the server.py middleware. Tests can replace
# this with their own instance via ``rate_limit.LIMITER = ...``.
LIMITER: RateLimiter = RateLimiter.from_env()


# Env values treated as "true" for the disable knob. Anything else (including
# unset, "0", "false", "no", etc.) leaves the limiter ENABLED — that is the
# safe production default and MUST NOT be relaxed.
_TRUTHY_DISABLE_VALUES: frozenset[str] = frozenset({"1", "true", "yes", "on"})

# Name of the env variable that disables the limiter. Documented in
# ``docs/rate-limits.md``; set in ``playwright.config.js`` for the E2E run.
DISABLE_ENV_VAR: str = "LVCODEX_RATE_LIMIT_DISABLE"


def is_disabled_via_env(env: Optional[Dict[str, str]] = None) -> bool:
    """Return True when the rate limiter should short-circuit to allow-all.

    Reads the env on every call so test fixtures that mutate
    :data:`os.environ` (or pass an explicit mapping) take effect immediately
    without re-instantiating :data:`LIMITER`. The default (variable unset)
    keeps the limiter ENABLED.
    """

    source = os.environ if env is None else env
    raw = source.get(DISABLE_ENV_VAR)
    if raw is None:
        return False
    return raw.strip().lower() in _TRUTHY_DISABLE_VALUES


def is_auth_path(path: str) -> bool:
    """Return True for ``/api/auth/*`` paths (used by the middleware)."""

    if not path:
        return False
    # Strip query string defensively — middleware should already pass the
    # parsed path, but allow either form.
    cut = path.split("?", 1)[0]
    return cut.startswith("/api/auth/") or cut == "/api/auth"


def is_protected_api_path(path: str) -> bool:
    """Return True if the path falls under the rate-limited API surface.

    Health checks (``/healthz``) are intentionally excluded — they must
    answer regardless of upstream rate-limit state so Fly.io's load
    balancer can keep routing.
    """

    if not path:
        return False
    cut = path.split("?", 1)[0]
    if cut == "/healthz":
        return False
    return cut.startswith("/api/")


def retry_after_header_value(seconds: float) -> str:
    """Render a Retry-After header value (integer seconds, min 1)."""

    rounded = max(1, int(seconds + 0.999))  # ceil, never below 1s
    return str(rounded)
