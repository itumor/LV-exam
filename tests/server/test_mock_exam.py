"""T-033 — Mock-exam orchestration tests.

Covers the deliverables called out in the T-033 brief:

1. **Timer expiry** — calling :func:`expire_section` records a row with
   ``expired=True`` and clamps the time-spent at the section budget.
2. **Partial completion** — a sitting where only some sections were
   submitted reports the missing sections as ``score=None`` in the
   result payload and ``overall.pass=False``.
3. **Full submission scoring** — submitting all four sections with
   passing scores yields a result with ``overall.pass=True`` and an
   empty ``weak_skill_suggestions`` list.
4. **History listing** — every mock-exam shows up in
   :func:`list_history` newest-first with the per-skill score map
   inlined.
5. **Idempotent submission** — re-submitting the same section returns
   the original score with ``idempotent=True`` and never double-scores.
6. **Multi-user isolation** — user B cannot read user A's mock-exam.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import server  # noqa: F401  — ensures package import side-effects run
from server_app.services import mock_exam as mock_exam_service
from server_app.services.mock_exam import (
    MockExamNotFound,
    SECTION_DURATIONS_SECONDS,
    TOTAL_DURATION_SECONDS,
    expire_section,
    get_result,
    list_history,
    start_mock_exam,
    submit_section,
)


def _seed_account(account_id: str, email: str) -> None:
    """Insert a minimal account row so the FK constraints are satisfied."""

    with server.db_connection() as conn:
        conn.execute(
            """
            INSERT INTO accounts (id, email, password_salt, password_hash,
                                  status, created_at, deleted_at)
            VALUES (?, ?, 'salt', 'hash', 'active', '2026-05-23T00:00:00Z', NULL)
            """,
            (account_id, email),
        )


class MockExamServiceTests(unittest.TestCase):
    """Unit tests for the mock-exam service module (T-033)."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "auth.sqlite3"
        self.auth_db_patch = patch.object(
            server, "AUTH_DB_PATH", self.db_path
        )
        self.auth_db_patch.start()
        # Force the service's one-shot DDL guard to re-apply against
        # this fresh temp DB. Without this, a previously-loaded test
        # leaves the global flag set and our tables never get created.
        mock_exam_service._DDL_APPLIED = False
        server.init_auth_store()
        mock_exam_service.ensure_mock_exam_tables()
        _seed_account("acct_alice_t033", "alice@example.test")
        _seed_account("acct_bob_t033", "bob@example.test")

    def tearDown(self) -> None:
        self.auth_db_patch.stop()
        self.tmpdir.cleanup()
        mock_exam_service._DDL_APPLIED = False

    # ------------------------------------------------------------------
    # Constants — the timer contract is wired in code.
    # ------------------------------------------------------------------

    def test_section_durations_match_brief(self) -> None:
        """Listening 25m, reading 30m, writing 35m, speaking 15m."""

        self.assertEqual(SECTION_DURATIONS_SECONDS["listening"], 25 * 60)
        self.assertEqual(SECTION_DURATIONS_SECONDS["reading"], 30 * 60)
        self.assertEqual(SECTION_DURATIONS_SECONDS["writing"], 35 * 60)
        self.assertEqual(SECTION_DURATIONS_SECONDS["speaking"], 15 * 60)
        self.assertEqual(
            TOTAL_DURATION_SECONDS,
            (25 + 30 + 35 + 15) * 60,
        )

    # ------------------------------------------------------------------
    # 1) Start
    # ------------------------------------------------------------------

    def test_start_returns_durations_and_first_skill(self) -> None:
        result = start_mock_exam("acct_alice_t033")
        self.assertEqual(result["status"], "started")
        self.assertEqual(result["current_skill"], "listening")
        self.assertEqual(
            result["durations_seconds"], dict(SECTION_DURATIONS_SECONDS)
        )
        self.assertEqual(
            result["total_duration_seconds"], TOTAL_DURATION_SECONDS
        )
        self.assertEqual(result["level_code"], "A2")
        self.assertIn("expires_at", result)
        self.assertGreater(result["expires_at"], result["started_at"])

    def test_start_is_idempotent_when_id_supplied(self) -> None:
        first = start_mock_exam(
            "acct_alice_t033", mock_exam_id="mock_fixed"
        )
        second = start_mock_exam(
            "acct_alice_t033", mock_exam_id="mock_fixed"
        )
        self.assertEqual(first["id"], second["id"])

    # ------------------------------------------------------------------
    # 2) Submission scoring
    # ------------------------------------------------------------------

    def test_submit_section_scores_passing_listening(self) -> None:
        sit = start_mock_exam("acct_alice_t033", mock_exam_id="mock_a")
        # 10 correct out of 10 — passes 9/15.
        answer_key = {"task1": ["A"] * 10}
        answers = {"task1": ["A"] * 10}
        result = submit_section(
            sit["id"],
            "acct_alice_t033",
            "listening",
            answers=answers,
            answer_key=answer_key,
        )
        self.assertEqual(result["section"]["score"], 10)
        self.assertTrue(result["section"]["passed"])
        self.assertFalse(result["section"]["expired"])
        self.assertEqual(result["mock_exam"]["status"], "in_progress")
        self.assertEqual(result["mock_exam"]["current_skill"], "reading")

    def test_submit_section_below_threshold_marks_failed(self) -> None:
        sit = start_mock_exam("acct_alice_t033", mock_exam_id="mock_b")
        answer_key = {"task1": ["A"] * 10}
        # Only 5 correct → below 9 → not passing.
        answers = {"task1": ["A"] * 5 + ["wrong"] * 5}
        result = submit_section(
            sit["id"],
            "acct_alice_t033",
            "listening",
            answers=answers,
            answer_key=answer_key,
        )
        self.assertEqual(result["section"]["score"], 5)
        self.assertFalse(result["section"]["passed"])

    def test_submit_section_rejects_unknown_skill(self) -> None:
        sit = start_mock_exam("acct_alice_t033", mock_exam_id="mock_c")
        with self.assertRaises(mock_exam_service.MockExamError):
            submit_section(
                sit["id"], "acct_alice_t033", "telekinesis", answers={}
            )

    def test_submit_section_is_idempotent_per_skill(self) -> None:
        sit = start_mock_exam("acct_alice_t033", mock_exam_id="mock_d")
        answer_key = {"task1": ["A"] * 9}
        answers = {"task1": ["A"] * 9}
        first = submit_section(
            sit["id"],
            "acct_alice_t033",
            "listening",
            answers=answers,
            answer_key=answer_key,
        )
        # Second submit with different answers must NOT overwrite — the
        # service returns the original row with idempotent=True.
        second = submit_section(
            sit["id"],
            "acct_alice_t033",
            "listening",
            answers={"task1": ["wrong"] * 9},
            answer_key=answer_key,
        )
        self.assertTrue(second["idempotent"])
        self.assertEqual(second["section"]["score"], first["section"]["score"])

    # ------------------------------------------------------------------
    # 3) Timer expiry
    # ------------------------------------------------------------------

    def test_expire_section_marks_row_and_clamps_time(self) -> None:
        sit = start_mock_exam("acct_alice_t033", mock_exam_id="mock_e")
        answer_key = {"task1": ["A"] * 10}
        # Learner only managed to answer 3 before the timer fired.
        partial = {"task1": ["A", "A", "A"]}
        result = expire_section(
            sit["id"],
            "acct_alice_t033",
            "listening",
            answers=partial,
            answer_key=answer_key,
            # Misreporting client claims 99 minutes — must be clamped at
            # the listening budget (25 * 60 = 1500 s).
            time_spent_seconds=99 * 60,
        )
        self.assertTrue(result["section"]["expired"])
        self.assertEqual(result["section"]["score"], 3)
        self.assertFalse(result["section"]["passed"])
        self.assertEqual(
            result["section"]["time_spent_seconds"],
            SECTION_DURATIONS_SECONDS["listening"],
        )

    # ------------------------------------------------------------------
    # 4) Result aggregation
    # ------------------------------------------------------------------

    def test_partial_completion_reports_missing_sections(self) -> None:
        sit = start_mock_exam(
            "acct_alice_t033", mock_exam_id="mock_partial"
        )
        # Only listening submitted.
        submit_section(
            sit["id"],
            "acct_alice_t033",
            "listening",
            answers={"task1": ["A"] * 9},
            answer_key={"task1": ["A"] * 9},
        )
        result = get_result(sit["id"], "acct_alice_t033")
        self.assertFalse(result["completed"])
        self.assertFalse(result["overall"]["pass"])
        # Submitted skill has a real score.
        self.assertEqual(result["per_skill"]["listening"]["score"], 9)
        # Missing skills are placeholders, not absent keys.
        for skill in ("reading", "writing", "speaking"):
            self.assertIn(skill, result["per_skill"])
            self.assertIsNone(result["per_skill"][skill]["score"])
        # Weak-skill suggestions only include sections that actually
        # failed (not the missing ones — those have no row yet).
        self.assertEqual(result["weak_skill_suggestions"], [])

    def test_full_submission_passing_run(self) -> None:
        sit = start_mock_exam("acct_alice_t033", mock_exam_id="mock_pass")
        for skill in ("listening", "reading", "writing", "speaking"):
            submit_section(
                sit["id"],
                "acct_alice_t033",
                skill,
                # 10 correct out of 10 → 10 points → passes 9/15.
                answers={"task1": ["A"] * 10},
                answer_key={"task1": ["A"] * 10},
            )
        result = get_result(sit["id"], "acct_alice_t033")
        self.assertTrue(result["completed"])
        self.assertTrue(result["overall"]["pass"])
        self.assertEqual(result["overall"]["total_score"], 40)
        self.assertEqual(result["overall"]["min_per_skill"], 9)
        self.assertEqual(result["weak_skill_suggestions"], [])
        # Mock exam itself is marked completed.
        self.assertEqual(result["mock_exam"]["status"], "completed")
        self.assertIsNotNone(result["mock_exam"]["completed_at"])

    def test_full_submission_with_weak_skills_lists_them(self) -> None:
        sit = start_mock_exam("acct_alice_t033", mock_exam_id="mock_mixed")
        # Listening + reading pass; writing + speaking fail.
        pass_inputs = {"task1": ["A"] * 9}
        pass_key = {"task1": ["A"] * 9}
        fail_inputs = {"task1": ["A"] * 4 + ["wrong"] * 5}
        for skill in ("listening", "reading"):
            submit_section(
                sit["id"],
                "acct_alice_t033",
                skill,
                answers=pass_inputs,
                answer_key=pass_key,
            )
        for skill in ("writing", "speaking"):
            submit_section(
                sit["id"],
                "acct_alice_t033",
                skill,
                answers=fail_inputs,
                answer_key=pass_key,
            )
        result = get_result(sit["id"], "acct_alice_t033")
        self.assertTrue(result["completed"])
        self.assertFalse(result["overall"]["pass"])
        self.assertEqual(
            sorted(result["weak_skill_suggestions"]),
            ["speaking", "writing"],
        )

    # ------------------------------------------------------------------
    # 5) History
    # ------------------------------------------------------------------

    def test_history_returns_sittings_newest_first(self) -> None:
        first = start_mock_exam(
            "acct_alice_t033",
            mock_exam_id="mock_h1",
            started_at="2026-05-20T10:00:00Z",
        )
        second = start_mock_exam(
            "acct_alice_t033",
            mock_exam_id="mock_h2",
            started_at="2026-05-21T10:00:00Z",
        )
        # Complete the second one fully so its per_skill map has data.
        for skill in ("listening", "reading", "writing", "speaking"):
            submit_section(
                second["id"],
                "acct_alice_t033",
                skill,
                answers={"task1": ["A"] * 10},
                answer_key={"task1": ["A"] * 10},
            )
        entries = list_history("acct_alice_t033")
        self.assertEqual(len(entries), 2)
        # Newest first.
        self.assertEqual(entries[0]["id"], "mock_h2")
        self.assertEqual(entries[1]["id"], "mock_h1")
        self.assertTrue(entries[0]["pass"])
        self.assertTrue(entries[0]["completed"])
        self.assertFalse(entries[1]["completed"])
        self.assertEqual(entries[0]["total_score"], 40)
        # Sanity check the per-skill nesting.
        self.assertEqual(
            entries[0]["per_skill"]["listening"]["score"], 10
        )
        # Silence reference about the first sit being non-empty.
        self.assertEqual(first["id"], "mock_h1")

    def test_history_respects_account_isolation(self) -> None:
        start_mock_exam("acct_alice_t033", mock_exam_id="mock_alice")
        start_mock_exam("acct_bob_t033", mock_exam_id="mock_bob")
        alice_entries = list_history("acct_alice_t033")
        bob_entries = list_history("acct_bob_t033")
        self.assertEqual([e["id"] for e in alice_entries], ["mock_alice"])
        self.assertEqual([e["id"] for e in bob_entries], ["mock_bob"])

    # ------------------------------------------------------------------
    # 6) Multi-user isolation
    # ------------------------------------------------------------------

    def test_user_b_cannot_read_user_a_mock_exam(self) -> None:
        sit = start_mock_exam("acct_alice_t033", mock_exam_id="mock_iso")
        with self.assertRaises(MockExamNotFound):
            get_result(sit["id"], "acct_bob_t033")
        with self.assertRaises(MockExamNotFound):
            submit_section(
                sit["id"],
                "acct_bob_t033",
                "listening",
                answers={},
                answer_key={},
            )

    def test_history_pagination_caps_limit(self) -> None:
        for i in range(5):
            start_mock_exam(
                "acct_alice_t033",
                mock_exam_id=f"mock_p_{i}",
                started_at=f"2026-05-20T10:0{i}:00Z",
            )
        entries = list_history("acct_alice_t033", limit=3)
        self.assertEqual(len(entries), 3)
        # Test that limit <= 0 falls back to the default (>3 still returns all 5).
        all_entries = list_history("acct_alice_t033", limit=-1)
        self.assertEqual(len(all_entries), 5)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
