from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import server


def session_for(account_id: str = "acct_test") -> dict[str, object]:
    return {
        "account": {
            "id": account_id,
            "email": "learner@example.test",
            "status": "active",
            "created_at": "2026-05-05T00:00:00Z",
            "deleted_at": None,
        }
    }


class AttemptLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "auth.sqlite3"
        self.auth_db_patch = patch.object(server, "AUTH_DB_PATH", self.db_path)
        self.auth_db_patch.start()
        server.SCORING_RATE_LIMITS.clear()
        server.SCORING_RATE_LIMIT_MAX_REQUESTS = 5
        server.SCORING_RATE_LIMIT_WINDOW_SECONDS = 60
        server.init_auth_store()
        with server.db_connection() as conn:
            conn.execute(
                """
                INSERT INTO accounts (id, email, password_salt, password_hash, status, created_at, deleted_at)
                VALUES ('acct_test', 'learner@example.test', 'salt', 'hash', 'active', '2026-05-05T00:00:00Z', NULL)
                """
            )
            conn.execute(
                """
                INSERT INTO exams (id, title, content_version, status, manifest_payload, answer_key_payload, created_at, updated_at)
                VALUES ('exam_a', 'Exam A', 7, 'published', '{}', ?, '2026-05-05T00:00:00Z', '2026-05-05T00:00:00Z')
                """,
                ('{"listening":{"task1":["A","B"]}}',),
            )

    def tearDown(self) -> None:
        self.auth_db_patch.stop()
        self.tmpdir.cleanup()

    def test_start_save_submit_and_history_keep_exam_snapshot(self) -> None:
        started = server.start_attempt(
            {
                "attempt_id": "attempt_1",
                "exam_id": "exam_a",
                "exam_title": "Client supplied title should be ignored",
                "content_version": 7,
                "answer_key": {"listening": {"task1": ["client-key"]}},
            },
            session_for(),
        )["attempt"]

        self.assertEqual(started["status"], "started")
        self.assertEqual(started["content_version"], 7)

        saved = server.save_attempt_answer(
            "attempt_1",
            {"skill": "listening", "task_key": "task1", "item_index": 1, "answer": "A"},
            session_for(),
        )["attempt"]
        self.assertEqual(saved["status"], "in_progress")

        server.save_attempt_answer(
            "attempt_1",
            {"skill": "listening", "task_key": "task1", "item_index": 2, "answer": "wrong"},
            session_for(),
        )

        submitted = server.submit_attempt("attempt_1", session_for())
        self.assertEqual(submitted["attempt"]["status"], "scored")
        self.assertEqual(submitted["score"]["objective_correct"], 1)
        self.assertEqual(submitted["score"]["objective_possible"], 2)
        self.assertEqual(submitted["attempt"]["exam_snapshot"]["answer_key"]["listening"]["task1"], ["A", "B"])
        redacted = server.redact_attempt_for_learner(submitted["attempt"])
        self.assertNotIn("answer_key", redacted["exam_snapshot"])
        self.assertNotIn("expected", redacted["score_payload"]["scoring"]["items"][0])

        with server.db_connection() as conn:
            rows = conn.execute("SELECT * FROM attempts WHERE account_id = ? ORDER BY submitted_at DESC", ("acct_test",)).fetchall()
        self.assertEqual([row["id"] for row in rows], ["attempt_1"])
        self.assertEqual(server.serialize_attempt(rows[0])["score_total"], 1)

    def test_submitted_attempt_rejects_answer_changes_and_resubmission(self) -> None:
        server.start_attempt(
            {"attempt_id": "attempt_2", "exam_id": "exam_a", "answer_key": {"reading": {"task1": ["yes"]}}},
            session_for(),
        )
        server.submit_attempt("attempt_2", session_for())

        with self.assertRaises(server.ApiError) as save_ctx:
            server.save_attempt_answer(
                "attempt_2",
                {"skill": "reading", "task_key": "task1", "item_index": 1, "answer": "yes"},
                session_for(),
            )
        self.assertEqual(save_ctx.exception.status_code, 409)
        self.assertEqual(save_ctx.exception.code, "invalid_attempt_transition")

        resubmitted = server.submit_attempt("attempt_2", session_for())
        self.assertTrue(resubmitted["idempotent"])
        self.assertEqual(resubmitted["attempt"]["status"], "scored")

    def test_scoring_rate_limit_blocks_excess_submissions(self) -> None:
        server.SCORING_RATE_LIMIT_MAX_REQUESTS = 1
        server.check_scoring_rate_limit("acct_test")

        with self.assertRaises(server.ApiError) as ctx:
            server.check_scoring_rate_limit("acct_test")

        self.assertEqual(ctx.exception.status_code, 429)
        self.assertEqual(ctx.exception.code, "rate_limit_exceeded")


if __name__ == "__main__":
    unittest.main()
