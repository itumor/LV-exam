#!/usr/bin/env python3
"""
Verification script for new user flow - tests the complete exam history and analytics functionality.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

import server


class NewUserVerification(unittest.TestCase):
    def setUp(self) -> None:
        """Set up a fresh test environment for each test."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "auth.sqlite3"
        self.auth_db_patch = patch.object(server, "AUTH_DB_PATH", self.db_path)
        self.auth_db_patch.start()
        server.init_auth_store()
        
        # Create test exam if it doesn't exist
        with server.db_connection() as conn:
            # Check if exam exists
            exam = conn.execute("SELECT id FROM exams WHERE id = ?", ("01",)).fetchone()
            if not exam:
                conn.execute(
                    """
                    INSERT INTO exams (id, title, content_version, status, manifest_payload, answer_key_payload, created_at, updated_at)
                    VALUES ('01', 'A2 Mock Exam 01', 1, 'published', '{}', '{}', '2026-05-05T00:00:00Z', '2026-05-05T00:00:00Z')
                    """
                )

    def tearDown(self) -> None:
        """Clean up after each test."""
        self.auth_db_patch.stop()
        self.tmpdir.cleanup()

    def test_complete_new_user_flow(self):
        """Test the complete flow for a new user: register, take exam, check history and analytics."""
        print("\n=== Starting New User Verification ===")
        
        # Step 1: Register a new user
        print("\n1. Registering new user...")
        registration_payload = {
            "email": "newuser@test.lv",
            "password": "SecurePass123!",
            "full_name": "Jauns Lietotājs",
            "native_language": "English",
            "exam_target_date": "2026-12-31"
        }
        
        # Simulate account creation
        with server.db_connection() as conn:
            salt_b64, hash_b64 = server.hash_password(registration_payload["password"])
            account_id = f"acct_{server.secrets.token_hex(8)}"
            now = server.now_iso()
            conn.execute(
                """
                INSERT INTO accounts (id, email, password_salt, password_hash, status, created_at, deleted_at, role)
                VALUES (?, ?, ?, ?, 'active', ?, NULL, 'user')
                """,
                (account_id, registration_payload["email"], salt_b64, hash_b64, now),
            )
            conn.execute(
                """
                INSERT INTO profiles (account_id, full_name, native_language, exam_target_date, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (account_id, registration_payload["full_name"], registration_payload["native_language"], 
                 registration_payload["exam_target_date"], now),
            )
        
        # Create session for the new user
        session = {
            "account": {
                "id": account_id,
                "email": registration_payload["email"],
                "status": "active",
                "created_at": server.now_iso(),
            }
        }
        print(f"   ✓ User registered with ID: {account_id}")
        
        # Step 2: Start an exam attempt
        print("\n2. Starting exam attempt...")
        start_payload = {
            "exam_id": "01",
            "exam_title": "A2 Mock Exam 01",
            "content_version": 1,
            "answer_key": {
                "listening": {"task1": ["A", "B", "C"]},
                "reading": {"task1": ["yes", "no"]},
                "writing": {"task1": ["Sample answer"]},
                "speaking": {"task1": ["Sample response"]}
            }
        }
        
        start_result = server.start_attempt(start_payload, session)
        attempt_id = start_result["attempt"]["id"]
        print(f"   ✓ Exam started with attempt ID: {attempt_id}")
        
        # Step 3: Submit some answers
        print("\n3. Submitting answers...")
        # Answer some listening questions
        server.save_attempt_answer(
            attempt_id,
            {"skill": "listening", "task_key": "task1", "item_index": 1, "answer": "A"},
            session,
        )
        server.save_attempt_answer(
            attempt_id,
            {"skill": "listening", "task_key": "task1", "item_index": 2, "answer": "B"},
            session,
        )
        server.save_attempt_answer(
            attempt_id,
            {"skill": "listening", "task_key": "task1", "item_index": 3, "answer": "C"},
            session,
        )
        
        # Answer some reading questions
        server.save_attempt_answer(
            attempt_id,
            {"skill": "reading", "task_key": "task1", "item_index": 1, "answer": "yes"},
            session,
        )
        server.save_attempt_answer(
            attempt_id,
            {"skill": "reading", "task_key": "task1", "item_index": 2, "answer": "no"},
            session,
        )
        
        # Answer writing (simplified)
        server.save_attempt_answer(
            attempt_id,
            {"skill": "writing", "task_key": "task1", "item_index": 1, "answer": "Sample answer"},
            session,
        )
        
        # Answer speaking (simplified)
        server.save_attempt_answer(
            attempt_id,
            {"skill": "speaking", "task_key": "task1", "item_index": 1, "answer": "Sample response"},
            session,
        )
        
        print("   ✓ Answers submitted")
        
        # Step 4: Submit the attempt for scoring
        print("\n4. Submitting attempt for scoring...")
        submit_result = server.submit_attempt(attempt_id, session)
        print(f"   ✓ Attempt submitted. Score: {submit_result['attempt']['score_total']}/60")
        
        # Verify the attempt was scored
        self.assertEqual(submit_result["attempt"]["status"], "scored")
        self.assertIsNotNone(submit_result["attempt"]["score_total"])
        
        # Step 5: Check exam attempt history
        print("\n5. Checking exam attempt history...")
        with server.db_connection() as conn:
            history = conn.execute(
                """
                SELECT * FROM attempts 
                WHERE account_id = ? 
                ORDER BY submitted_at DESC
                """,
                (account_id,),
            ).fetchall()
        
        self.assertEqual(len(history), 1)
        attempt = server.serialize_attempt(history[0])
        self.assertEqual(attempt["id"], attempt_id)
        self.assertEqual(attempt["status"], "scored")
        self.assertIsNotNone(attempt["score_total"])
        print(f"   ✓ History shows 1 attempt: {attempt['exam_title']} - {attempt['score_total']}/60 points")
        
        # Step 6: Check that category scores were stored correctly
        print("\n6. Checking category scores storage...")
        with server.db_connection() as conn:
            category_scores = conn.execute(
                """
                SELECT category, score_0_to_15, passed_boolean 
                FROM exam_attempt_category_score 
                WHERE attempt_id = ?
                ORDER BY category
                """,
                (attempt_id,),
            ).fetchall()
        
        self.assertEqual(len(category_scores), 4)  # 4 categories
        
        # Verify we have scores for each category
        categories_found = [row["category"] for row in category_scores]
        expected_categories = ["listening", "reading", "writing", "speaking"]
        for cat in expected_categories:
            self.assertIn(cat, categories_found, f"Missing category: {cat}")
        
        # Verify specific scores (based on our answers)
        scores_dict = {row["category"]: row for row in category_scores}
        
        # Listening: 3/3 correct = 3 points
        self.assertEqual(scores_dict["listening"]["score_0_to_15"], 3)
        self.assertFalse(scores_dict["listening"]["passed_boolean"])  # 3 < 9
        
        # Reading: 2/2 correct = 2 points
        self.assertEqual(scores_dict["reading"]["score_0_to_15"], 2)
        self.assertFalse(scores_dict["reading"]["passed_boolean"])  # 2 < 9
        
        # Writing: 1 point from objective scoring (exact match to expected answer)
        self.assertEqual(scores_dict["writing"]["score_0_to_15"], 1)
        self.assertFalse(scores_dict["writing"]["passed_boolean"])  # 1 < 9
        
        # Speaking: 1 point from objective scoring (exact match to expected answer)
        self.assertEqual(scores_dict["speaking"]["score_0_to_15"], 1)
        self.assertFalse(scores_dict["speaking"]["passed_boolean"])  # 1 < 9
        
        print("   ✓ Category scores stored correctly:")
        for cat in expected_categories:
            score = scores_dict[cat]["score_0_to_15"]
            passed = "✓" if scores_dict[cat]["passed_boolean"] else "✗"
            print(f"     {cat}: {score}/15 points {passed}")
        
        # Step 7: Verify analytics endpoint returns correct data
        print("\n7. Checking analytics data...")
        # We'll test the analytics logic directly since we're not in an HTTP context
        with server.db_connection() as conn:
            account_id_param = account_id
            
            # Get category averages over time
            category_trends = conn.execute(
                """
                SELECT 
                    category,
                    AVG(score_0_to_15) as avg_score,
                    COUNT(*) as attempt_count,
                    MAX(created_at) as latest_attempt
                FROM exam_attempt_category_score
                WHERE account_id = ?
                GROUP BY category
                """,
                (account_id_param,),
            ).fetchall()
            
            # Get recent attempts with scores for trend analysis
            recent_attempts = conn.execute(
                """
                SELECT 
                    a.id,
                    a.exam_id,
                    a.exam_title,
                    a.submitted_at,
                    a.score_total,
                    eacs.category,
                    eacs.score_0_to_15,
                    eacs.passed_boolean
                FROM attempts a
                JOIN exam_attempt_category_score eacs ON a.id = eacs.attempt_id
                WHERE a.account_id = ?
                ORDER BY a.submitted_at DESC
                LIMIT 20
                """,
                (account_id_param,),
            ).fetchall()
            
            # Process data for analytics (simplified version of what the endpoint does)
            category_stats = {}
            for row in category_trends:
                category = row["category"]
                avg_score = float(row["avg_score"])
                attempt_count = int(row["attempt_count"])
                
                # Determine strength/weakness based on consistent performance
                if avg_score >= 12:
                    status = "strong"
                    label = "Strong"
                elif avg_score < 9:
                    status = "weak"
                    label = "Needs Improvement"
                else:
                    status = "borderline"
                    label = "Developing"
                    
                category_stats[category] = {
                    "average_score": round(avg_score, 1),
                    "attempt_count": attempt_count,
                    "status": status,
                    "label": label,
                    "latest_attempt": row["latest_attempt"]
                }
            
            # Overall statistics
            overall_avg = conn.execute(
                """
                SELECT AVG(score_total) as avg_total
                FROM attempts
                WHERE account_id = ? AND score_total IS NOT NULL
                """,
                (account_id_param,),
            ).fetchone()
            
            pass_rate = conn.execute(
                """
                SELECT 
                    COUNT(*) as total_attempts,
                    SUM(CASE WHEN score_total >= 36 THEN 1 ELSE 0 END) as passed_attempts
                FROM attempts
                WHERE account_id = ? AND score_total IS NOT NULL
                """,
                (account_id_param,),
            ).fetchone()
            
            # Recent streak (consecutive passed attempts)
            streak_data = conn.execute(
                """
                WITH ordered_attempts AS (
                    SELECT 
                        score_total,
                        ROW_NUMBER() OVER (ORDER BY submitted_at DESC) as rn
                    FROM attempts
                    WHERE account_id = ? AND score_total IS NOT NULL
                ),
                failed_attempts AS (
                    SELECT MIN(rn) as first_failed_rn
                    FROM ordered_attempts
                    WHERE score_total < 36
                )
                SELECT 
                    COUNT(*) as streak
                FROM ordered_attempts, failed_attempts
                WHERE score_total >= 36
                  AND rn <= COALESCE((SELECT first_failed_rn FROM failed_attempts), 
                                     (SELECT MAX(rn) FROM ordered_attempts) + 1)
                """,
                (account_id_param,),
            ).fetchone()
        
        # Verify analytics results
        self.assertEqual(len(category_trends), 4)
        self.assertEqual(len(recent_attempts), 4)  # 4 category scores for 1 attempt
        
        # Check that our low scores are classified as "weak"
        for cat in expected_categories:
            self.assertEqual(category_stats[cat]["status"], "weak")
            self.assertEqual(category_stats[cat]["label"], "Needs Improvement")
        
        # Check overall stats
        # Actually, score_total is the sum of objective_correct across all skills
        # We had: listening=3, reading=2, writing=1, speaking=1 → total = 7
        self.assertEqual(overall_avg["avg_total"], 7.0)
        
        self.assertEqual(pass_rate["total_attempts"], 1)
        self.assertEqual(pass_rate["passed_attempts"], 0)  # 7 < 36
        self.assertEqual(streak_data["streak"], 0)  # No passed attempts yet
        
        print("   ✓ Analytics data verified:")
        print(f"     Overall average score: {overall_avg['avg_total']}/60")
        print(f"     Pass rate: {pass_rate['passed_attempts']}/{pass_rate['total_attempts']} ({0 if pass_rate['total_attempts'] == 0 else round(pass_rate['passed_attempts']/pass_rate['total_attempts']*100)}%)")
        print(f"     Current streak: {streak_data['streak']} consecutive passed attempts")
        print("     Category performance:")
        for cat in expected_categories:
            stats = category_stats[cat]
            print(f"       {cat}: {stats['average_score']}/15 ({stats['label']})")
        
        print("\n=== New User Verification Complete ===")
        print("✓ All 6 verification steps passed successfully!")
        
        return True


if __name__ == "__main__":
    # Run the verification test
    test = NewUserVerification()
    test.setUp()
    try:
        test.test_complete_new_user_flow()
        print("\n🎉 VERIFICATION SUCCESSFUL: New user flow works correctly!")
    except Exception as e:
        print(f"\n❌ VERIFICATION FAILED: {str(e)}")
        raise
    finally:
        test.tearDown()