from __future__ import annotations

import io
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

import server


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


class DummyResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "DummyResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def read(self) -> bytes:
        return self._payload


class ServerContractTests(unittest.TestCase):
    def setUp(self) -> None:
        with server.EVALUATION_CACHE_LOCK:
            server.EVALUATION_CACHE.clear()
        with server.QUOTA_USAGE_LOCK:
            server.QUOTA_USAGE.clear()
        with server.AUDIT_LOG_LOCK:
            server.AUDIT_LOG.clear()

    def test_extract_json_object_accepts_fenced_or_plain_json(self) -> None:
        plain = server.extract_json_object('{"answer": "a"}')
        fenced = server.extract_json_object("```json\n{\"answer\": \"b\"}\n```")

        self.assertEqual(plain["answer"], "a")
        self.assertEqual(fenced["answer"], "b")

    def test_compact_exam_context_drops_export_sections(self) -> None:
        markdown = (FIXTURES / "exam-smoke.md").read_text(encoding="utf-8")
        compact = server.compact_exam_context(markdown)

        self.assertIn("### Klausīšanās prasmes pārbaude", compact)
        self.assertNotIn("## JSON Export", compact)
        self.assertNotIn("## TTS Export", compact)

    def test_provider_error_message_covers_quota_and_outage(self) -> None:
        self.assertIn("rate limit", server.provider_error_message(429, "").lower())
        self.assertIn("temporarily unavailable", server.provider_error_message(503, "").lower())

    def test_plan_request_limit_honors_env_override(self) -> None:
        with patch.dict(os.environ, {"AI_SCORING_DAILY_REQUEST_LIMIT_FREE": "7"}):
            self.assertEqual(server.plan_request_limit("free"), 7)

    def test_ai_scoring_credit_requirement_defaults_to_live_stripe_only(self) -> None:
        with patch.dict(os.environ, {"STRIPE_SECRET_KEY": "", "AI_SCORING_REQUIRE_AI_CREDIT": ""}):
            self.assertFalse(server.ai_scoring_requires_credit())
        with patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_live_fixture", "AI_SCORING_REQUIRE_AI_CREDIT": ""}):
            self.assertTrue(server.ai_scoring_requires_credit())
        with patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_live_fixture", "AI_SCORING_REQUIRE_AI_CREDIT": "false"}):
            self.assertFalse(server.ai_scoring_requires_credit())

    def test_call_groq_retries_transient_errors_before_succeeding(self) -> None:
        config = {
            "provider": "groq",
            "api_key": "fixture-key",
            "model": "fixture-model",
            "base_url": "https://example.test",
        }
        submission = {"submission_id": "sub-1", "learner_id": "learner-1"}
        exam_context = "### Klausīšanās prasmes pārbaude"
        attempts = {"count": 0}

        def fake_urlopen(request, timeout):
            attempts["count"] += 1
            if attempts["count"] < 3:
                error = HTTPError(
                    request.full_url,
                    429,
                    "Too Many Requests",
                    {"Retry-After": "0"},
                    io.BytesIO(b"{\"error\":\"quota\"}"),
                )
                error.close()
                raise error
            return DummyResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "status": "evaluated",
                                        "scores": {
                                            "listening": {
                                                "points": 15,
                                                "max_points": 15,
                                                "passed": True,
                                                "reason": "ok",
                                            },
                                            "reading": {
                                                "points": 15,
                                                "max_points": 15,
                                                "passed": True,
                                                "reason": "ok",
                                            },
                                            "writing": {
                                                "points": 15,
                                                "max_points": 15,
                                                "passed": True,
                                                "reason": "ok",
                                            },
                                            "speaking": {
                                                "points": 15,
                                                "max_points": 15,
                                                "passed": True,
                                                "reason": "ok",
                                            },
                                            "total": 60,
                                            "passed": True,
                                        },
                                        "corrections": [],
                                        "feedback": {
                                            "summary": "fixture",
                                            "strengths": [],
                                            "improvements": [],
                                            "next_practice": [],
                                        },
                                    }
                                )
                            }
                        }
                    ],
                    "usage": {"total_tokens": 42},
                }
            )

        with patch.object(server.urllib.request, "urlopen", side_effect=fake_urlopen), patch.object(server.time, "sleep") as sleep_mock:
            result = server.call_groq(config, submission, exam_context)

        self.assertEqual(attempts["count"], 3)
        self.assertEqual(result["provider"], "groq")
        self.assertEqual(result["evaluation"]["scores"]["total"], 60)
        self.assertEqual([call.args[0] for call in sleep_mock.call_args_list], [1, 2])

    def test_evaluate_submission_uses_cache_for_identical_requests(self) -> None:
        submission = {"submission_id": "sub-1", "learner_id": "learner-1"}
        exam_markdown = (FIXTURES / "exam-smoke.md").read_text(encoding="utf-8")
        config = {
            "provider": "groq",
            "api_key": "fixture-key",
            "model": "fixture-model",
            "base_url": "https://example.test",
        }

        def fake_provider_config():
            return config

        def fake_call_groq(*_args, **_kwargs):
            return {
                "provider": "groq",
                "model": "fixture-model",
                "evaluation": {
                    "status": "evaluated",
                    "scores": {
                        "listening": {"points": 15, "max_points": 15, "passed": True, "reason": "ok"},
                        "reading": {"points": 15, "max_points": 15, "passed": True, "reason": "ok"},
                        "writing": {"points": 15, "max_points": 15, "passed": True, "reason": "ok"},
                        "speaking": {"points": 15, "max_points": 15, "passed": True, "reason": "ok"},
                        "total": 60,
                        "passed": True,
                    },
                    "corrections": [],
                    "feedback": {
                        "summary": "fixture",
                        "strengths": [],
                        "improvements": [],
                        "next_practice": [],
                    },
                },
            }

        with patch.object(server, "provider_config", side_effect=fake_provider_config), patch.object(server, "call_groq", side_effect=fake_call_groq) as call_groq_mock:
            first = server.evaluate_submission(submission, exam_markdown)
            second = server.evaluate_submission(submission, exam_markdown)

        self.assertEqual(first["evaluation"]["scores"]["total"], 30)
        self.assertEqual(second["evaluation"]["scores"]["total"], 30)
        self.assertEqual(first["telemetry"]["identity"]["user_key"], "learner-1")
        self.assertEqual(call_groq_mock.call_count, 1)


if __name__ == "__main__":
    unittest.main()
