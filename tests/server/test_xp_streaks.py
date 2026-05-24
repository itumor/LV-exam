"""T-034 — XP + streak engine tests.

Covers the four deliverables called out in the T-034 brief:

1. **XP accumulation** — repeated awards across all four canonical kinds
   (``mission_complete``, ``quiz_correct``, ``mock_exam_complete``,
   ``perfect_skill_pass``) sum into ``total_xp``; each award writes one
   ``xp_log`` row tagged with the right kind.
2. **Streak continuity** — daily activity across consecutive local days
   increments ``current_days``; same-day repeat activity is idempotent.
3. **Gap reset** — silence > 36 hours resets ``current_days`` to 1.
4. **Longest preserved** — ``longest_days`` never decreases, even when
   the current streak resets after a gap.

The service is exercised directly (no HTTP plumbing); the dispatch hook
is verified at the structural level via ``ROUTES`` + the install marker
on ``AppHandler``.
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

# Ensure repo root is on sys.path so ``import server`` resolves under
# ``python -m unittest`` from arbitrary cwd.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import server  # noqa: E402  (shim → server_app.core; runs route hook installs)
from server_app.services import xp as xp_service  # noqa: E402


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _seed_account(account_id: str, email: str, *, tz: str | None = None) -> None:
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
        # ``user_timezone`` column may or may not exist depending on
        # migrations; tolerate failure so tests don't depend on the T-029
        # learner-timezone migration being applied.
        if tz:
            try:
                conn.execute(
                    "UPDATE accounts SET user_timezone = ? WHERE id = ?",
                    (tz, account_id),
                )
            except sqlite3.OperationalError:
                pass


# ---------------------------------------------------------------------------
# Base fixture — fresh tmp DB per test.
# ---------------------------------------------------------------------------


class _XpTestBase(unittest.TestCase):
    """Shared scaffolding for every T-034 test."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "auth.sqlite3"
        self.auth_db_patch = patch.object(server, "AUTH_DB_PATH", self.db_path)
        self.auth_db_patch.start()
        # The XP DDL guards itself with a once-flag; reset it so the
        # tables get re-created against this fresh tmp DB.
        xp_service._reset_ddl_cache_for_tests()
        server.init_auth_store()
        with server.db_connection() as conn:
            xp_service.ensure_xp_schema(conn)
        _seed_account("acct_alice_t034", "alice@example.test")
        _seed_account("acct_bob_t034", "bob@example.test")

    def tearDown(self) -> None:
        self.auth_db_patch.stop()
        self.tmpdir.cleanup()
        xp_service._reset_ddl_cache_for_tests()


# ---------------------------------------------------------------------------
# XP accumulation
# ---------------------------------------------------------------------------


