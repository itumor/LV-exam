#!/usr/bin/env python3
"""Serve the Latvian A2 app and evaluate submissions with an LLM provider."""

from __future__ import annotations

import json
import os
import math
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import hashlib
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
MAX_BODY_BYTES = 1_500_000
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
DEFAULT_CODEX_MODEL = "gpt-5.2"
CODEX_OSS_DEFAULT_MODEL_LABEL = "codex-oss-default"
CODEX_TIMEOUT_SECONDS = 300
DEFAULT_RETRY_LIMIT = 3
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
    def __init__(self, message: str, *, status_code: int = HTTPStatus.TOO_MANY_REQUESTS) -> None:
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
        str(submission.get("user_id", "") or "").strip()
        or str(submission.get("candidate_code", "") or "").strip()
        or candidate_code
        or str(submission.get("submission_id", "") or "").strip()
        or "anonymous"
    )
    plan = str(submission.get("plan", "") or submission.get("access_plan", "") or DEFAULT_PLAN).strip().lower()
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
    return DEFAULT_DAILY_COST_LIMIT_CENTS.get(plan, DEFAULT_DAILY_COST_LIMIT_CENTS["free"])


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


def estimate_request_cost_cents(provider: str, submission_context: dict[str, Any], exam_context: str) -> int:
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


def reserve_quota(identity: dict[str, str], estimated_cost_cents: int) -> dict[str, Any]:
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
            "candidate_code": redacted["submission"].get("candidate", {}).get("code") if isinstance(redacted["submission"].get("candidate"), dict) else None,
        }
    with AUDIT_LOG_LOCK:
        AUDIT_LOG.append(redacted)
        if len(AUDIT_LOG) > 200:
            del AUDIT_LOG[: len(AUDIT_LOG) - 200]


def safe_int(value: Any, *, field_name: str, minimum: int | None = None, maximum: int | None = None) -> int:
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


def normalize_score_section(raw_section: Any, *, skill: str) -> dict[str, Any]:
    if not isinstance(raw_section, dict):
        raise ValueError(f"Scores for {skill} must be an object.")
    points = safe_int(raw_section.get("points"), field_name=f"{skill}.points", minimum=0, maximum=15)
    max_points = safe_int(raw_section.get("max_points", 15), field_name=f"{skill}.max_points", minimum=15, maximum=15)
    reason = safe_text(raw_section.get("reason", ""), field_name=f"{skill}.reason", max_length=2000)
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
                "skill": safe_text(item.get("skill", ""), field_name=f"corrections[{index}].skill", max_length=40),
                "task": safe_text(item.get("task", ""), field_name=f"corrections[{index}].task", max_length=80),
                "item": safe_int(item.get("item", 1), field_name=f"corrections[{index}].item", minimum=1),
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
                "comment": safe_text(item.get("comment", ""), field_name=f"corrections[{index}].comment", max_length=2000),
            }
        )
    return normalized


def normalize_feedback_items(raw_items: Any, *, field_name: str) -> list[str]:
    if raw_items is None:
        return []
    if not isinstance(raw_items, list):
        raise ValueError(f"{field_name} must be an array.")
    return [safe_text(item, field_name=f"{field_name}[]", max_length=600) for item in raw_items]


def normalize_feedback(raw_feedback: Any) -> dict[str, Any]:
    if raw_feedback is None:
        raw_feedback = {}
    if not isinstance(raw_feedback, dict):
        raise ValueError("Feedback must be an object.")
    return {
        "summary": safe_text(raw_feedback.get("summary", ""), field_name="feedback.summary", max_length=4000),
        "strengths": normalize_feedback_items(raw_feedback.get("strengths"), field_name="feedback.strengths"),
        "improvements": normalize_feedback_items(raw_feedback.get("improvements"), field_name="feedback.improvements"),
        "next_practice": normalize_feedback_items(raw_feedback.get("next_practice"), field_name="feedback.next_practice"),
    }


def validate_and_normalize_evaluation_payload(raw_payload: Any) -> dict[str, Any]:
    if not isinstance(raw_payload, dict):
        raise ValueError("LLM response must be a JSON object.")
    status = safe_text(raw_payload.get("status", ""), field_name="status", max_length=40).lower()
    if status != "evaluated":
        raise ValueError("LLM response status must be 'evaluated'.")
    scores = raw_payload.get("scores")
    if not isinstance(scores, dict):
        raise ValueError("LLM response scores must be an object.")

    normalized_scores: dict[str, Any] = {}
    total = 0
    passed = True
    for skill in ("listening", "reading", "writing", "speaking"):
        normalized_section = normalize_score_section(scores.get(skill), skill=skill)
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


