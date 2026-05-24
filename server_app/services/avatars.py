"""T-051 — Avatar + cosmetics unlock service.

This module is the server-side source of truth for "which avatar is
this learner allowed to wear?". It pairs a static catalog of avatar
configurations (loaded from ``content/avatars/*.json``) with a small
unlock ledger persisted in ``avatar_unlocks``.

Three unlock tiers
------------------

Every avatar in the catalog declares exactly one of three unlock
contracts:

* ``free`` — every account holds the unlock implicitly. The catalog
  listing always reports ``unlocked=True`` for these, even before any
  row is written into ``avatar_unlocks``. We still allow the row to
  be created (so the audit ledger is uniform) but :func:`list_unlocked`
  never depends on it.
* ``xp`` — requires ``unlock.xp`` lifetime XP. The XP total is read
  from the ``xp_log`` table maintained by T-034 (sum of ``amount`` per
  ``account_id``). When the learner crosses the threshold,
  :func:`unlock_avatar` writes an ``avatar_unlocks`` row with
  ``source = 'xp'``.
* ``premium`` — requires an active subscription. The check goes
  through :class:`billing.BillingStore` (the same store the T-024
  entitlement gate uses). Institutional seat-holders (T-041) also
  satisfy the premium gate — same precedent as
  :func:`server_app.services.entitlements.require_entitlement`.

The split matters: a learner with infinite XP cannot wear a premium
avatar. A subscriber does *not* automatically own every XP avatar —
each must still be unlocked through XP play. The two ledgers stay
independent so a premium downgrade does not silently delete XP-earned
unlocks.

Schema
------

``avatar_unlocks`` (created lazily on first request):

    account_id    TEXT NOT NULL
    avatar_id     TEXT NOT NULL
    unlocked_at   TEXT NOT NULL   -- ISO-8601 UTC
    source        TEXT NOT NULL   -- 'xp' | 'premium' | 'free' | 'admin_grant'
    PRIMARY KEY (account_id, avatar_id)

Equipped avatar
---------------

``account_avatars`` is a tiny key/value table holding the currently
equipped avatar for an account. Equipping refuses any avatar the
account has not unlocked first, so the equip is a strictly downstream
operation of :func:`unlock_avatar` / :func:`list_unlocked`.

Public surface
--------------

``load_catalog(refresh=False) -> dict[str, Avatar]``
    Read ``content/avatars/*.json`` once and cache. ``refresh=True`` is
    used by tests pointing at a fixture directory.

``ensure_avatar_schema(conn) -> None``
    Idempotent DDL applier for ``avatar_unlocks`` + ``account_avatars``.

``unlock_avatar(conn, account_id, avatar_id, *, billing_state=None,
              now=None) -> dict``
    Apply the unlock contract and write a ledger row. Returns the
    resolved unlock state ``{avatar_id, source, unlocked_at,
    already_unlocked}``. Raises :class:`AvatarLockedError` if the
    learner does not satisfy the contract.

``list_unlocked(conn, account_id, *, billing_state=None) -> list[dict]``
    Return every avatar in the catalog with computed flags
    ``{unlocked, equipped, locked_reason}``. The frontend uses this
    to render the picker — locked avatars stay visible (greyed out)
    with a reason ("Reach 500 XP" / "Subscriber only").

``equip_avatar(conn, account_id, avatar_id) -> dict``
    Set ``account_avatars.equipped = avatar_id``. Refuses if the
    avatar is not in :func:`list_unlocked` for this account.

``get_equipped(conn, account_id) -> dict | None``
    Read the currently-equipped avatar (full catalog row).
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger("lvcodex.avatars")


# ---------------------------------------------------------------------------
# Catalog loader
# ---------------------------------------------------------------------------

UNLOCK_FREE = "free"
UNLOCK_XP = "xp"
UNLOCK_PREMIUM = "premium"
_VALID_KINDS = frozenset({UNLOCK_FREE, UNLOCK_XP, UNLOCK_PREMIUM})

#: Source values written into ``avatar_unlocks.source``.
SOURCE_FREE = "free"
SOURCE_XP = "xp"
SOURCE_PREMIUM = "premium"
SOURCE_ADMIN_GRANT = "admin_grant"

_DEFAULT_CATALOG_DIR = Path(__file__).resolve().parents[2] / "content" / "avatars"


@dataclass(frozen=True)
class Avatar:
    """Immutable in-memory representation of one ``content/avatars/*.json``."""

    id: str
    display_name: str
    description: str
    art_ref: str
    rarity: str
    tier: str
    unlock_kind: str
    unlock_xp: int = 0
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_free(self) -> bool:
        return self.unlock_kind == UNLOCK_FREE

    @property
    def is_xp(self) -> bool:
        return self.unlock_kind == UNLOCK_XP

    @property
    def is_premium(self) -> bool:
        return self.unlock_kind == UNLOCK_PREMIUM

    def to_public(self) -> dict[str, Any]:
        """Serialisable shape used by the HTTP layer."""

        return {
            "id": self.id,
            "display_name": self.display_name,
            "description": self.description,
            "art_ref": self.art_ref,
            "rarity": self.rarity,
            "tier": self.tier,
            "unlock": (
                {"kind": self.unlock_kind, "xp": self.unlock_xp}
                if self.is_xp
                else {"kind": self.unlock_kind}
            ),
        }


_CATALOG_CACHE: dict[str, Avatar] | None = None
_CATALOG_CACHE_DIR: Path | None = None
_CATALOG_LOCK = threading.Lock()


def _catalog_dir() -> Path:
    """Resolve the catalog directory.

    The env override (``LVCODEX_AVATARS_DIR``) is the same pattern used
    by the listening-feed module — keeps tests hermetic by pointing at
    a tmp directory of JSON fixtures.
    """

    override = os.environ.get("LVCODEX_AVATARS_DIR")
    if override:
        return Path(override)
    return _DEFAULT_CATALOG_DIR


def _coerce_avatar(payload: dict[str, Any]) -> Avatar:
    avatar_id = str(payload.get("id") or "").strip()
    if not avatar_id:
        raise ValueError("avatar config missing 'id'")
    unlock = payload.get("unlock") or {}
    if not isinstance(unlock, dict):
        raise ValueError(f"{avatar_id}: 'unlock' must be an object")
    kind = str(unlock.get("kind") or "").strip()
    if kind not in _VALID_KINDS:
        raise ValueError(
            f"{avatar_id}: unlock.kind must be one of {sorted(_VALID_KINDS)}"
        )
    xp_required = 0
    if kind == UNLOCK_XP:
        try:
            xp_required = int(unlock.get("xp") or 0)
        except (TypeError, ValueError):
            xp_required = 0
        if xp_required <= 0:
            raise ValueError(
                f"{avatar_id}: unlock.xp must be a positive integer"
            )
    return Avatar(
        id=avatar_id,
        display_name=str(payload.get("display_name") or avatar_id),
        description=str(payload.get("description") or ""),
        art_ref=str(payload.get("art_ref") or ""),
        rarity=str(payload.get("rarity") or "common"),
        tier=str(payload.get("tier") or kind),
        unlock_kind=kind,
        unlock_xp=xp_required,
        raw=payload,
    )


def load_catalog(*, refresh: bool = False) -> dict[str, Avatar]:
    """Return ``{avatar_id: Avatar}`` for every JSON in the catalog dir.

    The result is cached. ``refresh=True`` reloads (used by tests that
    swap the catalog directory via ``LVCODEX_AVATARS_DIR``). The cache
    is also invalidated when the directory the cache was built from no
    longer matches :func:`_catalog_dir` — so simply changing the env
    var between requests does the right thing in tests.
    """

    global _CATALOG_CACHE, _CATALOG_CACHE_DIR
    target = _catalog_dir()
    if not refresh and _CATALOG_CACHE is not None and _CATALOG_CACHE_DIR == target:
        return _CATALOG_CACHE
    with _CATALOG_LOCK:
        if not refresh and _CATALOG_CACHE is not None and _CATALOG_CACHE_DIR == target:
            return _CATALOG_CACHE
        loaded: dict[str, Avatar] = {}
        if target.exists():
            for path in sorted(target.glob("*.json")):
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as error:
                    logger.warning(
                        "avatars: failed to load %s — %s",
                        path,
                        error,
                    )
                    continue
                if not isinstance(payload, dict):
                    logger.warning("avatars: %s is not a JSON object", path)
                    continue
                try:
                    avatar = _coerce_avatar(payload)
                except ValueError as error:
                    logger.warning("avatars: %s", error)
                    continue
                if avatar.id in loaded:
                    logger.warning("avatars: duplicate id %s in catalog", avatar.id)
                    continue
                loaded[avatar.id] = avatar
        _CATALOG_CACHE = loaded
        _CATALOG_CACHE_DIR = target
        return loaded


def _reset_catalog_cache_for_tests() -> None:
    """Drop the catalog cache — used by tests."""

    global _CATALOG_CACHE, _CATALOG_CACHE_DIR
    with _CATALOG_LOCK:
        _CATALOG_CACHE = None
        _CATALOG_CACHE_DIR = None


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS avatar_unlocks (
    account_id   TEXT NOT NULL,
    avatar_id    TEXT NOT NULL,
    unlocked_at  TEXT NOT NULL,
    source       TEXT NOT NULL,
    PRIMARY KEY (account_id, avatar_id)
);

CREATE INDEX IF NOT EXISTS idx_avatar_unlocks_account
    ON avatar_unlocks(account_id);

CREATE TABLE IF NOT EXISTS account_avatars (
    account_id  TEXT PRIMARY KEY,
    avatar_id   TEXT NOT NULL,
    equipped_at TEXT NOT NULL
);
"""

_DDL_APPLIED = False
_DDL_LOCK = threading.Lock()


def ensure_avatar_schema(conn: sqlite3.Connection) -> None:
    """Create the avatar tables once per process."""

    global _DDL_APPLIED
    if _DDL_APPLIED:
        return
    with _DDL_LOCK:
        if _DDL_APPLIED:
            return
        conn.executescript(_DDL)
        _DDL_APPLIED = True


def _reset_ddl_cache_for_tests() -> None:
    global _DDL_APPLIED
    with _DDL_LOCK:
        _DDL_APPLIED = False


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class AvatarError(Exception):
    """Base error for avatar operations."""


class AvatarNotFoundError(AvatarError):
    """Raised when the requested avatar id is not in the catalog."""


class AvatarLockedError(AvatarError):
    """Raised when :func:`unlock_avatar` cannot satisfy the contract."""

    def __init__(
        self,
        avatar_id: str,
        *,
        reason: str,
        required: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            f"Avatar {avatar_id!r} is locked (reason: {reason})."
        )
        self.avatar_id = avatar_id
        self.reason = reason
        self.required = required or {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def _iso(now: datetime) -> str:
    return now.isoformat().replace("+00:00", "Z")


def _total_xp(conn: sqlite3.Connection, account_id: str) -> int:
    """Sum ``xp_log.amount`` for ``account_id``.

    Returns ``0`` when ``xp_log`` does not exist yet (T-034 schema
    hasn't been applied) — keeps the avatar service usable in tests
    that don't bootstrap the XP module.
    """

    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total "
            "FROM xp_log WHERE account_id = ?",
            (account_id,),
        ).fetchone()
    except sqlite3.OperationalError:
        return 0
    if row is None:
        return 0
    try:
        return int(row["total"] or 0)
    except (IndexError, KeyError, TypeError):
        return int(row[0] or 0)


def _premium_active(billing_state: dict[str, Any] | None) -> bool:
    """Return True if the supplied billing state authorises premium.

    The mapping mirrors :mod:`server_app.services.entitlements`: an
    active subscription, an institutional seat (signalled via
    ``has_active_seat``), or the admin-unlimited plan all count.
    """

    if billing_state is None:
        return False
    if billing_state.get("frozen"):
        return False
    if billing_state.get("current_plan") == "admin_unlimited":
        return True
    if billing_state.get("subscription_active"):
        return True
    if billing_state.get("has_active_seat"):
        return True
    return False


def _existing_unlock(
    conn: sqlite3.Connection, account_id: str, avatar_id: str
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT account_id, avatar_id, unlocked_at, source
        FROM avatar_unlocks
        WHERE account_id = ? AND avatar_id = ?
        """,
        (account_id, avatar_id),
    ).fetchone()
    if row is None:
        return None
    return {
        "account_id": row["account_id"],
        "avatar_id": row["avatar_id"],
        "unlocked_at": row["unlocked_at"],
        "source": row["source"],
    }


def _insert_unlock(
    conn: sqlite3.Connection,
    *,
    account_id: str,
    avatar_id: str,
    source: str,
    unlocked_at: str,
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO avatar_unlocks
            (account_id, avatar_id, unlocked_at, source)
        VALUES (?, ?, ?, ?)
        """,
        (account_id, avatar_id, unlocked_at, source),
    )


def _account_unlock_ids(
    conn: sqlite3.Connection, account_id: str
) -> set[str]:
    rows = conn.execute(
        "SELECT avatar_id FROM avatar_unlocks WHERE account_id = ?",
        (account_id,),
    ).fetchall()
    return {row["avatar_id"] for row in rows}


def _equipped_id(conn: sqlite3.Connection, account_id: str) -> str | None:
    row = conn.execute(
        "SELECT avatar_id FROM account_avatars WHERE account_id = ?",
        (account_id,),
    ).fetchone()
    if row is None:
        return None
    return row["avatar_id"]


# ---------------------------------------------------------------------------
# Locked-reason resolver
# ---------------------------------------------------------------------------


def _resolve_lock(
    avatar: Avatar,
    *,
    total_xp: int,
    premium_active: bool,
) -> tuple[bool, str | None, dict[str, Any]]:
    """Return ``(unlocked, reason, required)`` for a not-yet-stored avatar.

    Free avatars always unlock. XP avatars unlock when ``total_xp >=
    unlock_xp``. Premium avatars unlock only when ``premium_active`` is
    True — even with infinite XP, the gate stays closed.
    """

    if avatar.is_free:
        return (True, None, {})
    if avatar.is_xp:
        if total_xp >= avatar.unlock_xp:
            return (True, None, {})
        return (
            False,
            f"Reach {avatar.unlock_xp} XP",
            {"kind": "xp", "xp": avatar.unlock_xp, "have": total_xp},
        )
    if avatar.is_premium:
        if premium_active:
            return (True, None, {})
        return (
            False,
            "Subscriber only",
            {"kind": "premium"},
        )
    # Defensive: unknown kind — treat as locked.
    return (False, "Unknown lock", {"kind": avatar.unlock_kind})  # pragma: no cover


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def unlock_avatar(
    conn: sqlite3.Connection,
    account_id: str,
    avatar_id: str,
    *,
    billing_state: dict[str, Any] | None = None,
    now: datetime | None = None,
    source_override: str | None = None,
) -> dict[str, Any]:
    """Unlock ``avatar_id`` for ``account_id`` if the contract is satisfied.

    * If the unlock already exists, returns the existing row with
      ``already_unlocked=True``. No DDL / write side-effect.
    * Otherwise evaluates the contract:
        - ``free`` → always succeeds.
        - ``xp``   → succeeds when ``sum(xp_log.amount) >= unlock.xp``.
        - ``premium`` → succeeds when ``billing_state`` proves an
          active subscription / institutional seat.
    * On success writes one row into ``avatar_unlocks`` and returns
      it with ``already_unlocked=False``.

    Raises :class:`AvatarNotFoundError` for unknown avatar ids and
    :class:`AvatarLockedError` when the contract is not satisfied.
    """

    if not account_id:
        raise ValueError("account_id is required")
    if not avatar_id:
        raise ValueError("avatar_id is required")
    catalog = load_catalog()
    avatar = catalog.get(avatar_id)
    if avatar is None:
        raise AvatarNotFoundError(f"Unknown avatar id {avatar_id!r}.")

    ensure_avatar_schema(conn)

    existing = _existing_unlock(conn, account_id, avatar_id)
    if existing is not None:
        return {
            **existing,
            "already_unlocked": True,
        }

    if source_override == SOURCE_ADMIN_GRANT:
        instant = _iso(_now(now))
        _insert_unlock(
            conn,
            account_id=account_id,
            avatar_id=avatar_id,
            source=SOURCE_ADMIN_GRANT,
            unlocked_at=instant,
        )
        logger.info(
            "avatar_unlocked account=%s avatar=%s source=admin_grant",
            account_id,
            avatar_id,
        )
        return {
            "account_id": account_id,
            "avatar_id": avatar_id,
            "unlocked_at": instant,
            "source": SOURCE_ADMIN_GRANT,
            "already_unlocked": False,
        }

    total_xp = _total_xp(conn, account_id)
    premium_active = _premium_active(billing_state)
    unlocked, reason, required = _resolve_lock(
        avatar, total_xp=total_xp, premium_active=premium_active
    )
    if not unlocked:
        raise AvatarLockedError(avatar_id, reason=reason or "locked", required=required)

    if avatar.is_free:
        source = SOURCE_FREE
    elif avatar.is_xp:
        source = SOURCE_XP
    else:
        source = SOURCE_PREMIUM
    instant = _iso(_now(now))
    _insert_unlock(
        conn,
        account_id=account_id,
        avatar_id=avatar_id,
        source=source,
        unlocked_at=instant,
    )
    logger.info(
        "avatar_unlocked account=%s avatar=%s source=%s",
        account_id,
        avatar_id,
        source,
    )
    return {
        "account_id": account_id,
        "avatar_id": avatar_id,
        "unlocked_at": instant,
        "source": source,
        "already_unlocked": False,
    }


def list_unlocked(
    conn: sqlite3.Connection,
    account_id: str,
    *,
    billing_state: dict[str, Any] | None = None,
    only_unlocked: bool = False,
    only_paid_tier: bool | None = None,
) -> list[dict[str, Any]]:
    """Return every catalog avatar, decorated with per-account state.

    Each item carries:

    * ``avatar`` — the full catalog row (``Avatar.to_public()``).
    * ``unlocked`` — bool, derived from ``avatar_unlocks`` *or* the
      computed contract (free always, XP threshold, premium when
      ``billing_state`` is active).
    * ``source`` — the recorded source if a row exists, else
      ``None``.
    * ``equipped`` — bool, matches ``account_avatars.avatar_id``.
    * ``locked_reason`` — human-readable string when ``unlocked=False``.
    * ``required`` — machine-readable lock metadata (``{kind, xp,
      have}`` for XP, ``{kind: premium}`` for premium).

    Filters:

    * ``only_unlocked=True`` — strip locked avatars.
    * ``only_paid_tier=True``  — restrict to ``tier='premium'``.
    * ``only_paid_tier=False`` — restrict to ``tier!='premium'``
      (i.e. free + XP).
    * ``only_paid_tier=None``  — no tier filter.
    """

    ensure_avatar_schema(conn)
    catalog = load_catalog()
    stored = {}
    for avatar_id in _account_unlock_ids(conn, account_id):
        row = _existing_unlock(conn, account_id, avatar_id)
        if row is not None:
            stored[avatar_id] = row
    equipped = _equipped_id(conn, account_id)
    total_xp = _total_xp(conn, account_id)
    premium_active = _premium_active(billing_state)

    items: list[dict[str, Any]] = []
    for avatar in _sorted_catalog(catalog.values()):
        if only_paid_tier is True and avatar.tier != "premium":
            continue
        if only_paid_tier is False and avatar.tier == "premium":
            continue
        stored_row = stored.get(avatar.id)
        if stored_row is not None:
            unlocked = True
            reason: str | None = None
            required: dict[str, Any] = {}
            source = stored_row["source"]
            unlocked_at: str | None = stored_row["unlocked_at"]
        else:
            unlocked, reason, required = _resolve_lock(
                avatar, total_xp=total_xp, premium_active=premium_active
            )
            source = SOURCE_FREE if avatar.is_free and unlocked else None
            unlocked_at = None
        if only_unlocked and not unlocked:
            continue
        items.append(
            {
                "avatar": avatar.to_public(),
                "unlocked": bool(unlocked),
                "source": source,
                "unlocked_at": unlocked_at,
                "equipped": equipped == avatar.id,
                "locked_reason": reason,
                "required": required,
            }
        )
    return items


def _sorted_catalog(avatars: Iterable[Avatar]) -> list[Avatar]:
    """Sort avatars: free → XP (ascending threshold) → premium."""

    def _key(a: Avatar) -> tuple[int, int, str]:
        tier_rank = {"free": 0, "xp": 1, "premium": 2}.get(a.tier, 3)
        return (tier_rank, a.unlock_xp, a.id)

    return sorted(avatars, key=_key)


def equip_avatar(
    conn: sqlite3.Connection,
    account_id: str,
    avatar_id: str,
    *,
    billing_state: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Equip ``avatar_id`` for ``account_id``.

    Refuses to equip an avatar the account has not unlocked. For free
    avatars, the unlock row is created on the fly so equipping is the
    only call the frontend needs to make for a default avatar.

    Returns ``{account_id, avatar_id, equipped_at, avatar}``.
    """

    if not account_id:
        raise ValueError("account_id is required")
    if not avatar_id:
        raise ValueError("avatar_id is required")
    catalog = load_catalog()
    avatar = catalog.get(avatar_id)
    if avatar is None:
        raise AvatarNotFoundError(f"Unknown avatar id {avatar_id!r}.")

    ensure_avatar_schema(conn)
    existing = _existing_unlock(conn, account_id, avatar_id)
    if existing is None:
        # Free avatars are implicitly unlocked — write the row on first
        # equip so subsequent reads find a uniform ledger. For XP /
        # premium avatars, refuse to equip and surface the standard
        # locked reason.
        if avatar.is_free:
            unlock_avatar(conn, account_id, avatar_id, now=now)
        else:
            total_xp = _total_xp(conn, account_id)
            premium_active = _premium_active(billing_state)
            unlocked, reason, required = _resolve_lock(
                avatar, total_xp=total_xp, premium_active=premium_active
            )
            if not unlocked:
                raise AvatarLockedError(
                    avatar_id, reason=reason or "locked", required=required
                )
            # Eligible but no ledger row — promote it.
            unlock_avatar(
                conn,
                account_id,
                avatar_id,
                billing_state=billing_state,
                now=now,
            )

    instant = _iso(_now(now))
    conn.execute(
        """
        INSERT INTO account_avatars (account_id, avatar_id, equipped_at)
        VALUES (?, ?, ?)
        ON CONFLICT(account_id) DO UPDATE SET
            avatar_id = excluded.avatar_id,
            equipped_at = excluded.equipped_at
        """,
        (account_id, avatar_id, instant),
    )
    logger.info(
        "avatar_equipped account=%s avatar=%s",
        account_id,
        avatar_id,
    )
    return {
        "account_id": account_id,
        "avatar_id": avatar_id,
        "equipped_at": instant,
        "avatar": avatar.to_public(),
    }


def get_equipped(
    conn: sqlite3.Connection,
    account_id: str,
) -> dict[str, Any] | None:
    """Return the currently equipped avatar (full catalog row) or None."""

    ensure_avatar_schema(conn)
    equipped = _equipped_id(conn, account_id)
    if equipped is None:
        return None
    catalog = load_catalog()
    avatar = catalog.get(equipped)
    if avatar is None:
        return None
    return avatar.to_public()


# ---------------------------------------------------------------------------
# Convenience: auto-grant XP unlocks
# ---------------------------------------------------------------------------


def grant_xp_unlocks(
    conn: sqlite3.Connection,
    account_id: str,
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Auto-grant every XP avatar the learner already qualifies for.

    Idempotent — avatars already in ``avatar_unlocks`` are skipped. The
    caller is expected to invoke this from the XP-award path (T-034)
    after the streak / total has been updated, so unlocks track XP
    accrual without the frontend having to poll an unlock endpoint.

    Returns the list of unlocks created on this call (may be empty).
    """

    if not account_id:
        return []
    ensure_avatar_schema(conn)
    catalog = load_catalog()
    total_xp = _total_xp(conn, account_id)
    existing = _account_unlock_ids(conn, account_id)
    granted: list[dict[str, Any]] = []
    for avatar in catalog.values():
        if not avatar.is_xp:
            continue
        if avatar.id in existing:
            continue
        if total_xp < avatar.unlock_xp:
            continue
        instant = _iso(_now(now))
        _insert_unlock(
            conn,
            account_id=account_id,
            avatar_id=avatar.id,
            source=SOURCE_XP,
            unlocked_at=instant,
        )
        granted.append(
            {
                "account_id": account_id,
                "avatar_id": avatar.id,
                "unlocked_at": instant,
                "source": SOURCE_XP,
            }
        )
    if granted:
        logger.info(
            "avatar_xp_unlocks account=%s count=%s",
            account_id,
            len(granted),
        )
    return granted


__all__ = [
    "Avatar",
    "AvatarError",
    "AvatarLockedError",
    "AvatarNotFoundError",
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
