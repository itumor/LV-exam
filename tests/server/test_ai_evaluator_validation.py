"""T-026 AI evaluator validation + retry behaviour tests.

Covers the schema-level pydantic validation introduced in
``server_app.models.ai`` and the retry policy added in
``server_app.services.evaluator``:

* Request payload rejection (bad skill, wrong types, missing required keys).
* Response payload rejection (wrong status, out-of-range points, missing
  required block).
* :func:`call_with_retry` retries retriable exceptions up to ``max_attempts``
  and surfaces the original error after exhaustion.
* :func:`call_with_retry` does NOT retry non-retriable exceptions.
* Per-provider backoff base differs between Groq and OpenAI/Codex.
* :func:`build_provider_unavailable_response` shape matches the schema.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from pydantic import ValidationError

from server_app.models.ai import (
    AIEvaluationResponse,
    AIProviderUnavailableDetails,
    AIScoreRequest,
    next_utc_midnight_iso,
)
from server_app.services.evaluator import (
    DEFAULT_MAX_ATTEMPTS,
    EvaluationError,
    ProviderResponseError,
    build_provider_unavailable_response,
    call_with_retry,
    compute_backoff_delay,
    parse_ai_score_request,
    provider_backoff_base,
    validate_ai_response_with_pydantic,
)


# ---------------------------------------------------------------------------
# Request schema rejection
# ---------------------------------------------------------------------------


class AIScoreRequestSchemaTests(unittest.TestCase):
    def _valid_payload(self) -> dict:
        return {
            "submission_id": "sub-1",
            "exam_id": "01",
            "plan": "Free",  # case-insensitive; normalised to "free"
            "learner_id": "learner-7",
            "answers": {
                "writing": {"task1": ["Es esmu students."]},
                "speaking": {"task1": ["Es runaju latviski."]},
            },
        }

    def test_accepts_minimal_valid_payload(self) -> None:
        parsed = parse_ai_score_request(self._valid_payload())
        self.assertIsInstance(parsed, AIScoreRequest)
        self.assertEqual(parsed.plan, "free")  # normalisation
        self.assertEqual(parsed.identity()["user_key"], "learner-7")

    def test_rejects_missing_submission_id(self) -> None:
        payload = self._valid_payload()
        del payload["submission_id"]
        with self.assertRaises(EvaluationError) as ctx:
            parse_ai_score_request(payload)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.retry_state, "invalid_request")
        self.assertIn("validation_errors", ctx.exception.telemetry)

    def test_rejects_unknown_skill_name(self) -> None:
        payload = self._valid_payload()
        payload["answers"]["typing"] = {"task1": ["x"]}
        with self.assertRaises(EvaluationError):
            parse_ai_score_request(payload)

    def test_rejects_non_string_answer_entries(self) -> None:
        payload = self._valid_payload()
        payload["answers"]["writing"]["task1"] = [{"not": "a string"}]
        with self.assertRaises(EvaluationError):
            parse_ai_score_request(payload)

    def test_rejects_non_list_task_answers(self) -> None:
        payload = self._valid_payload()
        payload["answers"]["writing"]["task1"] = "not a list"
        with self.assertRaises(EvaluationError):
            parse_ai_score_request(payload)

    def test_identity_falls_back_through_keys(self) -> None:
        # No learner_id / learner_email — should fall back to candidate.code
        # then to submission_id, then to "anonymous".
        parsed = parse_ai_score_request(
            {
                "submission_id": "sub-x",
                "exam_id": "01",
                "candidate": {"code": "cand-9"},
                "answers": {},
            }
        )
        self.assertEqual(parsed.identity()["user_key"], "cand-9")

        parsed = parse_ai_score_request(
            {"submission_id": "sub-y", "exam_id": "01", "answers": {}}
        )
        self.assertEqual(parsed.identity()["user_key"], "sub-y")


# ---------------------------------------------------------------------------
# Response schema rejection
# ---------------------------------------------------------------------------


class AIEvaluationResponseSchemaTests(unittest.TestCase):
    def _valid_response(self) -> dict:
        return {
            "status": "evaluated",
            "scores": {
                "writing": {"points": 12, "max_points": 15, "reason": "Good."},
                "speaking": {"points": 10, "max_points": 15, "reason": "OK."},
            },
            "corrections": [
                {
                    "skill": "writing",
                    "task": "task1",
                    "item": 1,
                    "candidate_answer": "Es ir students",
                    "suggested_answer": "Es esmu students",
                    "comment": "verb form",
                }
            ],
            "feedback": {
                "summary": "Solid baseline.",
                "strengths": ["good vocabulary"],
                "improvements": ["verb agreement"],
                "next_practice": ["A2 verb drill"],
            },
        }

    def test_accepts_valid_response(self) -> None:
        parsed = validate_ai_response_with_pydantic(self._valid_response())
        self.assertIsInstance(parsed, AIEvaluationResponse)
        self.assertEqual(parsed.scores.total, 22)
        self.assertTrue(parsed.scores.passed)  # both ≥ 9

    def test_derives_passed_from_per_skill_threshold(self) -> None:
        response = self._valid_response()
        response["scores"]["writing"]["points"] = 6  # below 9
        parsed = validate_ai_response_with_pydantic(response)
        self.assertFalse(parsed.scores.passed)
        assert parsed.scores.writing is not None  # for type-checker
        self.assertFalse(parsed.scores.writing.passed)
        assert parsed.scores.speaking is not None
        self.assertTrue(parsed.scores.speaking.passed)

    def test_rejects_wrong_status(self) -> None:
        response = self._valid_response()
        response["status"] = "pending"
        with self.assertRaises(EvaluationError) as ctx:
            validate_ai_response_with_pydantic(response)
        self.assertEqual(ctx.exception.status_code, 502)
        self.assertEqual(ctx.exception.retry_state, "invalid_response")

    def test_rejects_out_of_range_points(self) -> None:
        response = self._valid_response()
        response["scores"]["writing"]["points"] = 99
        with self.assertRaises(EvaluationError):
            validate_ai_response_with_pydantic(response)

    def test_rejects_missing_scores_block(self) -> None:
        response = self._valid_response()
        del response["scores"]
        with self.assertRaises(EvaluationError):
            validate_ai_response_with_pydantic(response)

    def test_clamps_feedback_bullets_to_400_chars(self) -> None:
        response = self._valid_response()
        response["feedback"]["strengths"] = ["x" * 5000, ""]
        parsed = validate_ai_response_with_pydantic(response)
        self.assertEqual(len(parsed.feedback.strengths), 1)  # empty filtered
        self.assertEqual(len(parsed.feedback.strengths[0]), 400)


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------


class RetryPolicyTests(unittest.TestCase):
    def test_retries_retriable_errors_up_to_max_attempts(self) -> None:
        attempts = {"count": 0}

        def flaky() -> str:
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise ProviderResponseError("transient 502", retriable=True)
            return "ok"

        result = call_with_retry(
            flaky,
            provider="groq",
            max_attempts=DEFAULT_MAX_ATTEMPTS,
            sleep=lambda _delay: None,
        )
        self.assertEqual(result, "ok")
        self.assertEqual(attempts["count"], 3)

    def test_exhausts_retries_and_raises_last_error(self) -> None:
        attempts = {"count": 0}
        sleeps: list[float] = []

        def always_fails() -> None:
            attempts["count"] += 1
            raise ProviderResponseError("forever down", retriable=True)

        with self.assertRaises(ProviderResponseError) as ctx:
            call_with_retry(
                always_fails,
                provider="groq",
                max_attempts=3,
                sleep=sleeps.append,
            )
        self.assertEqual(attempts["count"], 3)
        # Two backoff sleeps between three attempts.
        self.assertEqual(len(sleeps), 2)
        self.assertIn("forever down", str(ctx.exception))

    def test_non_retriable_error_propagates_immediately(self) -> None:
        attempts = {"count": 0}

        def bad_payload() -> None:
            attempts["count"] += 1
            raise ValueError("invalid LLM JSON")

        with self.assertRaises(ValueError):
            call_with_retry(
                bad_payload,
                provider="codex",
                max_attempts=3,
                sleep=lambda _delay: None,
            )
        self.assertEqual(attempts["count"], 1)

    def test_per_provider_backoff_base_differs(self) -> None:
        groq_base = provider_backoff_base("groq")
        codex_base = provider_backoff_base("codex")
        # Groq backs off faster than Codex.
        self.assertLess(groq_base, codex_base)

    def test_backoff_grows_exponentially(self) -> None:
        # With jitter off, attempt-1 < attempt-2 < attempt-3 (until capped).
        d1 = compute_backoff_delay(1, provider="codex", jitter=False)
        d2 = compute_backoff_delay(2, provider="codex", jitter=False)
        d3 = compute_backoff_delay(3, provider="codex", jitter=False)
        self.assertLess(d1, d2)
        self.assertLess(d2, d3)

    def test_backoff_capped_at_max(self) -> None:
        d_huge = compute_backoff_delay(20, provider="codex", jitter=False)
        from server_app.services.evaluator import MAX_BACKOFF_SECONDS

        self.assertLessEqual(d_huge, MAX_BACKOFF_SECONDS)

    def test_on_attempt_callback_invoked_each_attempt(self) -> None:
        on_attempt = MagicMock()
        attempts = {"count": 0}

        def fails_twice() -> str:
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise TimeoutError("slow")
            return "done"

        result = call_with_retry(
            fails_twice,
            provider="openai",
            max_attempts=3,
            sleep=lambda _delay: None,
            on_attempt=on_attempt,
        )
        self.assertEqual(result, "done")
        self.assertEqual(on_attempt.call_count, 3)


# ---------------------------------------------------------------------------
# 503 response shape
# ---------------------------------------------------------------------------


class ProviderUnavailableResponseTests(unittest.TestCase):
    def test_response_matches_schema(self) -> None:
        body = build_provider_unavailable_response(
            provider="groq",
            attempts=3,
            retry_after_seconds=45,
        )
        # Round-trip through the model — guarantees schema fidelity.
        detail = AIProviderUnavailableDetails.model_validate(body)
        self.assertEqual(detail.code, "ai_provider_unavailable")
        self.assertEqual(detail.provider, "groq")
        self.assertEqual(detail.attempts, 3)
        self.assertEqual(detail.retry_after_seconds, 45)
        self.assertIn("groq", detail.message)

    def test_retry_after_clamped(self) -> None:
        body = build_provider_unavailable_response(
            provider="codex", attempts=3, retry_after_seconds=1_000_000
        )
        self.assertLessEqual(body["retry_after_seconds"], 86_400)

    def test_next_utc_midnight_is_iso_z(self) -> None:
        reset = next_utc_midnight_iso()
        self.assertTrue(reset.endswith("Z"))
        self.assertEqual(len(reset.split("T")[1]), len("00:00:00Z"))


if __name__ == "__main__":  # pragma: no cover - manual invocation
    unittest.main()
