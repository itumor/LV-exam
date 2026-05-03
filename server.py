#!/usr/bin/env python3
"""Serve the Latvian A2 app and evaluate submissions with an LLM provider."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import shutil
import sqlite3
import socket
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
MAX_BODY_BYTES = 1_500_000
DEFAULT_BILLING_DB_PATH = ROOT / "data" / "billing.sqlite3"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
DEFAULT_CODEX_MODEL = "gpt-5.2"
CODEX_OSS_DEFAULT_MODEL_LABEL = "codex-oss-default"
CODEX_TIMEOUT_SECONDS = 300
EVALUATION_CACHE: dict[str, dict[str, Any]] = {}
EVALUATION_CACHE_LOCK = threading.Lock()
AUTH_DB_PATH = ROOT / ".multica" / "auth.sqlite3"
AUTH_SESSION_COOKIE = "a2_session"
AUTH_SESSION_TTL_DAYS = 30
AUTH_WEBHOOK_SECRET = os.getenv("AUTH_WEBHOOK_SECRET", "").strip()


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
    return f"http://{host}"


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


def db_connection() -> sqlite3.Connection:
    AUTH_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(AUTH_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_auth_store() -> None:
    with db_connection() as conn:
        conn.executescript(
            """
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

            CREATE TABLE IF NOT EXISTS auth_webhook_events (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_attempts_account_submitted_at
            ON attempts(account_id, submitted_at DESC);
            """
        )


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    salt_bytes = salt or secrets.token_bytes(16)
    password_bytes = password.encode("utf-8")
    digest = hashlib.pbkdf2_hmac("sha256", password_bytes, salt_bytes, 120_000)
    return base64.b64encode(salt_bytes).decode("ascii"), base64.b64encode(digest).decode("ascii")


def verify_password(password: str, salt_b64: str, expected_hash_b64: str) -> bool:
    salt = base64.b64decode(salt_b64.encode("ascii"))
    _, actual_hash = hash_password(password, salt)
    return hmac.compare_digest(actual_hash, expected_hash_b64)


def make_session_token() -> str:
    return secrets.token_urlsafe(32)


def session_cookie_header(token: str) -> str:
    expires = datetime.now(timezone.utc) + timedelta(days=AUTH_SESSION_TTL_DAYS)
    return (
        f"{AUTH_SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax; "
        f"Expires={expires.strftime('%a, %d %b %Y %H:%M:%S GMT')}"
    )


def expired_session_cookie_header() -> str:
    return (
        f"{AUTH_SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; "
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


def serialize_account(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "email": row["email"],
        "status": row["status"],
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
    return {
        "id": row["id"],
        "account_id": row["account_id"],
        "exam_id": row["exam_id"],
        "exam_title": row["exam_title"],
        "status": row["status"],
        "submitted_at": row["submitted_at"],
        "score_total": row["score_total"],
        "score_payload": score_payload,
        "submission_payload": submission_payload,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def current_session_record(handler: SimpleHTTPRequestHandler) -> dict[str, Any] | None:
    token = parse_cookie_value(handler, AUTH_SESSION_COOKIE)
    if not token:
        return None
    now = now_iso()
    with db_connection() as conn:
        row = conn.execute(
            """
            SELECT s.token, s.account_id, s.expires_at, s.revoked_at, a.email, a.status,
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
        if row["revoked_at"] is not None or row["deleted_at"] is not None or row["status"] != "active":
            return None
        if row["expires_at"] <= now:
            conn.execute("UPDATE sessions SET revoked_at = ? WHERE token = ?", (now, token))
            return None
        conn.execute("UPDATE sessions SET last_seen_at = ? WHERE token = ?", (now, token))
        return {
            "token": row["token"],
            "account": {
                "id": row["account_id"],
                "email": row["email"],
                "status": row["status"],
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
    expires_at = (datetime.now(timezone.utc) + timedelta(days=AUTH_SESSION_TTL_DAYS)).isoformat().replace("+00:00", "Z")
    conn.execute(
        """
        INSERT INTO sessions (token, account_id, created_at, expires_at, revoked_at, last_seen_at)
        VALUES (?, ?, ?, ?, NULL, ?)
        """,
        (token, account_id, now, expires_at, now),
    )
    return token


def build_dashboard(conn: sqlite3.Connection, account_id: str) -> dict[str, Any]:
    profile = conn.execute("SELECT * FROM profiles WHERE account_id = ?", (account_id,)).fetchone()
    attempts = conn.execute(
        """
        SELECT * FROM attempts
        WHERE account_id = ?
        ORDER BY submitted_at DESC
        LIMIT 12
        """,
        (account_id,),
    ).fetchall()
    serialized_attempts = [serialize_attempt(row) for row in attempts]
    latest = serialized_attempts[0] if serialized_attempts else None
    skill_progress: dict[str, dict[str, int]] = {}
    for attempt in serialized_attempts:
        score_payload = attempt.get("score_payload") or {}
        scoring = score_payload.get("evaluation", {}).get("scores", {}) if isinstance(score_payload.get("evaluation"), dict) else score_payload.get("scoring", {})
        by_skill = scoring.get("by_skill") or {}
        for skill, score in by_skill.items():
            bucket = skill_progress.setdefault(skill, {"objective_correct": 0, "objective_possible": 0})
            bucket["objective_correct"] += int(score.get("objective_correct") or 0)
            bucket["objective_possible"] += int(score.get("objective_possible") or 0)
    return {
        "profile": serialize_profile(profile),
        "summary": {
            "attempts_taken": len(serialized_attempts),
            "latest_score": ((latest or {}).get("score_total") if latest else None),
            "skill_progress": skill_progress,
            "subscription_status": (serialize_profile(profile) or {}).get("exam_pack_status", "free"),
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
                INSERT INTO accounts (id, email, password_salt, password_hash, status, created_at, deleted_at)
                VALUES (?, ?, ?, ?, 'active', ?, NULL)
                """,
                (account_id, email, salt_b64, hash_b64, now),
            )
        except sqlite3.IntegrityError as error:
            raise ValueError("That email is already registered.") from error
        upsert_profile(conn, account_id, full_name, native_language, exam_target_date)
        token = create_session(conn, account_id)
        account = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        profile = conn.execute("SELECT * FROM profiles WHERE account_id = ?", (account_id,)).fetchone()
    return {
        "account": serialize_account(account),
        "profile": serialize_profile(profile),
        "dashboard": {"summary": {"attempts_taken": 0, "latest_score": None, "skill_progress": {}, "subscription_status": "free"}, "attempts": []},
    }, token


def login_account(payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
    email = normalize_email(str(payload.get("email", "")))
    password = str(payload.get("password", ""))
    if not email or not password:
        raise ValueError("Email and password are required.")
    with db_connection() as conn:
        account = conn.execute("SELECT * FROM accounts WHERE email = ?", (email,)).fetchone()
        if account is None or account["deleted_at"] is not None or account["status"] != "active":
            raise ValueError("Invalid email or password.")
        if not verify_password(password, account["password_salt"], account["password_hash"]):
            raise ValueError("Invalid email or password.")
        token = create_session(conn, account["id"])
        profile = conn.execute("SELECT * FROM profiles WHERE account_id = ?", (account["id"],)).fetchone()
    return {
        "account": serialize_account(account),
        "profile": serialize_profile(profile),
    }, token


def persist_attempt(payload: dict[str, Any], session: dict[str, Any]) -> dict[str, Any]:
    submission = payload.get("submission")
    if not isinstance(submission, dict):
        raise ValueError("Payload must include a submission object.")
    attempt_id = str(submission.get("submission_id") or payload.get("attempt_id") or f"attempt_{secrets.token_hex(8)}")
    exam_id = str(submission.get("exam_id") or "unknown_exam")
    exam_title = str(submission.get("exam_title") or "Untitled exam")
    status = str(submission.get("status") or "draft")
    submitted_at = str(submission.get("submitted_at") or now_iso())
    score_payload = payload.get("evaluation") or submission.get("ai_evaluation")
    score_total = None
    if isinstance(score_payload, dict):
        if isinstance(score_payload.get("evaluation"), dict):
            score_total = score_payload["evaluation"].get("scores", {}).get("total")
        else:
            score_total = score_payload.get("scores", {}).get("total")
    else:
        scoring = submission.get("scoring", {})
        if isinstance(scoring, dict):
            score_payload = {"scoring": scoring}
            score_total = scoring.get("objective_correct")
    with db_connection() as conn:
        conn.execute(
            """
            INSERT INTO attempts (
                id, account_id, exam_id, exam_title, status, submitted_at,
                score_total, score_payload, submission_payload, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                status = excluded.status,
                submitted_at = excluded.submitted_at,
                score_total = excluded.score_total,
                score_payload = excluded.score_payload,
                submission_payload = excluded.submission_payload,
                updated_at = excluded.updated_at
            """,
            (
                attempt_id,
                session["account"]["id"],
                exam_id,
                exam_title,
                status,
                submitted_at,
                score_total,
                json.dumps(score_payload, ensure_ascii=False),
                json.dumps(submission, ensure_ascii=False),
                now_iso(),
                now_iso(),
            ),
        )
        attempt = conn.execute("SELECT * FROM attempts WHERE id = ?", (attempt_id,)).fetchone()
    return {"attempt": serialize_attempt(attempt)}


def update_profile(payload: dict[str, Any], session: dict[str, Any]) -> dict[str, Any]:
    full_name = str(payload.get("full_name", "")).strip()
    native_language = str(payload.get("native_language", "")).strip() or None
    exam_target_date = str(payload.get("exam_target_date", "")).strip() or None
    exam_pack_status = str(payload.get("exam_pack_status", "")).strip() or None
    with db_connection() as conn:
        profile = conn.execute("SELECT * FROM profiles WHERE account_id = ?", (session["account"]["id"],)).fetchone()
        if profile is None:
            raise ValueError("Profile not found.")
        next_full_name = full_name or profile["full_name"]
        next_native_language = native_language if native_language is not None else profile["native_language"]
        next_exam_target_date = exam_target_date if exam_target_date is not None else profile["exam_target_date"]
        next_exam_pack_status = exam_pack_status or profile["exam_pack_status"]
        upsert_profile(conn, session["account"]["id"], next_full_name, next_native_language, next_exam_target_date)
        conn.execute(
            "UPDATE profiles SET exam_pack_status = ?, updated_at = ? WHERE account_id = ?",
            (next_exam_pack_status, now_iso(), session["account"]["id"]),
        )
        updated = conn.execute("SELECT * FROM profiles WHERE account_id = ?", (session["account"]["id"],)).fetchone()
    return {"profile": serialize_profile(updated)}


def delete_account(session: dict[str, Any]) -> dict[str, Any]:
    with db_connection() as conn:
        conn.execute("UPDATE sessions SET revoked_at = ? WHERE account_id = ?", (now_iso(), session["account"]["id"]))
        conn.execute("DELETE FROM accounts WHERE id = ?", (session["account"]["id"],))
    return {"deleted": True}


def export_account(session: dict[str, Any]) -> dict[str, Any]:
    with db_connection() as conn:
        account = conn.execute("SELECT * FROM accounts WHERE id = ?", (session["account"]["id"],)).fetchone()
        profile = conn.execute("SELECT * FROM profiles WHERE account_id = ?", (session["account"]["id"],)).fetchone()
        attempts = conn.execute("SELECT * FROM attempts WHERE account_id = ? ORDER BY submitted_at DESC", (session["account"]["id"],)).fetchall()
    return {
        "account": serialize_account(account),
        "profile": serialize_profile(profile),
        "attempts": [serialize_attempt(row) for row in attempts],
    }


def verify_auth_webhook(handler: SimpleHTTPRequestHandler, body: bytes) -> None:
    if not AUTH_WEBHOOK_SECRET:
        raise PermissionError("Auth webhook secret is not configured.")
    expected = handler.headers.get("X-Auth-Signature", "").strip()
    if not expected:
        raise PermissionError("Missing webhook signature.")
    actual = hmac.new(AUTH_WEBHOOK_SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()
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
        existing = conn.execute("SELECT event_id FROM auth_webhook_events WHERE event_id = ?", (event_id,)).fetchone()
        if existing is not None:
            return {"status": "duplicate", "event_id": event_id}
        conn.execute(
            "INSERT INTO auth_webhook_events (event_id, event_type, payload, created_at) VALUES (?, ?, ?, ?)",
            (event_id, event_type, json.dumps(payload, ensure_ascii=False), now_iso()),
        )
        account_email = normalize_email(str(payload.get("email", ""))) or None
        account_name = str(payload.get("full_name", "")).strip() or None
        if event_type in {"account.created", "account.updated", "profile.updated"} and account_email:
            account = conn.execute("SELECT id FROM accounts WHERE email = ?", (account_email,)).fetchone()
            if account is None:
                account_id = f"acct_{secrets.token_hex(8)}"
                salt_b64, hash_b64 = hash_password(str(payload.get("password", "temporary-webhook-password")))
                conn.execute(
                    """
                    INSERT INTO accounts (id, email, password_salt, password_hash, status, created_at, deleted_at)
                    VALUES (?, ?, ?, ?, 'active', ?, NULL)
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
            account = conn.execute("SELECT id FROM accounts WHERE email = ?", (account_email,)).fetchone()
            if account is not None:
                conn.execute("UPDATE sessions SET revoked_at = ? WHERE account_id = ?", (now_iso(), account["id"]))
                conn.execute("DELETE FROM accounts WHERE id = ?", (account["id"],))
    return {"status": "ok", "event_id": event_id}


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
        if self.path == "/api/session":
            session = current_session_record(self)
            json_response(self, HTTPStatus.OK, {"authenticated": bool(session), **(session or {})})
            return
        if self.path == "/api/dashboard":
            try:
                session = require_session(self)
                with db_connection() as conn:
                    json_response(self, HTTPStatus.OK, {"authenticated": True, **build_dashboard(conn, session["account"]["id"]), "account": session["account"]})
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
                json_response(self, HTTPStatus.OK, {"attempts": [serialize_attempt(row) for row in attempts]})
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
                json_response(self, HTTPStatus.BAD_REQUEST, {"error": "learner_id is required."})
                return
            store = get_billing_store()
            store.ensure_learner(learner_id)
            json_response(self, HTTPStatus.OK, {"learner_id": learner_id, "state": store.get_state(learner_id)})
            return

        if self.path.startswith("/api/billing/audit"):
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            learner_id = (params.get("learner_id") or [""])[0].strip()
            if not learner_id:
                json_response(self, HTTPStatus.BAD_REQUEST, {"error": "learner_id is required."})
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

        super().do_GET()

    def do_POST(self) -> None:
        try:
            if self.path == "/api/auth/register":
                payload = safe_read_json(self)
                response, token = create_account_record(payload)
                json_response_with_headers(self, HTTPStatus.CREATED, {**response, "authenticated": True}, {"Set-Cookie": session_cookie_header(token)})
                return
            if self.path == "/api/auth/login":
                payload = safe_read_json(self)
                response, token = login_account(payload)
                json_response_with_headers(self, HTTPStatus.OK, {**response, "authenticated": True}, {"Set-Cookie": session_cookie_header(token)})
                return
            if self.path == "/api/auth/logout":
                token = parse_cookie_value(self, AUTH_SESSION_COOKIE)
                if token:
                    with db_connection() as conn:
                        conn.execute("UPDATE sessions SET revoked_at = ? WHERE token = ?", (now_iso(), token))
                json_response_with_headers(self, HTTPStatus.OK, {"ok": True}, {"Set-Cookie": expired_session_cookie_header()})
                return
            if self.path == "/api/profile":
                payload = safe_read_json(self)
                session = require_session(self)
                json_response(self, HTTPStatus.OK, update_profile(payload, session))
                return
            if self.path == "/api/attempts":
                payload = safe_read_json(self)
                session = require_session(self)
                json_response(self, HTTPStatus.OK, persist_attempt(payload, session))
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
                payload = safe_read_json(self)
                submission = payload.get("submission")
                exam_markdown = payload.get("exam_markdown", "")
                learner_id = str(payload.get("learner_id", "")).strip()
                if not isinstance(submission, dict):
                    raise ValueError("Payload must include a submission object.")
                if not isinstance(exam_markdown, str) or not exam_markdown.strip():
                    raise ValueError("Payload must include exam_markdown text.")
                if not learner_id:
                    raise ValueError("Payload must include learner_id text.")
                store = get_billing_store()
                store.ensure_learner(learner_id, email=str(payload.get("email", "")).strip() or None)
                ai_credit_result = store.consume_ai_credit(learner_id, source_reference=submission.get("submission_id"), source_event_id=submission.get("submission_id"))
                if not ai_credit_result["allowed"]:
                    json_response(
                        self,
                        HTTPStatus.PAYMENT_REQUIRED,
                        {
                            "error": "AI scoring requires an available AI credit or active subscription.",
                            "billing_state": ai_credit_result["state"],
                        },
                    )
                    return
                result = evaluate_submission(submission, exam_markdown)
                result["billing"] = {
                    "learner_id": learner_id,
                    "ai_credit_consumed": True,
                    "billing_state": ai_credit_result["state"],
                }
                json_response(self, HTTPStatus.OK, result)
                return
            json_response(self, HTTPStatus.NOT_FOUND, {"error": "Unknown endpoint."})
            return
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            json_response(self, error.code, {"error": provider_error_message(error.code, detail), "detail": detail})
        except PermissionError as error:
            json_response(self, HTTPStatus.UNAUTHORIZED, {"error": str(error)})
        except Exception as error:  # noqa: BLE001 - this endpoint should always return JSON.
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(error)})

    def handle_checkout_session(self) -> None:
        try:
            payload = safe_read_json(self)
            learner_id = str(payload.get("learner_id", "")).strip()
            product_key = str(payload.get("product_key", "")).strip()
            email = str(payload.get("email", "")).strip() or None
            success_url = str(payload.get("success_url", "")).strip() or f"{request_base_url(self)}/latvian-a2-exam-app/?view=billing&checkout=success"
            cancel_url = str(payload.get("cancel_url", "")).strip() or f"{request_base_url(self)}/latvian-a2-exam-app/?view=billing&checkout=cancel"
            if not learner_id:
                raise ValueError("learner_id is required.")
            if not product_key:
                raise ValueError("product_key is required.")
            store = get_billing_store()
            learner = store.ensure_learner(learner_id, email=email)
            product = next((item for item in DEFAULT_PRODUCTS if item.key == product_key), None)
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
                source_reference=str(payload.get("source_reference", "")).strip() or None,
                source_event_id=str(payload.get("source_event_id", "")).strip() or None,
            )
            status = HTTPStatus.OK if result["allowed"] else HTTPStatus.PAYMENT_REQUIRED
            json_response(self, status, result)
        except Exception as error:  # noqa: BLE001 - keep API responses JSON.
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
                source_reference=str(payload.get("source_reference", "")).strip() or None,
                source_event_id=str(payload.get("source_event_id", "")).strip() or None,
            )
            status = HTTPStatus.OK if result["allowed"] else HTTPStatus.PAYMENT_REQUIRED
            json_response(self, status, result)
        except Exception as error:  # noqa: BLE001 - keep API responses JSON.
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
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(error)})


class DualStackServer(ThreadingHTTPServer):
    address_family = socket.AF_INET6

    def server_bind(self) -> None:
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        super().server_bind()


def main() -> int:
    load_dotenv(ROOT / ".env")
    init_auth_store()
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