def provider_call_once(config: dict[str, Any], submission_context: dict[str, Any], exam_context: str) -> dict[str, Any]:
    if config["provider"] == "groq":
        return call_groq(config, submission_context, exam_context)
    if config["provider"] == "codex" and config.get("mode") == "remote":
        return call_codex_remote(config, submission_context, exam_context)
    if config["provider"] == "codex":
        return call_codex(config, submission_context, exam_context)
    raise RuntimeError("Unsupported LLM provider.")


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


def json_response(handler: SimpleHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def safe_read_json(handler: SimpleHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length <= 0:
        raise ValueError("Request body is empty.")
    if length > MAX_BODY_BYTES:
        raise ValueError("Request body is too large.")
    raw = handler.rfile.read(length)
    return json.loads(raw.decode("utf-8"))


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


def submission_cache_key(submission: dict[str, Any], exam_context: str, provider: str, model: str) -> str:
    payload = json.dumps(
        {"submission": submission, "exam_context": exam_context, "provider": provider, "model": model},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compact_exam_context(markdown: str) -> str:
    lines = markdown.splitlines()
    kept: list[str] = []
    skip_headings = {
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
        "plan": submission.get("plan", DEFAULT_PLAN),
        "exam_id": submission.get("exam_id"),
        "exam_title": submission.get("exam_title"),
        "level": submission.get("level", "A2"),
        "language": submission.get("language", "lv"),
        "pass_rule": submission.get("pass_rule", {}),
        "progress": submission.get("progress", {}),
        "answers": submission.get("answers", {}),
        "answer_key": submission.get("answer_key", {}),
        "scoring": compact_scoring,
        "validation_queue": submission.get("validation_queue", []),
    }


def env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def provider_config() -> dict[str, Any]:
    provider = os.getenv("LLM_PROVIDER", "groq").strip().lower()

    if provider == "groq":
        api_key = os.getenv("GROQ_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is missing. Add it to .env or the container environment.")

        return {
            "provider": provider,
            "api_key": api_key,
            "model": os.getenv("LLM_MODEL", os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL)).strip() or DEFAULT_GROQ_MODEL,
            "base_url": os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/"),
        }

    if provider == "codex":
        remote_url = os.getenv("CODEX_REMOTE_URL", "").strip().rstrip("/")
        if remote_url:
            timeout_raw = os.getenv("CODEX_TIMEOUT_SECONDS", str(CODEX_TIMEOUT_SECONDS)).strip()
            try:
                timeout_seconds = int(timeout_raw)
            except ValueError as error:
                raise RuntimeError("CODEX_TIMEOUT_SECONDS must be an integer.") from error

            return {
                "provider": provider,
                "mode": "remote",
                "remote_url": remote_url,
                "model": os.getenv("CODEX_MODEL", DEFAULT_CODEX_MODEL).strip() or DEFAULT_CODEX_MODEL,
                "timeout_seconds": timeout_seconds,
            }

        cli_name = os.getenv("CODEX_CLI_PATH", "codex").strip() or "codex"
        cli_path = shutil.which(cli_name)
        if not cli_path:
            raise RuntimeError(
                "Codex CLI executable was not found. Install Codex CLI, set CODEX_CLI_PATH, "
                "or set CODEX_REMOTE_URL to a host-local Codex scoring server."
            )

        timeout_raw = os.getenv("CODEX_TIMEOUT_SECONDS", str(CODEX_TIMEOUT_SECONDS)).strip()
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

    raise RuntimeError("Unsupported LLM_PROVIDER. Set LLM_PROVIDER=groq or LLM_PROVIDER=codex.")


def build_evaluation_prompt(submission: dict[str, Any], exam_context: str) -> str:
    compact_submission = json.dumps(submission, ensure_ascii=False, indent=2)
    return f"""
You are a strict but helpful evaluator for the Latvian state language proficiency exam, A2 level.

Evaluate the candidate submission using the official-style pass rule:
- Total maximum: 60 points.
- Each skill maximum: 15 points.
- Passing requires at least 9/15 in every skill.

Use the exam Markdown, answer key, writing model answers, and speaking teacher notes as context.
Keep Latvian difficulty expectations at A2. Be generous with small spelling mistakes if the meaning is clear.
Objective answers already have a local pre-score; verify them but do not invent hidden answers.
For writing and speaking free text, score communicative success, task completion, vocabulary, grammar, and clarity.

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


def call_groq(config: dict[str, Any], submission_context: dict[str, Any], exam_context: str) -> dict[str, Any]:
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
        detail = error.read().decode("utf-8", errors="replace")
        raise ProviderResponseError(
            provider_error_message(error.code, detail),
            retriable=error.code in {429, 500, 502, 503, 504},
        ) from error
    except (TimeoutError, urllib.error.URLError, KeyError, json.JSONDecodeError) as error:
        raise ProviderResponseError(str(error), retriable=True) from error


def call_codex(config: dict[str, Any], submission_context: dict[str, Any], exam_context: str) -> dict[str, Any]:
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
        output = output_path.read_text(encoding="utf-8") if output_path.exists() else completed.stdout
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "No Codex CLI error output.").strip()
            raise RuntimeError(f"Codex CLI scoring failed with exit {completed.returncode}: {detail[:2000]}")

    return {
        "provider": config["provider"],
        "model": config["model"],
        "evaluation": extract_json_object(output),
        "usage": {},
    }


def call_codex_remote(config: dict[str, Any], submission_context: dict[str, Any], exam_context: str) -> dict[str, Any]:
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


def evaluate_submission(submission: dict[str, Any], exam_markdown: str) -> dict[str, Any]:
    config = provider_config()
    exam_context = compact_exam_context(exam_markdown)
    submission_context = compact_submission(submission)
    validate_submission_size(submission_context)
    cache_key = submission_cache_key(submission_context, exam_context, config["provider"], config["model"])
    with EVALUATION_CACHE_LOCK:
        cached = EVALUATION_CACHE.get(cache_key)
    if cached:
        return cached

    identity = identity_from_submission(submission_context)
    estimated_cost_cents = estimate_request_cost_cents(config["provider"], submission_context, exam_context)
    quota_snapshot = reserve_quota(identity, estimated_cost_cents)

    attempt_limit = retry_limit()
    attempt_history: list[dict[str, Any]] = []
    last_error: Exception | None = None
    last_status_code = HTTPStatus.BAD_GATEWAY
    for attempt in range(1, attempt_limit + 1):
        started = time.perf_counter()
        try:
            raw_result = provider_call_once(config, submission_context, exam_context)
            normalized_evaluation = validate_and_normalize_evaluation_payload(raw_result.get("evaluation"))
            result_payload = {
                "status": "evaluated",
                "provider": raw_result.get("provider", config["provider"]),
                "model": raw_result.get("model", config["model"]),
                "evaluation": normalized_evaluation,
                "usage": raw_result.get("usage", {}),
                "telemetry": {
                    "identity": identity,
                    "plan": identity["plan"],
                    "quota": {
                        "key": quota_snapshot["quota_key"],
                        "request_limit": quota_snapshot["request_limit"],
                        "cost_limit_cents": quota_snapshot["cost_limit_cents"],
                        "usage": quota_snapshot["usage"],
                    },
                    "request_bytes": len(
                        json.dumps(
                            {"submission": submission_context, "exam_context": exam_context},
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode("utf-8")
                    ),
                    "estimated_cost_cents": estimated_cost_cents,
                    "attempts": attempt_history + [
                        {
                            "attempt": attempt,
                            "status": "success",
                            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
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
                    "submission": submission_context,
                    "provider": result_payload["provider"],
                    "model": result_payload["model"],
                    "telemetry": result_payload["telemetry"],
                }
            )
            return result_payload
        except ProviderResponseError as error:
            last_error = error
            last_status_code = HTTPStatus.SERVICE_UNAVAILABLE if error.retriable else HTTPStatus.BAD_GATEWAY
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
        "telemetry": {
            "identity": identity,
            "plan": identity["plan"],
            "quota": {
                "key": quota_snapshot["quota_key"],
                "request_limit": quota_snapshot["request_limit"],
                "cost_limit_cents": quota_snapshot["cost_limit_cents"],
                "usage": quota_snapshot["usage"],
            },
            "request_bytes": len(
                json.dumps(
                    {"submission": submission_context, "exam_context": exam_context},
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
            "submission": submission_context,
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


class AppHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_POST(self) -> None:
        if self.path != "/api/evaluate":
            json_response(self, HTTPStatus.NOT_FOUND, {"error": "Unknown endpoint."})
            return

        try:
            payload = safe_read_json(self)
            submission = payload.get("submission")
            exam_markdown = payload.get("exam_markdown", "")
            if not isinstance(submission, dict):
                raise ValueError("Payload must include a submission object.")
            if not isinstance(exam_markdown, str) or not exam_markdown.strip():
                raise ValueError("Payload must include exam_markdown text.")
            result = evaluate_submission(submission, exam_markdown)
            json_response(self, HTTPStatus.OK, result)
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
                    "telemetry": error.telemetry,
                },
            )
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            json_response(self, error.code, {"error": provider_error_message(error.code, detail), "detail": detail})
        except Exception as error:  # noqa: BLE001 - this endpoint should always return JSON.
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(error)})


class DualStackServer(ThreadingHTTPServer):
    address_family = socket.AF_INET6

    def server_bind(self) -> None:
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        super().server_bind()


def main() -> int:
    load_dotenv(ROOT / ".env")
    port = int(os.getenv("PORT", "4173"))
    server = DualStackServer(("::", port), AppHandler)
    print(f"Serving Latvian A2 app at http://localhost:{port}/latvian-a2-exam-app/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
