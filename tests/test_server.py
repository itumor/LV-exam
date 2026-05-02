from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server


def build_submission() -> dict[str, object]:
    return {
        "submission_id": "sub-001",
        "exam_id": "a2_mock_exam_01",
        "exam_title": "A2 Mock Exam 01",
        "level": "A2",
        "language": "lv",
        "plan": "free",
        "candidate": {"code": "C-1001"},
        "pass_rule": {"total_max": 60, "skill_max": 15, "minimum_per_skill": 9},
        "progress": {"answered": 1, "total": 1},
        "answers": {
            "writing": {"task1": ["Sveiki", "Es esmu Anna"]},
            "speaking": {"task1": ["Man patīk mācīties"]},
        },
        "answer_key": {},
        "scoring": {
            "objective_correct": 0,
            "objective_possible": 0,
            "manual_review_possible": 30,
            "by_skill": {},
            "items": [],
        },
        "validation_queue": [],
    }


def build_exam_markdown() -> str:
    return """
# Demo exam

## Intro
Short context.
""".strip()


def build_provider_payload() -> dict[str, object]:
    return {
        "provider": "groq",
        "model": "test-model",
        "evaluation": {
            "status": "evaluated",
            "scores": {
                "listening": {"points": 8, "max_points": 15, "passed": False, "reason": "Needs more detail"},
                "reading": {"points": 9, "max_points": 15, "passed": True, "reason": "Good"},
                "writing": {"points": 10, "max_points": 15, "passed": True, "reason": "Clear"},
                "speaking": {"points": 11, "max_points": 15, "passed": True, "reason": "Clear"},
                "total": 999,
                "passed": False,
            },
            "corrections": [
                {
                    "skill": "writing",
                    "task": "task1",
                    "item": "2",
                    "candidate_answer": "Sveiki",
                    "suggested_answer": "Sveiki!",
                    "comment": "Add punctuation.",
                }
            ],
            "feedback": {
                "summary": "Practice feedback",
                "strengths": ["Clear answers"],
                "improvements": ["Add punctuation"],
                "next_practice": ["Write 3 short sentences"],
            },
        },
        "usage": {"input_tokens": 10, "output_tokens": 20},
    }


class ServerScoringTests(unittest.TestCase):
    def setUp(self) -> None:
        server.EVALUATION_CACHE.clear()
        server.QUOTA_USAGE.clear()
        server.AUDIT_LOG.clear()

    def test_successful_scoring_normalizes_payload_and_records_telemetry(self) -> None:
        with (
            mock.patch.object(server, "provider_config", return_value={"provider": "groq", "model": "test-model"}),
            mock.patch.object(server, "provider_call_once", return_value=build_provider_payload()) as provider_call,
        ):
            result = server.evaluate_submission(build_submission(), build_exam_markdown())

        self.assertEqual(result["status"], "evaluated")
        self.assertEqual(result["provider"], "groq")
        self.assertEqual(result["model"], "test-model")
        self.assertEqual(result["evaluation"]["scores"]["total"], 38)
        self.assertFalse(result["evaluation"]["scores"]["passed"])
        self.assertEqual(result["evaluation"]["scores"]["listening"]["passed"], False)
        self.assertEqual(result["telemetry"]["identity"]["user_key"], "C-1001")
        self.assertEqual(result["telemetry"]["plan"], "free")
        self.assertEqual(result["telemetry"]["quota"]["usage"]["requests"], 1)
        self.assertEqual(len(server.AUDIT_LOG), 1)
        self.assertEqual(provider_call.call_count, 1)

    def test_invalid_model_response_is_retried_then_rejected(self) -> None:
        with (
            mock.patch.object(server, "provider_config", return_value={"provider": "groq", "model": "test-model"}),
            mock.patch.object(server, "provider_call_once", return_value={"provider": "groq", "model": "test-model", "evaluation": {"status": "bad"}}) as provider_call,
            mock.patch.object(server.time, "sleep", return_value=None),
        ):
            with self.assertRaises(server.EvaluationError) as ctx:
                server.evaluate_submission(build_submission(), build_exam_markdown())

        self.assertEqual(ctx.exception.status_code, 502)
        self.assertEqual(ctx.exception.retry_state, "exhausted")
        self.assertEqual(provider_call.call_count, 3)

    def test_provider_timeout_is_retried_then_rejected(self) -> None:
        with (
            mock.patch.object(server, "provider_config", return_value={"provider": "groq", "model": "test-model"}),
            mock.patch.object(server, "provider_call_once", side_effect=TimeoutError("timed out")) as provider_call,
            mock.patch.object(server.time, "sleep", return_value=None),
        ):
            with self.assertRaises(server.EvaluationError) as ctx:
                server.evaluate_submission(build_submission(), build_exam_markdown())

        self.assertEqual(ctx.exception.status_code, 504)
        self.assertEqual(ctx.exception.retry_state, "exhausted")
        self.assertEqual(provider_call.call_count, 3)

    def test_quota_exceeded_blocks_before_provider_call(self) -> None:
        with (
            mock.patch.object(server, "provider_config", return_value={"provider": "groq", "model": "test-model"}),
            mock.patch.object(server, "plan_request_limit", return_value=0),
            mock.patch.object(server, "provider_call_once") as provider_call,
        ):
            with self.assertRaises(server.QuotaExceededError):
                server.evaluate_submission(build_submission(), build_exam_markdown())

        provider_call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