class XpAccumulationTests(_XpTestBase):
    """Repeated awards must sum into ``total_xp`` and emit ``xp_log`` rows."""

    def test_mission_complete_awards_ten_xp(self) -> None:
        with server.db_connection() as conn:
            result = xp_service.award_xp(
                conn, "acct_alice_t034", xp_service.KIND_MISSION_COMPLETE
            )
        self.assertEqual(result["awarded"]["amount"], 10)
        self.assertEqual(result["total_xp"], 10)

    def test_quiz_correct_awards_two_xp_per_correct(self) -> None:
        with server.db_connection() as conn:
            # Single answer ⇒ 2 XP.
            xp_service.award_xp(
                conn, "acct_alice_t034", xp_service.KIND_QUIZ_CORRECT
            )
            # Batch of 5 correct answers ⇒ 10 XP.
            xp_service.award_xp(
                conn,
                "acct_alice_t034",
                xp_service.KIND_QUIZ_CORRECT,
                amount=5 * xp_service.XP_AMOUNTS[xp_service.KIND_QUIZ_CORRECT],
            )
            summary = xp_service.get_summary(conn, "acct_alice_t034")
        self.assertEqual(summary["total_xp"], 12)

    def test_mock_exam_complete_awards_fifty_xp(self) -> None:
        with server.db_connection() as conn:
            result = xp_service.award_xp(
                conn, "acct_alice_t034", xp_service.KIND_MOCK_EXAM_COMPLETE
            )
        self.assertEqual(result["awarded"]["amount"], 50)
        self.assertEqual(result["total_xp"], 50)

    def test_perfect_skill_pass_awards_one_hundred_xp_bonus(self) -> None:
        with server.db_connection() as conn:
            result = xp_service.award_xp(
                conn, "acct_alice_t034", xp_service.KIND_PERFECT_SKILL_PASS
            )
        self.assertEqual(result["awarded"]["amount"], 100)
        self.assertEqual(result["total_xp"], 100)

    def test_repeated_awards_sum_total(self) -> None:
        with server.db_connection() as conn:
            xp_service.award_xp(
                conn, "acct_alice_t034", xp_service.KIND_MISSION_COMPLETE
            )
            xp_service.award_xp(
                conn,
                "acct_alice_t034",
                xp_service.KIND_QUIZ_CORRECT,
                amount=6,
            )
            xp_service.award_xp(
                conn,
                "acct_alice_t034",
                xp_service.KIND_MOCK_EXAM_COMPLETE,
            )
            xp_service.award_xp(
                conn,
                "acct_alice_t034",
                xp_service.KIND_PERFECT_SKILL_PASS,
            )
            summary = xp_service.get_summary(conn, "acct_alice_t034")
        self.assertEqual(summary["total_xp"], 10 + 6 + 50 + 100)
        self.assertEqual(len(summary["recent_log"]), 4)
        kinds_seen = {entry["kind"] for entry in summary["recent_log"]}
        self.assertEqual(
            kinds_seen,
            {
                xp_service.KIND_MISSION_COMPLETE,
                xp_service.KIND_QUIZ_CORRECT,
                xp_service.KIND_MOCK_EXAM_COMPLETE,
                xp_service.KIND_PERFECT_SKILL_PASS,
            },
        )

    def test_recent_log_newest_first_and_limited(self) -> None:
        with server.db_connection() as conn:
            for i in range(15):
                xp_service.award_xp(
                    conn,
                    "acct_alice_t034",
                    xp_service.KIND_QUIZ_CORRECT,
                    payload={"index": i},
                )
            summary = xp_service.get_summary(
                conn, "acct_alice_t034", recent_limit=10
            )
        self.assertEqual(len(summary["recent_log"]), 10)
        # awarded_at must be monotonically non-increasing.
        timestamps = [row["awarded_at"] for row in summary["recent_log"]]
        self.assertEqual(timestamps, sorted(timestamps, reverse=True))

    def test_awards_are_isolated_per_account(self) -> None:
        with server.db_connection() as conn:
            xp_service.award_xp(
                conn, "acct_alice_t034", xp_service.KIND_MISSION_COMPLETE
            )
            xp_service.award_xp(
                conn, "acct_bob_t034", xp_service.KIND_MOCK_EXAM_COMPLETE
            )
            alice = xp_service.get_summary(conn, "acct_alice_t034")
            bob = xp_service.get_summary(conn, "acct_bob_t034")
        self.assertEqual(alice["total_xp"], 10)
        self.assertEqual(bob["total_xp"], 50)


# ---------------------------------------------------------------------------
# Streak continuity, gap reset, and longest preservation
# ---------------------------------------------------------------------------


class StreakContinuityTests(_XpTestBase):
    """Daily activity bumps the streak; same-day repeats are idempotent."""

    def test_first_award_starts_streak_at_one(self) -> None:
        with server.db_connection() as conn:
            result = xp_service.award_xp(
                conn, "acct_alice_t034", xp_service.KIND_MISSION_COMPLETE
            )
        self.assertEqual(result["current_streak"], 1)
        self.assertEqual(result["longest_streak"], 1)

    def test_same_day_repeat_keeps_streak_at_one(self) -> None:
        instant = datetime(2026, 5, 24, 9, 0, tzinfo=timezone.utc)
        with server.db_connection() as conn:
            xp_service.award_xp(
                conn,
                "acct_alice_t034",
                xp_service.KIND_MISSION_COMPLETE,
                now=instant,
            )
            second = xp_service.award_xp(
                conn,
                "acct_alice_t034",
                xp_service.KIND_QUIZ_CORRECT,
                now=instant + timedelta(hours=2),
            )
        self.assertEqual(second["current_streak"], 1)
        self.assertEqual(second["longest_streak"], 1)

    def test_consecutive_days_increment_streak(self) -> None:
        day0 = datetime(2026, 5, 24, 9, 0, tzinfo=timezone.utc)
        with server.db_connection() as conn:
            for offset in range(5):
                xp_service.award_xp(
                    conn,
                    "acct_alice_t034",
                    xp_service.KIND_MISSION_COMPLETE,
                    now=day0 + timedelta(days=offset),
                )
            summary = xp_service.get_summary(conn, "acct_alice_t034")
        self.assertEqual(summary["current_streak"], 5)
        self.assertEqual(summary["longest_streak"], 5)

    def test_thirty_six_hour_gap_does_not_reset(self) -> None:
        """A 30-hour gap (next calendar day) should bump the streak, not reset it."""

        # Award at day 0 12:00, then day 1 18:00 — a 30h gap that
        # crosses one local-day boundary.
        with server.db_connection() as conn:
            xp_service.award_xp(
                conn,
                "acct_alice_t034",
                xp_service.KIND_MISSION_COMPLETE,
                now=datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc),
            )
            result = xp_service.award_xp(
                conn,
                "acct_alice_t034",
                xp_service.KIND_MISSION_COMPLETE,
                now=datetime(2026, 5, 25, 18, 0, tzinfo=timezone.utc),
            )
        self.assertEqual(result["current_streak"], 2)


