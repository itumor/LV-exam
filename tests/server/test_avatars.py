"""T-051 — Avatar + cosmetics unlock tests.

Covers every deliverable in the T-051 brief:

1. **Catalog loads + ships 20 avatars** — the shipped
   ``content/avatars/*.json`` files round-trip through
   :func:`server_app.services.avatars.load_catalog` and the catalog
   contains the documented tier split (5 free / 10 XP / 5 premium).
2. **XP-threshold unlock** — an account that crosses the XP threshold
   can unlock an XP-gated avatar; an account below the threshold gets
   :class:`AvatarLockedError` with a machine-readable ``required``
   payload.
3. **Premium gate** — XP alone cannot unlock a premium avatar, even
   with millions of XP. Only an active subscription (or institutional
   seat) opens the gate.
4. **Equip persistence + downgrade safety** — equipping a free avatar
   round-trips through :func:`equip_avatar` /
   :func:`get_equipped`; equipping a locked avatar raises and does NOT
   mutate ``account_avatars``.
5. **Auto-grant XP unlocks** — :func:`grant_xp_unlocks` issues every
   XP-tier unlock the learner has earned by their current XP total and
   is idempotent on repeat calls.
6. **Per-account isolation** — Bob's unlocks never appear in Alice's
   list_unlocked output.

Tests use a tmpfile SQLite DB and a tmp catalog directory shadowed by
the ``LVCODEX_AVATARS_DIR`` env override. The XP totals are seeded
directly into ``xp_log`` (the T-034 table the avatar service reads).
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Ensure repo root is on sys.path so ``import server`` resolves under
# ``python -m unittest`` from arbitrary cwd.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import server  # noqa: E402  (shim → server_app.core; runs route hook installs)
from server_app.services import avatars as avatars_service  # noqa: E402


# ---------------------------------------------------------------------------
# Tmp catalog fixture — three avatars covering every tier.
# ---------------------------------------------------------------------------


FIXTURE_AVATARS: list[dict[str, object]] = [
    {
        "id": "fx-free-one",
        "display_name": "Fixture Free One",
        "description": "Free starter — every account holds it.",
        "art_ref": "/assets/fixture/free-one.svg",
        "rarity": "common",
        "tier": "free",
        "unlock": {"kind": "free"},
    },
    {
        "id": "fx-free-two",
        "display_name": "Fixture Free Two",
        "description": "Second free starter.",
        "art_ref": "/assets/fixture/free-two.svg",
        "rarity": "common",
        "tier": "free",
        "unlock": {"kind": "free"},
    },
    {
        "id": "fx-xp-100",
        "display_name": "Fixture XP 100",
        "description": "Unlocks at 100 XP.",
        "art_ref": "/assets/fixture/xp-100.svg",
        "rarity": "uncommon",
        "tier": "xp",
        "unlock": {"kind": "xp", "xp": 100},
    },
    {
        "id": "fx-xp-500",
        "display_name": "Fixture XP 500",
        "description": "Unlocks at 500 XP.",
        "art_ref": "/assets/fixture/xp-500.svg",
        "rarity": "rare",
        "tier": "xp",
        "unlock": {"kind": "xp", "xp": 500},
    },
    {
        "id": "fx-premium-one",
        "display_name": "Fixture Premium",
        "description": "Subscriber-only.",
        "art_ref": "/assets/fixture/premium-one.svg",
        "rarity": "legendary",
        "tier": "premium",
        "unlock": {"kind": "premium"},
    },
]


def _write_fixture_catalog(target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    for entry in FIXTURE_AVATARS:
        (target_dir / f"{entry['id']}.json").write_text(
            json.dumps(entry), encoding="utf-8"
        )


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _seed_account(account_id: str, email: str) -> None:
    with server.db_connection() as conn:
        conn.execute(
            """
            INSERT INTO accounts (id, email, password_salt, password_hash,
                                  status, created_at, deleted_at)
            VALUES (?, ?, 'salt', 'hash', 'active',
                    '2026-05-23T00:00:00Z', NULL)
            """,
            (account_id, email),
        )


def _ensure_xp_log(conn: sqlite3.Connection) -> None:
    """Create the minimal ``xp_log`` shape the service reads."""

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS xp_log (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            amount INTEGER NOT NULL,
            payload TEXT NOT NULL DEFAULT '{}',
            awarded_at TEXT NOT NULL
        );
        """
    )


