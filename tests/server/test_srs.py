"""T-032 — Spaced-repetition (SM-2) service tests.

Covers the four deliverables called out in the T-032 brief:

1. **SM-2 correctness** — the ease update formula matches the original
   SuperMemo-2 paper (Wozniak), and the interval progression follows the
   canonical ``1d → 6d → interval * ease`` schedule.
2. **Due selection** — :func:`due_cards` returns the cards whose
   ``next_due <= today`` (UTC), sorted oldest-due-first, and is capped
   by :data:`srs_service.DEFAULT_DUE_LIMIT`.
3. **Quality 0 resets ease** — a single ``quality 0`` lapse resets the
   repetition index to ``0`` and the schedule to the first-interval
   baseline; the ease itself is bumped down but never below
   :data:`srs_service.MIN_EASE`.
4. **Multi-user isolation** — Alice's deck never bleeds into Bob's
   ``due_cards`` query, and :func:`review_card` refuses to mutate a
   card that belongs to another account.

The service is exercised directly (no HTTP plumbing); the dispatch
hooks are verified at the structural level via ``ROUTES`` + the install
marker on ``AppHandler``.
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
from server_app.services import srs as srs_service  # noqa: E402


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


# ---------------------------------------------------------------------------
# Base fixture — fresh tmp DB per test.
# ---------------------------------------------------------------------------


class _SrsTestBase(unittest.TestCase):
    """Shared scaffolding for every T-032 test."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "auth.sqlite3"
        self.auth_db_patch = patch.object(server, "AUTH_DB_PATH", self.db_path)
        self.auth_db_patch.start()
        # The SRS DDL guards itself with a once-flag; reset it so the
        # tables get re-created against this fresh tmp DB.
        srs_service._reset_ddl_cache_for_tests()
        server.init_auth_store()
        with server.db_connection() as conn:
            srs_service.ensure_srs_schema(conn)
        _seed_account("acct_alice_t032", "alice@example.test")
        _seed_account("acct_bob_t032", "bob@example.test")

    def tearDown(self) -> None:
        self.auth_db_patch.stop()
        self.tmpdir.cleanup()
        srs_service._reset_ddl_cache_for_tests()


# ---------------------------------------------------------------------------
# SM-2 algorithm correctness
# ---------------------------------------------------------------------------


