"""T-051 — Avatar + cosmetics route module (re-export shim).

The actual dispatch wiring lives in :mod:`server_app.core` (look for
the ``T-051`` hook block) so the ``do_GET`` / ``do_POST`` wrappers can
be installed at the right point in the chain — specifically BEFORE
the T-036 SPA static handler so T-036 stays the outermost ``do_GET``
wrapper.

This module exists for two reasons:

1. The modularization audit (``tests/server/test_modularization.py``)
   reads ``ROUTES`` from each per-domain module to verify every
   documented route resolves to a dispatch path.
2. Re-exporting the service surface keeps a stable import path
   (``server_app.routes.avatars``) for downstream callers and tests.
"""

from __future__ import annotations

from server_app.services.avatars import (  # noqa: F401
    Avatar,
    AvatarError,
    AvatarLockedError,
    AvatarNotFoundError,
    SOURCE_ADMIN_GRANT,
    SOURCE_FREE,
    SOURCE_PREMIUM,
    SOURCE_XP,
    UNLOCK_FREE,
    UNLOCK_PREMIUM,
    UNLOCK_XP,
    ensure_avatar_schema,
    equip_avatar,
    get_equipped,
    grant_xp_unlocks,
    list_unlocked,
    load_catalog,
    unlock_avatar,
)

ROUTES: list[tuple[str, str]] = [
    ("GET", "/api/avatars"),
    ("POST", "/api/avatars/equip"),
    ("POST", "/api/avatars/unlock"),
]

__all__ = [
    "Avatar",
    "AvatarError",
    "AvatarLockedError",
    "AvatarNotFoundError",
    "ROUTES",
    "SOURCE_ADMIN_GRANT",
    "SOURCE_FREE",
    "SOURCE_PREMIUM",
    "SOURCE_XP",
    "UNLOCK_FREE",
    "UNLOCK_PREMIUM",
    "UNLOCK_XP",
    "ensure_avatar_schema",
    "equip_avatar",
    "get_equipped",
    "grant_xp_unlocks",
    "list_unlocked",
    "load_catalog",
    "unlock_avatar",
]
