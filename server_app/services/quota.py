"""Quota / rate-limit service (T-020).

Re-exports the daily / hourly per-learner quota helpers and the
in-process per-IP rate limiter used by the auth + scoring routes.
The token-bucket implementation (T-015) lives in
:mod:`rate_limit` (top-level module); this service module wraps the
quota-checking surface that consumers use.
"""

from __future__ import annotations

from server_app.core import (  # noqa: F401
    QuotaExceededError,
    check_rate_limit,
    check_scoring_rate_limit,
    cost_rate_cents_per_1k_tokens,
    estimate_request_cost_cents,
    estimate_text_tokens,
    plan_cost_limit_cents,
    plan_request_limit,
    reserve_quota,
    retry_limit,
    validate_submission_size,
)

__all__ = [
    "QuotaExceededError",
    "check_rate_limit",
    "check_scoring_rate_limit",
    "cost_rate_cents_per_1k_tokens",
    "estimate_request_cost_cents",
    "estimate_text_tokens",
    "plan_cost_limit_cents",
    "plan_request_limit",
    "reserve_quota",
    "retry_limit",
    "validate_submission_size",
]
