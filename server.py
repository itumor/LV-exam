#!/usr/bin/env python3
"""Serve the Latvian A2 app and evaluate submissions with an LLM provider."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import os
import re
import shutil
import sqlite3
import socket
import sys
import subprocess
import tempfile
import threading
import time
import secrets
from functools import lru_cache
import urllib.parse
import urllib.error
import urllib.request
from http.cookies import SimpleCookie
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from billing import BillingStore, FREE_EXAM_ID, DEFAULT_PRODUCTS, StripeClient


ROOT = Path(__file__).resolve().parent
UPLOAD_ROOT = ROOT / "data" / "uploads"
MAX_BODY_BYTES = 1_500_000
MAX_AUDIO_BYTES = 20_000_000
DEFAULT_BILLING_DB_PATH = ROOT / "data" / "billing.sqlite3"
PUBLIC_APP_PREFIX = "/latvian-a2-exam-app/"
PUBLIC_ATTACHMENT_PREFIX = "/codex/Attachments/"
PUBLIC_LISTENING_PREFIX = "/latvian-listening-library/"
PUBLIC_LISTENING_WEB_PREFIX = "/latvian-listening-library/web/"
PUBLIC_LISTENING_WEB_DATA_PREFIX = "/latvian-listening-library/web/data/"
PUBLIC_LISTENING_DATA_PREFIX = "/latvian-listening-library/data/"
PUBLIC_EXAM_SIM_PREFIX = "/latvian-listening-library/exam-simulation/"
PRIVATE_STATIC_EXTENSIONS = {
    ".db",
    ".env",
    ".err",
    ".json",
    ".lock",
    ".log",
    ".py",
    ".sqlite",
    ".sqlite3",
    ".sql",
    ".toml",
    ".yaml",
    ".yml",
}
PUBLIC_APP_EXTENSIONS = {".css", ".html", ".js", ".md", ".png", ".svg", ".ico", ".txt"}
PUBLIC_ATTACHMENT_EXTENSIONS = {
    ".mp3",
    ".ogg",
    ".wav",
    ".webm",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
}
PUBLIC_LISTENING_WEB_EXTENSIONS = {
    ".css",
    ".html",
    ".js",
    ".json",
    ".ico",
    ".png",
    ".svg",
    ".txt",
}
PUBLIC_LISTENING_DATA_EXTENSIONS = {".json", ".md", ".mp3"}
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
DEFAULT_CODEX_MODEL = "gpt-5.2"
CODEX_OSS_DEFAULT_MODEL_LABEL = "codex-oss-default"
CODEX_TIMEOUT_SECONDS = 300
DEFAULT_RETRY_LIMIT = 3
SCORING_PROMPT_VERSION = "2026-05-05"
SCORING_RUBRIC_VERSION = "a2-writing-speaking-v1"
SCORING_SKILLS = ("listening", "reading", "writing", "speaking")
FREE_TEXT_SKILLS = ("writing", "speaking")
DEFAULT_DAILY_REQUEST_LIMITS = {
    "anonymous": 2,
    "free": 3,
    "pro": 12,
    "enterprise": 30,
    "admin": 100,
}
DEFAULT_DAILY_COST_LIMIT_CENTS = {
    "anonymous": 50,
    "free": 100,
    "pro": 500,
    "enterprise": 2_000,
    "admin": 10_000,
}
MAX_FREE_TEXT_CHARS = int(os.getenv("AI_SCORING_MAX_FREE_TEXT_CHARS", "12000"))
MAX_TOTAL_ANSWER_CHARS = int(os.getenv("AI_SCORING_MAX_TOTAL_ANSWER_CHARS", "40000"))
DEFAULT_PLAN = os.getenv("AI_SCORING_DEFAULT_PLAN", "free").strip().lower() or "free"
EVALUATION_CACHE: dict[str, dict[str, Any]] = {}
EVALUATION_CACHE_LOCK = threading.Lock()
QUOTA_USAGE: dict[str, dict[str, Any]] = {}
QUOTA_USAGE_LOCK = threading.Lock()
AUDIT_LOG: list[dict[str, Any]] = []
AUDIT_LOG_LOCK = threading.Lock()


class ProviderResponseError(RuntimeError):
    def __init__(self, message: str, *, retriable: bool = False) -> None:
        super().__init__(message)
        self.retriable = retriable


class QuotaExceededError(RuntimeError):
    def __init__(
        self, message: str, *, status_code: int = HTTPStatus.TOO_MANY_REQUESTS
    ) -> None:
        super().__init__(message)
        self.status_code = status_code


class EvaluationError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = HTTPStatus.BAD_GATEWAY,
        retry_state: str = "failed",
        telemetry: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_state = retry_state
        self.telemetry = telemetry or {}


def current_day_key() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def identity_from_submission(submission: dict[str, Any]) -> dict[str, str]:
    candidate = submission.get("candidate", {})
    candidate_code = ""
    if isinstance(candidate, dict):
        candidate_code = str(candidate.get("code", "") or "").strip()
    user_key = (
        str(submission.get("learner_id", "") or "").strip()
        or str(submission.get("learner_email", "") or "").strip()
        or str(submission.get("user_id", "") or "").strip()
        or str(submission.get("candidate_code", "") or "").strip()
        or candidate_code
        or str(submission.get("submission_id", "") or "").strip()
        or "anonymous"
    )
    plan = (
        str(
            submission.get("plan", "")
            or submission.get("access_plan", "")
            or DEFAULT_PLAN
        )
        .strip()
        .lower()
    )
    if not plan:
        plan = DEFAULT_PLAN
    return {"user_key": user_key, "plan": plan}


def retry_limit() -> int:
    raw = os.getenv("AI_SCORING_MAX_RETRIES", str(DEFAULT_RETRY_LIMIT)).strip()
    try:
        return max(1, int(raw))
    except ValueError as error:
        raise RuntimeError("AI_SCORING_MAX_RETRIES must be an integer.") from error


def plan_request_limit(plan: str) -> int:
    env_name = f"AI_SCORING_DAILY_REQUEST_LIMIT_{plan.upper()}"
    raw = os.getenv(env_name, "").strip()
    if raw:
        try:
            return max(0, int(raw))
        except ValueError as error:
            raise RuntimeError(f"{env_name} must be an integer.") from error
    return DEFAULT_DAILY_REQUEST_LIMITS.get(plan, DEFAULT_DAILY_REQUEST_LIMITS["free"])


def plan_cost_limit_cents(plan: str) -> int:
    env_name = f"AI_SCORING_DAILY_COST_LIMIT_CENTS_{plan.upper()}"
    raw = os.getenv(env_name, "").strip()
    if raw:
        try:
            return max(0, int(raw))
        except ValueError as error:
            raise RuntimeError(f"{env_name} must be an integer.") from error
    return DEFAULT_DAILY_COST_LIMIT_CENTS.get(
        plan, DEFAULT_DAILY_COST_LIMIT_CENTS["free"]
    )


def cost_rate_cents_per_1k_tokens(provider: str) -> float:
    if provider == "groq":
        raw = os.getenv("GROQ_COST_CENTS_PER_1K_TOKENS", "1.0").strip()
    else:
        raw = os.getenv("CODEX_COST_CENTS_PER_1K_TOKENS", "1.0").strip()
    try:
        value = float(raw)
    except ValueError as error:
        raise RuntimeError("AI scoring cost rate must be numeric.") from error
    return max(0.0, value)


def estimate_text_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


def estimate_request_cost_cents(
    provider: str, submission_context: dict[str, Any], exam_context: str
) -> int:
    request_text = json.dumps(
        {"submission": submission_context, "exam_context": exam_context},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    input_tokens = estimate_text_tokens(request_text)
    output_tokens = int(os.getenv("AI_SCORING_MAX_OUTPUT_TOKENS", "1200"))
    rate = cost_rate_cents_per_1k_tokens(provider)
    estimated = ((input_tokens + output_tokens) * rate) / 1000.0
    return max(1, math.ceil(estimated))


def validate_submission_size(submission_context: dict[str, Any]) -> None:
    answers = submission_context.get("answers", {})
    if not isinstance(answers, dict):
        raise ValueError("Submission answers must be an object.")
    total_chars = 0
    for skill_values in answers.values():
        if not isinstance(skill_values, dict):
            raise ValueError("Submission answers must be nested objects.")
        for task_values in skill_values.values():
            if not isinstance(task_values, list):
                raise ValueError("Submission answers must contain arrays of responses.")
            for answer in task_values:
                answer_text = str(answer or "")
                total_chars += len(answer_text)
                if len(answer_text) > MAX_FREE_TEXT_CHARS:
                    raise ValueError("A response is too long for AI scoring.")
    if total_chars > MAX_TOTAL_ANSWER_CHARS:
        raise ValueError("The submitted answers are too large for AI scoring.")


def reserve_quota(
    identity: dict[str, str], estimated_cost_cents: int
) -> dict[str, Any]:
    plan = identity["plan"]
    user_key = identity["user_key"]
    quota_key = f"{plan}:{user_key}:{current_day_key()}"
    request_limit = plan_request_limit(plan)
    cost_limit = plan_cost_limit_cents(plan)

    with QUOTA_USAGE_LOCK:
        usage = QUOTA_USAGE.setdefault(
            quota_key,
            {
                "requests": 0,
                "estimated_cost_cents": 0,
                "plan": plan,
                "user_key": user_key,
                "day": current_day_key(),
            },
        )
        if usage["requests"] >= request_limit:
            raise QuotaExceededError(
                f"AI scoring quota exceeded for plan '{plan}'. Retry tomorrow or upgrade your plan."
            )
        if usage["estimated_cost_cents"] + estimated_cost_cents > cost_limit:
            raise QuotaExceededError(
                f"AI scoring daily cost budget exceeded for plan '{plan}'. Try again tomorrow."
            )
        usage["requests"] += 1
        usage["estimated_cost_cents"] += estimated_cost_cents
        usage["last_request_at"] = time.time()
        return {
            "quota_key": quota_key,
            "request_limit": request_limit,
            "cost_limit_cents": cost_limit,
            "usage": dict(usage),
        }


def record_audit_event(event: dict[str, Any]) -> None:
    redacted = dict(event)
    if "submission" in redacted:
        redacted["submission"] = {
            "submission_id": redacted["submission"].get("submission_id"),
            "exam_id": redacted["submission"].get("exam_id"),
            "plan": redacted["submission"].get("plan"),
            "candidate_code": redacted["submission"].get("candidate", {}).get("code")
            if isinstance(redacted["submission"].get("candidate"), dict)
            else None,
        }
    with AUDIT_LOG_LOCK:
        AUDIT_LOG.append(redacted)
        if len(AUDIT_LOG) > 200:
            del AUDIT_LOG[: len(AUDIT_LOG) - 200]


def safe_int(
    value: Any,
    *,
    field_name: str,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer.")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be an integer.") from error
    if minimum is not None and parsed < minimum:
        raise ValueError(f"{field_name} must be at least {minimum}.")
    if maximum is not None and parsed > maximum:
        raise ValueError(f"{field_name} must be at most {maximum}.")
    return parsed


def safe_bool(value: Any, *, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError(f"{field_name} must be a boolean.")


def safe_text(value: Any, *, field_name: str, max_length: int = 4000) -> str:
    if value is None:
        return ""
    if not isinstance(value, (str, int, float)):
        raise ValueError(f"{field_name} must be text.")
    text = str(value).strip()
    if len(text) > max_length:
        raise ValueError(f"{field_name} is too long.")
    return text


def safe_positive_float(value: Any, *, field_name: str, minimum: float = 0.0) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be numeric.")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be numeric.") from error
    if parsed < minimum:
        raise ValueError(f"{field_name} must be at least {minimum}.")
    return parsed


def local_skill_points(skill_summary: dict[str, Any]) -> int:
    objective_correct = safe_int(
        skill_summary.get("objective_correct", 0),
        field_name="objective_correct",
        minimum=0,
        maximum=15,
    )
    return min(15, objective_correct)


def local_skill_score(skill: str, skill_summary: dict[str, Any]) -> dict[str, Any]:
    points = local_skill_points(skill_summary)
    return {
        "points": points,
        "max_points": 15,
        "passed": points >= 9,
        "reason": f"Local objective pre-score for {skill}; AI scoring is not applied to this skill.",
    }


def locked_local_scores(submission_context: dict[str, Any]) -> dict[str, Any]:
    scoring = submission_context.get("scoring", {})
    by_skill = scoring.get("by_skill", {}) if isinstance(scoring, dict) else {}
    local_scores: dict[str, Any] = {}
    for skill in ("listening", "reading"):
        skill_summary = by_skill.get(skill, {}) if isinstance(by_skill, dict) else {}
        if not isinstance(skill_summary, dict):
            skill_summary = {}
        local_scores[skill] = local_skill_score(skill, skill_summary)
    return local_scores


def normalize_score_section(raw_section: Any, *, skill: str) -> dict[str, Any]:
    if not isinstance(raw_section, dict):
        raise ValueError(f"Scores for {skill} must be an object.")
    points = safe_int(
        raw_section.get("points"), field_name=f"{skill}.points", minimum=0, maximum=15
    )
    max_points = safe_int(
        raw_section.get("max_points", 15),
        field_name=f"{skill}.max_points",
        minimum=15,
        maximum=15,
    )
    reason = safe_text(
        raw_section.get("reason", ""), field_name=f"{skill}.reason", max_length=2000
    )
    return {
        "points": points,
        "max_points": max_points,
        "passed": points >= 9,
        "reason": reason,
    }


def normalize_corrections(raw_corrections: Any) -> list[dict[str, Any]]:
    if raw_corrections is None:
        return []
    if not isinstance(raw_corrections, list):
        raise ValueError("Corrections must be an array.")
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(raw_corrections[:50], start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Correction #{index} must be an object.")
        normalized.append(
            {
                "skill": safe_text(
                    item.get("skill", ""),
                    field_name=f"corrections[{index}].skill",
                    max_length=40,
                ),
                "task": safe_text(
                    item.get("task", ""),
                    field_name=f"corrections[{index}].task",
                    max_length=80,
                ),
                "item": safe_int(
                    item.get("item", 1),
                    field_name=f"corrections[{index}].item",
                    minimum=1,
                ),
                "candidate_answer": safe_text(
                    item.get("candidate_answer", ""),
                    field_name=f"corrections[{index}].candidate_answer",
                    max_length=1200,
                ),
                "suggested_answer": safe_text(
                    item.get("suggested_answer", ""),
                    field_name=f"corrections[{index}].suggested_answer",
                    max_length=1200,
                ),
                "comment": safe_text(
                    item.get("comment", ""),
                    field_name=f"corrections[{index}].comment",
                    max_length=2000,
                ),
            }
        )
    return normalized


def normalize_feedback_items(raw_items: Any, *, field_name: str) -> list[str]:
    if raw_items is None:
        return []
    if not isinstance(raw_items, list):
        raise ValueError(f"{field_name} must be an array.")
    return [
        safe_text(item, field_name=f"{field_name}[]", max_length=600)
        for item in raw_items
    ]


def normalize_feedback(raw_feedback: Any) -> dict[str, Any]:
    if raw_feedback is None:
        raw_feedback = {}
    if not isinstance(raw_feedback, dict):
        raise ValueError("Feedback must be an object.")
    return {
        "summary": safe_text(
            raw_feedback.get("summary", ""),
            field_name="feedback.summary",
            max_length=4000,
        ),
        "strengths": normalize_feedback_items(
            raw_feedback.get("strengths"), field_name="feedback.strengths"
        ),
        "improvements": normalize_feedback_items(
            raw_feedback.get("improvements"), field_name="feedback.improvements"
        ),
        "next_practice": normalize_feedback_items(
            raw_feedback.get("next_practice"), field_name="feedback.next_practice"
        ),
    }


def validate_and_normalize_evaluation_payload(raw_payload: Any) -> dict[str, Any]:
    if not isinstance(raw_payload, dict):
        raise ValueError("LLM response must be a JSON object.")
    status = safe_text(
        raw_payload.get("status", ""), field_name="status", max_length=40
    ).lower()
    if status != "evaluated":
        raise ValueError("LLM response status must be 'evaluated'.")
    scores = raw_payload.get("scores")
    if not isinstance(scores, dict):
        raise ValueError("LLM response scores must be an object.")

    normalized_scores: dict[str, Any] = {}
    total = 0
    passed = True
    for skill in SCORING_SKILLS:
        raw_section = scores.get(skill)
        if raw_section is None:
            if skill in FREE_TEXT_SKILLS:
                raise ValueError(f"Scores for {skill} must be an object.")
            continue
        normalized_section = normalize_score_section(raw_section, skill=skill)
        normalized_scores[skill] = normalized_section
        total += normalized_section["points"]
        passed = passed and normalized_section["passed"]

    normalized_scores["total"] = total
    normalized_scores["passed"] = passed
    return {
        "status": "evaluated",
        "scores": normalized_scores,
        "corrections": normalize_corrections(raw_payload.get("corrections", [])),
        "feedback": normalize_feedback(raw_payload.get("feedback", {})),
    }


def merge_local_and_ai_scores(
    normalized_evaluation: dict[str, Any],
    submission_context: dict[str, Any],
) -> dict[str, Any]:
    scores = dict(normalized_evaluation.get("scores", {}))
    local_scores = locked_local_scores(submission_context)
    for skill in FREE_TEXT_SKILLS:
        scores[skill] = scores.get(skill, {})
    scores.update(local_scores)
    total = sum(
        section.get("points", 0)
        for skill, section in scores.items()
        if skill in SCORING_SKILLS
    )
    passed = all(
        section.get("passed", False)
        for skill, section in scores.items()
        if skill in SCORING_SKILLS
    )
    scores["total"] = total
    scores["passed"] = passed
    merged = dict(normalized_evaluation)
    merged["scores"] = scores
    return merged


def provider_call_once(
    config: dict[str, Any], submission_context: dict[str, Any], exam_context: str
) -> dict[str, Any]:
    if config["provider"] == "groq":
        return call_groq(config, submission_context, exam_context)
    if config["provider"] == "codex" and config.get("mode") == "remote":
        return call_codex_remote(config, submission_context, exam_context)
    if config["provider"] == "codex":
        return call_codex(config, submission_context, exam_context)
    raise RuntimeError("Unsupported LLM provider.")


AUTH_DB_PATH = ROOT / ".multica" / "auth.sqlite3"
AUTH_SESSION_COOKIE = "a2_session"
AUTH_SESSION_TTL_DAYS = 30
AUTH_WEBHOOK_SECRET = os.getenv("AUTH_WEBHOOK_SECRET", "").strip()
ATTEMPT_STATUSES = {"started", "in_progress", "submitted", "scored", "expired"}
MUTABLE_ATTEMPT_STATUSES = {"started", "in_progress"}
ACCOUNT_ROLES = {"user", "admin", "superadmin"}
SCORING_RATE_LIMIT_WINDOW_SECONDS = int(
    os.getenv("SCORING_RATE_LIMIT_WINDOW_SECONDS", "60")
)
SCORING_RATE_LIMIT_MAX_REQUESTS = int(os.getenv("SCORING_RATE_LIMIT_MAX_REQUESTS", "5"))
SCORING_RATE_LIMITS: dict[str, list[float]] = {}
SCORING_RATE_LIMIT_LOCK = threading.Lock()


def built_in_exam_catalog() -> list[dict[str, Any]]:
    return [
        {
            "id": str(index).zfill(2),
            "title": f"A2 Mock Exam {str(index).zfill(2)}",
            "description": "Built-in Latvian A2 practice exam.",
            "content_version": 1,
            "status": "published",
            "manifest": {
                "markdownPath": f"/codex/A2_Mock_Exam_{str(index).zfill(2)}.md",
                "sourcePath": f"codex/A2_Mock_Exam_{str(index).zfill(2)}.md",
                "attachmentRoot": f"/codex/Attachments/A2_Mock_Exam_{str(index).zfill(2)}/",
            },
        }
        for index in range(1, 11)
    ]


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


RATE_LIMIT_LOCK = threading.Lock()
RATE_LIMIT_BUCKETS: dict[str, list[float]] = {}
SENTRY_SDK: Any | None = None


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def json_response(
    handler: SimpleHTTPRequestHandler, status: int, payload: dict[str, Any]
) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def text_response(
    handler: SimpleHTTPRequestHandler, status: int, body: str, content_type: str
) -> None:
    raw = body.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


def api_error_response(handler: SimpleHTTPRequestHandler, error: ApiError) -> None:
    payload: dict[str, Any] = {
        "error": {
            "code": error.code,
            "message": error.message,
        }
    }
    if error.details:
        payload["error"]["details"] = error.details
    json_response(handler, error.status_code, payload)


def init_sentry() -> None:
    global SENTRY_SDK
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        return
    try:
        import sentry_sdk  # type: ignore[import-not-found]
    except ImportError:
        log_event("warning", "sentry_unavailable", reason="sentry_sdk_not_installed")
        return
    sentry_sdk.init(
        dsn=dsn,
        environment=os.getenv("APP_ENV", "production"),
        release=os.getenv("APP_RELEASE", ""),
        traces_sample_rate=float(
            os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.0") or "0.0"
        ),
    )
    SENTRY_SDK = sentry_sdk


def capture_exception(error: BaseException) -> None:
    if SENTRY_SDK is not None:
        SENTRY_SDK.capture_exception(error)


def log_event(level: str, event: str, **fields: Any) -> None:
    payload = {
        "ts": now_iso(),
        "level": level,
        "event": event,
        **fields,
    }
    print(
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        file=sys.stderr,
        flush=True,
    )


def client_ip(handler: SimpleHTTPRequestHandler) -> str:
    forwarded = handler.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip()
    return forwarded or handler.client_address[0]


def check_rate_limit(key: str, *, limit_env: str, window_env: str) -> tuple[bool, int]:
    limit = int(os.getenv(limit_env, "20") or "20")
    window_seconds = int(os.getenv(window_env, "60") or "60")
    if limit <= 0 or window_seconds <= 0:
        return True, 0
    now = time.monotonic()
    cutoff = now - window_seconds
    with RATE_LIMIT_LOCK:
        bucket = [item for item in RATE_LIMIT_BUCKETS.get(key, []) if item >= cutoff]
        if len(bucket) >= limit:
            retry_after = max(1, int(window_seconds - (now - bucket[0])))
            RATE_LIMIT_BUCKETS[key] = bucket
            return False, retry_after
        bucket.append(now)
        RATE_LIMIT_BUCKETS[key] = bucket
    return True, 0


def json_response_with_headers(
    handler: SimpleHTTPRequestHandler,
    status: int,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    for key, value in (headers or {}).items():
        handler.send_header(key, value)
    handler.end_headers()
    handler.wfile.write(body)


def is_production() -> bool:
    return os.getenv("APP_ENV", "").strip().lower() == "production"


def normalize_request_path(raw_path: str) -> str:
    parsed_path = urllib.parse.urlparse(raw_path).path
    decoded = urllib.parse.unquote(parsed_path)
    normalized = os.path.normpath(decoded)
    if decoded.endswith("/") and not normalized.endswith("/"):
        normalized += "/"
    if not normalized.startswith("/"):
        normalized = "/" + normalized
    return normalized


def path_has_private_segment(path: str) -> bool:
    return any(
        part.startswith(".") for part in Path(path).parts if part not in {"/", ""}
    )


def is_public_static_path(raw_path: str) -> bool:
    path = normalize_request_path(raw_path)
    if ".." in Path(path).parts or path_has_private_segment(path):
        return False
    if path == PUBLIC_APP_PREFIX:
        return True
    if path.startswith(PUBLIC_APP_PREFIX):
        if path.endswith("/"):
            return False
        return Path(path).suffix.lower() in PUBLIC_APP_EXTENSIONS
    if path.startswith(PUBLIC_ATTACHMENT_PREFIX):
        suffix = Path(path).suffix.lower()
        return (
            suffix in PUBLIC_ATTACHMENT_EXTENSIONS
            and suffix not in PRIVATE_STATIC_EXTENSIONS
        )
    if path in {
        "/latvian-listening-library",
        PUBLIC_LISTENING_PREFIX,
        PUBLIC_LISTENING_WEB_PREFIX,
    }:
        return True
    if path in {
        "/latvian-listening-library/exam-simulation",
        PUBLIC_EXAM_SIM_PREFIX,
    }:
        return True
    if path.startswith(PUBLIC_LISTENING_PREFIX) and not path.startswith(
        PUBLIC_LISTENING_WEB_PREFIX
    ):
        suffix = Path(path).suffix.lower()
        if path.startswith(f"{PUBLIC_LISTENING_PREFIX}data/"):
            return suffix in PUBLIC_LISTENING_DATA_EXTENSIONS
        return suffix in PUBLIC_LISTENING_WEB_EXTENSIONS
    if path.startswith(PUBLIC_LISTENING_WEB_DATA_PREFIX):
        if path.endswith("/"):
            return False
        return Path(path).suffix.lower() in PUBLIC_LISTENING_DATA_EXTENSIONS
    if path.startswith(PUBLIC_LISTENING_WEB_PREFIX):
        if path.endswith("/"):
            return False
        return Path(path).suffix.lower() in PUBLIC_LISTENING_WEB_EXTENSIONS
    if path.startswith(PUBLIC_LISTENING_DATA_PREFIX):
        if path.endswith("/"):
            return False
        return Path(path).suffix.lower() in PUBLIC_LISTENING_DATA_EXTENSIONS
    if path in {"/latvian-listening-library/exam-simulation", PUBLIC_EXAM_SIM_PREFIX}:
        return True
    if path.startswith(PUBLIC_EXAM_SIM_PREFIX):
        if path.endswith("/"):
            return False
        return Path(path).suffix.lower() in PUBLIC_LISTENING_WEB_EXTENSIONS
    return False


def static_cache_control(raw_path: str) -> str:
    path = normalize_request_path(raw_path)
    if path.startswith(PUBLIC_ATTACHMENT_PREFIX):
        return "public, max-age=86400"
    if path.startswith(f"{PUBLIC_LISTENING_PREFIX}data/"):
        return "public, max-age=86400"
    if path.startswith(PUBLIC_LISTENING_PREFIX) and Path(path).suffix.lower() in {
        ".css",
        ".js",
        ".ico",
        ".png",
        ".svg",
    }:
        return "public, max-age=300"
    if path.startswith(PUBLIC_LISTENING_DATA_PREFIX):
        return "public, max-age=86400"
    if path.startswith(PUBLIC_LISTENING_WEB_PREFIX) and Path(path).suffix.lower() in {
        ".css",
        ".js",
        ".ico",
        ".png",
        ".svg",
    }:
        return "public, max-age=300"
    if path.startswith(PUBLIC_EXAM_SIM_PREFIX) and Path(path).suffix.lower() in {
        ".css",
        ".js",
        ".ico",
        ".png",
        ".svg",
    }:
        return "public, max-age=300"
    if path.startswith(PUBLIC_APP_PREFIX) and Path(path).suffix.lower() in {
        ".css",
        ".js",
        ".svg",
        ".png",
        ".ico",
    }:
        return "public, max-age=300"
    return "no-store"


def safe_read_json(handler: SimpleHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length <= 0:
        raise ValueError("Request body is empty.")
    if length > MAX_BODY_BYTES:
        raise ValueError("Request body is too large.")
    raw = handler.rfile.read(length)
    return json.loads(raw.decode("utf-8"))


def safe_read_raw_body(handler: SimpleHTTPRequestHandler) -> bytes:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length <= 0:
        raise ValueError("Request body is empty.")
    if length > MAX_BODY_BYTES:
        raise ValueError("Request body is too large.")
    return handler.rfile.read(length)


def request_base_url(handler: SimpleHTTPRequestHandler) -> str:
    host = handler.headers.get("Host", "localhost:4173")
    proto = handler.headers.get("X-Forwarded-Proto", "").split(",", 1)[0].strip()
    scheme = proto or ("https" if is_production() else "http")
    return f"{scheme}://{host}"


def billing_db_path() -> Path:
    return Path(os.getenv("BILLING_DB_PATH", str(DEFAULT_BILLING_DB_PATH)))


@lru_cache(maxsize=1)
def get_billing_store() -> BillingStore:
    return BillingStore(billing_db_path())


def get_stripe_client() -> StripeClient:
    return StripeClient(os.getenv("STRIPE_SECRET_KEY", "").strip())


def get_product_price_id(product_key: str) -> str:
    product = next((item for item in DEFAULT_PRODUCTS if item.key == product_key), None)
    if not product:
        return ""
    return os.getenv(product.price_env, "").strip()


def stripe_webhook_secret() -> str:
    return os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()


def extract_json_object(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("LLM response did not contain a JSON object.")
    value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("LLM response JSON was not an object.")
    return value


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class ClosingSqliteConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc, tb) -> bool:
        try:
            return bool(super().__exit__(exc_type, exc, tb))
        finally:
            self.close()


def db_connection() -> sqlite3.Connection:
    path = Path(os.getenv("AUTH_DB_PATH", str(AUTH_DB_PATH)))
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, factory=ClosingSqliteConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_auth_store() -> None:
    with db_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                account_id TEXT REFERENCES accounts(id) ON DELETE CASCADE,
                email TEXT NOT NULL UNIQUE,
                display_name TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS accounts (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password_salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                deleted_at TEXT
            );

            CREATE TABLE IF NOT EXISTS profiles (
                account_id TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
                full_name TEXT NOT NULL,
                native_language TEXT,
                exam_target_date TEXT,
                exam_pack_status TEXT NOT NULL DEFAULT 'free',
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT,
                last_seen_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS attempts (
                id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                exam_id TEXT NOT NULL,
                exam_title TEXT NOT NULL,
                status TEXT NOT NULL,
                submitted_at TEXT NOT NULL,
                score_total INTEGER,
                score_payload TEXT NOT NULL,
                submission_payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS exams (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                content_version INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'published',
                manifest_payload TEXT NOT NULL,
                answer_key_payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS attempt_answers (
                id TEXT PRIMARY KEY,
                attempt_id TEXT NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
                account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                skill TEXT NOT NULL,
                task_key TEXT NOT NULL,
                item_index INTEGER NOT NULL,
                answer_payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(attempt_id, skill, task_key, item_index)
            );

            CREATE TABLE IF NOT EXISTS attempt_scores (
                id TEXT PRIMARY KEY,
                attempt_id TEXT NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
                account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                scoring_version TEXT NOT NULL,
                score_total INTEGER NOT NULL,
                score_payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS exam_attempt_category_score (
                id TEXT PRIMARY KEY,
                attempt_id TEXT NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
                account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                category TEXT NOT NULL CHECK (category IN ('listening', 'reading', 'writing', 'speaking')),
                score_0_to_15 INTEGER NOT NULL CHECK (score_0_to_15 >= 0 AND score_0_to_15 <= 15),
                passed_boolean BOOLEAN NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_exam_attempt_category_score_attempt_category 
            ON exam_attempt_category_score(attempt_id, category);

            CREATE INDEX IF NOT EXISTS idx_exam_attempt_category_score_account_category 
            ON exam_attempt_category_score(account_id, category, created_at DESC);

            CREATE TABLE IF NOT EXISTS ai_evaluations (
                id TEXT PRIMARY KEY,
                attempt_id TEXT NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
                account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                status TEXT NOT NULL,
                evaluation_payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS payments (
                id TEXT PRIMARY KEY,
                account_id TEXT REFERENCES accounts(id) ON DELETE SET NULL,
                provider TEXT NOT NULL,
                provider_reference TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL,
                amount_cents INTEGER,
                currency TEXT,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS subscriptions (
                id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                provider TEXT NOT NULL,
                provider_reference TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL,
                current_period_end TEXT,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS entitlements (
                id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                entitlement_type TEXT NOT NULL,
                source_reference TEXT,
                starts_at TEXT NOT NULL,
                expires_at TEXT,
                consumed_at TEXT,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS auth_webhook_events (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_attempts_account_submitted_at
            ON attempts(account_id, submitted_at DESC);

            CREATE INDEX IF NOT EXISTS idx_attempt_answers_attempt
            ON attempt_answers(attempt_id, skill, task_key, item_index);

            CREATE INDEX IF NOT EXISTS idx_attempt_scores_attempt
            ON attempt_scores(attempt_id, created_at DESC);
            """
        )
        ensure_column(conn, "attempts", "content_version", "INTEGER NOT NULL DEFAULT 1")
        ensure_column(
            conn, "attempts", "exam_snapshot_payload", "TEXT NOT NULL DEFAULT '{}'"
        )
        ensure_column(conn, "attempts", "answer_payload", "TEXT NOT NULL DEFAULT '{}'")
        ensure_column(conn, "attempts", "started_at", "TEXT")
        ensure_column(conn, "attempts", "expires_at", "TEXT")
        ensure_column(conn, "attempts", "scored_at", "TEXT")
        ensure_column(conn, "accounts", "role", "TEXT NOT NULL DEFAULT 'user'")
        ensure_column(conn, "users", "role", "TEXT NOT NULL DEFAULT 'user'")
        ensure_builtin_exam_catalog(conn)
        ensure_bootstrap_superadmin(conn)


