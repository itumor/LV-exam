"""LLM evaluator service (T-020, T-026).

Re-exports the LLM-evaluation pipeline (prompt builder, provider calls,
retry/quota plumbing) from :mod:`server_app.core`. Provider selection is
environment-driven (``LLM_PROVIDER``); see ``provider_config`` for the
resolution logic.

T-026 additions
---------------
* :func:`call_with_retry` — provider-aware exponential-backoff retry policy
  (max 3 attempts by default, distinct from the request-rate limit at
  :func:`check_scoring_rate_limit`). Backoff is per-provider: Groq backs off
  faster (smaller base) because its 429s clear quickly, OpenAI/Codex backs
  off slower because timeouts there are usually upstream model congestion.
* :func:`build_provider_unavailable_response` — formats the HTTP 503 body
  emitted when all retries exhaust, so callers don't have to know the
  pydantic schema name.
* :func:`validate_ai_response_with_pydantic` — pydantic-backed validation of
  the LLM response payload. Falls through to the legacy
  ``validate_and_normalize_evaluation_payload`` for the merge-into-locked-
  scores step.
"""

from __future__ import annotations

import json
import logging
import random
import time
from typing import Any, Callable, Optional

from pydantic import ValidationError

from server_app.core import (  # noqa: F401
    EvaluationError,
    ProviderResponseError,
    ai_scoring_requires_credit,
    build_evaluation_prompt,
    call_codex,
    call_codex_remote,
    call_groq,
    compact_submission,
    evaluate_submission,
    merge_local_and_ai_scores,
    provider_call_once,
    provider_config,
    provider_error_message,
    validate_and_normalize_evaluation_payload,
)
from server_app.models.ai import (
    AIEvaluationResponse,
    AIProviderUnavailableDetails,
    AIScoreRequest,
)


logger = logging.getLogger("lvcodex.evaluator")


# ---------------------------------------------------------------------------
# Provider-aware retry policy (T-026)
# ---------------------------------------------------------------------------


# Backoff base seconds per provider. Groq replies fast and most errors clear
# under 1s; OpenAI/Codex 5xx + timeouts usually need longer waits. We cap each
# at MAX_BACKOFF_SECONDS to keep the request thread responsive (the request
# handler holds a TCP connection while we retry).
PROVIDER_BACKOFF_BASE_SECONDS = {
    "groq": 0.5,
    "codex": 1.5,
    "openai": 1.5,
}
DEFAULT_BACKOFF_BASE_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 8.0
DEFAULT_MAX_ATTEMPTS = 3


def provider_backoff_base(provider: str) -> float:
    """Return the per-provider exponential-backoff base in seconds.

    Falls back to :data:`DEFAULT_BACKOFF_BASE_SECONDS` for unknown providers.
    """

    return PROVIDER_BACKOFF_BASE_SECONDS.get(
        (provider or "").strip().lower(), DEFAULT_BACKOFF_BASE_SECONDS
    )


def compute_backoff_delay(
    attempt: int,
    *,
    provider: str,
    jitter: bool = True,
    base_seconds: Optional[float] = None,
    max_seconds: float = MAX_BACKOFF_SECONDS,
) -> float:
    """Exponential backoff with optional jitter, per provider.

    ``attempt`` is 1-indexed (first retry = attempt 1). The delay is
    ``base * 2^(attempt-1)`` clamped to ``max_seconds``. Jitter adds up to
    25 % randomness so concurrent failing requests don't reconverge in
    lockstep (thundering-herd safeguard).
    """

    if attempt < 1:
        return 0.0
    base = base_seconds if base_seconds is not None else provider_backoff_base(provider)
    raw = base * (2 ** (attempt - 1))
    delay = min(raw, max_seconds)
    if jitter:
        delay = delay * (1 + random.uniform(-0.25, 0.25))
    return max(0.0, delay)


