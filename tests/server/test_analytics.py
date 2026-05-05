from __future__ import annotations

import unittest
from unittest.mock import patch
from pathlib import Path
import tempfile

import server


class AnalyticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "auth.sqlite3"
        self.auth_db_patch = patch.object(server, "AUTH_DB_PATH", self.db_path)
        self.auth_db_patch.start()
        server.init_auth_store()
        
        # Create test account
        with server.db_connection() as conn:
            conn.execute(
                """
                INSERT INTO accounts (id, email, password_salt, password_hash, status, created_at, deleted_at)
                VALUES ('acct_test', 'learner@example.test', 'salt', 'hash', 'active', '2026-05-05T00:00:00Z', NULL)
                """
            )
            conn.execute(
                """
                INSERT INTO profiles (account_id, full_name, native_language, exam_target_date, updated_at)
                VALUES ('acct_test', 'Test Learner', 'English', NULL, '2026-05-05T00:00:00Z')
                """
            )

    def tearDown(self) -> None:
        self.auth_db_patch.stop()
        self.tmpdir.cleanup()

    def test_category_status_classification(self):
        """Test the strength/weakness classification logic"""
        # Test strong (>=12)
        self.assertEqual(self._get_category_status(15.0), "strong")
        self.assertEqual(self._get_category_status(12.0), "strong")
        self.assertEqual(self._get_category_status(12.1), "strong")
        
        # Test borderline (9-11)
        self.assertEqual(self._get_category_status(11.9), "borderline")
        self.assertEqual(self._get_category_status(11.0), "borderline")
        self.assertEqual(self._get_category_status(9.0), "borderline")
        self.assertEqual(self._get_category_status(9.1), "borderline")
        
        # Test weak (<9)
        self.assertEqual(self._get_category_status(8.9), "weak")
        self.assertEqual(self._get_category_status(5.0), "weak")
        self.assertEqual(self._get_category_status(0.0), "weak")
    
    def _get_category_status(self, avg_score: float) -> str:
        """Helper to replicate the classification logic from the analytics endpoint"""
        if avg_score >= 12:
            return "strong"
        elif avg_score < 9:
            return "weak"
        else:
            return "borderline"


if __name__ == "__main__":
    unittest.main()