from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import server


def session(role: str, account_id: str = "acct_actor") -> dict[str, object]:
    return {
        "account": {
            "id": account_id,
            "email": f"{role}@example.test",
            "status": "active",
            "role": role,
            "created_at": "2026-05-05T00:00:00Z",
            "deleted_at": None,
        }
    }


class AdminConsoleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "auth.sqlite3"
        self.auth_db_patch = patch.object(server, "AUTH_DB_PATH", self.db_path)
        self.auth_db_patch.start()
        server.init_auth_store()
        with server.db_connection() as conn:
            conn.execute(
                """
                INSERT INTO accounts (id, email, password_salt, password_hash, status, created_at, deleted_at, role)
                VALUES ('acct_actor', 'admin@example.test', 'salt', 'hash', 'active', '2026-05-05T00:00:00Z', NULL, 'admin')
                """
            )
            conn.execute(
                """
                INSERT INTO accounts (id, email, password_salt, password_hash, status, created_at, deleted_at, role)
                VALUES ('acct_user', 'learner@example.test', 'salt', 'hash', 'active', '2026-05-05T00:00:00Z', NULL, 'user')
                """
            )

    def tearDown(self) -> None:
        self.auth_db_patch.stop()
        self.tmpdir.cleanup()

    def test_catalog_hides_archived_exams_from_learners(self) -> None:
        server.update_admin_exam_status("01", {"status": "archived"})

        learner_catalog = server.list_exam_catalog()
        admin_catalog = server.list_exam_catalog(session("admin"))

        self.assertNotIn("01", {exam["id"] for exam in learner_catalog["exams"]})
        self.assertIn("01", {exam["id"] for exam in admin_catalog["exams"]})

    def test_admin_cannot_promote_accounts_but_superadmin_can(self) -> None:
        with self.assertRaises(server.ApiError) as admin_ctx:
            server.update_admin_account("acct_user", {"role": "admin", "status": "active"}, session("admin"))
        self.assertEqual(admin_ctx.exception.status_code, 403)

        updated = server.update_admin_account("acct_user", {"role": "admin", "status": "active"}, session("superadmin"))
        self.assertEqual(updated["account"]["role"], "admin")

    def test_admin_can_create_publish_and_delete_exam_catalog_entry(self) -> None:
        created = server.save_admin_exam(
            {
                "id": "custom-a2",
                "title": "Custom A2",
                "status": "draft",
                "markdownPath": "/codex/A2_Mock_Exam_01.md",
                "sourcePath": "codex/A2_Mock_Exam_01.md",
                "answer_key": {"reading": {"task1": ["a"]}},
            },
            session("admin"),
        )["exam"]
        self.assertEqual(created["status"], "draft")

        published = server.update_admin_exam_status("custom-a2", {"status": "published"})["exam"]
        self.assertEqual(published["status"], "published")

        deleted = server.delete_admin_exam("custom-a2")
        self.assertTrue(deleted["deleted"])
        self.assertNotIn("custom-a2", {exam["id"] for exam in server.list_exam_catalog(session("admin"))["exams"]})


if __name__ == "__main__":
    unittest.main()
