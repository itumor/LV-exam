"""T-050 — Story-mode mission tests.

Covers the deliverables called out in the T-050 brief:

1. **Catalogue shape** — exactly 8 missions across 5 cities (Rīga M1+M2,
   Jūrmala M3, Liepāja M4, Daugavpils M5+M6, Cēsis M7+M8) each with
   ordered scenes, NPC references (T-045), and unlock criteria.
2. **Sequential unlock** — M1 is available cold-start; M2 unlocks after
   M1 + XP threshold; M8 requires M7 + total-XP + streak-days.
3. **Scene completion** — first POST inserts one ``story_progress`` row
   and awards scene XP; second POST is idempotent (no row, no XP).
4. **Mission completion** — completing every scene of a mission flips
   the mission to ``completed`` and awards the ``xp_on_complete`` bonus.
5. **XP integration (T-034)** — every award flows through the canonical
   :func:`server_app.services.xp.award_xp` so totals + streaks stay
   consistent with daily missions.
6. **Per-account isolation** — Bob cannot complete on Alice's behalf;
   each learner has an independent progression.
7. **Routing-wiring contract** — ``ROUTES`` documents both endpoints
   and the ``_t050_installed`` marker is set on :class:`AppHandler`.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

# Ensure repo root is on sys.path so ``import server`` resolves under
# ``python -m unittest`` from arbitrary cwd.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import server  # noqa: E402  (shim → server_app.core; runs route hook installs)
from server_app.services import story as story_service  # noqa: E402
from server_app.services import xp as xp_service  # noqa: E402


# ---------------------------------------------------------------------------
# DB helpers — seed accounts.
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


def _grant_xp(account_id: str, amount: int) -> None:
    """Seed ``xp_log`` so unlock thresholds can be tested in isolation.

    Inserts a raw row (bypassing the streak engine) so a single test can
    set ``total_xp`` to an arbitrary value without also bumping the
    learner's streak.
    """

    with server.db_connection() as conn:
        xp_service.ensure_xp_schema(conn)
        conn.execute(
            """
            INSERT INTO xp_log (id, account_id, kind, amount, payload, awarded_at)
            VALUES (?, ?, 'mission_complete', ?, '{}', '2026-05-23T00:00:00Z')
            """,
            (f"seed_{account_id}_{uuid.uuid4().hex[:8]}", account_id, int(amount)),
        )


def _set_streak(account_id: str, days: int) -> None:
    """Seed ``user_streaks`` so a story-mission streak unlock can be tested."""

    with server.db_connection() as conn:
        xp_service.ensure_xp_schema(conn)
        conn.execute(
            """
            INSERT INTO user_streaks
                (account_id, current_days, longest_days,
                 last_active_date, last_active_at, updated_at)
            VALUES (?, ?, ?, '2026-05-23', '2026-05-23T00:00:00Z',
                    '2026-05-23T00:00:00Z')
            ON CONFLICT(account_id) DO UPDATE SET
                current_days = excluded.current_days,
                longest_days = excluded.longest_days
            """,
            (account_id, int(days), int(days)),
        )


# ---------------------------------------------------------------------------
# Base fixture — fresh tmp DB per test.
# ---------------------------------------------------------------------------


class _StoryTestBase(unittest.TestCase):
    """Shared scaffolding for every T-050 test."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "auth.sqlite3"
        self.auth_db_patch = patch.object(server, "AUTH_DB_PATH", self.db_path)
        self.auth_db_patch.start()
        story_service._reset_story_ddl_cache()
        story_service._reset_catalogue_cache_for_tests()
        xp_service._reset_ddl_cache_for_tests()
        server.init_auth_store()
        with server.db_connection() as conn:
            story_service.ensure_story_schema(conn)
            xp_service.ensure_xp_schema(conn)
        _seed_account("acct_alice_t050", "alice@example.test")
        _seed_account("acct_bob_t050", "bob@example.test")

    def tearDown(self) -> None:
        self.auth_db_patch.stop()
        self.tmpdir.cleanup()
        story_service._reset_story_ddl_cache()
        story_service._reset_catalogue_cache_for_tests()
        xp_service._reset_ddl_cache_for_tests()


# ---------------------------------------------------------------------------
# Catalogue shape
# ---------------------------------------------------------------------------