def _seed_xp(account_id: str, amount: int) -> None:
    with server.db_connection() as conn:
        _ensure_xp_log(conn)
        conn.execute(
            """
            INSERT INTO xp_log (id, account_id, kind, amount, payload, awarded_at)
            VALUES (?, ?, 'test_seed', ?, '{}', '2026-05-22T00:00:00Z')
            """,
            (f"xp_seed_{account_id}_{amount}", account_id, int(amount)),
        )


# ---------------------------------------------------------------------------
# Base fixture — tmp DB + tmp catalog directory.
# ---------------------------------------------------------------------------


class _AvatarTestBase(unittest.TestCase):
    """Shared scaffolding for every T-051 test."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "auth.sqlite3"
        self.auth_db_patch = patch.object(server, "AUTH_DB_PATH", self.db_path)
        self.auth_db_patch.start()

        avatars_service._reset_ddl_cache_for_tests()
        avatars_service._reset_catalog_cache_for_tests()
        server.init_auth_store()

        self.catalog_dir = Path(self.tmpdir.name) / "avatars"
        _write_fixture_catalog(self.catalog_dir)
        self._prev_catalog_env = os.environ.get("LVCODEX_AVATARS_DIR")
        os.environ["LVCODEX_AVATARS_DIR"] = str(self.catalog_dir)

        _seed_account("acct_alice_t051", "alice@example.test")
        _seed_account("acct_bob_t051", "bob@example.test")

    def tearDown(self) -> None:
        self.auth_db_patch.stop()
        self.tmpdir.cleanup()
        avatars_service._reset_ddl_cache_for_tests()
        avatars_service._reset_catalog_cache_for_tests()
        if self._prev_catalog_env is None:
            os.environ.pop("LVCODEX_AVATARS_DIR", None)
        else:
            os.environ["LVCODEX_AVATARS_DIR"] = self._prev_catalog_env


# ---------------------------------------------------------------------------
# Shipped catalog — proves 20 avatars + tier breakdown
# ---------------------------------------------------------------------------


class ShippedCatalogTests(unittest.TestCase):
    """The 20 avatar JSON files shipped under ``content/avatars/`` must load."""

    def setUp(self) -> None:
        # Force the loader back to the on-disk default — undo any
        # LVCODEX_AVATARS_DIR set by a previous test (defensive).
        self._prev_env = os.environ.pop("LVCODEX_AVATARS_DIR", None)
        avatars_service._reset_catalog_cache_for_tests()

    def tearDown(self) -> None:
        if self._prev_env is not None:
            os.environ["LVCODEX_AVATARS_DIR"] = self._prev_env
        avatars_service._reset_catalog_cache_for_tests()

    def test_catalog_loads_twenty_avatars(self) -> None:
        catalog = avatars_service.load_catalog(refresh=True)
        self.assertEqual(len(catalog), 20, f"expected 20 avatars, got {len(catalog)}")

    def test_tier_breakdown_is_five_ten_five(self) -> None:
        catalog = avatars_service.load_catalog(refresh=True)
        free = [a for a in catalog.values() if a.is_free]
        xp = [a for a in catalog.values() if a.is_xp]
        premium = [a for a in catalog.values() if a.is_premium]
        self.assertEqual(len(free), 5)
        self.assertEqual(len(xp), 10)
        self.assertEqual(len(premium), 5)

    def test_xp_avatars_have_positive_xp_threshold(self) -> None:
        catalog = avatars_service.load_catalog(refresh=True)
        for avatar in catalog.values():
            if avatar.is_xp:
                self.assertGreater(
                    avatar.unlock_xp,
                    0,
                    f"{avatar.id} must declare a positive xp threshold",
                )

    def test_premium_avatars_carry_no_xp_threshold(self) -> None:
        catalog = avatars_service.load_catalog(refresh=True)
        for avatar in catalog.values():
            if avatar.is_premium:
                self.assertEqual(avatar.unlock_xp, 0)


# ---------------------------------------------------------------------------
# Unlock by XP threshold
# ---------------------------------------------------------------------------


class UnlockByXpTests(_AvatarTestBase):
    """Crossing the XP threshold unlocks the corresponding avatar."""

    def test_below_threshold_raises_locked_error(self) -> None:
        _seed_xp("acct_alice_t051", 50)  # below the 100 threshold
        with server.db_connection() as conn:
            with self.assertRaises(avatars_service.AvatarLockedError) as ctx:
                avatars_service.unlock_avatar(
                    conn, "acct_alice_t051", "fx-xp-100"
                )
        self.assertEqual(ctx.exception.required["kind"], "xp")
        self.assertEqual(ctx.exception.required["xp"], 100)
        self.assertEqual(ctx.exception.required["have"], 50)

    def test_at_threshold_unlocks(self) -> None:
        _seed_xp("acct_alice_t051", 100)
        with server.db_connection() as conn:
            result = avatars_service.unlock_avatar(
                conn, "acct_alice_t051", "fx-xp-100"
            )
        self.assertEqual(result["source"], avatars_service.SOURCE_XP)
        self.assertFalse(result["already_unlocked"])

    def test_unlock_is_idempotent(self) -> None:
        _seed_xp("acct_alice_t051", 150)
        with server.db_connection() as conn:
            first = avatars_service.unlock_avatar(
                conn, "acct_alice_t051", "fx-xp-100"
            )
            second = avatars_service.unlock_avatar(
                conn, "acct_alice_t051", "fx-xp-100"
            )
        self.assertFalse(first["already_unlocked"])
        self.assertTrue(second["already_unlocked"])
        self.assertEqual(first["unlocked_at"], second["unlocked_at"])

    def test_higher_threshold_avatar_stays_locked(self) -> None:
        _seed_xp("acct_alice_t051", 200)  # crosses 100, not 500
        with server.db_connection() as conn:
            # 100 unlocks
            ok = avatars_service.unlock_avatar(
                conn, "acct_alice_t051", "fx-xp-100"
            )
            self.assertEqual(ok["source"], avatars_service.SOURCE_XP)
            # 500 does not
            with self.assertRaises(avatars_service.AvatarLockedError):
                avatars_service.unlock_avatar(
                    conn, "acct_alice_t051", "fx-xp-500"
                )

    def test_grant_xp_unlocks_issues_every_eligible(self) -> None:
        """``grant_xp_unlocks`` collapses the XP catalog into one call."""

        _seed_xp("acct_alice_t051", 600)  # crosses both 100 and 500
        with server.db_connection() as conn:
            granted = avatars_service.grant_xp_unlocks(
                conn, "acct_alice_t051"
            )
        granted_ids = {row["avatar_id"] for row in granted}
        self.assertEqual(granted_ids, {"fx-xp-100", "fx-xp-500"})

    def test_grant_xp_unlocks_is_idempotent(self) -> None:
        _seed_xp("acct_alice_t051", 600)
        with server.db_connection() as conn:
            first = avatars_service.grant_xp_unlocks(conn, "acct_alice_t051")
            second = avatars_service.grant_xp_unlocks(conn, "acct_alice_t051")
        self.assertEqual(len(first), 2)
        self.assertEqual(len(second), 0)

    def test_award_xp_auto_grants_eligible_avatars(self) -> None:
        """Awarding XP that crosses an avatar threshold must auto-unlock it."""

        from server_app.services import xp as xp_service

        xp_service._reset_ddl_cache_for_tests()
        with server.db_connection() as conn:
            xp_service.ensure_xp_schema(conn)
            # 50 award * 3 → 150 XP, crosses the 100 threshold.
            for _ in range(3):
                xp_service.award_xp(
                    conn,
                    "acct_alice_t051",
                    "mission_complete",
                    amount=50,
                )
            rows = conn.execute(
                "SELECT avatar_id, source FROM avatar_unlocks "
                "WHERE account_id = ?",
                ("acct_alice_t051",),
            ).fetchall()
        unlocked = {row["avatar_id"]: row["source"] for row in rows}
        self.assertEqual(
            unlocked.get("fx-xp-100"),
            avatars_service.SOURCE_XP,
            "award_xp must call grant_xp_unlocks via the T-051 hook",
        )
        # The 500 threshold avatar must stay locked.
        self.assertNotIn("fx-xp-500", unlocked)


# ---------------------------------------------------------------------------
# Premium gate
# ---------------------------------------------------------------------------


class PremiumGateTests(_AvatarTestBase):
    """Premium avatars require an active subscription. XP cannot bypass."""

    def test_free_account_cannot_unlock_premium(self) -> None:
        with server.db_connection() as conn:
            with self.assertRaises(avatars_service.AvatarLockedError) as ctx:
                avatars_service.unlock_avatar(
                    conn, "acct_alice_t051", "fx-premium-one"
                )
        self.assertEqual(ctx.exception.required["kind"], "premium")

    def test_infinite_xp_does_not_unlock_premium(self) -> None:
        _seed_xp("acct_alice_t051", 1_000_000)
        with server.db_connection() as conn:
            with self.assertRaises(avatars_service.AvatarLockedError) as ctx:
                avatars_service.unlock_avatar(
                    conn, "acct_alice_t051", "fx-premium-one"
                )
        self.assertEqual(ctx.exception.reason, "Subscriber only")

    def test_active_subscription_unlocks_premium(self) -> None:
        billing = {"subscription_active": True}
        with server.db_connection() as conn:
            result = avatars_service.unlock_avatar(
                conn,
                "acct_alice_t051",
                "fx-premium-one",
                billing_state=billing,
            )
        self.assertEqual(result["source"], avatars_service.SOURCE_PREMIUM)

    def test_institutional_seat_unlocks_premium(self) -> None:
        """T-041 institutional seats count as premium (mirrors T-024 gate)."""

        billing = {"has_active_seat": True}
        with server.db_connection() as conn:
            result = avatars_service.unlock_avatar(
                conn,
                "acct_alice_t051",
                "fx-premium-one",
                billing_state=billing,
            )
        self.assertEqual(result["source"], avatars_service.SOURCE_PREMIUM)

    def test_frozen_account_cannot_unlock_premium(self) -> None:
        billing = {"subscription_active": True, "frozen": True}
        with server.db_connection() as conn:
            with self.assertRaises(avatars_service.AvatarLockedError):
                avatars_service.unlock_avatar(
                    conn,
                    "acct_alice_t051",
                    "fx-premium-one",
                    billing_state=billing,
                )


# ---------------------------------------------------------------------------
# Equip persistence
# ---------------------------------------------------------------------------


class EquipPersistenceTests(_AvatarTestBase):
    """Equipping must round-trip through the DB and survive a re-read."""

    def test_equip_free_avatar_and_read_back(self) -> None:
        with server.db_connection() as conn:
            equipped = avatars_service.equip_avatar(
                conn, "acct_alice_t051", "fx-free-one"
            )
            stored = avatars_service.get_equipped(conn, "acct_alice_t051")
        self.assertEqual(equipped["avatar_id"], "fx-free-one")
        self.assertIsNotNone(stored)
        self.assertEqual(stored["id"], "fx-free-one")

    def test_equip_replaces_previously_equipped(self) -> None:
        with server.db_connection() as conn:
            avatars_service.equip_avatar(
                conn, "acct_alice_t051", "fx-free-one"
            )
            avatars_service.equip_avatar(
                conn, "acct_alice_t051", "fx-free-two"
            )
            stored = avatars_service.get_equipped(conn, "acct_alice_t051")
        self.assertEqual(stored["id"], "fx-free-two")

    def test_equip_unknown_avatar_raises_not_found(self) -> None:
        with server.db_connection() as conn:
            with self.assertRaises(avatars_service.AvatarNotFoundError):
                avatars_service.equip_avatar(
                    conn, "acct_alice_t051", "fx-does-not-exist"
                )

    def test_equip_locked_avatar_raises_and_does_not_mutate(self) -> None:
        with server.db_connection() as conn:
            with self.assertRaises(avatars_service.AvatarLockedError):
                avatars_service.equip_avatar(
                    conn, "acct_alice_t051", "fx-xp-500"
                )
            stored = avatars_service.get_equipped(conn, "acct_alice_t051")
        self.assertIsNone(stored, "locked equip must not write account_avatars")

    def test_equip_writes_unlock_row_for_free_avatar(self) -> None:
        """Equipping a free avatar should leave an ``avatar_unlocks`` row."""

        with server.db_connection() as conn:
            avatars_service.equip_avatar(
                conn, "acct_alice_t051", "fx-free-one"
            )
            rows = conn.execute(
                "SELECT avatar_id, source FROM avatar_unlocks "
                "WHERE account_id = ?",
                ("acct_alice_t051",),
            ).fetchall()
        sources = {row["avatar_id"]: row["source"] for row in rows}
        self.assertEqual(sources.get("fx-free-one"), avatars_service.SOURCE_FREE)

    def test_equip_premium_unlocked_account_persists(self) -> None:
        billing = {"subscription_active": True}
        with server.db_connection() as conn:
            avatars_service.equip_avatar(
                conn,
                "acct_alice_t051",
                "fx-premium-one",
                billing_state=billing,
            )
            stored = avatars_service.get_equipped(conn, "acct_alice_t051")
        self.assertEqual(stored["id"], "fx-premium-one")


# ---------------------------------------------------------------------------
# Listing + filters
# ---------------------------------------------------------------------------


class ListUnlockedTests(_AvatarTestBase):
    """``list_unlocked`` decorates the catalog with per-account state."""

    def test_free_avatars_are_unlocked_by_default(self) -> None:
        with server.db_connection() as conn:
            items = avatars_service.list_unlocked(conn, "acct_alice_t051")
        by_id = {it["avatar"]["id"]: it for it in items}
        self.assertTrue(by_id["fx-free-one"]["unlocked"])
        self.assertTrue(by_id["fx-free-two"]["unlocked"])
        # XP avatars w/o XP — locked.
        self.assertFalse(by_id["fx-xp-100"]["unlocked"])
        self.assertEqual(by_id["fx-xp-100"]["required"]["kind"], "xp")
        # Premium w/o subscription — locked.
        self.assertFalse(by_id["fx-premium-one"]["unlocked"])
        self.assertEqual(by_id["fx-premium-one"]["required"]["kind"], "premium")

    def test_only_paid_tier_true_returns_only_premium(self) -> None:
        with server.db_connection() as conn:
            items = avatars_service.list_unlocked(
                conn, "acct_alice_t051", only_paid_tier=True
            )
        tiers = {it["avatar"]["tier"] for it in items}
        self.assertEqual(tiers, {"premium"})

    def test_only_paid_tier_false_excludes_premium(self) -> None:
        with server.db_connection() as conn:
            items = avatars_service.list_unlocked(
                conn, "acct_alice_t051", only_paid_tier=False
            )
        tiers = {it["avatar"]["tier"] for it in items}
        self.assertNotIn("premium", tiers)

    def test_equipped_flag_matches_account_avatars(self) -> None:
        with server.db_connection() as conn:
            avatars_service.equip_avatar(
                conn, "acct_alice_t051", "fx-free-one"
            )
            items = avatars_service.list_unlocked(conn, "acct_alice_t051")
        equipped = [it for it in items if it["equipped"]]
        self.assertEqual(len(equipped), 1)
        self.assertEqual(equipped[0]["avatar"]["id"], "fx-free-one")

    def test_alice_unlocks_do_not_leak_into_bob(self) -> None:
        _seed_xp("acct_alice_t051", 200)
        with server.db_connection() as conn:
            avatars_service.grant_xp_unlocks(conn, "acct_alice_t051")
            bob_items = avatars_service.list_unlocked(conn, "acct_bob_t051")
        bob_by_id = {it["avatar"]["id"]: it for it in bob_items}
        self.assertFalse(bob_by_id["fx-xp-100"]["unlocked"])


# ---------------------------------------------------------------------------
# Routes registry — proves the audit list picks up our 3 routes.
# ---------------------------------------------------------------------------


class RoutesRegistryTests(unittest.TestCase):
    """The routes module must declare and re-export the service surface."""

    def test_routes_module_lists_three_routes(self) -> None:
        from server_app.routes import avatars as avatars_routes
        self.assertIn(("GET", "/api/avatars"), avatars_routes.ROUTES)
        self.assertIn(("POST", "/api/avatars/equip"), avatars_routes.ROUTES)
        self.assertIn(("POST", "/api/avatars/unlock"), avatars_routes.ROUTES)

    def test_routes_in_global_registry(self) -> None:
        from server_app.routes import ROUTES
        owners = {pattern: owner for _method, pattern, owner in ROUTES}
        self.assertEqual(owners.get("/api/avatars"), "avatars")
        self.assertEqual(owners.get("/api/avatars/equip"), "avatars")

    def test_handler_marker_installed(self) -> None:
        from server_app import AppHandler
        self.assertTrue(
            getattr(AppHandler, "_t051_installed", False),
            "T-051 hook block did not install — check core.py wiring",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
