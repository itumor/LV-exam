"""T-035 — Vertical "TikTok-style" listening feed routes.

Owns the two endpoints that power the feed UI shipped under
``latvian-listening-library/web/feed.html``:

* ``GET  /api/listening-feed?cursor=...&limit=...`` — paginated feed of
  curated clips with embedded micro-quizzes (one multiple-choice
  question per clip). Reuses the curated catalogue at
  ``latvian-listening-library/web/microClips.json`` so we don't
  duplicate audio assets between the legacy ``micro.html`` UI and the
  new feed.
* ``POST /api/listening-feed/{clip_id}/answer`` — submit the learner's
  quiz answer. Returns correctness + XP delta and persists the answer
  to ``listening_feed_answers`` for downstream analytics (T-030
  readiness dashboard, T-034 XP engine).

The dispatch wiring lives in :mod:`server_app.core` — this module only
declares ownership and re-exports the service surface so the
modularization audit (``tests/server/test_modularization.py``) can
verify the routes resolve to a known dispatch path.
"""

from __future__ import annotations

from server_app.services.listening_feed import (  # noqa: F401
    build_listening_feed,
    correct_index_for,
    find_clip,
    load_clips,
    record_quiz_answer,
)

ROUTES: list[tuple[str, str]] = [
    ("GET", "/api/listening-feed"),
    ("POST", "/api/listening-feed/<clip_id>/answer"),
]

__all__ = [
    "ROUTES",
    "build_listening_feed",
    "correct_index_for",
    "find_clip",
    "load_clips",
    "record_quiz_answer",
]
