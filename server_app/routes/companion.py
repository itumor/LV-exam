"""AI companion routes (T-053).

The companion exposes two HTTP routes:

* ``POST /api/companion/chat``       — send a learner message, receive a
                                       tutor reply persisted via the
                                       :data:`companion_memory` table.
* ``GET  /api/companion/nudge``      — daily rules-based nudge derived
                                       from the learner's recent
                                       activity pattern (no LLM call).

The dispatch wiring is installed inside :mod:`server_app.core` (look for
the ``T-053`` hook block) so the do_GET / do_POST wrapper chain stays
in one ordered place — exactly the pattern used by T-031, T-034, T-043.

This module exists so the per-domain modularization audit
(:mod:`tests.server.test_modularization`) can attribute the two routes
to a single owner.
"""

from __future__ import annotations

from server_app.services.companion import (  # noqa: F401
    COMPANION_MEMORY_BYTE_BUDGET,
    CompanionChatRequest,
    CompanionChatResponse,
    CompanionError,
    CompanionInvalidRequest,
    CompanionMemorySnapshot,
    CompanionNudge,
    CompanionProviderError,
    compute_daily_nudge,
    ensure_companion_tables_ready,
    generate_chat_reply,
    load_memory,
    nudge_for_account,
    parse_chat_request,
    truncate_summary,
    update_memory,
)


ROUTES: list[tuple[str, str]] = [
    ("POST", "/api/companion/chat"),
    ("GET", "/api/companion/nudge"),
]


__all__ = [
    "COMPANION_MEMORY_BYTE_BUDGET",
    "CompanionChatRequest",
    "CompanionChatResponse",
    "CompanionError",
    "CompanionInvalidRequest",
    "CompanionMemorySnapshot",
    "CompanionNudge",
    "CompanionProviderError",
    "ROUTES",
    "compute_daily_nudge",
    "ensure_companion_tables_ready",
    "generate_chat_reply",
    "load_memory",
    "nudge_for_account",
    "parse_chat_request",
    "truncate_summary",
    "update_memory",
]