class StoryCatalogueTests(unittest.TestCase):
    """Verify the brief's 8 missions / 5 cities contract."""

    def test_catalogue_has_exactly_eight_missions(self) -> None:
        missions = story_service.list_missions()
        self.assertEqual(
            len(missions),
            8,
            "T-050 brief requires exactly 8 story missions",
        )

    def test_canonical_mission_ids(self) -> None:
        missions = story_service.list_missions()
        ids = [m["id"] for m in missions]
        self.assertEqual(list(ids), list(story_service.EXPECTED_MISSION_IDS))

    def test_missions_cover_five_cities(self) -> None:
        missions = story_service.list_missions()
        cities = {m["city"] for m in missions}
        self.assertEqual(cities, set(story_service.EXPECTED_CITIES))

    def test_each_mission_has_ordered_scenes(self) -> None:
        for mission in story_service.list_missions():
            self.assertGreater(
                len(mission["scenes"]),
                0,
                f"{mission['id']} must define at least one scene",
            )
            orders = [s.get("order", 0) for s in mission["scenes"]]
            self.assertEqual(
                orders,
                sorted(orders),
                f"{mission['id']} scenes must be in monotonic order",
            )

    def test_scenes_reference_known_npcs(self) -> None:
        """Every scene's ``npc_id`` must exist in the T-045 NPC catalogue."""

        from server_app.services import npc as npc_service

        npc_ids = {n["id"] for n in npc_service.list_npcs()}
        self.assertGreater(len(npc_ids), 0, "expected at least one NPC on disk")
        for mission in story_service.list_missions():
            for scene in mission["scenes"]:
                ref = scene.get("npc_id")
                if ref is None:
                    continue
                self.assertIn(
                    ref,
                    npc_ids,
                    f"{mission['id']}::{scene.get('id')} references unknown NPC {ref!r}",
                )

    def test_each_mission_has_unlock_criteria_block(self) -> None:
        for mission in story_service.list_missions():
            self.assertIn("unlock_criteria", mission)
            criteria = mission["unlock_criteria"]
            self.assertIsInstance(criteria, dict)
            self.assertIn("requires_missions", criteria)
            self.assertIsInstance(criteria["requires_missions"], list)

    def test_first_mission_has_no_prerequisites(self) -> None:
        first = story_service.load_mission("m1-riga-arrival")
        self.assertEqual(first["unlock_criteria"]["requires_missions"], [])
        self.assertEqual(first["unlock_criteria"].get("min_total_xp", 0), 0)
        self.assertEqual(first["unlock_criteria"].get("min_streak_days", 0), 0)

    def test_final_mission_requires_seven_predecessors(self) -> None:
        """M8 must chain through M7 and require non-trivial XP + streak."""

        last = story_service.load_mission("m8-cesis-exam-prep")
        self.assertEqual(
            last["unlock_criteria"]["requires_missions"], ["m7-cesis-castle"]
        )
        self.assertGreater(last["unlock_criteria"]["min_total_xp"], 0)
        self.assertGreater(last["unlock_criteria"]["min_streak_days"], 0)


# ---------------------------------------------------------------------------
# Sequential unlock
# ---------------------------------------------------------------------------


