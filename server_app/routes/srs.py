"""T-032 — Spaced-repetition (SRS) routes (re-export module).

The actual dispatch wiring lives in :mod:`server_app.core` (look for the
``T-032`` hook block) so it can be installed at the right point in the
``do_GET`` / ``do_POST`` wrapper chain — specifically **before** the
T-036 SPA static handler so the static handler remains the outermost
``do_GET`` wrapper.

This module exists for two reasons:

1. The modularization audit (``tests/server/test_modularization.py``)
   reads ``ROUTES`` from each per-domain module to verify every
   documented route resolves to a dispatch path.
2. Re-exporting the service surface keeps a stable import path
   (``server_app.routes.srs``) for downstream code and tests.
"""

from __future__ import annotations

from server_app.services.srs import (  # noqa: F401
    DEFAULT_DUE_LIMIT,
    DEFAULT_EASE,
    FIRST_INTERVAL_DAYS,
    MIN_EASE,
    RECALL_THRESHOLD,
    SECOND_INTERVAL_DAYS,
    add_card,
    due_cards,
    ensure_srs_schema,
    get_card,
    review_card,
)

ROUTES: list[tuple[str, str]] = [
    ("GET", "/api/srs/due"),
    ("POST", "/api/srs/cards"),
    ("POST", "/api/srs/cards/{card_id}/review"),
]

__all__ = [
    "DEFAULT_DUE_LIMIT",
    "DEFAULT_EASE",
    "FIRST_INTERVAL_DAYS",
    "MIN_EASE",
    "RECALL_THRESHOLD",
    "ROUTES",
    "SECOND_INTERVAL_DAYS",
    "add_card",
    "due_cards",
    "ensure_srs_schema",
    "get_card",
    "review_card",
]