def ensure_column(
    conn: sqlite3.Connection, table_name: str, column_name: str, definition: str
) -> None:
    columns = {
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def ensure_builtin_exam_catalog(conn: sqlite3.Connection) -> None:
    now = now_iso()
    for exam in built_in_exam_catalog():
        conn.execute(
            """
            INSERT INTO exams (id, title, content_version, status, manifest_payload, answer_key_payload, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, '{}', ?, ?)
            ON CONFLICT(id) DO NOTHING
            """,
            (
                exam["id"],
                exam["title"],
                exam["content_version"],
                exam["status"],
                json.dumps(
                    {"description": exam["description"], **exam["manifest"]},
                    ensure_ascii=False,
                ),
                now,
                now,
            ),
        )


def ensure_bootstrap_superadmin(conn: sqlite3.Connection) -> None:
    """Seed one local superadmin when none exists.

    Cheap/free deployments need an initial admin, but we avoid overwriting an
    existing production account. Set A2_BOOTSTRAP_SUPERADMIN_EMAIL/PASSWORD in
    the host environment before first boot.
    """
    existing = conn.execute(
        "SELECT id FROM accounts WHERE role = 'superadmin' AND deleted_at IS NULL LIMIT 1"
    ).fetchone()
    if existing is not None:
        return
    configured_email = os.getenv("A2_BOOTSTRAP_SUPERADMIN_EMAIL", "").strip()
    configured_password = os.getenv("A2_BOOTSTRAP_SUPERADMIN_PASSWORD", "")
    if is_production() and (not configured_email or not configured_password):
        log_event(
            "warning",
            "superadmin_bootstrap_skipped",
            reason="missing_explicit_production_credentials",
        )
        return
    if is_production() and len(configured_password) < 8:
        log_event(
            "warning",
            "superadmin_bootstrap_skipped",
            reason="weak_explicit_production_password",
        )
        return
    email = normalize_email(configured_email or "superadmin@example.com")
    password = configured_password or "ChangeMe123!"
    if len(password) < 8:
        password = "ChangeMe123!"
    account = conn.execute(
        "SELECT * FROM accounts WHERE email = ?", (email,)
    ).fetchone()
    now = now_iso()
    if account is None:
        salt_b64, hash_b64 = hash_password(password)
        account_id = "acct_superadmin_seed"
        conn.execute(
            """
            INSERT INTO accounts (id, email, password_salt, password_hash, status, created_at, deleted_at, role)
            VALUES (?, ?, ?, ?, 'active', ?, NULL, 'superadmin')
            """,
            (account_id, email, salt_b64, hash_b64, now),
        )
        upsert_profile(conn, account_id, "Seed Superadmin", None, None)
        return
    conn.execute(
        "UPDATE accounts SET role = 'superadmin' WHERE id = ?", (account["id"],)
    )


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    salt_bytes = salt or secrets.token_bytes(16)
    password_bytes = password.encode("utf-8")
    digest = hashlib.pbkdf2_hmac("sha256", password_bytes, salt_bytes, 120_000)
    return base64.b64encode(salt_bytes).decode("ascii"), base64.b64encode(
        digest
    ).decode("ascii")


def verify_password(password: str, salt_b64: str, expected_hash_b64: str) -> bool:
    salt = base64.b64decode(salt_b64.encode("ascii"))
    _, actual_hash = hash_password(password, salt)
    return hmac.compare_digest(actual_hash, expected_hash_b64)


def make_session_token() -> str:
    return secrets.token_urlsafe(32)


def session_cookie_header(token: str) -> str:
    expires = datetime.now(timezone.utc) + timedelta(days=AUTH_SESSION_TTL_DAYS)
    secure = "; Secure" if is_production() else ""
    return (
        f"{AUTH_SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax{secure}; "
        f"Expires={expires.strftime('%a, %d %b %Y %H:%M:%S GMT')}"
    )


def expired_session_cookie_header() -> str:
    secure = "; Secure" if is_production() else ""
    return (
        f"{AUTH_SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax{secure}; "
        "Expires=Thu, 01 Jan 1970 00:00:00 GMT"
    )


def parse_cookie_value(handler: SimpleHTTPRequestHandler, cookie_name: str) -> str:
    raw_cookie = handler.headers.get("Cookie", "")
    if not raw_cookie:
        return ""
    cookie = SimpleCookie()
    cookie.load(raw_cookie)
    morsel = cookie.get(cookie_name)
    return morsel.value if morsel else ""


def get_session_user_role(handler: SimpleHTTPRequestHandler) -> str:
    token = parse_cookie_value(handler, AUTH_SESSION_COOKIE)
    if not token:
        return "user"
    with db_connection() as conn:
        session = conn.execute(
            "SELECT account_id FROM sessions WHERE token = ? AND (expires_at IS NULL OR expires_at > ?) AND revoked_at IS NULL",
            (token, now_iso()),
        ).fetchone()
        if not session:
            return "user"
        account = conn.execute(
            "SELECT role FROM accounts WHERE id = ? AND deleted_at IS NULL",
            (session["account_id"],),
        ).fetchone()
        return account["role"] if account else "user"


def serialize_account(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "email": row["email"],
        "status": row["status"],
        "role": row["role"] if "role" in row.keys() else "user",
        "created_at": row["created_at"],
        "deleted_at": row["deleted_at"],
    }


def serialize_profile(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "account_id": row["account_id"],
        "full_name": row["full_name"],
        "native_language": row["native_language"],
        "exam_target_date": row["exam_target_date"],
        "exam_pack_status": row["exam_pack_status"],
        "updated_at": row["updated_at"],
    }


def serialize_attempt(row: sqlite3.Row) -> dict[str, Any]:
    score_payload = json.loads(row["score_payload"])
    submission_payload = json.loads(row["submission_payload"])
    exam_snapshot_payload = json.loads(row["exam_snapshot_payload"] or "{}")
    answer_payload = json.loads(row["answer_payload"] or "{}")
    return {
        "id": row["id"],
        "account_id": row["account_id"],
        "exam_id": row["exam_id"],
        "exam_title": row["exam_title"],
        "status": row["status"],
        "content_version": row["content_version"],
        "exam_snapshot": exam_snapshot_payload,
        "answers": answer_payload,
        "submitted_at": row["submitted_at"],
        "started_at": row["started_at"],
        "expires_at": row["expires_at"],
        "scored_at": row["scored_at"],
        "score_total": row["score_total"],
        "score_payload": score_payload,
        "submission_payload": submission_payload,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def redact_score_payload_for_learner(score_payload: Any) -> Any:
    clone = json.loads(json.dumps(score_payload or {}))
    scoring = clone.get("scoring") if isinstance(clone, dict) else None
    if (
        scoring is None
        and isinstance(clone, dict)
        and isinstance(clone.get("evaluation"), dict)
    ):
        scoring = clone["evaluation"].get("scoring")
    if isinstance(scoring, dict) and isinstance(scoring.get("items"), list):
        scoring["items"] = [
            {
                key: item.get(key)
                for key in ("skill", "task", "item", "actual", "correct", "scoring")
            }
            for item in scoring["items"]
            if isinstance(item, dict)
        ]
    return clone


def serialize_attempt_for_learner(row: sqlite3.Row) -> dict[str, Any]:
    attempt = serialize_attempt(row)
    return redact_attempt_for_learner(attempt)


def redact_attempt_for_learner(attempt: dict[str, Any]) -> dict[str, Any]:
    attempt = json.loads(json.dumps(attempt))
    attempt["exam_snapshot"].pop("answer_key", None)
    if isinstance(attempt.get("submission_payload"), dict):
        attempt["submission_payload"].pop("answer_key", None)
        attempt["submission_payload"].pop("validation_queue", None)
    attempt["score_payload"] = redact_score_payload_for_learner(
        attempt.get("score_payload")
    )
    return attempt


def parse_json_object(
    value: Any, default: dict[str, Any] | None = None
) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return default or {}
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return default or {}
    return parsed if isinstance(parsed, dict) else (default or {})


def normalize_answer(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def compute_objective_score(
    answer_key: dict[str, Any], answers: dict[str, Any]
) -> dict[str, Any]:
    by_skill: dict[str, dict[str, Any]] = {}
    items: list[dict[str, Any]] = []
    for skill in ("listening", "reading", "writing", "speaking"):
        skill_score = {
            "objective_correct": 0,
            "objective_possible": 0,
            "manual_review_possible": 15,
            "max_points": 15,
            "minimum_to_pass": 9,
        }
        by_skill[skill] = skill_score
        for task_key, expected_answers in (answer_key.get(skill) or {}).items():
            if not isinstance(expected_answers, list):
                continue
            for index, expected in enumerate(expected_answers):
                actual = (answers.get(skill) or {}).get(task_key) or []
                actual_value = (
                    actual[index]
                    if isinstance(actual, list) and index < len(actual)
                    else ""
                )
                correct = normalize_answer(actual_value) == normalize_answer(expected)
                skill_score["objective_possible"] += 1
                skill_score["objective_correct"] += 1 if correct else 0
                items.append(
                    {
                        "skill": skill,
                        "task": task_key,
                        "item": index + 1,
                        "expected": expected,
                        "actual": actual_value,
                        "correct": correct,
                        "scoring": "objective",
                    }
                )
        skill_score["manual_review_possible"] = max(
            0, 15 - skill_score["objective_possible"]
        )
    objective_correct = sum(skill["objective_correct"] for skill in by_skill.values())
    objective_possible = sum(skill["objective_possible"] for skill in by_skill.values())
    manual_possible = sum(
        skill["manual_review_possible"] for skill in by_skill.values()
    )
    return {
        "mode": "server_objective",
        "scoring_version": "objective-v1",
        "objective_correct": objective_correct,
        "objective_possible": objective_possible,
        "manual_review_possible": manual_possible,
        "estimated_minimum_points": objective_correct,
        "estimated_maximum_points_after_review": objective_correct + manual_possible,
        "by_skill": by_skill,
        "items": items,
    }


def check_scoring_rate_limit(identity: str) -> None:
    now = time.time()
    with SCORING_RATE_LIMIT_LOCK:
        recent = [
            timestamp
            for timestamp in SCORING_RATE_LIMITS.get(identity, [])
            if now - timestamp < SCORING_RATE_LIMIT_WINDOW_SECONDS
        ]
        if len(recent) >= SCORING_RATE_LIMIT_MAX_REQUESTS:
            retry_after = max(
                1, int(SCORING_RATE_LIMIT_WINDOW_SECONDS - (now - recent[0]))
            )
            raise ApiError(
                HTTPStatus.TOO_MANY_REQUESTS,
                "rate_limit_exceeded",
                "Scoring rate limit exceeded. Please wait before trying again.",
                {"retry_after_seconds": retry_after},
            )
        recent.append(now)
        SCORING_RATE_LIMITS[identity] = recent


def current_session_record(handler: SimpleHTTPRequestHandler) -> dict[str, Any] | None:
    token = parse_cookie_value(handler, AUTH_SESSION_COOKIE)
    if not token:
        return None
    now = now_iso()
    with db_connection() as conn:
        row = conn.execute(
            """
            SELECT s.token, s.account_id, s.expires_at, s.revoked_at, a.email, a.status, a.role,
                   a.created_at AS account_created_at, a.deleted_at,
                   p.full_name, p.native_language, p.exam_target_date, p.exam_pack_status, p.updated_at AS profile_updated_at
            FROM sessions s
            JOIN accounts a ON a.id = s.account_id
            LEFT JOIN profiles p ON p.account_id = a.id
            WHERE s.token = ?
            """,
            (token,),
        ).fetchone()
        if row is None:
            return None
        if (
            row["revoked_at"] is not None
            or row["deleted_at"] is not None
            or row["status"] != "active"
        ):
            return None
        if row["expires_at"] <= now:
            conn.execute(
                "UPDATE sessions SET revoked_at = ? WHERE token = ?", (now, token)
            )
            return None
        conn.execute(
            "UPDATE sessions SET last_seen_at = ? WHERE token = ?", (now, token)
        )
        return {
            "token": row["token"],
            "account": {
                "id": row["account_id"],
                "email": row["email"],
                "status": row["status"],
                "role": row["role"] or "user",
                "created_at": row["account_created_at"],
                "deleted_at": row["deleted_at"],
            },
            "profile": {
                "account_id": row["account_id"],
                "full_name": row["full_name"],
                "native_language": row["native_language"],
                "exam_target_date": row["exam_target_date"],
                "exam_pack_status": row["exam_pack_status"] or "free",
                "updated_at": row["profile_updated_at"],
            },
        }


def require_session(handler: SimpleHTTPRequestHandler) -> dict[str, Any]:
    session = current_session_record(handler)
    if session is None:
        raise PermissionError("Authentication required.")
    return session


def upsert_profile(
    conn: sqlite3.Connection,
    account_id: str,
    full_name: str,
    native_language: str | None,
    exam_target_date: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO profiles (account_id, full_name, native_language, exam_target_date, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(account_id) DO UPDATE SET
            full_name = excluded.full_name,
            native_language = excluded.native_language,
            exam_target_date = excluded.exam_target_date,
            updated_at = excluded.updated_at
        """,
        (account_id, full_name, native_language, exam_target_date, now_iso()),
    )


def create_session(conn: sqlite3.Connection, account_id: str) -> str:
    token = make_session_token()
    now = now_iso()
    expires_at = (
        (datetime.now(timezone.utc) + timedelta(days=AUTH_SESSION_TTL_DAYS))
        .isoformat()
        .replace("+00:00", "Z")
    )
    conn.execute(
        """
        INSERT INTO sessions (token, account_id, created_at, expires_at, revoked_at, last_seen_at)
        VALUES (?, ?, ?, ?, NULL, ?)
        """,
        (token, account_id, now, expires_at, now),
    )
    return token


def build_dashboard(conn: sqlite3.Connection, account_id: str) -> dict[str, Any]:
    profile = conn.execute(
        "SELECT * FROM profiles WHERE account_id = ?", (account_id,)
    ).fetchone()
    attempts = conn.execute(
        """
        SELECT * FROM attempts
        WHERE account_id = ?
        ORDER BY submitted_at DESC
        LIMIT 12
        """,
        (account_id,),
    ).fetchall()
    serialized_attempts = [serialize_attempt_for_learner(row) for row in attempts]
    latest = serialized_attempts[0] if serialized_attempts else None
    skill_progress: dict[str, dict[str, int]] = {}
    for attempt in serialized_attempts:
        score_payload = attempt.get("score_payload") or {}
        scoring = (
            score_payload.get("evaluation", {}).get("scores", {})
            if isinstance(score_payload.get("evaluation"), dict)
            else score_payload.get("scoring", {})
        )
        by_skill = scoring.get("by_skill") or {}
        for skill, score in by_skill.items():
            bucket = skill_progress.setdefault(
                skill, {"objective_correct": 0, "objective_possible": 0}
            )
            bucket["objective_correct"] += int(score.get("objective_correct") or 0)
            bucket["objective_possible"] += int(score.get("objective_possible") or 0)
    return {
        "profile": serialize_profile(profile),
        "summary": {
            "attempts_taken": len(serialized_attempts),
            "latest_score": ((latest or {}).get("score_total") if latest else None),
            "skill_progress": skill_progress,
            "subscription_status": (serialize_profile(profile) or {}).get(
                "exam_pack_status", "free"
            ),
        },
        "attempts": serialized_attempts,
    }


def create_account_record(payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
    email = normalize_email(str(payload.get("email", "")))
    password = str(payload.get("password", ""))
    full_name = str(payload.get("full_name", "")).strip()
    native_language = str(payload.get("native_language", "")).strip() or None
    exam_target_date = str(payload.get("exam_target_date", "")).strip() or None
    if not email or "@" not in email:
        raise ValueError("A valid email address is required.")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    if not full_name:
        raise ValueError("Full name is required.")

    salt_b64, hash_b64 = hash_password(password)
    now = now_iso()
    account_id = f"acct_{secrets.token_hex(8)}"
    with db_connection() as conn:
        try:
            conn.execute(
                """
                INSERT INTO accounts (id, email, password_salt, password_hash, status, created_at, deleted_at, role)
                VALUES (?, ?, ?, ?, 'active', ?, NULL, 'user')
                """,
                (account_id, email, salt_b64, hash_b64, now),
            )
        except sqlite3.IntegrityError as error:
            raise ValueError("That email is already registered.") from error
        upsert_profile(conn, account_id, full_name, native_language, exam_target_date)
        token = create_session(conn, account_id)
        account = conn.execute(
            "SELECT * FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()
        profile = conn.execute(
            "SELECT * FROM profiles WHERE account_id = ?", (account_id,)
        ).fetchone()
    return {
        "account": serialize_account(account),
        "profile": serialize_profile(profile),
        "dashboard": {
            "summary": {
                "attempts_taken": 0,
                "latest_score": None,
                "skill_progress": {},
                "subscription_status": "free",
            },
            "attempts": [],
        },
    }, token


def login_account(payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
    email = normalize_email(str(payload.get("email", "")))
    password = str(payload.get("password", ""))
    if not email or not password:
        raise ValueError("Email and password are required.")
    with db_connection() as conn:
        account = conn.execute(
            "SELECT * FROM accounts WHERE email = ?", (email,)
        ).fetchone()
        if (
            account is None
            or account["deleted_at"] is not None
            or account["status"] != "active"
        ):
            raise ValueError("Invalid email or password.")
        if not verify_password(
            password, account["password_salt"], account["password_hash"]
        ):
            raise ValueError("Invalid email or password.")
        token = create_session(conn, account["id"])
        profile = conn.execute(
            "SELECT * FROM profiles WHERE account_id = ?", (account["id"],)
        ).fetchone()
    return {
        "account": serialize_account(account),
        "profile": serialize_profile(profile),
    }, token


def persist_attempt(payload: dict[str, Any], session: dict[str, Any]) -> dict[str, Any]:
    raise ApiError(
        HTTPStatus.GONE,
        "legacy_attempt_upsert_disabled",
        "Client-trusted attempt upserts are disabled. Use /api/attempts/start, /answers, and /submit.",
    )


def start_attempt(payload: dict[str, Any], session: dict[str, Any]) -> dict[str, Any]:
    exam_id = exam_catalog_id(str(payload.get("exam_id", "")).strip())
    if not exam_id:
        raise ApiError(
            HTTPStatus.BAD_REQUEST, "invalid_request", "exam_id is required."
        )
    now = now_iso()
    attempt_id = str(payload.get("attempt_id") or f"attempt_{secrets.token_hex(8)}")
    expires_at = str(payload.get("expires_at") or "")
    with db_connection() as conn:
        existing = conn.execute(
            "SELECT * FROM attempts WHERE id = ?", (attempt_id,)
        ).fetchone()
        if existing is not None:
            if existing["account_id"] != session["account"]["id"]:
                raise ApiError(
                    HTTPStatus.FORBIDDEN,
                    "attempt_id_conflict",
                    "Attempt ID belongs to another account.",
                )
            return {"attempt": serialize_attempt(existing)}
        exam_row = load_exam_catalog_row(conn, exam_id, published_only=True)
        if exam_row is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "exam_not_found", "Exam not found.")
        manifest = parse_json_object(exam_row["manifest_payload"])
        exam_title = exam_row["title"]
        content_version = int(exam_row["content_version"] or 1)
        answer_key = load_server_answer_key(exam_id)
        exam_snapshot = {
            "exam_id": exam_id,
            "exam_title": exam_title,
            "content_version": content_version,
            "answer_key": answer_key,
            "manifest": manifest,
        }
        conn.execute(
            """
            INSERT INTO attempts (
                id, account_id, exam_id, exam_title, status, submitted_at,
                score_total, score_payload, submission_payload, created_at, updated_at,
                content_version, exam_snapshot_payload, answer_payload, started_at, expires_at, scored_at
            )
            VALUES (?, ?, ?, ?, 'started', ?, NULL, '{}', '{}', ?, ?, ?, ?, '{}', ?, ?, NULL)
            """,
            (
                attempt_id,
                session["account"]["id"],
                exam_id,
                exam_title,
                now,
                now,
                now,
                content_version,
                json.dumps(exam_snapshot, ensure_ascii=False),
                now,
                expires_at or None,
            ),
        )
        attempt = conn.execute(
            "SELECT * FROM attempts WHERE id = ?", (attempt_id,)
        ).fetchone()
    return {"attempt": serialize_attempt(attempt)}


def load_owned_attempt(
    conn: sqlite3.Connection, attempt_id: str, session: dict[str, Any]
) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM attempts WHERE id = ? AND account_id = ?",
        (attempt_id, session["account"]["id"]),
    ).fetchone()
    if row is None:
        raise ApiError(HTTPStatus.NOT_FOUND, "attempt_not_found", "Attempt not found.")
    return row


def save_attempt_answer(
    attempt_id: str, payload: dict[str, Any], session: dict[str, Any]
) -> dict[str, Any]:
    skill = str(payload.get("skill", "")).strip()
    task_key = str(payload.get("task_key") or payload.get("task") or "").strip()
    if not skill or not task_key:
        raise ApiError(
            HTTPStatus.BAD_REQUEST,
            "invalid_request",
            "skill and task_key are required.",
        )
    try:
        item_index = int(payload.get("item_index", payload.get("item", 1))) - 1
    except (TypeError, ValueError) as error:
        raise ApiError(
            HTTPStatus.BAD_REQUEST, "invalid_request", "item_index must be an integer."
        ) from error
    if item_index < 0:
        raise ApiError(
            HTTPStatus.BAD_REQUEST, "invalid_request", "item_index must be at least 1."
        )
    answer_value = payload.get("answer", payload.get("value", ""))
    now = now_iso()
    with db_connection() as conn:
        attempt = load_owned_attempt(conn, attempt_id, session)
        if attempt["status"] not in MUTABLE_ATTEMPT_STATUSES:
            raise ApiError(
                HTTPStatus.CONFLICT,
                "invalid_attempt_transition",
                f"Cannot save answers when attempt status is {attempt['status']}.",
            )
        answers = parse_json_object(attempt["answer_payload"])
        skill_answers = answers.setdefault(skill, {})
        task_answers = skill_answers.setdefault(task_key, [])
        while len(task_answers) <= item_index:
            task_answers.append("")
        task_answers[item_index] = answer_value
        answer_id = f"answer_{hashlib.sha256(f'{attempt_id}:{skill}:{task_key}:{item_index}'.encode('utf-8')).hexdigest()[:24]}"
        conn.execute(
            """
            INSERT INTO attempt_answers (id, attempt_id, account_id, skill, task_key, item_index, answer_payload, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(attempt_id, skill, task_key, item_index) DO UPDATE SET
                answer_payload = excluded.answer_payload,
                updated_at = excluded.updated_at
            """,
            (
                answer_id,
                attempt_id,
                session["account"]["id"],
                skill,
                task_key,
                item_index,
                json.dumps({"answer": answer_value}, ensure_ascii=False),
                now,
                now,
            ),
        )
        conn.execute(
            "UPDATE attempts SET status = 'in_progress', answer_payload = ?, updated_at = ? WHERE id = ?",
            (json.dumps(answers, ensure_ascii=False), now, attempt_id),
        )
        updated = conn.execute(
            "SELECT * FROM attempts WHERE id = ?", (attempt_id,)
        ).fetchone()
    return {"attempt": serialize_attempt(updated)}


def submit_attempt(attempt_id: str, session: dict[str, Any]) -> dict[str, Any]:
    now = now_iso()
    with db_connection() as conn:
        attempt = load_owned_attempt(conn, attempt_id, session)
        if attempt["status"] not in MUTABLE_ATTEMPT_STATUSES:
            if attempt["status"] in {"submitted", "scored"}:
                score_payload = parse_json_object(attempt["score_payload"])
                existing_score = (
                    score_payload.get("scoring")
                    or score_payload.get("evaluation", {}).get("scoring")
                    or score_payload
                )
                return {
                    "attempt": serialize_attempt(attempt),
                    "score": existing_score,
                    "idempotent": True,
                }
            raise ApiError(
                HTTPStatus.CONFLICT,
                "invalid_attempt_transition",
                f"Cannot submit attempt when status is {attempt['status']}.",
            )
        check_scoring_rate_limit(session["account"]["id"])
        snapshot = parse_json_object(attempt["exam_snapshot_payload"])
        answer_key = parse_json_object(snapshot.get("answer_key"))
        answers = parse_json_object(attempt["answer_payload"])
        scoring = compute_objective_score(answer_key, answers)
        score_total = int(scoring["objective_correct"])
        score_id = f"score_{secrets.token_hex(8)}"
        conn.execute(
            """
            INSERT INTO attempt_scores (id, attempt_id, account_id, scoring_version, score_total, score_payload, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                score_id,
                attempt_id,
                session["account"]["id"],
                scoring["scoring_version"],
                score_total,
                json.dumps(scoring, ensure_ascii=False),
                now,
            ),
        )
        # Insert category scores
        by_skill = scoring.get("by_skill", {})
        for skill in ("listening", "reading", "writing", "speaking"):
            skill_data = by_skill.get(skill, {})
            objective_correct = int(skill_data.get("objective_correct", 0))
            passed_boolean = objective_correct >= 9
            category_score_id = f"category_score_{secrets.token_hex(8)}"
            conn.execute(
                """
                INSERT INTO exam_attempt_category_score 
                (id, attempt_id, account_id, category, score_0_to_15, passed_boolean, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    category_score_id,
                    attempt_id,
                    session["account"]["id"],
                    skill,
                    objective_correct,
                    passed_boolean,
                    now,
                ),
            )
        conn.execute(
            """
            UPDATE attempts
            SET status = 'scored',
                submitted_at = ?,
                scored_at = ?,
                score_total = ?,
                score_payload = ?,
                submission_payload = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                now,
                now,
                score_total,
                json.dumps({"scoring": scoring}, ensure_ascii=False),
                json.dumps(
                    {"answers": answers, "scoring": scoring}, ensure_ascii=False
                ),
                now,
                attempt_id,
            ),
        )
        updated = conn.execute(
            "SELECT * FROM attempts WHERE id = ?", (attempt_id,)
        ).fetchone()
    return {"attempt": serialize_attempt(updated), "score": scoring}


def expire_attempt(attempt_id: str, session: dict[str, Any]) -> dict[str, Any]:
    now = now_iso()
    with db_connection() as conn:
        attempt = load_owned_attempt(conn, attempt_id, session)
        if attempt["status"] in {"submitted", "scored"}:
            raise ApiError(
                HTTPStatus.CONFLICT,
                "invalid_attempt_transition",
                f"Cannot expire attempt when status is {attempt['status']}.",
            )
        conn.execute(
            "UPDATE attempts SET status = 'expired', updated_at = ? WHERE id = ?",
            (now, attempt_id),
        )
        updated = conn.execute(
            "SELECT * FROM attempts WHERE id = ?", (attempt_id,)
        ).fetchone()
    return {"attempt": serialize_attempt(updated)}


def update_profile(payload: dict[str, Any], session: dict[str, Any]) -> dict[str, Any]:
    full_name = str(payload.get("full_name", "")).strip()
    native_language = str(payload.get("native_language", "")).strip() or None
    exam_target_date = str(payload.get("exam_target_date", "")).strip() or None
    exam_pack_status = str(payload.get("exam_pack_status", "")).strip() or None
    with db_connection() as conn:
        profile = conn.execute(
            "SELECT * FROM profiles WHERE account_id = ?", (session["account"]["id"],)
        ).fetchone()
        if profile is None:
            raise ValueError("Profile not found.")
        next_full_name = full_name or profile["full_name"]
        next_native_language = (
            native_language
            if native_language is not None
            else profile["native_language"]
        )
        next_exam_target_date = (
            exam_target_date
            if exam_target_date is not None
            else profile["exam_target_date"]
        )
        next_exam_pack_status = exam_pack_status or profile["exam_pack_status"]
        upsert_profile(
            conn,
            session["account"]["id"],
            next_full_name,
            next_native_language,
            next_exam_target_date,
        )
        conn.execute(
            "UPDATE profiles SET exam_pack_status = ?, updated_at = ? WHERE account_id = ?",
            (next_exam_pack_status, now_iso(), session["account"]["id"]),
        )
        updated = conn.execute(
            "SELECT * FROM profiles WHERE account_id = ?", (session["account"]["id"],)
        ).fetchone()
    return {"profile": serialize_profile(updated)}


def delete_account(session: dict[str, Any]) -> dict[str, Any]:
    with db_connection() as conn:
        conn.execute(
            "UPDATE sessions SET revoked_at = ? WHERE account_id = ?",
            (now_iso(), session["account"]["id"]),
        )
        conn.execute("DELETE FROM accounts WHERE id = ?", (session["account"]["id"],))
    return {"deleted": True}


def export_account(session: dict[str, Any]) -> dict[str, Any]:
    with db_connection() as conn:
        account = conn.execute(
            "SELECT * FROM accounts WHERE id = ?", (session["account"]["id"],)
        ).fetchone()
        profile = conn.execute(
            "SELECT * FROM profiles WHERE account_id = ?", (session["account"]["id"],)
        ).fetchone()
        attempts = conn.execute(
            "SELECT * FROM attempts WHERE account_id = ? ORDER BY submitted_at DESC",
            (session["account"]["id"],),
        ).fetchall()
    return {
        "account": serialize_account(account),
        "profile": serialize_profile(profile),
        "attempts": [serialize_attempt_for_learner(row) for row in attempts],
    }


def account_role(session: dict[str, Any]) -> str:
    return str((session.get("account") or {}).get("role") or "user")


def require_admin_session(handler: SimpleHTTPRequestHandler) -> dict[str, Any]:
    session = require_session(handler)
    if account_role(session) not in {"admin", "superadmin"}:
        raise ApiError(
            HTTPStatus.FORBIDDEN, "admin_required", "Admin access is required."
        )
    return session


def can_manage_account(
    actor: dict[str, Any], target: sqlite3.Row, next_role: str | None = None
) -> bool:
    actor_role = account_role(actor)
    target_role = target["role"] or "user"
    if actor_role == "superadmin":
        return True
    if target_role in {"admin", "superadmin"}:
        return False
    if next_role and next_role != "user":
        return False
    return actor_role == "admin"


def serialize_exam_catalog(
    row: sqlite3.Row, *, include_answer_key: bool = False
) -> dict[str, Any]:
    manifest = parse_json_object(row["manifest_payload"])
    payload = {
        "id": row["id"],
        "title": row["title"],
        "description": manifest.get("description", ""),
        "content_version": row["content_version"],
        "status": row["status"],
        "markdownPath": f"/api/exams/{row['id']}/content",
        "sourcePath": manifest.get("sourcePath")
        or manifest.get("source_path")
        or f"codex/A2_Mock_Exam_{row['id']}.md",
        "attachmentRoot": manifest.get("attachmentRoot")
        or manifest.get("attachment_root")
        or f"/codex/Attachments/A2_Mock_Exam_{row['id']}/",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if include_answer_key:
        payload["answer_key"] = parse_json_object(row["answer_key_payload"])
        payload["manifest"] = manifest
        payload["rawMarkdownPath"] = (
            manifest.get("markdownPath")
            or manifest.get("markdown_path")
            or f"/codex/A2_Mock_Exam_{row['id']}.md"
        )
    return payload


def list_exam_catalog(session: dict[str, Any] | None = None) -> dict[str, Any]:
    admin = bool(session and account_role(session) in {"admin", "superadmin"})
    with db_connection() as conn:
        if admin:
            rows = conn.execute(
                "SELECT * FROM exams ORDER BY updated_at DESC, id"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM exams WHERE status = 'published' ORDER BY id"
            ).fetchall()
    return {
        "exams": [serialize_exam_catalog(row, include_answer_key=admin) for row in rows]
    }


def admin_overview() -> dict[str, Any]:
    with db_connection() as conn:
        return {
            "summary": {
                "accounts": conn.execute(
                    "SELECT COUNT(*) FROM accounts WHERE deleted_at IS NULL"
                ).fetchone()[0],
                "admins": conn.execute(
                    "SELECT COUNT(*) FROM accounts WHERE deleted_at IS NULL AND role IN ('admin', 'superadmin')"
                ).fetchone()[0],
                "exams": conn.execute("SELECT COUNT(*) FROM exams").fetchone()[0],
                "published": conn.execute(
                    "SELECT COUNT(*) FROM exams WHERE status = 'published'"
                ).fetchone()[0],
                "submissions": conn.execute(
                    "SELECT COUNT(*) FROM attempts WHERE status IN ('submitted', 'scored')"
                ).fetchone()[0],
            }
        }


def list_admin_accounts() -> dict[str, Any]:
    with db_connection() as conn:
        rows = conn.execute(
            """
            SELECT a.*, p.full_name, p.native_language, p.exam_target_date, p.exam_pack_status, p.updated_at AS profile_updated_at
            FROM accounts a
            LEFT JOIN profiles p ON p.account_id = a.id
            WHERE a.deleted_at IS NULL
            ORDER BY a.created_at DESC
            """
        ).fetchall()
    accounts = []
    for row in rows:
        accounts.append(
            {
                "account": serialize_account(row),
                "profile": {
                    "account_id": row["id"],
                    "full_name": row["full_name"],
                    "native_language": row["native_language"],
                    "exam_target_date": row["exam_target_date"],
                    "exam_pack_status": row["exam_pack_status"] or "free",
                    "updated_at": row["profile_updated_at"],
                },
            }
        )
    return {"accounts": accounts}


def update_admin_account(
    account_id: str, payload: dict[str, Any], session: dict[str, Any]
) -> dict[str, Any]:
    next_status = str(payload.get("status") or "").strip()
    next_role = str(payload.get("role") or "").strip()
    if next_status not in {"active", "disabled"}:
        raise ApiError(
            HTTPStatus.BAD_REQUEST,
            "invalid_status",
            "Account status must be active or disabled.",
        )
    if next_role not in ACCOUNT_ROLES:
        raise ApiError(
            HTTPStatus.BAD_REQUEST, "invalid_role", "Account role is invalid."
        )
    with db_connection() as conn:
        target = conn.execute(
            "SELECT * FROM accounts WHERE id = ? AND deleted_at IS NULL", (account_id,)
        ).fetchone()
        if target is None:
            raise ApiError(
                HTTPStatus.NOT_FOUND, "account_not_found", "Account not found."
            )
        if account_id == session["account"]["id"] and (
            next_status != "active" or next_role != account_role(session)
        ):
            raise ApiError(
                HTTPStatus.FORBIDDEN,
                "self_lockout_blocked",
                "You cannot remove your own active admin access.",
            )
        if not can_manage_account(session, target, next_role):
            raise ApiError(
                HTTPStatus.FORBIDDEN,
                "superadmin_required",
                "Only superadmins can manage admin accounts.",
            )
        conn.execute(
            "UPDATE accounts SET status = ?, role = ? WHERE id = ?",
            (next_status, next_role, account_id),
        )
        if next_status != "active":
            conn.execute(
                "UPDATE sessions SET revoked_at = ? WHERE account_id = ?",
                (now_iso(), account_id),
            )
        updated = conn.execute(
            "SELECT * FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()
    return {"account": serialize_account(updated)}


def save_admin_exam(
    payload: dict[str, Any], session: dict[str, Any], exam_id: str | None = None
) -> dict[str, Any]:
    title = str(payload.get("title") or "").strip()
    if not title:
        raise ApiError(
            HTTPStatus.BAD_REQUEST, "invalid_exam", "Exam title is required."
        )
    status = str(payload.get("status") or "draft").strip()
    if status not in {"draft", "published", "archived"}:
        raise ApiError(
            HTTPStatus.BAD_REQUEST, "invalid_exam_status", "Exam status is invalid."
        )
    description = str(payload.get("description") or "").strip()
    markdown_path = str(
        payload.get("markdownPath") or payload.get("markdown_path") or ""
    ).strip()
    source_path = str(
        payload.get("sourcePath") or payload.get("source_path") or ""
    ).strip()
    attachment_root = str(
        payload.get("attachmentRoot") or payload.get("attachment_root") or ""
    ).strip()
    if not exam_id:
        requested_id = (
            re.sub(r"[^a-zA-Z0-9_-]+", "-", str(payload.get("id") or title).strip())
            .strip("-")
            .lower()
        )
        exam_id = requested_id[:48] or f"exam_{secrets.token_hex(6)}"
    if not markdown_path:
        markdown_path = f"/codex/A2_Mock_Exam_{exam_id}.md"
    if not source_path:
        source_path = markdown_path.removeprefix("/")
    if not attachment_root:
        attachment_root = f"/codex/Attachments/A2_Mock_Exam_{exam_id}/"
    manifest = {
        "description": description,
        "markdownPath": markdown_path,
        "sourcePath": source_path,
        "attachmentRoot": attachment_root,
        "createdBy": session["account"]["id"],
    }
    answer_key = payload.get("answer_key")
    answer_key_payload = json.dumps(
        answer_key if isinstance(answer_key, dict) else {}, ensure_ascii=False
    )
    now = now_iso()
    with db_connection() as conn:
        existing = conn.execute(
            "SELECT * FROM exams WHERE id = ?", (exam_id,)
        ).fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO exams (id, title, content_version, status, manifest_payload, answer_key_payload, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    exam_id,
                    title,
                    int(payload.get("content_version") or 1),
                    status,
                    json.dumps(manifest, ensure_ascii=False),
                    answer_key_payload,
                    now,
                    now,
                ),
            )
        else:
            current_manifest = parse_json_object(existing["manifest_payload"])
            current_manifest.update(manifest)
            next_answer_key = (
                answer_key_payload
                if isinstance(answer_key, dict)
                else existing["answer_key_payload"]
            )
            conn.execute(
                """
                UPDATE exams
                SET title = ?, content_version = ?, status = ?, manifest_payload = ?, answer_key_payload = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    title,
                    int(
                        payload.get("content_version")
                        or existing["content_version"]
                        or 1
                    ),
                    status,
                    json.dumps(current_manifest, ensure_ascii=False),
                    next_answer_key,
                    now,
                    exam_id,
                ),
            )
        row = conn.execute("SELECT * FROM exams WHERE id = ?", (exam_id,)).fetchone()
    return {"exam": serialize_exam_catalog(row, include_answer_key=True)}


def update_admin_exam_status(exam_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    status = str(payload.get("status") or "").strip()
    if status not in {"draft", "published", "archived"}:
        raise ApiError(
            HTTPStatus.BAD_REQUEST, "invalid_exam_status", "Exam status is invalid."
        )
    with db_connection() as conn:
        conn.execute(
            "UPDATE exams SET status = ?, updated_at = ? WHERE id = ?",
            (status, now_iso(), exam_id),
        )
        row = conn.execute("SELECT * FROM exams WHERE id = ?", (exam_id,)).fetchone()
    if row is None:
        raise ApiError(HTTPStatus.NOT_FOUND, "exam_not_found", "Exam not found.")
    return {"exam": serialize_exam_catalog(row, include_answer_key=True)}


def delete_admin_exam(exam_id: str) -> dict[str, Any]:
    with db_connection() as conn:
        conn.execute("DELETE FROM exams WHERE id = ?", (exam_id,))
    return {"deleted": True}


def list_admin_attempts() -> dict[str, Any]:
    with db_connection() as conn:
        rows = conn.execute(
            """
            SELECT at.*, a.email
            FROM attempts at
            JOIN accounts a ON a.id = at.account_id
            ORDER BY at.submitted_at DESC
            LIMIT 200
            """
        ).fetchall()
    return {
        "attempts": [
            {**serialize_attempt(row), "account_email": row["email"]} for row in rows
        ]
    }


def list_admin_settings() -> dict[str, Any]:
    with db_connection() as conn:
        rows = conn.execute("SELECT * FROM app_settings ORDER BY key").fetchall()
    return {"settings": {row["key"]: row["value"] for row in rows}}


def save_admin_settings(payload: dict[str, Any]) -> dict[str, Any]:
    settings = payload.get("settings")
    if not isinstance(settings, dict):
        raise ApiError(
            HTTPStatus.BAD_REQUEST, "invalid_settings", "settings must be an object."
        )
    with db_connection() as conn:
        for key, value in settings.items():
            clean_key = str(key).strip()
            if not re.fullmatch(r"[a-z0-9_]{2,50}", clean_key):
                raise ApiError(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_setting_key",
                    "Setting keys must be lowercase snake_case.",
                )
            conn.execute(
                """
                INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (clean_key, str(value), now_iso()),
            )
    return list_admin_settings()


def verify_auth_webhook(handler: SimpleHTTPRequestHandler, body: bytes) -> None:
    if not AUTH_WEBHOOK_SECRET:
        raise PermissionError("Auth webhook secret is not configured.")
    expected = handler.headers.get("X-Auth-Signature", "").strip()
    if not expected:
        raise PermissionError("Missing webhook signature.")
    actual = hmac.new(
        AUTH_WEBHOOK_SECRET.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, actual):
        raise PermissionError("Invalid webhook signature.")


def handle_auth_webhook(handler: SimpleHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length <= 0:
        raise ValueError("Request body is empty.")
    if length > MAX_BODY_BYTES:
        raise ValueError("Request body is too large.")
    body = handler.rfile.read(length)
    verify_auth_webhook(handler, body)
    payload = json.loads(body.decode("utf-8"))
    event_id = str(payload.get("event_id") or payload.get("id") or "").strip()
    event_type = str(payload.get("event_type") or payload.get("type") or "").strip()
    if not event_id or not event_type:
        raise ValueError("Webhook payload must include event_id and event_type.")
    with db_connection() as conn:
        existing = conn.execute(
            "SELECT event_id FROM auth_webhook_events WHERE event_id = ?", (event_id,)
        ).fetchone()
        if existing is not None:
            return {"status": "duplicate", "event_id": event_id}
        conn.execute(
            "INSERT INTO auth_webhook_events (event_id, event_type, payload, created_at) VALUES (?, ?, ?, ?)",
            (event_id, event_type, json.dumps(payload, ensure_ascii=False), now_iso()),
        )
        account_email = normalize_email(str(payload.get("email", ""))) or None
        account_name = str(payload.get("full_name", "")).strip() or None
        if (
            event_type in {"account.created", "account.updated", "profile.updated"}
            and account_email
        ):
            account = conn.execute(
                "SELECT id FROM accounts WHERE email = ?", (account_email,)
            ).fetchone()
            if account is None:
                account_id = f"acct_{secrets.token_hex(8)}"
                salt_b64, hash_b64 = hash_password(
                    str(payload.get("password", "temporary-webhook-password"))
                )
                conn.execute(
                    """
                    INSERT INTO accounts (id, email, password_salt, password_hash, status, created_at, deleted_at, role)
                    VALUES (?, ?, ?, ?, 'active', ?, NULL, 'user')
                    """,
                    (account_id, account_email, salt_b64, hash_b64, now_iso()),
                )
            else:
                account_id = account["id"]
            if account_name:
                upsert_profile(
                    conn,
                    account_id,
                    account_name,
                    str(payload.get("native_language", "")).strip() or None,
                    str(payload.get("exam_target_date", "")).strip() or None,
                )
        if event_type == "account.deleted" and account_email:
            account = conn.execute(
                "SELECT id FROM accounts WHERE email = ?", (account_email,)
            ).fetchone()
            if account is not None:
                conn.execute(
                    "UPDATE sessions SET revoked_at = ? WHERE account_id = ?",
                    (now_iso(), account["id"]),
                )
                conn.execute("DELETE FROM accounts WHERE id = ?", (account["id"],))
    return {"status": "ok", "event_id": event_id}


def submission_cache_key(
    submission: dict[str, Any], exam_context: str, provider: str, model: str
) -> str:
    payload = json.dumps(
        {
            "submission": submission,
            "exam_context": exam_context,
            "provider": provider,
            "model": model,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compact_exam_context(markdown: str) -> str:
    lines = markdown.splitlines()
    kept: list[str] = []
    skip_headings = {
        "## Answer Key",
        "## Listening Transcripts",
        "## Writing Model Answers",
        "## Speaking Teacher Notes",
        "## JSON Export",
        "## TTS Export",
        "## Image Generation Prompts",
        "## TTS Scripts",
    }
    skipping = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            skipping = stripped in skip_headings
        if not skipping:
            kept.append(line)
    return "\n".join(kept).strip()


def student_exam_markdown(markdown: str) -> str:
    lines = markdown.splitlines()
    kept: list[str] = []
    private_section = False
    private_headings = {
        "## Answer Key",
        "## Listening Transcripts",
        "## Writing Model Answers",
        "## Speaking Teacher Notes",
        "## Teacher Version",
        "## Teacher Key",
        "## JSON Export",
        "## TTS Export",
        "## Image Generation Prompts",
        "## TTS Scripts",
    }
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            private_section = stripped in private_headings
        if not private_section:
            kept.append(line)
    return "\n".join(kept).strip() + "\n"


def parse_answer_values(value: str) -> list[str]:
    matches = re.findall(r"(\d+)\.\s*([^,;\n]+)", value)
    return [
        re.sub(r"\s{2,}", " ", match[1]).strip().removesuffix(".") for match in matches
    ]


def skill_key_from_heading(value: str) -> str:
    normalized = value.lower()
    if "klaus" in normalized:
        return "listening"
    if "las" in normalized:
        return "reading"
    if "rakst" in normalized:
        return "writing"
    if "run" in normalized:
        return "speaking"
    return ""


def extract_answer_key_from_markdown(markdown: str) -> dict[str, Any]:
    lines = markdown.splitlines()
    answer_lines: list[str] = []
    in_answer_key = False
    for line in lines:
        stripped = line.strip()
        if stripped == "## Answer Key":
            in_answer_key = True
            continue
        if in_answer_key and stripped.startswith("## "):
            break
        if in_answer_key:
            answer_lines.append(line)

    key: dict[str, Any] = {}
    current_skill = ""
    for line in answer_lines:
        stripped = line.strip()
        heading = re.match(r"^###\s+(.+)$", stripped)
        if heading:
            current_skill = skill_key_from_heading(heading.group(1))
            if current_skill:
                key.setdefault(current_skill, {})
            continue
        clean_line = stripped.replace("**", "")
        task_line = re.match(
            r"^(\d+)\.?\s*uzdevums:?\s*(.+)$", clean_line, flags=re.IGNORECASE
        )
        if task_line and current_skill:
            key[current_skill][f"task{task_line.group(1)}"] = parse_answer_values(
                task_line.group(2)
            )
    return key


def exam_catalog_id(exam_id: str) -> str:
    raw = str(exam_id or "").strip()
    match = re.fullmatch(r"a2_mock_exam_(\d+)", raw)
    if match:
        return match.group(1).zfill(2)
    return raw.zfill(2) if raw.isdigit() and len(raw) < 2 else raw


def load_exam_catalog_row(
    conn: sqlite3.Connection, exam_id: str, *, published_only: bool = True
) -> sqlite3.Row | None:
    catalog_id = exam_catalog_id(exam_id)
    if published_only:
        return conn.execute(
            "SELECT * FROM exams WHERE id = ? AND status = 'published'", (catalog_id,)
        ).fetchone()
    return conn.execute("SELECT * FROM exams WHERE id = ?", (catalog_id,)).fetchone()


def exam_markdown_path_from_manifest(manifest: dict[str, Any], exam_id: str) -> Path:
    configured = str(
        manifest.get("sourcePath") or manifest.get("source_path") or ""
    ).strip()
    if not configured:
        markdown_path = (
            str(manifest.get("markdownPath") or manifest.get("markdown_path") or "")
            .strip()
            .lstrip("/")
        )
        configured = (
            markdown_path or f"codex/A2_Mock_Exam_{exam_catalog_id(exam_id)}.md"
        )
    candidate = (ROOT / configured).resolve()
    if not candidate.is_file() or ROOT not in candidate.parents:
        raise ApiError(
            HTTPStatus.NOT_FOUND,
            "exam_content_not_found",
            "Exam content was not found.",
        )
    return candidate


def load_exam_markdown(exam_id: str) -> str:
    with db_connection() as conn:
        row = load_exam_catalog_row(conn, exam_id)
        if row is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "exam_not_found", "Exam not found.")
        manifest = parse_json_object(row["manifest_payload"])
        path = exam_markdown_path_from_manifest(manifest, row["id"])
    return path.read_text(encoding="utf-8")


def load_server_answer_key(
    exam_id: str, fallback: dict[str, Any] | None = None
) -> dict[str, Any]:
    with db_connection() as conn:
        row = load_exam_catalog_row(conn, exam_id, published_only=False)
        if row is not None:
            stored = parse_json_object(row["answer_key_payload"])
            if stored:
                return stored
            manifest = parse_json_object(row["manifest_payload"])
            try:
                markdown = exam_markdown_path_from_manifest(
                    manifest, row["id"]
                ).read_text(encoding="utf-8")
            except ApiError:
                markdown = ""
            extracted = extract_answer_key_from_markdown(markdown) if markdown else {}
            if extracted:
                conn.execute(
                    "UPDATE exams SET answer_key_payload = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(extracted, ensure_ascii=False), now_iso(), row["id"]),
                )
                return extracted
    return fallback or {}


def compact_submission(submission: dict[str, Any]) -> dict[str, Any]:
    scoring = submission.get("scoring", {})
    compact_scoring = {
        "objective_correct": scoring.get("objective_correct"),
        "objective_possible": scoring.get("objective_possible"),
        "manual_review_possible": scoring.get("manual_review_possible"),
        "by_skill": scoring.get("by_skill", {}),
        "items": scoring.get("items", []),
    }
    return {
        "submission_id": submission.get("submission_id"),
        "candidate": submission.get("candidate", {}),
        "candidate_code": submission.get("candidate_code"),
        "learner_id": submission.get("learner_id"),
        "learner_email": submission.get("learner_email"),
        "plan": submission.get("plan"),
        "access_plan": submission.get("access_plan"),
        "user_id": submission.get("user_id"),
        "exam_id": submission.get("exam_id"),
        "exam_title": submission.get("exam_title"),
        "level": submission.get("level", "A2"),
        "language": submission.get("language", "lv"),
        "pass_rule": submission.get("pass_rule", {}),
        "progress": submission.get("progress", {}),
        "answers": submission.get("answers", {}),
        "scoring": compact_scoring,
        "validation_queue": submission.get("validation_queue", []),
    }


def ai_scoring_submission(submission: dict[str, Any]) -> dict[str, Any]:
    scoring = submission.get("scoring", {})
    by_skill = scoring.get("by_skill", {}) if isinstance(scoring, dict) else {}
    answers = submission.get("answers", {}) if isinstance(submission, dict) else {}
    validation_queue = (
        submission.get("validation_queue", []) if isinstance(submission, dict) else []
    )
    if not isinstance(validation_queue, list):
        validation_queue = []

    free_text_answers: dict[str, Any] = {}
    free_text_scores: dict[str, Any] = {}
    for skill in FREE_TEXT_SKILLS:
        if isinstance(answers, dict) and isinstance(answers.get(skill), dict):
            free_text_answers[skill] = answers[skill]
        skill_summary = by_skill.get(skill, {}) if isinstance(by_skill, dict) else {}
        if not isinstance(skill_summary, dict):
            skill_summary = {}
        free_text_scores[skill] = {
            "objective_correct": skill_summary.get("objective_correct", 0),
            "objective_possible": skill_summary.get("objective_possible", 0),
            "manual_review_possible": skill_summary.get("manual_review_possible", 0),
        }

    filtered_validation_queue = [
        item
        for item in validation_queue
        if isinstance(item, dict) and item.get("skill") in FREE_TEXT_SKILLS
    ]

    return {
        "submission_id": submission.get("submission_id"),
        "candidate": submission.get("candidate", {}),
        "learner_id": submission.get("learner_id"),
        "learner_email": submission.get("learner_email"),
        "plan": submission.get("plan", DEFAULT_PLAN),
        "exam_id": submission.get("exam_id"),
        "exam_title": submission.get("exam_title"),
        "level": submission.get("level", "A2"),
        "language": submission.get("language", "lv"),
        "pass_rule": submission.get("pass_rule", {}),
        "progress": submission.get("progress", {}),
        "answers": free_text_answers,
        "scoring": {
            "objective_correct": scoring.get("objective_correct", 0)
            if isinstance(scoring, dict)
            else 0,
            "objective_possible": scoring.get("objective_possible", 0)
            if isinstance(scoring, dict)
            else 0,
            "manual_review_possible": scoring.get("manual_review_possible", 0)
            if isinstance(scoring, dict)
            else 0,
            "by_skill": free_text_scores,
            "items": [
                {
                    key: item.get(key)
                    for key in ("skill", "task", "item", "actual", "correct", "scoring")
                }
                for item in scoring.get("items", [])
                if isinstance(item, dict) and item.get("skill") in FREE_TEXT_SKILLS
            ]
            if isinstance(scoring, dict)
            else [],
        },
        "validation_queue": filtered_validation_queue,
        "locked_scores": locked_local_scores(submission),
    }


def scoring_input_hash(
    provider: str, model: str, submission: dict[str, Any], exam_context: str
) -> str:
    payload = json.dumps(
        {
            "prompt_version": SCORING_PROMPT_VERSION,
            "rubric_version": SCORING_RUBRIC_VERSION,
            "provider": provider,
            "model": model,
            "submission": submission,
            "exam_context": exam_context,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def ai_scoring_requires_credit() -> bool:
    explicit = os.getenv("AI_SCORING_REQUIRE_AI_CREDIT", "").strip()
    if explicit:
        return env_flag("AI_SCORING_REQUIRE_AI_CREDIT")
    return bool(os.getenv("STRIPE_SECRET_KEY", "").strip())


def provider_config() -> dict[str, Any]:
    provider = os.getenv("LLM_PROVIDER", "groq").strip().lower()

    if provider == "groq":
        api_key = os.getenv("GROQ_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY is missing. Add it to .env or the container environment."
            )

        return {
            "provider": provider,
            "api_key": api_key,
            "model": os.getenv(
                "LLM_MODEL", os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL)
            ).strip()
            or DEFAULT_GROQ_MODEL,
            "base_url": os.getenv(
                "GROQ_BASE_URL", "https://api.groq.com/openai/v1"
            ).rstrip("/"),
        }

    if provider == "codex":
        remote_url = os.getenv("CODEX_REMOTE_URL", "").strip().rstrip("/")
        if remote_url:
            timeout_raw = os.getenv(
                "CODEX_TIMEOUT_SECONDS", str(CODEX_TIMEOUT_SECONDS)
            ).strip()
            try:
                timeout_seconds = int(timeout_raw)
            except ValueError as error:
                raise RuntimeError(
                    "CODEX_TIMEOUT_SECONDS must be an integer."
                ) from error

            return {
                "provider": provider,
                "mode": "remote",
                "remote_url": remote_url,
                "model": os.getenv("CODEX_MODEL", DEFAULT_CODEX_MODEL).strip()
                or DEFAULT_CODEX_MODEL,
                "timeout_seconds": timeout_seconds,
            }

        cli_name = os.getenv("CODEX_CLI_PATH", "codex").strip() or "codex"
        cli_path = shutil.which(cli_name)
        if not cli_path:
            raise RuntimeError(
                "Codex CLI executable was not found. Install Codex CLI, set CODEX_CLI_PATH, "
                "or set CODEX_REMOTE_URL to a host-local Codex scoring server."
            )

        timeout_raw = os.getenv(
            "CODEX_TIMEOUT_SECONDS", str(CODEX_TIMEOUT_SECONDS)
        ).strip()
        try:
            timeout_seconds = int(timeout_raw)
        except ValueError as error:
            raise RuntimeError("CODEX_TIMEOUT_SECONDS must be an integer.") from error

        oss = env_flag("CODEX_OSS")
        model = os.getenv("CODEX_MODEL", "").strip()
        if not model and not oss:
            model = DEFAULT_CODEX_MODEL
        return {
            "provider": provider,
            "mode": "local",
            "cli_path": cli_path,
            "model": model or CODEX_OSS_DEFAULT_MODEL_LABEL,
            "model_arg": model,
            "profile": os.getenv("CODEX_PROFILE", "").strip(),
            "oss": oss,
            "local_provider": os.getenv("CODEX_LOCAL_PROVIDER", "").strip(),
            "timeout_seconds": timeout_seconds,
        }

    raise RuntimeError(
        "Unsupported LLM_PROVIDER. Set LLM_PROVIDER=groq or LLM_PROVIDER=codex."
    )


def build_evaluation_prompt(submission: dict[str, Any], exam_context: str) -> str:
    compact_submission = json.dumps(submission, ensure_ascii=False, indent=2)
    return f"""
You are a strict but helpful evaluator for the Latvian state language proficiency exam, A2 level.

Prompt version: {SCORING_PROMPT_VERSION}
Rubric version: {SCORING_RUBRIC_VERSION}

Evaluate the candidate submission using the official-style pass rule:
- Total maximum: 60 points.
- Each skill maximum: 15 points.
- Passing requires at least 9/15 in every skill.

Use the exam Markdown, answer key, writing model answers, and speaking teacher notes as context.
AI scoring applies only to writing and speaking free text.
Listening and reading are locked to the local deterministic estimate already included in the submission; do not change those scores.
Keep Latvian difficulty expectations at A2. Be generous with small spelling mistakes if the meaning is clear.
Objective answers already have a local pre-score; verify them but do not invent hidden answers.
For writing and speaking free text, score communicative success, task completion, vocabulary, grammar, and clarity.
Use the deterministic rubric:
- Writing: task completion, message clarity, vocabulary range, grammar control, and whether the response is understandable without guesswork.
- Speaking: task completion, fluency, pronunciation cues if described, vocabulary range, grammar control, and whether the response answers the prompt directly.

Return valid JSON only. Use this exact shape:
{{
  "status": "evaluated",
  "scores": {{
    "listening": {{"points": 0, "max_points": 15, "passed": false, "reason": ""}},
    "reading": {{"points": 0, "max_points": 15, "passed": false, "reason": ""}},
    "writing": {{"points": 0, "max_points": 15, "passed": false, "reason": ""}},
    "speaking": {{"points": 0, "max_points": 15, "passed": false, "reason": ""}},
    "total": 0,
    "passed": false
  }},
  "corrections": [
    {{"skill": "", "task": "", "item": 1, "candidate_answer": "", "suggested_answer": "", "comment": ""}}
  ],
  "feedback": {{
    "summary": "",
    "strengths": [],
    "improvements": [],
    "next_practice": []
  }}
}}

Exam Context:
```markdown
{exam_context}
```

Candidate submission:
```json
{compact_submission}
```
""".strip()


def call_groq(
    config: dict[str, Any], submission_context: dict[str, Any], exam_context: str
) -> dict[str, Any]:
    payload = {
        "model": config["model"],
        "messages": [
            {
                "role": "system",
                "content": "You grade Latvian A2 exam submissions. Return only valid JSON.",
            },
            {
                "role": "user",
                "content": build_evaluation_prompt(submission_context, exam_context),
            },
        ],
        "temperature": 0.2,
        "top_p": 1,
        "max_completion_tokens": 4096,
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        f"{config['base_url']}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
            "User-Agent": "lvcodex-a2-evaluator/1.0",
        },
        method="POST",
    )

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                result = json.loads(response.read().decode("utf-8"))
            content = result["choices"][0]["message"]["content"]
            evaluation = extract_json_object(content)
            return {
                "provider": config["provider"],
                "model": config["model"],
                "evaluation": evaluation,
                "usage": result.get("usage", {}),
            }
        except urllib.error.HTTPError as error:
            last_error = error
            if error.code not in {429, 500, 502, 503, 504} or attempt == 2:
                raise
            retry_after = error.headers.get("Retry-After")
            delay = 2**attempt
            if retry_after:
                try:
                    delay = max(delay, int(float(retry_after)))
                except ValueError:
                    pass
            time.sleep(delay)

    assert last_error is not None
    raise last_error


def call_codex(
    config: dict[str, Any], submission_context: dict[str, Any], exam_context: str
) -> dict[str, Any]:
    prompt = "\n\n".join(
        [
            "Return exactly one JSON object and no Markdown fences.",
            "Do not inspect or modify local files; all evaluation context is included below.",
            build_evaluation_prompt(submission_context, exam_context),
        ]
    )

    with tempfile.TemporaryDirectory(prefix="lvcodex-eval-") as tmp_dir:
        output_path = Path(tmp_dir) / "codex-evaluation.json"
        command = [
            config["cli_path"],
            "exec",
            "--skip-git-repo-check",
            "--ephemeral",
            "--sandbox",
            "read-only",
            "--cd",
            tmp_dir,
            "--output-last-message",
            str(output_path),
        ]
        if config.get("profile"):
            command.extend(["--profile", config["profile"]])
        if config.get("model_arg"):
            command.extend(["--model", config["model_arg"]])
        if config.get("oss"):
            command.append("--oss")
        if config.get("local_provider"):
            command.extend(["--local-provider", config["local_provider"]])
        command.append("-")

        try:
            completed = subprocess.run(
                command,
                input=prompt,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=tmp_dir,
                timeout=config["timeout_seconds"],
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(
                f"Codex CLI scoring timed out after {config['timeout_seconds']} seconds."
            ) from error
        output = (
            output_path.read_text(encoding="utf-8")
            if output_path.exists()
            else completed.stdout
        )
        if completed.returncode != 0:
            detail = (
                completed.stderr or completed.stdout or "No Codex CLI error output."
            ).strip()
            raise RuntimeError(
                f"Codex CLI scoring failed with exit {completed.returncode}: {detail[:2000]}"
            )

    return {
        "provider": config["provider"],
        "model": config["model"],
        "evaluation": extract_json_object(output),
        "usage": {},
    }


def call_codex_remote(
    config: dict[str, Any], submission_context: dict[str, Any], exam_context: str
) -> dict[str, Any]:
    payload = {
        "submission": submission_context,
        "exam_markdown": exam_context,
    }
    request = urllib.request.Request(
        config["remote_url"],
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "lvcodex-a2-evaluator/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=config["timeout_seconds"]) as response:
        result = json.loads(response.read().decode("utf-8"))

    result["provider"] = "codex"
    result["mode"] = "remote"
    return result


def provider_call_once(
    config: dict[str, Any], submission_context: dict[str, Any], exam_context: str
) -> dict[str, Any]:
    if config["provider"] == "groq":
        return call_groq(config, submission_context, exam_context)
    if config["provider"] == "codex" and config.get("mode") == "remote":
        return call_codex_remote(config, submission_context, exam_context)
    if config["provider"] == "codex":
        return call_codex(config, submission_context, exam_context)
    raise RuntimeError("Unsupported LLM provider.")


def evaluate_submission(
    submission: dict[str, Any], exam_markdown: str
) -> dict[str, Any]:
    config = provider_config()
    exam_context = compact_exam_context(exam_markdown)
    submission_context = compact_submission(submission)
    ai_submission_context = ai_scoring_submission(submission_context)
    validate_submission_size(ai_submission_context)
    input_hash = scoring_input_hash(
        config["provider"], config["model"], ai_submission_context, exam_context
    )
    cache_key = submission_cache_key(
        ai_submission_context, exam_context, config["provider"], config["model"]
    )
    with EVALUATION_CACHE_LOCK:
        cached = EVALUATION_CACHE.get(cache_key)
    if cached:
        return cached

    identity = identity_from_submission(submission_context)
    estimated_cost_cents = estimate_request_cost_cents(
        config["provider"], ai_submission_context, exam_context
    )
    quota_snapshot = reserve_quota(identity, estimated_cost_cents)

    attempt_limit = retry_limit()
    attempt_history: list[dict[str, Any]] = []
    last_error: Exception | None = None
    last_status_code = HTTPStatus.BAD_GATEWAY
    for attempt in range(1, attempt_limit + 1):
        started = time.perf_counter()
        try:
            raw_result = provider_call_once(config, ai_submission_context, exam_context)
            normalized_evaluation = validate_and_normalize_evaluation_payload(
                raw_result.get("evaluation")
            )
            merged_evaluation = merge_local_and_ai_scores(
                normalized_evaluation, submission_context
            )
            result_payload = {
                "status": "evaluated",
                "provider": raw_result.get("provider", config["provider"]),
                "model": raw_result.get("model", config["model"]),
                "provider_status": "ok",
                "prompt_version": SCORING_PROMPT_VERSION,
                "rubric_version": SCORING_RUBRIC_VERSION,
                "input_hash": input_hash,
                "evaluation": merged_evaluation,
                "usage": raw_result.get("usage", {}),
                "telemetry": {
                    "identity": identity,
                    "plan": identity["plan"],
                    "provider_status": "ok",
                    "prompt_version": SCORING_PROMPT_VERSION,
                    "rubric_version": SCORING_RUBRIC_VERSION,
                    "input_hash": input_hash,
                    "quota": {
                        "key": quota_snapshot["quota_key"],
                        "request_limit": quota_snapshot["request_limit"],
                        "cost_limit_cents": quota_snapshot["cost_limit_cents"],
                        "usage": quota_snapshot["usage"],
                    },
                    "request_bytes": len(
                        json.dumps(
                            {
                                "submission": ai_submission_context,
                                "exam_context": exam_context,
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode("utf-8")
                    ),
                    "estimated_cost_cents": estimated_cost_cents,
                    "attempts": attempt_history
                    + [
                        {
                            "attempt": attempt,
                            "status": "success",
                            "provider_status": "ok",
                            "duration_ms": round(
                                (time.perf_counter() - started) * 1000, 2
                            ),
                        }
                    ],
                    "retry_limit": attempt_limit,
                },
            }
            with EVALUATION_CACHE_LOCK:
                EVALUATION_CACHE[cache_key] = result_payload
            record_audit_event(
                {
                    "event": "evaluation.success",
                    "submission": ai_submission_context,
                    "provider": result_payload["provider"],
                    "model": result_payload["model"],
                    "telemetry": result_payload["telemetry"],
                }
            )
            return result_payload
        except ProviderResponseError as error:
            last_error = error
            last_status_code = (
                HTTPStatus.SERVICE_UNAVAILABLE
                if error.retriable
                else HTTPStatus.BAD_GATEWAY
            )
        except TimeoutError as error:
            last_error = error
            last_status_code = HTTPStatus.GATEWAY_TIMEOUT
        except urllib.error.URLError as error:
            last_error = error
            last_status_code = HTTPStatus.GATEWAY_TIMEOUT
        except ValueError as error:
            last_error = error
            last_status_code = HTTPStatus.BAD_GATEWAY
        except Exception as error:  # noqa: BLE001 - all provider failures should be normalized here.
            last_error = error
            last_status_code = HTTPStatus.BAD_GATEWAY

        attempt_history.append(
            {
                "attempt": attempt,
                "status": "retrying" if attempt < attempt_limit else "failed",
                "provider_status": "retrying" if attempt < attempt_limit else "failed",
                "error": str(last_error),
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            }
        )
        if attempt < attempt_limit:
            time.sleep(min(2 ** (attempt - 1), 8))
            continue
        break

    failure_payload = {
        "status": "failed",
        "error": str(last_error) if last_error else "AI scoring failed.",
        "retry_state": "exhausted" if attempt_history else "not_started",
        "provider": config["provider"],
        "model": config["model"],
        "provider_status": "failed",
        "prompt_version": SCORING_PROMPT_VERSION,
        "rubric_version": SCORING_RUBRIC_VERSION,
        "input_hash": input_hash,
        "telemetry": {
            "identity": identity,
            "plan": identity["plan"],
            "provider_status": "failed",
            "prompt_version": SCORING_PROMPT_VERSION,
            "rubric_version": SCORING_RUBRIC_VERSION,
            "input_hash": input_hash,
            "quota": {
                "key": quota_snapshot["quota_key"],
                "request_limit": quota_snapshot["request_limit"],
                "cost_limit_cents": quota_snapshot["cost_limit_cents"],
                "usage": quota_snapshot["usage"],
            },
            "request_bytes": len(
                json.dumps(
                    {"submission": ai_submission_context, "exam_context": exam_context},
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ),
            "estimated_cost_cents": estimated_cost_cents,
            "attempts": attempt_history,
            "retry_limit": attempt_limit,
        },
    }
    record_audit_event(
        {
            "event": "evaluation.failure",
            "submission": ai_submission_context,
            "provider": config["provider"],
            "model": config["model"],
            "status_code": int(last_status_code),
            "telemetry": failure_payload["telemetry"],
            "error": str(last_error) if last_error else "AI scoring failed.",
        }
    )
    raise EvaluationError(
        failure_payload["error"],
        status_code=last_status_code,
        retry_state="exhausted",
        telemetry=failure_payload["telemetry"],
    )


def provider_error_message(status_code: int, detail: str) -> str:
    if status_code == 413:
        return "The evaluation prompt was too large for the LLM provider."
    if status_code == 429:
        return "The LLM provider rate limit was reached. Please wait a moment and try again."
    if status_code in {500, 502, 503, 504}:
        return "The LLM provider is temporarily unavailable. Please try again shortly."
    return "LLM provider request failed."


def upload_storage_for_id(upload_id: str) -> Path:
    """Return the path to the JSON metadata file for a given upload_id."""
    safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", upload_id)
    return UPLOAD_ROOT / "speaking" / f"{safe_id}.meta.json"


def store_speaking_upload(
    content: bytes,
    content_type: str,
    query: dict[str, list[str]],
) -> dict[str, Any]:
    """Persist a speaking audio upload and return metadata."""
    submission_id = (query.get("submission_id") or [""])[0].strip()
    task = (query.get("task") or [""])[0].strip()
    exam_id = (query.get("exam_id") or [""])[0].strip()

    if not submission_id:
        raise ValueError("submission_id is required")

    upload_id = secrets.token_urlsafe(16)
    ext = (
        "webm"
        if "webm" in content_type
        else ("ogg" if "ogg" in content_type else "bin")
    )
    audio_filename = f"{upload_id}.{ext}"

    speaking_dir = UPLOAD_ROOT / "speaking"
    speaking_dir.mkdir(parents=True, exist_ok=True)

    audio_path = speaking_dir / audio_filename
    audio_path.write_bytes(content)

    metadata = {
        "upload_id": upload_id,
        "submission_id": submission_id,
        "task": task,
        "exam_id": exam_id,
        "content_type": content_type,
        "audio_filename": audio_filename,
        "size_bytes": len(content),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }
    meta_path = upload_storage_for_id(upload_id)
    meta_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return {
        "upload_id": upload_id,
        "submission_id": submission_id,
        "task": task,
        "upload_url": f"/api/uploads/speaking/{upload_id}",
    }


class AppHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(self)")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: blob:; "
            "media-src 'self' blob:; "
            "connect-src 'self'; "
            "base-uri 'self'; "
            "frame-ancestors 'none'; "
            "form-action 'self'",
        )
        if is_production():
            self.send_header(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        if getattr(self, "command", "") in {
            "GET",
            "HEAD",
        } and not normalize_request_path(getattr(self, "path", "")).startswith("/api/"):
            self.send_header(
                "Cache-Control", static_cache_control(getattr(self, "path", ""))
            )
        elif normalize_request_path(getattr(self, "path", "")).startswith("/api/"):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_head(self):  # type: ignore[override]
        path = normalize_request_path(self.path)
        if path in {"/", "", "/latvian-a2-exam-app"}:
            self.path = PUBLIC_APP_PREFIX
            return super().send_head()
        if path in {"/latvian-listening-library", PUBLIC_LISTENING_PREFIX}:
            self.path = PUBLIC_LISTENING_WEB_PREFIX
            return super().send_head()
        if path.startswith(PUBLIC_LISTENING_PREFIX) and not path.startswith(
            PUBLIC_LISTENING_WEB_PREFIX
        ):
            if not is_public_static_path(path):
                self.send_error(HTTPStatus.NOT_FOUND, "Not found")
                return None
            suffix_path = path[len(PUBLIC_LISTENING_PREFIX) :]
            if suffix_path:
                self.path = f"{PUBLIC_LISTENING_WEB_PREFIX}{suffix_path}"
                return super().send_head()
        if not is_public_static_path(path):
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return None
        return super().send_head()

    def log_message(self, format: str, *args: Any) -> None:
        log_event(
            "info",
            "server_message",
            remote_ip=client_ip(self),
            method=getattr(self, "command", ""),
            path=getattr(self, "path", ""),
            message=format % args,
        )

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        log_event(
            "info",
            "http_access",
            remote_ip=client_ip(self),
            method=getattr(self, "command", ""),
            path=urllib.parse.urlparse(getattr(self, "path", "")).path,
            status=code,
            size=size,
        )

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/healthz":
            json_response(self, HTTPStatus.OK, {"status": "ok"})
            return
        if self.path == "/api/session":
            session = current_session_record(self)
            json_response(
                self, HTTPStatus.OK, {"authenticated": bool(session), **(session or {})}
            )
            return
        if self.path == "/api/exams/catalog":
            session = current_session_record(self)
            json_response(self, HTTPStatus.OK, list_exam_catalog(session))
            return
        exam_content_match = re.fullmatch(r"/api/exams/([^/]+)/content", parsed.path)
        if exam_content_match:
            try:
                markdown = load_exam_markdown(exam_content_match.group(1))
                text_response(
                    self,
                    HTTPStatus.OK,
                    student_exam_markdown(markdown),
                    "text/markdown; charset=utf-8",
                )
            except ApiError as error:
                api_error_response(self, error)
            return
        exam_answer_key_match = re.fullmatch(
            r"/api/exams/([^/]+)/answer-key", parsed.path
        )
        if exam_answer_key_match:
            try:
                exam_id = exam_answer_key_match.group(1)
                answer_key = load_server_answer_key(exam_id)
                json_response(self, HTTPStatus.OK, {"answer_key": answer_key})
            except ApiError as error:
                api_error_response(self, error)
            return
        if self.path == "/api/dashboard":
            try:
                session = require_session(self)
                with db_connection() as conn:
                    json_response(
                        self,
                        HTTPStatus.OK,
                        {
                            "authenticated": True,
                            **build_dashboard(conn, session["account"]["id"]),
                            "account": session["account"],
                        },
                    )
            except PermissionError as error:
                json_response(self, HTTPStatus.UNAUTHORIZED, {"error": str(error)})
            return
        if self.path == "/api/account/export":
            try:
                session = require_session(self)
                json_response(self, HTTPStatus.OK, export_account(session))
            except PermissionError as error:
                json_response(self, HTTPStatus.UNAUTHORIZED, {"error": str(error)})
            return
        if self.path == "/api/attempts":
            try:
                session = require_session(self)
                with db_connection() as conn:
                    attempts = conn.execute(
                        "SELECT * FROM attempts WHERE account_id = ? ORDER BY submitted_at DESC",
                        (session["account"]["id"],),
                    ).fetchall()
                json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "attempts": [
                            serialize_attempt_for_learner(row) for row in attempts
                        ]
                    },
                )
            except PermissionError as error:
                json_response(self, HTTPStatus.UNAUTHORIZED, {"error": str(error)})
            return
        attempt_match = re.fullmatch(r"/api/attempts/([^/]+)", parsed.path)
        if attempt_match:
            try:
                session = require_session(self)
                with db_connection() as conn:
                    attempt = load_owned_attempt(conn, attempt_match.group(1), session)
                json_response(
                    self,
                    HTTPStatus.OK,
                    {"attempt": serialize_attempt_for_learner(attempt)},
                )
            except ApiError as error:
                api_error_response(self, error)
            except PermissionError as error:
                json_response(self, HTTPStatus.UNAUTHORIZED, {"error": str(error)})
            return
        if self.path == "/api/admin/overview":
            try:
                require_admin_session(self)
                json_response(self, HTTPStatus.OK, admin_overview())
            except ApiError as error:
                api_error_response(self, error)
            except PermissionError as error:
                json_response(self, HTTPStatus.UNAUTHORIZED, {"error": str(error)})
            return
        if self.path == "/api/admin/accounts":
            try:
                require_admin_session(self)
                json_response(self, HTTPStatus.OK, list_admin_accounts())
            except ApiError as error:
                api_error_response(self, error)
            except PermissionError as error:
                json_response(self, HTTPStatus.UNAUTHORIZED, {"error": str(error)})
            return
        if self.path == "/api/admin/exams":
            try:
                session = require_admin_session(self)
                json_response(self, HTTPStatus.OK, list_exam_catalog(session))
            except ApiError as error:
                api_error_response(self, error)
            except PermissionError as error:
                json_response(self, HTTPStatus.UNAUTHORIZED, {"error": str(error)})
            return
        admin_exam_match = re.fullmatch(r"/api/admin/exams/([^/]+)", parsed.path)
        if admin_exam_match:
            try:
                require_admin_session(self)
                with db_connection() as conn:
                    row = conn.execute(
                        "SELECT * FROM exams WHERE id = ?", (admin_exam_match.group(1),)
                    ).fetchone()
                if row is None:
                    raise ApiError(
                        HTTPStatus.NOT_FOUND, "exam_not_found", "Exam not found."
                    )
                json_response(
                    self,
                    HTTPStatus.OK,
                    {"exam": serialize_exam_catalog(row, include_answer_key=True)},
                )
            except ApiError as error:
                api_error_response(self, error)
            except PermissionError as error:
                json_response(self, HTTPStatus.UNAUTHORIZED, {"error": str(error)})
            return
        if self.path == "/api/admin/attempts":
            try:
                require_admin_session(self)
                json_response(self, HTTPStatus.OK, list_admin_attempts())
            except ApiError as error:
                api_error_response(self, error)
            except PermissionError as error:
                json_response(self, HTTPStatus.UNAUTHORIZED, {"error": str(error)})
            return
        if self.path == "/api/admin/settings":
            try:
                require_admin_session(self)
                json_response(self, HTTPStatus.OK, list_admin_settings())
            except ApiError as error:
                api_error_response(self, error)
            except PermissionError as error:
                json_response(self, HTTPStatus.UNAUTHORIZED, {"error": str(error)})
            return
        if self.path.startswith("/api/billing/config"):
            payload = {
                "free_exam_id": FREE_EXAM_ID,
                "stripe_enabled": bool(get_stripe_client().enabled()),
                "products": [],
                "success_url": f"{request_base_url(self)}/latvian-a2-exam-app/?view=billing&billing=success",
                "cancel_url": f"{request_base_url(self)}/latvian-a2-exam-app/?view=billing&billing=cancel",
            }
            for product in DEFAULT_PRODUCTS:
                price_id = get_product_price_id(product.key)
                payload["products"].append(
                    {
                        "key": product.key,
                        "name": product.name,
                        "mode": product.mode,
                        "quantity": product.quantity,
                        "grants_attempts": product.grants_attempts,
                        "grants_ai_credits": product.grants_ai_credits,
                        "price_id_configured": bool(price_id),
                        "price_id": price_id,
                    }
                )
            json_response(self, HTTPStatus.OK, payload)
            return

        if self.path.startswith("/api/billing/state"):
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            learner_id = (params.get("learner_id") or [""])[0].strip()
            if not learner_id:
                json_response(
                    self, HTTPStatus.BAD_REQUEST, {"error": "learner_id is required."}
                )
                return
            store = get_billing_store()
            store.ensure_learner(learner_id)
            user_role = get_session_user_role(self)
            json_response(
                self,
                HTTPStatus.OK,
                {
                    "learner_id": learner_id,
                    "state": store.get_state(learner_id, user_role=user_role),
                },
            )
            return

        if self.path.startswith("/api/billing/audit"):
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            learner_id = (params.get("learner_id") or [""])[0].strip()
            if not learner_id:
                json_response(
                    self, HTTPStatus.BAD_REQUEST, {"error": "learner_id is required."}
                )
                return
            store = get_billing_store()
            json_response(
                self,
                HTTPStatus.OK,
                {
                    "learner_id": learner_id,
                    "events": store.list_recent_events(learner_id, limit=20),
                    "activity": store.list_recent_activity(learner_id, limit=20),
                },
            )
            return

        # Speaking audio playback
        parsed_path = urllib.parse.urlparse(self.path).path
        if parsed_path.startswith("/api/uploads/speaking/"):
            upload_id = parsed_path[len("/api/uploads/speaking/") :]
            meta_path = upload_storage_for_id(upload_id)
            if not meta_path.exists():
                json_response(
                    self, HTTPStatus.NOT_FOUND, {"error": "Upload not found."}
                )
                return
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            audio_path = UPLOAD_ROOT / "speaking" / metadata["audio_filename"]
            if not audio_path.exists():
                json_response(
                    self, HTTPStatus.NOT_FOUND, {"error": "Audio file not found."}
                )
                return
            audio_bytes = audio_path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", metadata.get("content_type", "audio/webm"))
            self.send_header("Content-Length", str(len(audio_bytes)))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            self.wfile.write(audio_bytes)
            return

        super().do_GET()

    def do_POST(self) -> None:
        try:
            parsed = urllib.parse.urlparse(self.path)
            if self.path == "/api/auth/register":
                payload = safe_read_json(self)
                response, token = create_account_record(payload)
                json_response_with_headers(
                    self,
                    HTTPStatus.CREATED,
                    {**response, "authenticated": True},
                    {"Set-Cookie": session_cookie_header(token)},
                )
                return
            if self.path == "/api/auth/login":
                payload = safe_read_json(self)
                response, token = login_account(payload)
                json_response_with_headers(
                    self,
                    HTTPStatus.OK,
                    {**response, "authenticated": True},
                    {"Set-Cookie": session_cookie_header(token)},
                )
                return
            if self.path == "/api/auth/logout":
                token = parse_cookie_value(self, AUTH_SESSION_COOKIE)
                if token:
                    with db_connection() as conn:
                        conn.execute(
                            "UPDATE sessions SET revoked_at = ? WHERE token = ?",
                            (now_iso(), token),
                        )
                json_response_with_headers(
                    self,
                    HTTPStatus.OK,
                    {"ok": True},
                    {"Set-Cookie": expired_session_cookie_header()},
                )
                return
            if self.path == "/api/profile":
                payload = safe_read_json(self)
                session = require_session(self)
                json_response(self, HTTPStatus.OK, update_profile(payload, session))
                return
            if self.path == "/api/admin/exams":
                payload = safe_read_json(self)
                session = require_admin_session(self)
                json_response(self, HTTPStatus.OK, save_admin_exam(payload, session))
                return
            admin_exam_match = re.fullmatch(r"/api/admin/exams/([^/]+)", parsed.path)
            if admin_exam_match:
                payload = safe_read_json(self)
                session = require_admin_session(self)
                json_response(
                    self,
                    HTTPStatus.OK,
                    save_admin_exam(payload, session, admin_exam_match.group(1)),
                )
                return
            admin_exam_status_match = re.fullmatch(
                r"/api/admin/exams/([^/]+)/status", parsed.path
            )
            if admin_exam_status_match:
                payload = safe_read_json(self)
                require_admin_session(self)
                json_response(
                    self,
                    HTTPStatus.OK,
                    update_admin_exam_status(admin_exam_status_match.group(1), payload),
                )
                return
            admin_exam_delete_match = re.fullmatch(
                r"/api/admin/exams/([^/]+)/delete", parsed.path
            )
            if admin_exam_delete_match:
                require_admin_session(self)
                json_response(
                    self,
                    HTTPStatus.OK,
                    delete_admin_exam(admin_exam_delete_match.group(1)),
                )
                return
            admin_account_match = re.fullmatch(
                r"/api/admin/accounts/([^/]+)", parsed.path
            )
            if admin_account_match:
                payload = safe_read_json(self)
                session = require_admin_session(self)
                json_response(
                    self,
                    HTTPStatus.OK,
                    update_admin_account(
                        admin_account_match.group(1), payload, session
                    ),
                )
                return
            if self.path == "/api/admin/settings":
                payload = safe_read_json(self)
                require_admin_session(self)
                json_response(self, HTTPStatus.OK, save_admin_settings(payload))
                return
            if self.path == "/api/attempts":
                raise ApiError(
                    HTTPStatus.GONE,
                    "legacy_attempt_upsert_disabled",
                    "Client-trusted attempt upserts are disabled. Use the attempt lifecycle endpoints.",
                )
                return
            if self.path == "/api/attempts/start":
                payload = safe_read_json(self)
                session = require_session(self)
                if not payload.get("attempt_id"):
                    payload["attempt_id"] = f"attempt_{secrets.token_hex(8)}"
                with db_connection() as conn:
                    existing_attempt = conn.execute(
                        "SELECT * FROM attempts WHERE id = ?",
                        (payload["attempt_id"],),
                    ).fetchone()
                    exam_exists = (
                        load_exam_catalog_row(
                            conn, str(payload.get("exam_id", "")), published_only=True
                        )
                        is not None
                    )
                if (
                    existing_attempt is not None
                    and existing_attempt["account_id"] != session["account"]["id"]
                ):
                    raise ApiError(
                        HTTPStatus.FORBIDDEN,
                        "attempt_id_conflict",
                        "Attempt ID belongs to another account.",
                    )
                if existing_attempt is None and not exam_exists:
                    raise ApiError(
                        HTTPStatus.NOT_FOUND, "exam_not_found", "Exam not found."
                    )
                if existing_attempt is None:
                    learner_id = session["account"]["id"]
                    store = get_billing_store()
                    store.ensure_learner(
                        learner_id, email=session["account"].get("email")
                    )
                    billing_access = store.consume_exam_access(
                        learner_id,
                        exam_catalog_id(str(payload.get("exam_id", ""))),
                        source_reference=str(payload["attempt_id"]),
                        source_event_id=str(payload["attempt_id"]),
                        user_role=account_role(session),
                    )
                    if not billing_access["allowed"]:
                        json_response(self, HTTPStatus.PAYMENT_REQUIRED, billing_access)
                        return
                result = start_attempt(payload, session)
                result["attempt"] = redact_attempt_for_learner(result["attempt"])
                json_response(self, HTTPStatus.CREATED, result)
                return
            if self.path == "/api/attempts/history":
                session = require_session(self)
                query = urllib.parse.urlparse(self.path).query
                params = urllib.parse.parse_qs(query)
                exam_id = params.get("exam_id", [None])[0]
                days_back = params.get("days_back", [None])[0]
                limit_param = params.get("limit", [None])[0]
                limit = (
                    int(limit_param) if limit_param and limit_param.isdigit() else 50
                )
                with db_connection() as conn:
                    account_id = session["account"]["id"]
                    if exam_id:
                        attempts = conn.execute(
                            """
                            SELECT * FROM attempts 
                            WHERE account_id = ? AND exam_id = ? 
                            ORDER BY submitted_at DESC 
                            LIMIT ?
                            """,
                            (account_id, exam_id, limit),
                        ).fetchall()
                    elif days_back and days_back.isdigit():
                        cutoff_time = (
                            datetime.now(timezone.utc) - timedelta(days=int(days_back))
                        ).isoformat()
                        attempts = conn.execute(
                            """
                            SELECT * FROM attempts 
                            WHERE account_id = ? AND submitted_at >= ? 
                            ORDER BY submitted_at DESC 
                            LIMIT ?
                            """,
                            (account_id, cutoff_time, limit),
                        ).fetchall()
                    else:
                        attempts = conn.execute(
                            """
                            SELECT * FROM attempts 
                            WHERE account_id = ? 
                            ORDER BY submitted_at DESC 
                            LIMIT ?
                            """,
                            (account_id, limit),
                        ).fetchall()
                json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "attempts": [
                            serialize_attempt_for_learner(row) for row in attempts
                        ]
                    },
                )
                return
            if self.path == "/api/attempts/analytics":
                session = require_session(self)
                with db_connection() as conn:
                    account_id = session["account"]["id"]
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
                        (account_id,),
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
                        (account_id,),
                    ).fetchall()

                    # Process data for analytics
                    trends_data = {}
                    for row in recent_attempts:
                        attempt_id = row["id"]
                        if attempt_id not in trends_data:
                            trends_data[attempt_id] = {
                                "attempt_id": attempt_id,
                                "exam_id": row["exam_id"],
                                "exam_title": row["exam_title"],
                                "submitted_at": row["submitted_at"],
                                "total_score": row["score_total"],
                                "categories": {},
                            }
                        trends_data[attempt_id]["categories"][row["category"]] = {
                            "score": row["score_0_to_15"],
                            "passed": bool(row["passed_boolean"]),
                        }

                    # Calculate strengths and weaknesses
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
                            "latest_attempt": row["latest_attempt"],
                        }

                    # Overall statistics
                    overall_avg = conn.execute(
                        """
                        SELECT AVG(score_total) as avg_total
                        FROM attempts
                        WHERE account_id = ? AND score_total IS NOT NULL
                        """,
                        (account_id,),
                    ).fetchone()

                    pass_rate = conn.execute(
                        """
                        SELECT 
                            COUNT(*) as total_attempts,
                            SUM(CASE WHEN score_total >= 36 THEN 1 ELSE 0 END) as passed_attempts
                        FROM attempts
                        WHERE account_id = ? AND score_total IS NOT NULL
                        """,
                        (account_id,),
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
                        (account_id,),
                    ).fetchone()

                json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "trends": list(trends_data.values()),
                        "category_stats": category_stats,
                        "overall": {
                            "average_score": round(overall_avg["avg_total"], 1)
                            if overall_avg["avg_total"]
                            else 0,
                            "pass_rate": round(
                                (
                                    pass_rate["passed_attempts"]
                                    / pass_rate["total_attempts"]
                                    * 100
                                )
                                if pass_rate["total_attempts"] > 0
                                else 0,
                                1,
                            ),
                            "total_attempts": pass_rate["total_attempts"],
                            "passed_attempts": pass_rate["passed_attempts"],
                            "current_streak": streak_data["streak"]
                            if streak_data["streak"]
                            else 0,
                        },
                    },
                )
                return
            answer_match = re.fullmatch(r"/api/attempts/([^/]+)/answers", parsed.path)
            if answer_match:
                payload = safe_read_json(self)
                session = require_session(self)
                result = save_attempt_answer(answer_match.group(1), payload, session)
                result["attempt"] = redact_attempt_for_learner(result["attempt"])
                json_response(self, HTTPStatus.OK, result)
                return
            submit_match = re.fullmatch(r"/api/attempts/([^/]+)/submit", parsed.path)
            if submit_match:
                session = require_session(self)
                result = submit_attempt(submit_match.group(1), session)
                result["attempt"] = redact_attempt_for_learner(result["attempt"])
                result["score"] = redact_score_payload_for_learner(
                    {"scoring": result.get("score", {})}
                ).get("scoring", result.get("score", {}))
                json_response(self, HTTPStatus.OK, result)
                return
            expire_match = re.fullmatch(r"/api/attempts/([^/]+)/expire", parsed.path)
            if expire_match:
                session = require_session(self)
                result = expire_attempt(expire_match.group(1), session)
                result["attempt"] = redact_attempt_for_learner(result["attempt"])
                json_response(self, HTTPStatus.OK, result)
                return
            if self.path == "/api/account/delete":
                session = require_session(self)
                json_response(self, HTTPStatus.OK, delete_account(session))
                return
            if self.path == "/api/webhooks/auth":
                json_response(self, HTTPStatus.OK, handle_auth_webhook(self))
                return
            if self.path == "/api/billing/checkout-session":
                self.handle_checkout_session()
                return
            if self.path == "/api/billing/consume-exam":
                self.handle_consume_exam()
                return
            if self.path == "/api/billing/consume-ai-credit":
                self.handle_consume_ai_credit()
                return
            if self.path == "/api/stripe/webhook":
                self.handle_stripe_webhook()
                return
            if self.path == "/api/evaluate":
                rate_key = f"evaluate:{client_ip(self)}"
                allowed, retry_after = check_rate_limit(
                    rate_key,
                    limit_env="EVALUATE_RATE_LIMIT_PER_MINUTE",
                    window_env="EVALUATE_RATE_LIMIT_WINDOW_SECONDS",
                )
                if not allowed:
                    log_event(
                        "warning",
                        "rate_limit_blocked",
                        endpoint="/api/evaluate",
                        remote_ip=client_ip(self),
                    )
                    json_response_with_headers(
                        self,
                        HTTPStatus.TOO_MANY_REQUESTS,
                        {
                            "error": "Too many scoring requests. Please wait and try again."
                        },
                        {"Retry-After": str(retry_after)},
                    )
                    return
                payload = safe_read_json(self)
                submission = payload.get("submission")
                exam_markdown = payload.get("exam_markdown", "")
                learner_id = str(payload.get("learner_id", "")).strip()
                learner_email = str(payload.get("email", "")).strip()
                if not isinstance(submission, dict):
                    raise ValueError("Payload must include a submission object.")
                if not isinstance(exam_markdown, str) or not exam_markdown.strip():
                    raise ValueError("Payload must include exam_markdown text.")
                submission = dict(submission)
                if learner_id:
                    submission["learner_id"] = learner_id
                if learner_email:
                    submission["learner_email"] = learner_email
                check_scoring_rate_limit(learner_id)
                user_role = get_session_user_role(self)
                billing_result: dict[str, Any] = {
                    "learner_id": learner_id,
                    "ai_credit_required": ai_scoring_requires_credit()
                    and user_role not in {"admin", "superadmin"},
                    "ai_credit_consumed": False,
                }
                if learner_id:
                    store = get_billing_store()
                    store.ensure_learner(learner_id, email=learner_email or None)
                    if billing_result["ai_credit_required"]:
                        billing_state = store.get_state(learner_id, user_role=user_role)
                        if (
                            billing_state.get("frozen")
                            or int(billing_state.get("ai_credits_remaining") or 0) <= 0
                        ):
                            json_response(
                                self,
                                HTTPStatus.PAYMENT_REQUIRED,
                                {
                                    "error": "AI scoring requires an available AI credit or active subscription.",
                                    "billing_state": billing_state,
                                },
                            )
                            return
                        billing_result["billing_state"] = billing_state
                    else:
                        billing_result["billing_state"] = store.get_state(learner_id)
                elif billing_result["ai_credit_required"]:
                    raise ValueError("Payload must include learner_id text.")
                result = evaluate_submission(submission, exam_markdown)
                if learner_id and billing_result["ai_credit_required"]:
                    ai_credit_result = get_billing_store().consume_ai_credit(
                        learner_id,
                        source_reference=submission.get("submission_id"),
                        source_event_id=submission.get("submission_id"),
                        user_role=user_role,
                    )
                    if not ai_credit_result["allowed"]:
                        json_response(
                            self,
                            HTTPStatus.PAYMENT_REQUIRED,
                            {
                                "error": "AI scoring completed but the credit could not be committed. Please retry from your saved attempt.",
                                "billing_state": ai_credit_result["state"],
                            },
                        )
                        return
                    billing_result["ai_credit_consumed"] = True
                    billing_result["billing_state"] = ai_credit_result["state"]
                result["billing"] = billing_result
                json_response(self, HTTPStatus.OK, result)
                return
            # Speaking audio upload
            parsed_path = urllib.parse.urlparse(self.path)
            if parsed_path.path == "/api/uploads/speaking":
                content_length = int(self.headers.get("Content-Length", 0))
                if content_length > MAX_AUDIO_BYTES:
                    json_response(
                        self,
                        HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                        {"error": "Audio file too large."},
                    )
                    return
                content = self.rfile.read(content_length) if content_length > 0 else b""
                content_type = self.headers.get("Content-Type", "audio/webm")
                query = urllib.parse.parse_qs(parsed_path.query)
                result = store_speaking_upload(
                    content=content, content_type=content_type, query=query
                )
                json_response(self, HTTPStatus.CREATED, result)
                return
            json_response(self, HTTPStatus.NOT_FOUND, {"error": "Unknown endpoint."})
            return
        except QuotaExceededError as error:
            json_response(
                self,
                error.status_code,
                {
                    "status": "quota_exceeded",
                    "error": str(error),
                },
            )
        except EvaluationError as error:
            json_response(
                self,
                error.status_code,
                {
                    "status": "failed",
                    "error": str(error),
                    "retry_state": error.retry_state,
                    "provider_status": "failed",
                    "telemetry": error.telemetry,
                },
            )
        except ApiError as error:
            api_error_response(self, error)
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            capture_exception(error)
            log_event("error", "api_provider_error", path=self.path, status=error.code)
            json_response(
                self,
                error.code,
                {"error": provider_error_message(error.code, detail), "detail": detail},
            )
        except PermissionError as error:
            log_event(
                "warning",
                "api_permission_error",
                path=self.path,
                remote_ip=client_ip(self),
            )
            json_response(self, HTTPStatus.UNAUTHORIZED, {"error": str(error)})
        except Exception as error:  # noqa: BLE001 - this endpoint should always return JSON.
            capture_exception(error)
            log_event("error", "api_error", path=self.path, error=type(error).__name__)
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(error)})

    def handle_checkout_session(self) -> None:
        try:
            payload = safe_read_json(self)
            learner_id = str(payload.get("learner_id", "")).strip()
            product_key = str(payload.get("product_key", "")).strip()
            email = str(payload.get("email", "")).strip() or None
            success_url = (
                str(payload.get("success_url", "")).strip()
                or f"{request_base_url(self)}/latvian-a2-exam-app/?view=billing&checkout=success"
            )
            cancel_url = (
                str(payload.get("cancel_url", "")).strip()
                or f"{request_base_url(self)}/latvian-a2-exam-app/?view=billing&checkout=cancel"
            )
            if not learner_id:
                raise ValueError("learner_id is required.")
            if not product_key:
                raise ValueError("product_key is required.")
            store = get_billing_store()
            learner = store.ensure_learner(learner_id, email=email)
            product = next(
                (item for item in DEFAULT_PRODUCTS if item.key == product_key), None
            )
            if not product:
                raise ValueError("Unknown product_key.")
            price_id = get_product_price_id(product_key)
            client = get_stripe_client()
            if client.enabled():
                if not price_id:
                    raise ValueError(f"Missing Stripe price ID for {product_key}.")
                session = client.create_checkout_session(
                    product=product,
                    price_id=price_id,
                    learner_id=learner_id,
                    email=email,
                    success_url=success_url,
                    cancel_url=cancel_url,
                    metadata={"learner_id": learner_id, "product_key": product_key},
                )
                json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "mode": "stripe",
                        "learner": learner,
                        "product": product.key,
                        "checkout_url": session.get("url"),
                        "session": session,
                    },
                )
                return

            session = client.create_mock_checkout_session(
                product=product,
                learner_id=learner_id,
                email=email,
                success_url=success_url,
                cancel_url=cancel_url,
            )
            json_response(
                self,
                HTTPStatus.OK,
                {
                    "mode": "mock",
                    "learner": learner,
                    "product": product.key,
                    "checkout_url": session.get("url"),
                    "session": session,
                },
            )
        except Exception as error:  # noqa: BLE001 - keep API responses JSON.
            capture_exception(error)
            log_event("error", "checkout_session_error", error=type(error).__name__)
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(error)})

    def handle_consume_exam(self) -> None:
        try:
            payload = safe_read_json(self)
            learner_id = str(payload.get("learner_id", "")).strip()
            exam_id = str(payload.get("exam_id", "")).strip()
            if not learner_id:
                raise ValueError("learner_id is required.")
            if not exam_id:
                raise ValueError("exam_id is required.")
            store = get_billing_store()
            store.ensure_learner(learner_id)
            result = store.consume_exam_access(
                learner_id,
                exam_id,
                source_reference=str(payload.get("source_reference", "")).strip()
                or None,
                source_event_id=str(payload.get("source_event_id", "")).strip() or None,
            )
            status = HTTPStatus.OK if result["allowed"] else HTTPStatus.PAYMENT_REQUIRED
            json_response(self, status, result)
        except Exception as error:  # noqa: BLE001 - keep API responses JSON.
            capture_exception(error)
            log_event("error", "consume_exam_error", error=type(error).__name__)
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(error)})

    def handle_consume_ai_credit(self) -> None:
        try:
            payload = safe_read_json(self)
            learner_id = str(payload.get("learner_id", "")).strip()
            if not learner_id:
                raise ValueError("learner_id is required.")
            store = get_billing_store()
            store.ensure_learner(learner_id)
            result = store.consume_ai_credit(
                learner_id,
                source_reference=str(payload.get("source_reference", "")).strip()
                or None,
                source_event_id=str(payload.get("source_event_id", "")).strip() or None,
            )
            status = HTTPStatus.OK if result["allowed"] else HTTPStatus.PAYMENT_REQUIRED
            json_response(self, status, result)
        except Exception as error:  # noqa: BLE001 - keep API responses JSON.
            capture_exception(error)
            log_event("error", "consume_ai_credit_error", error=type(error).__name__)
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(error)})

    def handle_stripe_webhook(self) -> None:
        try:
            payload = safe_read_raw_body(self)
            secret = stripe_webhook_secret()
            if not secret:
                raise ValueError("STRIPE_WEBHOOK_SECRET is required.")
            signature = self.headers.get("Stripe-Signature")
            store = get_billing_store()
            result = store.handle_webhook(payload, signature, secret)
            json_response(self, HTTPStatus.OK, {"status": "ok", "result": result})
        except Exception as error:  # noqa: BLE001 - keep API responses JSON.
            capture_exception(error)
            log_event("error", "stripe_webhook_error", error=type(error).__name__)
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(error)})


class DualStackServer(ThreadingHTTPServer):
    address_family = socket.AF_INET6

    def server_bind(self) -> None:
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        super().server_bind()


def main() -> int:
    load_dotenv(ROOT / ".env")
    init_sentry()
    init_auth_store()
    port = int(os.getenv("PORT", "4173"))
    server = DualStackServer(("::", port), AppHandler)
    print(
        f"Serving Latvian A2 app at http://localhost:{port}/latvian-a2-exam-app/",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