class Sm2CorrectnessTests(_SrsTestBase):
    """The SuperMemo-2 update matches the original paper's formulas."""

    def test_new_card_starts_at_default_ease(self) -> None:
        with server.db_connection() as conn:
            card = srs_service.add_card(
                conn, "acct_alice_t032", "māja", "māja", "house"
            )
        self.assertEqual(card["ease"], srs_service.DEFAULT_EASE)
        self.assertEqual(card["interval_days"], 0)
        self.assertEqual(card["repetitions"], 0)

    def test_first_grade_5_schedules_one_day_out(self) -> None:
        """The very first successful recall puts the card 1 day out."""

        anchor = datetime(2026, 5, 24, 10, 0, tzinfo=timezone.utc)
        with server.db_connection() as conn:
            card = srs_service.add_card(
                conn, "acct_alice_t032", "māja", "māja", "house", now=anchor
            )
            updated = srs_service.review_card(
                conn, "acct_alice_t032", card["id"], 5, now=anchor
            )
        self.assertEqual(updated["interval_days"], 1)
        self.assertEqual(updated["repetitions"], 1)
        # 5 → ease bumps by 0.1 → 2.6
        self.assertAlmostEqual(updated["ease"], 2.6, places=6)
        self.assertEqual(updated["next_due"], "2026-05-25")

    def test_second_grade_5_schedules_six_days_out(self) -> None:
        anchor = datetime(2026, 5, 24, 10, 0, tzinfo=timezone.utc)
        with server.db_connection() as conn:
            card = srs_service.add_card(
                conn, "acct_alice_t032", "māja", "māja", "house", now=anchor
            )
            srs_service.review_card(
                conn, "acct_alice_t032", card["id"], 5, now=anchor
            )
            second = srs_service.review_card(
                conn,
                "acct_alice_t032",
                card["id"],
                5,
                now=anchor + timedelta(days=1),
            )
        self.assertEqual(second["interval_days"], 6)
        self.assertEqual(second["repetitions"], 2)
        self.assertEqual(second["next_due"], "2026-05-31")

    def test_third_grade_5_multiplies_interval_by_ease(self) -> None:
        """After the 2nd success the interval is ``previous_interval * ease``."""

        anchor = datetime(2026, 5, 24, 10, 0, tzinfo=timezone.utc)
        with server.db_connection() as conn:
            card = srs_service.add_card(
                conn, "acct_alice_t032", "māja", "māja", "house", now=anchor
            )
            srs_service.review_card(
                conn, "acct_alice_t032", card["id"], 5, now=anchor
            )
            srs_service.review_card(
                conn,
                "acct_alice_t032",
                card["id"],
                5,
                now=anchor + timedelta(days=1),
            )
            third = srs_service.review_card(
                conn,
                "acct_alice_t032",
                card["id"],
                5,
                now=anchor + timedelta(days=7),
            )
        # After three grade-5s, ease = 2.5 + 3 * 0.1 = 2.8
        self.assertAlmostEqual(third["ease"], 2.8, places=6)
        # Interval = round(6 * 2.8) = 17
        self.assertEqual(third["interval_days"], 17)
        self.assertEqual(third["repetitions"], 3)

    def test_grade_3_keeps_card_in_recall_path(self) -> None:
        """Grade 3 is the minimum recall — still increments repetitions."""

        with server.db_connection() as conn:
            card = srs_service.add_card(
                conn, "acct_alice_t032", "māja", "māja", "house"
            )
            updated = srs_service.review_card(
                conn, "acct_alice_t032", card["id"], 3
            )
        # Grade 3 → delta = 0.1 - 2*(0.08 + 2*0.02) = 0.1 - 0.24 = -0.14
        # Ease = 2.5 - 0.14 = 2.36
        self.assertAlmostEqual(updated["ease"], 2.36, places=6)
        self.assertEqual(updated["repetitions"], 1)
        self.assertEqual(updated["interval_days"], 1)

    def test_ease_never_falls_below_floor(self) -> None:
        """Successive bad reviews must clamp ease at MIN_EASE (1.3)."""

        with server.db_connection() as conn:
            card = srs_service.add_card(
                conn, "acct_alice_t032", "māja", "māja", "house"
            )
            for _ in range(20):
                updated = srs_service.review_card(
                    conn, "acct_alice_t032", card["id"], 0
                )
        self.assertAlmostEqual(updated["ease"], srs_service.MIN_EASE, places=6)


# ---------------------------------------------------------------------------
# Due selection
# ---------------------------------------------------------------------------


class DueSelectionTests(_SrsTestBase):
    """``due_cards`` returns cards with ``next_due <= today`` only."""

    def test_new_card_is_due_today(self) -> None:
        with server.db_connection() as conn:
            srs_service.add_card(
                conn, "acct_alice_t032", "māja", "māja", "house"
            )
            due = srs_service.due_cards(conn, "acct_alice_t032")
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0]["lemma"], "māja")

    def test_card_with_future_due_is_not_returned(self) -> None:
        anchor = datetime(2026, 5, 24, 10, 0, tzinfo=timezone.utc)
        with server.db_connection() as conn:
            card = srs_service.add_card(
                conn, "acct_alice_t032", "māja", "māja", "house", now=anchor
            )
            # Successful recall on day 0 → next_due = day 1.
            srs_service.review_card(
                conn, "acct_alice_t032", card["id"], 5, now=anchor
            )
            # Query while still on day 0 → empty queue.
            due = srs_service.due_cards(conn, "acct_alice_t032", now=anchor)
        self.assertEqual(due, [])

    def test_due_again_after_interval_elapses(self) -> None:
        anchor = datetime(2026, 5, 24, 10, 0, tzinfo=timezone.utc)
        with server.db_connection() as conn:
            card = srs_service.add_card(
                conn, "acct_alice_t032", "māja", "māja", "house", now=anchor
            )
            srs_service.review_card(
                conn, "acct_alice_t032", card["id"], 5, now=anchor
            )
            due_after_one_day = srs_service.due_cards(
                conn, "acct_alice_t032", now=anchor + timedelta(days=1)
            )
        self.assertEqual(len(due_after_one_day), 1)

    def test_due_sorted_oldest_first(self) -> None:
        """When multiple cards are due, the oldest ``next_due`` wins."""

        anchor = datetime(2026, 5, 24, 10, 0, tzinfo=timezone.utc)
        with server.db_connection() as conn:
            # Three cards, all due today.
            for offset, lemma in enumerate(["a", "b", "c"]):
                srs_service.add_card(
                    conn,
                    "acct_alice_t032",
                    lemma,
                    lemma,
                    f"english_{lemma}",
                    now=anchor + timedelta(seconds=offset),
                )
            due = srs_service.due_cards(conn, "acct_alice_t032")
        # All due today; tie-broken by created_at ASC.
        self.assertEqual([c["lemma"] for c in due], ["a", "b", "c"])

    def test_due_respects_explicit_limit(self) -> None:
        with server.db_connection() as conn:
            for i in range(5):
                srs_service.add_card(
                    conn, "acct_alice_t032", f"word_{i}", f"word_{i}", f"en_{i}"
                )
            due = srs_service.due_cards(conn, "acct_alice_t032", limit=2)
        self.assertEqual(len(due), 2)