def call_with_retry(
    fn: Callable[[], Any],
    *,
    provider: str,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
    on_attempt: Optional[Callable[[int, Optional[BaseException]], None]] = None,
    retriable_exceptions: tuple[type[BaseException], ...] = (
        ProviderResponseError,
        TimeoutError,
        ConnectionError,
        OSError,
    ),
) -> Any:
    """Run ``fn`` up to ``max_attempts`` times with exponential backoff.

    Distinct from the per-IP token bucket in ``rate_limit.py`` — this retry
    operates *inside* a single request after the rate limit has already
    admitted it. The two layers compose: rate limit gates ingress, retry
    smooths over transient provider blips.

    Non-retriable failures (e.g. ``ValueError`` for a malformed LLM payload)
    re-raise immediately. Retriable errors trigger a backoff sleep, except
    after the final attempt when we re-raise so the caller can wrap into a
    503 response.
    """

    if max_attempts < 1:
        raise ValueError("max_attempts must be ≥ 1")

    last_error: Optional[BaseException] = None
    for attempt in range(1, max_attempts + 1):
        try:
            result = fn()
            if on_attempt is not None:
                on_attempt(attempt, None)
            return result
        except retriable_exceptions as error:  # type: ignore[misc]
            last_error = error
            if on_attempt is not None:
                on_attempt(attempt, error)
            if attempt >= max_attempts:
                break
            delay = compute_backoff_delay(attempt, provider=provider)
            logger.warning(
                "ai_provider_retry provider=%s attempt=%s delay=%.2fs error=%s",
                provider,
                attempt,
                delay,
                error,
            )
            sleep(delay)
        except Exception as error:  # noqa: BLE001 - non-retriable surface
            if on_attempt is not None:
                on_attempt(attempt, error)
            raise

    # All retries exhausted — re-raise the last seen retriable error so the
    # caller can decide whether to translate to a 503 (provider down) or a
    # 504 (timeout). We never swallow.
    assert last_error is not None  # noqa: S101 — by construction, see loop above
    raise last_error


# ---------------------------------------------------------------------------
# Pydantic validation (T-026)
# ---------------------------------------------------------------------------


def parse_ai_score_request(raw: Any) -> AIScoreRequest:
    """Validate an inbound AI scoring request using the pydantic model.

    Raises :class:`EvaluationError` (status 400) on validation failure so the
    HTTP layer can render a 400 with the field-level errors verbatim.
    """

    try:
        return AIScoreRequest.model_validate(raw)
    except ValidationError as error:
        raise EvaluationError(
            "AI scoring request payload failed schema validation.",
            status_code=400,
            retry_state="invalid_request",
            telemetry={"validation_errors": error.errors()},
        ) from error


def validate_ai_response_with_pydantic(raw_payload: Any) -> AIEvaluationResponse:
    """Validate an LLM scoring response using the pydantic model.

    The legacy hand-written validator in ``server_app.core`` is still used by
    the historic dispatch path; this function provides a strict, typed entry
    point for new code (T-045 NPC scoring, T-046 voice pipeline).

    Raises :class:`EvaluationError` (status 502) on validation failure so the
    HTTP layer can render the upstream-misbehaved error consistently.
    """

    try:
        return AIEvaluationResponse.model_validate(raw_payload)
    except ValidationError as error:
        raise EvaluationError(
            "AI provider returned a payload that failed schema validation.",
            status_code=502,
            retry_state="invalid_response",
            telemetry={"validation_errors": error.errors()},
        ) from error


# ---------------------------------------------------------------------------
# Failure-mode helpers (T-026 — visible failure modes per roadmap A P3)
# ---------------------------------------------------------------------------


def build_provider_unavailable_response(
    *,
    provider: str,
    attempts: int,
    retry_after_seconds: int = 60,
    message: Optional[str] = None,
) -> dict[str, Any]:
    """Render the HTTP 503 body for a provider-down scenario.

    Returns a JSON-serialisable dict matching
    :class:`AIProviderUnavailableDetails`. Callers should wrap this in
    ``{"error": …}`` to match the application's existing ApiError envelope.
    """

    detail = AIProviderUnavailableDetails(
        message=message
        or (
            f"AI scoring provider '{provider}' is temporarily unavailable. "
            "Please retry shortly."
        ),
        provider=provider,
        attempts=max(1, attempts),
        retry_after_seconds=max(1, min(retry_after_seconds, 86_400)),
    )
    return json.loads(detail.model_dump_json())


__all__ = [
    "DEFAULT_BACKOFF_BASE_SECONDS",
    "DEFAULT_MAX_ATTEMPTS",
    "EvaluationError",
    "MAX_BACKOFF_SECONDS",
    "PROVIDER_BACKOFF_BASE_SECONDS",
    "ProviderResponseError",
    "ai_scoring_requires_credit",
    "build_evaluation_prompt",
    "build_provider_unavailable_response",
    "call_codex",
    "call_codex_remote",
    "call_groq",
    "call_with_retry",
    "compact_submission",
    "compute_backoff_delay",
    "evaluate_submission",
    "merge_local_and_ai_scores",
    "parse_ai_score_request",
    "provider_backoff_base",
    "provider_call_once",
    "provider_config",
    "provider_error_message",
    "validate_ai_response_with_pydantic",
    "validate_and_normalize_evaluation_payload",
]
