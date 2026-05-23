"""Attempt-lifecycle routes (T-020).

Covers the full attempt CRUD surface plus the AI ``/api/evaluate``
scoring endpoint (which is grouped here because it consumes the same
session + quota stack as attempt submission). The history/analytics
read endpoints also live in this group.
"""

from __future__ import annotations

from server_app.core import (  # noqa: F401
    build_dashboard,
    expire_attempt,
    evaluate_submission,
    load_owned_attempt,
    persist_attempt,
    redact_attempt_for_learner,
    redact_score_payload_for_learner,
    save_attempt_answer,
    serialize_attempt,
    serialize_attempt_for_learner,
    start_attempt,
    submit_attempt,
)

ROUTES: list[tuple[str, str]] = [
    ("GET", "/api/attempts"),
    ("GET", "/api/attempts/<attempt_id>"),
    ("POST", "/api/attempts/start"),
    ("POST", "/api/attempts/<attempt_id>/answers"),
    ("POST", "/api/attempts/<attempt_id>/submit"),
    ("POST", "/api/attempts/<attempt_id>/expire"),
    ("POST", "/api/attempts/history"),
    ("POST", "/api/attempts/analytics"),
    ("GET", "/api/dashboard"),
    ("POST", "/api/evaluate"),
]

__all__ = [
    "ROUTES",
    "build_dashboard",
    "evaluate_submission",
    "expire_attempt",
    "load_owned_attempt",
    "persist_attempt",
    "redact_attempt_for_learner",
    "redact_score_payload_for_learner",
    "save_attempt_answer",
    "serialize_attempt",
    "serialize_attempt_for_learner",
    "start_attempt",
    "submit_attempt",
]
