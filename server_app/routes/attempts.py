"""Attempt-lifecycle routes (T-020).

Covers the full attempt CRUD surface plus the AI ``/api/evaluate``
scoring endpoint (which is grouped here because it consumes the same
session + quota stack as attempt submission). The history/analytics
read endpoints also live in this group.

T-024 — server-enforced entitlements
------------------------------------

The T-024 hook block at the end of :mod:`server_app.core` gates the
following routes BEFORE the handler body executes (admin / superadmin
bypass; free / non-paying users get HTTP 402):

* ``POST /api/attempts/start``  -> ``kind="exam_unlock"``
* ``POST /api/evaluate``        -> ``kind="ai_credit"``
* ``POST /api/uploads/speaking`` (owned by :mod:`server_app.routes.uploads`)
  -> ``kind="exam_unlock"``

The hook is intentionally read-only — actual consumption stays inside
the handler body via :meth:`billing.BillingStore.consume_exam_access`
and :meth:`billing.BillingStore.consume_ai_credit`. The two layers
together cover both denial (gate) and overcounting (lock + write).
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
from server_app.services.entitlements import (  # noqa: F401
    EntitlementError,
    entitled,
    require_entitlement,
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
    # T-030 — A2 readiness dashboard (per-skill 9/15 + badges).
    ("GET", "/api/readiness"),
]

__all__ = [
    "EntitlementError",
    "ROUTES",
    "build_dashboard",
    "entitled",
    "evaluate_submission",
    "expire_attempt",
    "load_owned_attempt",
    "persist_attempt",
    "redact_attempt_for_learner",
    "redact_score_payload_for_learner",
    "require_entitlement",
    "save_attempt_answer",
    "serialize_attempt",
    "serialize_attempt_for_learner",
    "start_attempt",
    "submit_attempt",
]