class StoryUnlockTests(_StoryTestBase):
    """Missions unlock in sequence."""

    def test_cold_start_only_first_mission_is_available(self) -> None:
        with server.db_connection() as conn:
            state = story_service.get_state(conn, "acct_alice_t050")
        statuses = {m["id"]: m["status"] for m in state["missions"]}
        self.assertEqual(statuses["m1-riga-arrival"], "available")
        for mid in story_service.EXPECTED_MISSION_IDS[1:]:
            self.assertEqual(
                statuses[mid], "locked", f"{mid} must be locked at cold start"
            )

    def test_completing_m1_unlocks_m2_when_xp_met(self) -> None:
        with server.db_connection() as conn:
            mission = story_service.load_mission("m1-riga-arrival")
            for scene in mission["scenes"]:
                story_service.complete_scene(
                    conn, "acct_alice_t050", "m1-riga-arrival", scene["id"]
                )
            state = story_service.get_state(conn, "acct_alice_t050")
        statuses = {m["id"]: m["status"] for m in state["missions"]}
        self.assertEqual(statuses["m1-riga-arrival"], "completed")
        # M2 requires 30 XP — three scenes at 10 each + 50 mission bonus = 80 total.
        self.assertEqual(statuses["m2-riga-market"], "available")
        # M3 requires M2 done plus 90 XP — still locked.
        self.assertEqual(statuses["m3-jurmala-beach"], "locked")

    def test_completing_locked_mission_raises(self) -> None:
        """Skipping ahead must be rejected at the service layer."""

        with server.db_connection() as conn:
            mission = story_service.load_mission("m3-jurmala-beach")
            first_scene = mission["scenes"][0]["id"]
            with self.assertRaises(story_service.MissionLocked):
                story_service.complete_scene(
                    conn, "acct_alice_t050", "m3-jurmala-beach", first_scene
                )

    def test_final_mission_streak_gate_blocks_progress(self) -> None:
        """M8 requires a 7-day streak even if the learner has plenty of XP."""

        # Grant a lot of XP but no streak → still locked.
        _grant_xp("acct_alice_t050", 9999)
        with server.db_connection() as conn:
            state = story_service.get_state(conn, "acct_alice_t050")
        unlock = next(
            m for m in state["missions"] if m["id"] == "m8-cesis-exam-prep"
        )["unlock"]
        self.assertFalse(unlock["unlocked"])
        # Missing prerequisite missions OR streak — both should be reasons.
        self.assertTrue(
            unlock["missing_missions"] or unlock["has_streak_days"] < unlock["needs_streak_days"]
        )


# ---------------------------------------------------------------------------
# Scene completion
# ---------------------------------------------------------------------------


class StoryCompletionTests(_StoryTestBase):
    """Scene completion: idempotency + persistence."""

    def test_first_completion_inserts_progress_and_awards_xp(self) -> None:
        with server.db_connection() as conn:
            result = story_service.complete_scene(
                conn,
                "acct_alice_t050",
                "m1-riga-arrival",
                "s1-greet-taxi-driver",
            )
        self.assertTrue(result["newly_completed"])
        self.assertFalse(result["mission_completed"])
        self.assertGreater(result["scene_xp_awarded"], 0)
        self.assertEqual(result["mission_bonus_xp_awarded"], 0)

        # Progress row exists.
        with server.db_connection() as conn:
            rows = conn.execute(
                "SELECT scene_id FROM story_progress WHERE account_id = ?",
                ("acct_alice_t050",),
            ).fetchall()
        self.assertEqual(
            {r["scene_id"] for r in rows},
            {"s1-greet-taxi-driver"},
        )
        # XP log row exists.
        with server.db_connection() as conn:
            xp_total = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) AS t FROM xp_log WHERE account_id = ?",
                ("acct_alice_t050",),
            ).fetchone()["t"]
        self.assertEqual(xp_total, result["scene_xp_awarded"])

    def test_repeat_completion_is_idempotent(self) -> None:
        with server.db_connection() as conn:
            first = story_service.complete_scene(
                conn,
                "acct_alice_t050",
                "m1-riga-arrival",
                "s1-greet-taxi-driver",
            )
            second = story_service.complete_scene(
                conn,
                "acct_alice_t050",
                "m1-riga-arrival",
                "s1-greet-taxi-driver",
            )
        self.assertTrue(first["newly_completed"])
        self.assertFalse(second["newly_completed"])
        self.assertEqual(second["scene_xp_awarded"], 0)
        # Only one progress row.
        with server.db_connection() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS n FROM story_progress WHERE account_id = ?",
                ("acct_alice_t050",),
            ).fetchone()["n"]
        self.assertEqual(count, 1)
        # XP total reflects the FIRST award only.
        with server.db_connection() as conn:
            xp_total = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) AS t FROM xp_log WHERE account_id = ?",
                ("acct_alice_t050",),
            ).fetchone()["t"]
        self.assertEqual(xp_total, first["scene_xp_awarded"])

    def test_completing_all_scenes_awards_mission_bonus(self) -> None:
        mission = story_service.load_mission("m1-riga-arrival")
        scene_ids = [s["id"] for s in mission["scenes"]]
        with server.db_connection() as conn:
            for sid in scene_ids[:-1]:
                step = story_service.complete_scene(
                    conn, "acct_alice_t050", "m1-riga-arrival", sid
                )
                self.assertEqual(step["mission_bonus_xp_awarded"], 0)
            last = story_service.complete_scene(
                conn, "acct_alice_t050", "m1-riga-arrival", scene_ids[-1]
            )
        self.assertTrue(last["mission_completed"])
        self.assertTrue(last["mission_just_completed"])
        self.assertGreater(last["mission_bonus_xp_awarded"], 0)
        # XP log carries the sum of all scene awards + mission bonus.
        with server.db_connection() as conn:
            xp_total = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) AS t FROM xp_log WHERE account_id = ?",
                ("acct_alice_t050",),
            ).fetchone()["t"]
        scene_xp_total = sum(s.get("xp", story_service.DEFAULT_SCENE_XP) for s in mission["scenes"])
        self.assertEqual(
            xp_total, scene_xp_total + mission["xp_on_complete"]
        )

    def test_unknown_mission_id_raises_mission_not_found(self) -> None:
        with server.db_connection() as conn:
            with self.assertRaises(story_service.MissionNotFound):
                story_service.complete_scene(
                    conn, "acct_alice_t050", "nope-not-real", "s1"
                )

    def test_unknown_scene_id_raises_scene_not_found(self) -> None:
        with server.db_connection() as conn:
            with self.assertRaises(story_service.SceneNotFound):
                story_service.complete_scene(
                    conn,
                    "acct_alice_t050",
                    "m1-riga-arrival",
                    "scene-that-does-not-exist",
                )

    def test_bob_progress_does_not_leak_into_alice(self) -> None:
        """Per-account isolation — each learner has independent progress."""

        with server.db_connection() as conn:
            story_service.complete_scene(
                conn,
                "acct_bob_t050",
                "m1-riga-arrival",
                "s1-greet-taxi-driver",
            )
            alice = story_service.get_state(conn, "acct_alice_t050")
            bob = story_service.get_state(conn, "acct_bob_t050")
        alice_m1 = next(m for m in alice["missions"] if m["id"] == "m1-riga-arrival")
        bob_m1 = next(m for m in bob["missions"] if m["id"] == "m1-riga-arrival")
        self.assertEqual(alice_m1["scenes_completed"], 0)
        self.assertEqual(bob_m1["scenes_completed"], 1)


