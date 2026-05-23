"""DB row mappers / dataclasses (T-020).

Re-exports the row-serialisation helpers from :mod:`server_app.core` so
that downstream code can ``from server_app.models import
serialize_attempt`` instead of reaching into ``server.py``.

Sub-modules:
    * :mod:`server_app.models.ai` — pydantic schemas for AI scoring
      payloads (T-026).
"""

from __future__ import annotations

from server_app.core import (  # noqa: F401
    ApiError,
    redact_attempt_for_learner,
    redact_score_payload_for_learner,
    serialize_account,
    serialize_attempt,
    serialize_attempt_for_learner,
    serialize_exam_catalog,
    serialize_profile,
)
from . import ai  # noqa: F401

__all__ = [
    "ApiError",
    "ai",
    "redact_attempt_for_learner",
    "redact_score_payload_for_learner",
    "serialize_account",
    "serialize_attempt",
    "serialize_attempt_for_learner",
    "serialize_exam_catalog",
    "serialize_profile",
]