class StreakGapResetTests(_XpTestBase):
    """A gap > 36h resets the streak to 1 but never lowers the longest."""

    def test_gap_over_thirty_six_hours_resets_to_one(self) -> None:
        day0 = datetime(2026, 5, 20, 9, 0, tzinfo=timezone.utc)
        with server.db_connection() as conn:
            for offset in range(3):
                xp_service.award_xp(
                    conn,
                    "acct_alice_t034",
                    xp_service.KIND_MISSION_COMPLETE,
                    now=day0 + timedelta(days=offset),
                )
            # Sanity: streak is 3 after three consecutive days.
            summary = xp_service.get_summary(conn, "acct_alice_t034")
            self.assertEqual(summary["current_streak"], 3)

            # Now skip ~2 days (48h gap > 36h cutoff).
            reset = xp_service.award_xp(
                conn,
                "acct_alice_t034",
                xp_service.KIND_MISSION_COMPLETE,
                now=day0 + timedelta(days=4, hours=12),
            )
        self.assertEqual(reset["current_streak"], 1)
        # Longest must remain at the previous high-water mark.
        self.assertEqual(reset["longest_streak"], 3)


class LongestStreakPreservationTests(_XpTestBase):
    """``longest_days`` only grows — confirms it survives a reset."""

    def test_longest_grows_then_holds_after_reset(self) -> None:
        day0 = datetime(2026, 5, 1, 8, 0, tzinfo=timezone.utc)
        with server.db_connection() as conn:
            # Streak of 7.
            for offset in range(7):
                xp_service.award_xp(
                    conn,
                    "acct_alice_t034",
                    xp_service.KIND_MISSION_COMPLETE,
                    now=day0 + timedelta(days=offset),
                )
            self.assertEqual(
                xp_service.get_summary(conn, "acct_alice_t034")["current_streak"],
                7,
            )
            # Now a 4-day gap → reset to 1.
            xp_service.award_xp(
                conn,
                "acct_alice_t034",
                xp_service.KIND_MISSION_COMPLETE,
                now=day0 + timedelta(days=11),
            )
            after_reset = xp_service.get_summary(conn, "acct_alice_t034")
        self.assertEqual(after_reset["current_streak"], 1)
        self.assertEqual(after_reset["longest_streak"], 7)

    def test_new_high_replaces_longest(self) -> None:
        """A new streak that beats the previous best updates longest."""

        day0 = datetime(2026, 5, 1, 8, 0, tzinfo=timezone.utc)
        with server.db_connection() as conn:
            for offset in range(3):
                xp_service.award_xp(
                    conn,
                    "acct_alice_t034",
                    xp_service.KIND_MISSION_COMPLETE,
                    now=day0 + timedelta(days=offset),
                )
            # Reset + grow to 5.
            for offset in range(5):
                xp_service.award_xp(
                    conn,
                    "acct_alice_t034",
                    xp_service.KIND_MISSION_COMPLETE,
                    now=day0 + timedelta(days=10 + offset),
                )
            final = xp_service.get_summary(conn, "acct_alice_t034")
        self.assertEqual(final["current_streak"], 5)
        self.assertEqual(final["longest_streak"], 5)


# ---------------------------------------------------------------------------
# Summary endpoint shape
# ---------------------------------------------------------------------------


class SummaryShapeTests(_XpTestBase):
    """The summary returned by ``get_summary`` matches the brief's contract."""

    def test_empty_account_returns_zero_totals_and_empty_log(self) -> None:
        with server.db_connection() as conn:
            summary = xp_service.get_summary(conn, "acct_alice_t034")
        self.assertEqual(summary["total_xp"], 0)
        self.assertEqual(summary["current_streak"], 0)
        self.assertEqual(summary["longest_streak"], 0)
        self.assertEqual(summary["recent_log"], [])

    def test_summary_keys_match_brief_contract(self) -> None:
        with server.db_connection() as conn:
            xp_service.award_xp(
                conn, "acct_alice_t034", xp_service.KIND_MISSION_COMPLETE
            )
            summary = xp_service.get_summary(conn, "acct_alice_t034")
        expected = {"total_xp", "current_streak", "longest_streak", "recent_log"}
        self.assertTrue(expected.issubset(summary.keys()))


# ---------------------------------------------------------------------------
# Routing-wiring contract — verifies the install hook is in place.
# ---------------------------------------------------------------------------


class XpRoutesContractTests(unittest.TestCase):
    """Structural assertions on the dispatcher wiring."""

    def test_routes_module_documents_summary(self) -> None:
        from server_app.routes import xp as xp_routes
        documented = {(method, pattern) for method, pattern in xp_routes.ROUTES}
        self.assertIn(("GET", "/api/xp/summary"), documented)

    def test_install_marker_is_set_on_app_handler(self) -> None:
        """The end-of-core hook must have run during import."""

        from server_app import AppHandler
        self.assertTrue(getattr(AppHandler, "_t034_installed", False))


if __name__ == "__main__":  # pragma: no cover - manual invocation
    unittest.main()
