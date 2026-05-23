"""LLM evaluator service (T-020).

Re-exports the LLM-evaluation pipeline (prompt builder, provider calls,
retry/quota plumbing) from :mod:`server_app.core`. Provider selection
is environment-driven (``LLM_PROVIDER``); see ``provider_config`` for
the resolution logic.
"""

from __future__ import annotations

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

__all__ = [
    "EvaluationError",
    "ProviderResponseError",
    "ai_scoring_requires_credit",
    "build_evaluation_prompt",
    "call_codex",
    "call_codex_remote",
    "call_groq",
    "compact_submission",
    "evaluate_submission",
    "merge_local_and_ai_scores",
    "provider_call_once",
    "provider_config",
    "provider_error_message",
    "validate_and_normalize_evaluation_payload",
]