# ---------------------------------------------------------------------------
# Quality 0 resets ease (+ repetition index)
# ---------------------------------------------------------------------------


class Quality0ResetTests(_SrsTestBase):
    """A single ``quality 0`` review resets the schedule to baseline."""

    def test_quality_zero_resets_repetitions_to_zero(self) -> None:
        anchor = datetime(2026, 5, 24, 10, 0, tzinfo=timezone.utc)
        with server.db_connection() as conn:
            card = srs_service.add_card(
                conn, "acct_alice_t032", "māja", "māja", "house", now=anchor
            )
            # Two successful recalls → repetitions = 2, interval = 6
            srs_service.review_card(
                conn, "acct_alice_t032", card["id"], 5, now=anchor
            )
            after_two = srs_service.review_card(
                conn,
                "acct_alice_t032",
                card["id"],
                5,
                now=anchor + timedelta(days=1),
            )
            self.assertEqual(after_two["repetitions"], 2)

            # Now a quality-0 blackout → repetitions resets to 0,
            # interval back to FIRST_INTERVAL_DAYS.
            lapsed = srs_service.review_card(
                conn,
                "acct_alice_t032",
                card["id"],
                0,
                now=anchor + timedelta(days=7),
            )
        self.assertEqual(lapsed["repetitions"], 0)
        self.assertEqual(lapsed["interval_days"], srs_service.FIRST_INTERVAL_DAYS)

    def test_quality_zero_drops_ease_but_holds_at_floor(self) -> None:
        """Ease falls but never below MIN_EASE on a single quality-0."""

        with server.db_connection() as conn:
            card = srs_service.add_card(
                conn, "acct_alice_t032", "māja", "māja", "house"
            )
            # First quality-0 from default 2.5 ease:
            #   delta = 0.1 - 5*(0.08 + 5*0.02) = 0.1 - 5*0.18 = -0.8
            #   ease = max(1.3, 2.5 - 0.8) = 1.7
            after = srs_service.review_card(
                conn, "acct_alice_t032", card["id"], 0
            )
        self.assertAlmostEqual(after["ease"], 1.7, places=6)
        self.assertGreaterEqual(after["ease"], srs_service.MIN_EASE)

    def test_quality_zero_keeps_card_in_due_queue(self) -> None:
        """A lapse must keep the card in the daily queue for re-drill."""

        anchor = datetime(2026, 5, 24, 10, 0, tzinfo=timezone.utc)
        with server.db_connection() as conn:
            card = srs_service.add_card(
                conn, "acct_alice_t032", "māja", "māja", "house", now=anchor
            )
            srs_service.review_card(
                conn, "acct_alice_t032", card["id"], 0, now=anchor
            )
            # Tomorrow the card must reappear.
            due_tomorrow = srs_service.due_cards(
                conn, "acct_alice_t032", now=anchor + timedelta(days=1)
            )
        self.assertEqual(len(due_tomorrow), 1)
        self.assertEqual(due_tomorrow[0]["id"], card["id"])

    def test_review_appends_one_row_to_reviews_table(self) -> None:
        with server.db_connection() as conn:
            card = srs_service.add_card(
                conn, "acct_alice_t032", "māja", "māja", "house"
            )
            srs_service.review_card(
                conn, "acct_alice_t032", card["id"], 0
            )
            srs_service.review_card(
                conn, "acct_alice_t032", card["id"], 4
            )
            rows = conn.execute(
                "SELECT quality FROM srs_reviews WHERE card_id = ? ORDER BY reviewed_at",
                (card["id"],),
            ).fetchall()
        self.assertEqual([int(r["quality"]) for r in rows], [0, 4])


# ---------------------------------------------------------------------------
# Multi-user isolation
# ---------------------------------------------------------------------------