# ---------------------------------------------------------------------------
# XP integration (T-034)
# ---------------------------------------------------------------------------


class StoryXpIntegrationTests(_StoryTestBase):
    """Story XP must flow through the canonical T-034 engine."""

    def test_scene_completion_emits_canonical_kind(self) -> None:
        """Story XP rows must be tagged ``mission_complete`` so totals match."""

        with server.db_connection() as conn:
            story_service.complete_scene(
                conn,
                "acct_alice_t050",
                "m1-riga-arrival",
                "s1-greet-taxi-driver",
            )
            kinds = conn.execute(
                "SELECT DISTINCT kind FROM xp_log WHERE account_id = ?",
                ("acct_alice_t050",),
            ).fetchall()
        self.assertEqual(
            {r["kind"] for r in kinds},
            {xp_service.KIND_MISSION_COMPLETE},
        )

    def test_streak_bumps_when_story_scene_completes(self) -> None:
        """Completing a scene must bump the learner's daily streak."""

        with server.db_connection() as conn:
            story_service.complete_scene(
                conn,
                "acct_alice_t050",
                "m1-riga-arrival",
                "s1-greet-taxi-driver",
            )
            row = conn.execute(
                "SELECT current_days FROM user_streaks WHERE account_id = ?",
                ("acct_alice_t050",),
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertGreaterEqual(int(row["current_days"]), 1)


# ---------------------------------------------------------------------------
# Routing-wiring contract
# ---------------------------------------------------------------------------


class StoryRoutesContractTests(unittest.TestCase):
    """Structural assertions on the dispatcher wiring."""

    def test_routes_module_documents_state_and_complete(self) -> None:
        from server_app.routes import story as story_routes

        documented = {(method, pattern) for method, pattern in story_routes.ROUTES}
        self.assertIn(("GET", "/api/story/state"), documented)
        self.assertIn(
            ("POST", "/api/story/<mission_id>/scene/<scene_id>/complete"),
            documented,
        )

    def test_install_marker_is_set_on_app_handler(self) -> None:
        """The route hook must have run on import."""

        from server_app import AppHandler

        self.assertTrue(getattr(AppHandler, "_t050_installed", False))


if __name__ == "__main__":  # pragma: no cover - manual invocation
    unittest.main()
