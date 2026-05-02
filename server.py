#!/usr/bin/env python3
"""Serve the Latvian A2 app and evaluate submissions with an LLM provider."""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import hashlib
import uuid
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlparse
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
MAX_BODY_BYTES = 1_500_000
MAX_UPLOAD_BYTES = 15_000_000
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
DEFAULT_CODEX_MODEL = "gpt-5.2"
CODEX_OSS_DEFAULT_MODEL_LABEL = "codex-oss-default"
CODEX_TIMEOUT_SECONDS = 300
UPLOAD_ROOT = ROOT / ".runtime" / "speaking_uploads"
EVALUATION_CACHE: dict[str, dict[str, Any]] = {}
EVALUATION_CACHE_LOCK = threading.Lock()


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


def safe_upload_extension(content_type: str) -> str:
    lowered = content_type.lower()
    if "webm" in lowered:
        return ".webm"
    if "mp4" in lowered or "m4a" in lowered:
        return ".m4a"
    if "ogg" in lowered:
        return ".ogg"
    return ".bin"


def relative_or_absolute_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def upload_storage_for_id(upload_id: str) -> Path:
    return UPLOAD_ROOT / f"{upload_id}.json"


def store_speaking_upload(
    *,
    content: bytes,
    content_type: str,
    query: dict[str, list[str]],
) -> dict[str, Any]:
    if len(content) == 0:
        raise ValueError("Audio upload body is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("Audio upload is too large.")

    submission_id = (query.get("submission_id") or [""])[0].strip()
    task = (query.get("task") or [""])[0].strip()
    exam_id = (query.get("exam_id") or [""])[0].strip()
    if not submission_id:
        raise ValueError("submission_id is required for speaking uploads.")
    if not task:
        raise ValueError("task is required for speaking uploads.")

    upload_id = uuid.uuid4().hex
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    upload_dir = UPLOAD_ROOT / submission_id / task
    upload_dir.mkdir(parents=True, exist_ok=True)
    extension = safe_upload_extension(content_type or "audio/webm")
    audio_path = upload_dir / f"{upload_id}{extension}"
    meta_path = upload_storage_for_id(upload_id)
    created_at = time.time()
    audio_path.write_bytes(content)
    meta_path.write_text(
        json.dumps(
            {
                "upload_id": upload_id,
                "submission_id": submission_id,
                "task": task,
                "exam_id": exam_id,
                "content_type": content_type or "audio/webm",
                "file_path": relative_or_absolute_path(audio_path),
                "created_at": created_at,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {
        "upload_id": upload_id,
        "submission_id": submission_id,
        "task": task,
        "exam_id": exam_id,
        "content_type": content_type or "audio/webm",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(created_at)),
        "upload_url": f"/api/uploads/speaking/{upload_id}",
    }


def find_uploaded_recording(upload_id: str) -> tuple[Path, dict[str, Any]]:
    meta_matches = list(UPLOAD_ROOT.rglob(f"{upload_id}.json"))
    if not meta_matches:
        raise FileNotFoundError(upload_id)
    meta_path = meta_matches[0]
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    file_path = ROOT / metadata["file_path"]
    if not file_path.exists():
        raise FileNotFoundError(upload_id)
    return file_path, metadata


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
            delay = 2 ** attempt
            if retry_after:
                try:
                    delay = max(delay, int(float(retry_after)))
                except ValueError:
                    pass
            time.sleep(delay)

    assert last_error is not None
    raise last_error


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
    cache_key = submission_cache_key(submission_context, exam_context, config["provider"], config["model"])
    with EVALUATION_CACHE_LOCK:
        cached = EVALUATION_CACHE.get(cache_key)
    if cached:
        return cached

    if config["provider"] == "groq":
        result_payload = call_groq(config, submission_context, exam_context)
    elif config["provider"] == "codex" and config.get("mode") == "remote":
        result_payload = call_codex_remote(config, submission_context, exam_context)
    elif config["provider"] == "codex":
        result_payload = call_codex(config, submission_context, exam_context)
    else:
        raise RuntimeError("Unsupported LLM provider.")

    with EVALUATION_CACHE_LOCK:
        EVALUATION_CACHE[cache_key] = result_payload
    return result_payload


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

    def do_GET(self) -> None:
        if self.path.startswith("/api/uploads/speaking/"):
            upload_id = self.path.rsplit("/", 1)[-1].split("?", 1)[0].strip()
            try:
                file_path, metadata = find_uploaded_recording(upload_id)
            except FileNotFoundError:
                json_response(self, HTTPStatus.NOT_FOUND, {"error": "Upload not found."})
                return

            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", metadata.get("content_type", "audio/webm"))
            self.send_header("Content-Length", str(file_path.stat().st_size))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            with file_path.open("rb") as stream:
                shutil.copyfileobj(stream, self.wfile)
            return

        return super().do_GET()

    def do_POST(self) -> None:
        if self.path.startswith("/api/uploads/speaking"):
            try:
                parsed = urlparse(self.path)
                query = parse_qs(parsed.query)
                length = int(self.headers.get("Content-Length", "0") or "0")
                if length <= 0:
                    raise ValueError("Audio upload body is empty.")
                if length > MAX_UPLOAD_BYTES:
                    raise ValueError("Audio upload is too large.")
                content = self.rfile.read(length)
                result = store_speaking_upload(
                    content=content,
                    content_type=self.headers.get("Content-Type", "audio/webm"),
                    query=query,
                )
                json_response(self, HTTPStatus.OK, result)
            except Exception as error:  # noqa: BLE001 - API should always return JSON.
                json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return

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