class MultiUserIsolationTests(_SrsTestBase):
    """Alice's deck must not leak into Bob's queue, and vice versa."""

    def test_alice_due_excludes_bob_cards(self) -> None:
        with server.db_connection() as conn:
            srs_service.add_card(
                conn, "acct_alice_t032", "māja", "māja", "house"
            )
            srs_service.add_card(
                conn, "acct_bob_t032", "māja", "māja", "house"
            )
            srs_service.add_card(
                conn, "acct_bob_t032", "suns", "suns", "dog"
            )
            alice = srs_service.due_cards(conn, "acct_alice_t032")
            bob = srs_service.due_cards(conn, "acct_bob_t032")
        self.assertEqual([c["lemma"] for c in alice], ["māja"])
        self.assertEqual(sorted(c["lemma"] for c in bob), ["māja", "suns"])
        # No card id can appear in both queues.
        alice_ids = {c["id"] for c in alice}
        bob_ids = {c["id"] for c in bob}
        self.assertEqual(alice_ids & bob_ids, set())

    def test_review_rejects_foreign_card(self) -> None:
        """``review_card`` raises PermissionError for an other-user card."""

        with server.db_connection() as conn:
            alice_card = srs_service.add_card(
                conn, "acct_alice_t032", "māja", "māja", "house"
            )
            with self.assertRaises(PermissionError):
                srs_service.review_card(
                    conn, "acct_bob_t032", alice_card["id"], 5
                )

    def test_get_card_returns_none_for_foreign_card(self) -> None:
        with server.db_connection() as conn:
            alice_card = srs_service.add_card(
                conn, "acct_alice_t032", "māja", "māja", "house"
            )
            self.assertIsNone(
                srs_service.get_card(conn, "acct_bob_t032", alice_card["id"])
            )

    def test_add_card_is_idempotent_per_account_lemma(self) -> None:
        """Same ``(account_id, lemma)`` returns the existing row."""

        with server.db_connection() as conn:
            first = srs_service.add_card(
                conn, "acct_alice_t032", "māja", "māja", "house"
            )
            second = srs_service.add_card(
                conn, "acct_alice_t032", "māja", "māja", "house"
            )
        self.assertEqual(first["id"], second["id"])

    def test_same_lemma_different_account_gets_different_card(self) -> None:
        with server.db_connection() as conn:
            alice = srs_service.add_card(
                conn, "acct_alice_t032", "māja", "māja", "house"
            )
            bob = srs_service.add_card(
                conn, "acct_bob_t032", "māja", "māja", "house"
            )
        self.assertNotEqual(alice["id"], bob["id"])


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class ValidationTests(_SrsTestBase):
    """Service-level argument validation."""

    def test_quality_out_of_range_raises(self) -> None:
        with server.db_connection() as conn:
            card = srs_service.add_card(
                conn, "acct_alice_t032", "māja", "māja", "house"
            )
            with self.assertRaises(ValueError):
                srs_service.review_card(
                    conn, "acct_alice_t032", card["id"], 6
                )
            with self.assertRaises(ValueError):
                srs_service.review_card(
                    conn, "acct_alice_t032", card["id"], -1
                )

    def test_add_card_requires_all_fields(self) -> None:
        with server.db_connection() as conn:
            with self.assertRaises(ValueError):
                srs_service.add_card(
                    conn, "acct_alice_t032", "", "māja", "house"
                )
            with self.assertRaises(ValueError):
                srs_service.add_card(
                    conn, "acct_alice_t032", "māja", "māja", ""
                )


# ---------------------------------------------------------------------------
# Routing-wiring contract — verifies the install hook is in place.
# ---------------------------------------------------------------------------


class SrsRoutesContractTests(unittest.TestCase):
    """Structural assertions on the dispatcher wiring."""

    def test_routes_module_documents_endpoints(self) -> None:
        from server_app.routes import srs as srs_routes
        documented = {(m, p) for m, p in srs_routes.ROUTES}
        self.assertIn(("GET", "/api/srs/due"), documented)
        self.assertIn(("POST", "/api/srs/cards"), documented)
        self.assertIn(("POST", "/api/srs/cards/{card_id}/review"), documented)

    def test_install_marker_is_set_on_app_handler(self) -> None:
        """The end-of-core hook must have run during import."""

        from server_app import AppHandler
        self.assertTrue(getattr(AppHandler, "_t032_installed", False))


if __name__ == "__main__":  # pragma: no cover - manual invocation
    unittest.main()
