"""A2 readiness service (T-030).

Computes per-learner readiness for the Latvian A2 naturalisation exam by
aggregating the last N attempts (default 10) into a per-skill predicted
score plus a traffic-light "risk" badge.

Data sources
------------

The service reads from :data:`exam_attempt_category_score`, the table
populated by the attempt-submit hook with per-skill rows shaped
``(account_id, attempt_id, category, score_0_to_15, passed_boolean,
created_at)``. Each finished attempt contributes up to four rows — one
per A2 skill. We keep the most recent ``RECENCY_WINDOW`` attempts for
each skill, weight them by recency (newer attempts count more), and emit
a single rolled-up score per skill.

The 9/15 pass threshold (the A2 naturalisation rule) lives in
:mod:`server_app.services.schema_a2` as :data:`A2_MIN_PER_SKILL` —
:func:`compute_readiness` reuses :func:`schema_a2.is_passing` rather than
hard-coding the integer to keep the rule in a single place.

Output shape
------------

.. code-block:: json

    {
      "skills": [
        {
          "skill": "listening",
          "avg_score": 11.4,
          "predicted_pass": true,
          "badge": "green",
          "sample_size": 5
        },
        ...
      ],
      "overall_pass_predicted": true,
      "last_updated": "2026-05-24T07:48:00Z"
    }

Badge logic
-----------

* ``green``  — ``avg_score >= 12`` (comfortable pass margin).
* ``yellow`` — ``9 <= avg_score < 12`` (borderline; would pass today but
  one bad day flips the result).
* ``red``    — ``avg_score < 9`` (below the 9/15 threshold; the learner
  is currently predicted to fail this skill).

Empty history (no attempts at all in a skill) yields ``badge="red"`` with
``predicted_pass=False`` and ``sample_size=0`` — the dashboard then
nudges the learner to start practising the skill rather than hiding the
row entirely.

Recency weighting
-----------------

Each attempt in the window receives a linear weight: the newest attempt
gets weight ``N`` (where ``N == sample_size``), the next gets ``N-1``,
and so on down to weight ``1`` for the oldest. This gives the most
recent attempt the strongest pull on the rolled-up score without
discarding the historical baseline entirely. We deliberately avoid
fancy decay curves (exponential, half-life) because the regulator-facing
9/15 rule is itself linear and the dashboard needs to be explainable to
the learner.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any, Iterable

from server_app.services import schema_a2

__all__ = [
    "BADGE_GREEN",
    "BADGE_YELLOW",
    "BADGE_RED",
    "BADGE_FOR_PASS_THRESHOLD",
    "BADGE_FOR_COMFORTABLE_PASS",
    "RECENCY_WINDOW",
    "compute_readiness",
    "classify_badge",
    "weighted_average",
]


# ---------------------------------------------------------------------------
# Constants — kept here so dashboards/tests can import them by name.
# ---------------------------------------------------------------------------

#: Number of most-recent attempts considered when rolling up a skill.
RECENCY_WINDOW = 10

BADGE_GREEN = "green"
BADGE_YELLOW = "yellow"
BADGE_RED = "red"

#: Threshold (inclusive) at which a skill earns the green badge.
BADGE_FOR_COMFORTABLE_PASS = 12.0

#: Threshold (inclusive) at which a skill is predicted to pass the 9/15
#: rule — anything below this is the red badge.
BADGE_FOR_PASS_THRESHOLD = float(schema_a2.A2_MIN_PER_SKILL)  # 9.0


# ---------------------------------------------------------------------------
# Pure helpers (no DB access — easy to unit-test).
# ---------------------------------------------------------------------------


def classify_badge(avg_score: float | None, *, sample_size: int) -> str:
    """Map a rolled-up score to a traffic-light badge.

    ``avg_score=None`` (no attempts at all) is treated as red so the UI
    consistently signals "practise this skill" rather than rendering an
    ambiguous "no data" pill.
    """

    if sample_size <= 0 or avg_score is None:
        return BADGE_RED
    if avg_score >= BADGE_FOR_COMFORTABLE_PASS:
        return BADGE_GREEN
    if avg_score >= BADGE_FOR_PASS_THRESHOLD:
        return BADGE_YELLOW
    return BADGE_RED


def weighted_average(scores: Iterable[float]) -> float | None:
    """Linear-recency weighted mean of ``scores``.

    ``scores`` MUST be ordered newest-first (the SQL query already
    enforces this). The most recent value gets weight ``N``, the next
    ``N-1`` and so on down to ``1`` for the oldest. Returns ``None``
    when the iterable is empty so callers can distinguish "no data"
    from a literal zero average.
    """

    values = [float(s) for s in scores]
    n = len(values)
    if n == 0:
        return None
    if n == 1:
        return values[0]
    # Newest first → highest weight first.
    weights = list(range(n, 0, -1))  # [N, N-1, ..., 1]
    numerator = sum(v * w for v, w in zip(values, weights))
    denominator = sum(weights)
    return numerator / denominator


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Main entry point — used by the /api/readiness route handler.
# ---------------------------------------------------------------------------


def compute_readiness(
    conn: sqlite3.Connection,
    account_id: str,
    *,
    window: int = RECENCY_WINDOW,
    now_iso: str | None = None,
) -> dict[str, Any]:
    """Return the readiness payload for ``account_id``.

    Parameters
    ----------
    conn
        Open SQLite/PG connection from :func:`server_app.core.db_connection`.
    account_id
        Account whose readiness is being computed. ``""`` returns the
        empty-history payload (used by the unauthenticated v2 placeholder).
    window
        How many most-recent attempts per skill to consider. Defaults to
        :data:`RECENCY_WINDOW` (10).
    now_iso
        Override timestamp used in ``last_updated``. Tests inject a
        fixed value here; production callers leave it as ``None`` and
        get :func:`datetime.now`.

    Returns
    -------
    dict
        ``{"skills": [...], "overall_pass_predicted": bool,
        "last_updated": "..."}``. The four A2 skills are always present
        in the canonical order even when the learner has zero history —
        callers can render the skeleton without conditional checks.
    """

    skills_payload: list[dict[str, Any]] = []
    per_skill_avg: dict[str, float | None] = {}

    if account_id:
        for skill in schema_a2.A2_SKILLS:
            rows = conn.execute(
                """
                SELECT score_0_to_15, created_at
                FROM exam_attempt_category_score
                WHERE account_id = ? AND category = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (account_id, skill, int(window)),
            ).fetchall()
            scores = [int(r["score_0_to_15"]) for r in rows]
            avg = weighted_average(scores)
            per_skill_avg[skill] = avg
            sample_size = len(scores)
            badge = classify_badge(avg, sample_size=sample_size)
            skills_payload.append(
                {
                    "skill": skill,
                    "avg_score": round(avg, 1) if avg is not None else None,
                    "predicted_pass": _predicted_pass(avg),
                    "badge": badge,
                    "sample_size": sample_size,
                }
            )
    else:
        # No account → emit a skeleton with red badges everywhere. This
        # keeps the SPA placeholder route renderable for logged-out
        # visitors poking at /v2/readiness.
        for skill in schema_a2.A2_SKILLS:
            per_skill_avg[skill] = None
            skills_payload.append(
                {
                    "skill": skill,
                    "avg_score": None,
                    "predicted_pass": False,
                    "badge": BADGE_RED,
                    "sample_size": 0,
                }
            )

    overall = _overall_pass(per_skill_avg)
    return {
        "skills": skills_payload,
        "overall_pass_predicted": overall,
        "last_updated": now_iso or _now_iso(),
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _predicted_pass(avg_score: float | None) -> bool:
    """Single-skill pass prediction — the 9/15 rule in float form."""

    if avg_score is None:
        return False
    return avg_score >= BADGE_FOR_PASS_THRESHOLD


def _overall_pass(per_skill_avg: dict[str, float | None]) -> bool:
    """All four A2 skills must be predicted to pass for the overall flag.

    Funnels through :func:`schema_a2.is_passing` so the 9/15-per-skill
    rule lives in exactly one place. We pass ``int(round(avg))`` because
    ``is_passing`` operates on integer points — for the readiness
    prediction we round to the nearest integer so a 8.9 average flips to
    9 (consistent with how the learner perceives a "just-passing"
    average) — but the underlying ``avg_score`` we surface to the UI is
    still the float so the dashboard can render the precise number.
    """

    rounded_scores: dict[str, int] = {}
    for skill, avg in per_skill_avg.items():
        if avg is None:
            # Any missing skill cannot pass overall — short-circuit to
            # match ``is_passing``'s semantics for absent keys.
            return False
        rounded_scores[skill] = int(round(avg))
    return schema_a2.is_passing(rounded_scores)
