"""T-031 — Daily mission generator + analytics tests.

Covers the deliverables called out in the T-031 brief:

1. **Deterministic generation per-day** — calling
   :func:`server_app.services.missions.get_or_generate_today` twice on
   the same ``(account_id, local_date)`` returns the *same* three mission
   rows (same ids, same payloads).
2. **Three mission kinds** — the canonical slot order is
   ``(weak_skill_drill, listening_clip, writing_prompt)`` and the result
   carries exactly one mission per kind.
3. **Completion idempotency** — calling
   :func:`server_app.services.missions.complete_mission` twice on the
   same mission flips ``completed_at`` exactly once and emits exactly
   one ``mission_completed`` analytics event.
4. **Weak-skill targeting** — when the readiness service reports a
   single failing skill (e.g. listening at 5/15), the generated
   ``weak_skill_drill`` mission targets that skill.
5. **Cold-start fallback** — a learner with no attempt history gets the
   ``COLD_START_SKILL`` (``listening``) drill.
6. **Per-account isolation** — Bob cannot complete Alice's mission.

The service is exercised directly (no HTTP plumbing); the dispatch hook
is verified at the structural level via ``ROUTES`` + the install marker
on ``AppHandler`` so the routing wiring stays under regression test.
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
from server_app.services import missions as missions_service  # noqa: E402
from server_app.services import schema_a2  # noqa: E402


# ---------------------------------------------------------------------------
# Listening-clip fixture — keeps tests independent of the real catalogue
# (which lives in ``latvian-listening-library/web/microClips.json``).
# ---------------------------------------------------------------------------


SAMPLE_CLIPS = [
    {
        "id": "mission-clip-001",
        "title": "Sveiks",
        "audio_url": "data/A1_klausisanas/audio/1_1.mp3",
        "transcript": "Sveiks!",
        "translation": "Hello!",
        "difficulty": "A1",
        "category": "greetings",
    },
    {
        "id": "mission-clip-002",
        "title": "Veikals",
        "audio_url": "data/A1_klausisanas/audio/1_2.mp3",
        "transcript": "Es eju uz veikalu.",
        "translation": "I am going to the shop.",
        "difficulty": "A1",
        "category": "shopping",
    },
    {
        "id": "mission-clip-003",
        "title": "Skola",
        "audio_url": "data/A1_klausisanas/audio/1_3.mp3",
        "transcript": "Es eju uz skolu.",
        "translation": "I am going to school.",
        "difficulty": "A1",
        "category": "school",
    },
]


def _write_clip_fixture(tmpdir: Path) -> Path:
    path = tmpdir / "mission-clips.json"
    path.write_text(json.dumps(SAMPLE_CLIPS), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# DB helpers — seed accounts + exam_attempt_category_score rows so the
# readiness-backed weak-skill picker has real data to chew on.
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


def _seed_score(
    *,
    account_id: str,
    attempt_id: str,
    skill: str,
    score: int,
    created_at: str = "2026-05-22T00:00:00Z",
) -> None:
    """Insert one (attempt, skill) score row for the readiness picker."""

    with server.db_connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO attempts
            (id, account_id, exam_id, exam_title, status, submitted_at,
             score_total, score_payload, submission_payload,
             created_at, updated_at)
            VALUES (?, ?, 'a2-builtin', 'A2 Mock', 'submitted', ?,
                    NULL, '{}', '{}', ?, ?)
            """,
            (attempt_id, account_id, created_at, created_at, created_at),
        )
        conn.execute(
            """
            INSERT INTO exam_attempt_category_score
            (id, attempt_id, account_id, category, score_0_to_15,
             passed_boolean, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"eacs_{attempt_id}_{skill}",
                attempt_id,
                account_id,
                skill,
                int(score),
                1 if score >= schema_a2.A2_MIN_PER_SKILL else 0,
                created_at,
            ),
        )


# ---------------------------------------------------------------------------
# Base fixture — fresh tmp DB + clip catalogue per test.
# ---------------------------------------------------------------------------


class _MissionTestBase(unittest.TestCase):
    """Shared scaffolding for every T-031 test."""

    def setUp(self) -> None:
        # Fresh sqlite DB per test — avoids interference across cases.
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "auth.sqlite3"
        self.auth_db_patch = patch.object(server, "AUTH_DB_PATH", self.db_path)
        self.auth_db_patch.start()
        # The mission DDL guards itself with a once-flag; reset it so the
        # tables get re-created against this fresh tmp DB.
        missions_service._reset_ddl_cache_for_tests()
        server.init_auth_store()
        missions_service.ensure_missions_schema(
            sqlite3.connect(self.db_path)
        )

        # Point the listening-clip loader at a controlled fixture so the
        # tests don't depend on the production catalogue.
        self.clip_fixture = _write_clip_fixture(Path(self.tmpdir.name))
        self._prev_clip_env = os.environ.get("LVCODEX_LISTENING_FEED_PATH")
        os.environ["LVCODEX_LISTENING_FEED_PATH"] = str(self.clip_fixture)
        missions_service._reset_clip_cache_for_tests()

        _seed_account("acct_alice_t031", "alice@example.test")
        _seed_account("acct_bob_t031", "bob@example.test")

    def tearDown(self) -> None:
        self.auth_db_patch.stop()
        self.tmpdir.cleanup()
        missions_service._reset_ddl_cache_for_tests()
        missions_service._reset_clip_cache_for_tests()
        if self._prev_clip_env is None:
            os.environ.pop("LVCODEX_LISTENING_FEED_PATH", None)
        else:
            os.environ["LVCODEX_LISTENING_FEED_PATH"] = self._prev_clip_env


# ---------------------------------------------------------------------------
# Generation tests
# ---------------------------------------------------------------------------


class MissionGenerationTests(_MissionTestBase):
    """Verify the brief's three-mission contract + determinism."""

    def test_generates_exactly_three_missions_in_canonical_slot_order(self) -> None:
        with server.db_connection() as conn:
            payload = missions_service.get_or_generate_today(conn, "acct_alice_t031")

        missions = payload["missions"]
        self.assertEqual(len(missions), 3, "must always return 3 missions")
        slots = [m["slot"] for m in missions]
        self.assertEqual(slots, list(missions_service.MISSION_SLOTS))

        # The brief calls out three mission kinds — verify each one is present.
        kinds = {m["kind"] for m in missions}
        self.assertEqual(
            kinds,
            {"weak_skill_drill", "listening_clip", "writing_prompt"},
        )

    def test_summary_counts_completed_vs_total(self) -> None:
        with server.db_connection() as conn:
            payload = missions_service.get_or_generate_today(conn, "acct_alice_t031")
        self.assertEqual(payload["summary"]["completed"], 0)
        self.assertEqual(payload["summary"]["total"], 3)
        self.assertEqual(payload["summary"]["ratio"], 0.0)

    def test_payload_contains_local_date_and_timezone(self) -> None:
        with server.db_connection() as conn:
            payload = missions_service.get_or_generate_today(conn, "acct_alice_t031")
        self.assertIn("local_date", payload)
        self.assertIn("timezone", payload)
        self.assertRegex(payload["local_date"], r"^\d{4}-\d{2}-\d{2}$")

    def test_deterministic_generation_returns_same_missions_on_second_call(self) -> None:
        """Generation must be a read on the second call — same ids, same payloads."""

        with server.db_connection() as conn:
            first = missions_service.get_or_generate_today(conn, "acct_alice_t031")
            second = missions_service.get_or_generate_today(conn, "acct_alice_t031")

        first_ids = [m["id"] for m in first["missions"]]
        second_ids = [m["id"] for m in second["missions"]]
        self.assertEqual(first_ids, second_ids)
        # Payloads must match byte-for-byte (slot, kind, title, description,
        # serialised payload). Use JSON for stable equality.
        self.assertEqual(
            json.dumps(first["missions"], sort_keys=True),
            json.dumps(second["missions"], sort_keys=True),
        )

    def test_two_learners_get_independent_mission_sets(self) -> None:
        with server.db_connection() as conn:
            alice = missions_service.get_or_generate_today(conn, "acct_alice_t031")
            bob = missions_service.get_or_generate_today(conn, "acct_bob_t031")
        alice_ids = {m["id"] for m in alice["missions"]}
        bob_ids = {m["id"] for m in bob["missions"]}
        self.assertTrue(alice_ids.isdisjoint(bob_ids))


# ---------------------------------------------------------------------------
# Weak-skill targeting
# ---------------------------------------------------------------------------


class WeakSkillTargetingTests(_MissionTestBase):
    """The weak_skill_drill mission must point at the learner's worst skill."""

    def test_cold_start_falls_back_to_listening(self) -> None:
        """A learner with zero attempts gets the listening drill."""

        with server.db_connection() as conn:
            self.assertEqual(
                missions_service.compute_weak_skill(conn, "acct_alice_t031"),
                missions_service.COLD_START_SKILL,
            )
            payload = missions_service.get_or_generate_today(conn, "acct_alice_t031")
        drill = next(
            m for m in payload["missions"] if m["slot"] == missions_service.SLOT_WEAK_SKILL
        )
        self.assertEqual(drill["skill"], missions_service.COLD_START_SKILL)

    def test_targets_lowest_scoring_skill_from_readiness(self) -> None:
        """Writing scored at 5/15 → drill must target writing."""

        # All four skills at 13 except writing at 5 → writing is the weakest.
        for skill, score in (
            ("listening", 13),
            ("reading", 13),
            ("writing", 5),
            ("speaking", 13),
        ):
            _seed_score(
                account_id="acct_alice_t031",
                attempt_id=f"att_alice_weak_{skill}",
                skill=skill,
                score=score,
            )

        with server.db_connection() as conn:
            weak = missions_service.compute_weak_skill(conn, "acct_alice_t031")
            self.assertEqual(weak, "writing")
            payload = missions_service.get_or_generate_today(conn, "acct_alice_t031")
        drill = next(
            m for m in payload["missions"]
            if m["slot"] == missions_service.SLOT_WEAK_SKILL
        )
        self.assertEqual(drill["skill"], "writing")
        self.assertEqual(drill["kind"], "weak_skill_drill")
        # Payload metadata identifies the source — keeps analytics clean.
        self.assertEqual(drill["payload"]["skill"], "writing")
        self.assertEqual(drill["payload"]["source"], "readiness_weak_skill")

    def test_speaking_lowest_targets_speaking(self) -> None:
        for skill, score in (
            ("listening", 12),
            ("reading", 12),
            ("writing", 12),
            ("speaking", 3),
        ):
            _seed_score(
                account_id="acct_alice_t031",
                attempt_id=f"att_alice_speak_{skill}",
                skill=skill,
                score=score,
            )
        with server.db_connection() as conn:
            self.assertEqual(
                missions_service.compute_weak_skill(conn, "acct_alice_t031"),
                "speaking",
            )


# ---------------------------------------------------------------------------
# Completion idempotency + analytics
# ---------------------------------------------------------------------------


class MissionCompletionTests(_MissionTestBase):
    """Completion must flip the flag exactly once and emit exactly one event."""

    def test_first_completion_flips_flag_and_emits_event(self) -> None:
        with server.db_connection() as conn:
            payload = missions_service.get_or_generate_today(conn, "acct_alice_t031")
            mission_id = payload["missions"][0]["id"]
            result = missions_service.complete_mission(
                conn, "acct_alice_t031", mission_id
            )
        self.assertTrue(result["mission"]["completed"])
        self.assertIsNotNone(result["mission"]["completed_at"])
        self.assertTrue(result["analytics_event_emitted"])
        self.assertEqual(result["summary"]["completed"], 1)
        self.assertEqual(result["summary"]["total"], 3)

    def test_second_completion_is_idempotent_and_silent(self) -> None:
        with server.db_connection() as conn:
            payload = missions_service.get_or_generate_today(conn, "acct_alice_t031")
            mission_id = payload["missions"][0]["id"]
            first = missions_service.complete_mission(
                conn, "acct_alice_t031", mission_id
            )
            second = missions_service.complete_mission(
                conn, "acct_alice_t031", mission_id
            )
        # Same row returned; first emitted an event, second did NOT.
        self.assertTrue(first["analytics_event_emitted"])
        self.assertFalse(second["analytics_event_emitted"])
        self.assertEqual(
            first["mission"]["completed_at"],
            second["mission"]["completed_at"],
            "completed_at must be locked on first completion",
        )
        # Only one analytics row exists for this mission.
        with server.db_connection() as conn:
            row_count = conn.execute(
                """
                SELECT COUNT(*) AS n FROM mission_analytics_events
                WHERE account_id = ? AND mission_id = ? AND event = ?
                """,
                ("acct_alice_t031", mission_id, "mission_completed"),
            ).fetchone()["n"]
        self.assertEqual(row_count, 1)

    def test_complete_unknown_mission_raises_value_error(self) -> None:
        with server.db_connection() as conn:
            with self.assertRaises(ValueError):
                missions_service.complete_mission(
                    conn, "acct_alice_t031", "msn_does_not_exist"
                )

    def test_other_account_cannot_complete_mission(self) -> None:
        """Bob must not be able to flip Alice's mission."""

        with server.db_connection() as conn:
            payload = missions_service.get_or_generate_today(conn, "acct_alice_t031")
            mission_id = payload["missions"][0]["id"]
            with self.assertRaises(PermissionError):
                missions_service.complete_mission(
                    conn, "acct_bob_t031", mission_id
                )
        # And the row remains uncompleted.
        with server.db_connection() as conn:
            row = conn.execute(
                "SELECT completed_at FROM daily_missions WHERE id = ?",
                (mission_id,),
            ).fetchone()
        self.assertIsNone(row["completed_at"])

    def test_completing_all_three_marks_summary_ratio_one(self) -> None:
        with server.db_connection() as conn:
            payload = missions_service.get_or_generate_today(conn, "acct_alice_t031")
            for m in payload["missions"]:
                missions_service.complete_mission(
                    conn, "acct_alice_t031", m["id"]
                )
            final = missions_service.get_or_generate_today(conn, "acct_alice_t031")
        self.assertEqual(final["summary"]["completed"], 3)
        self.assertEqual(final["summary"]["ratio"], 1.0)
        for m in final["missions"]:
            self.assertTrue(m["completed"])


# ---------------------------------------------------------------------------
# Routing-wiring contract — verifies the install hook is in place.
# ---------------------------------------------------------------------------


class MissionRoutesContractTests(unittest.TestCase):
    """Structural assertions on the dispatcher wiring."""

    def test_routes_module_documents_today_and_complete(self) -> None:
        from server_app.routes import missions as mission_routes
        documented = {(method, pattern) for method, pattern in mission_routes.ROUTES}
        self.assertIn(("GET", "/api/missions/today"), documented)
        self.assertIn(
            ("POST", "/api/missions/<mission_id>/complete"), documented
        )

    def test_install_marker_is_set_on_app_handler(self) -> None:
        """The end-of-core hook must have run during import."""

        from server_app import AppHandler
        self.assertTrue(getattr(AppHandler, "_t031_installed", False))


if __name__ == "__main__":  # pragma: no cover - manual invocation
    unittest.main()
