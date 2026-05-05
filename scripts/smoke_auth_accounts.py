#!/usr/bin/env python3
"""Deterministic smoke coverage for auth, dashboard, export, delete, and webhook rejection."""

from __future__ import annotations

import contextlib
import http.cookiejar
import json
import os
import secrets
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server as app_server


@dataclass
class Response:
    status: int
    payload: dict
    headers: dict[str, str]


def request_json(
    base_url: str,
    method: str,
    path: str,
    payload: dict | None = None,
    opener: urllib.request.OpenerDirector | None = None,
    headers: dict[str, str] | None = None,
) -> Response:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        urllib.parse.urljoin(base_url, path),
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            **(headers or {}),
        },
    )
    active_opener = opener or urllib.request.build_opener()
    try:
        with active_opener.open(request, timeout=10) as response:
            raw = response.read().decode("utf-8")
            return Response(
                status=response.status,
                payload=json.loads(raw),
                headers=dict(response.headers.items()),
            )
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8")
        return Response(
            status=error.code,
            payload=json.loads(raw),
            headers=dict(error.headers.items()) if error.headers else {},
        )


def wait_for_server(base_url: str) -> None:
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            response = request_json(base_url, "GET", "/api/session")
            if response.status == 200:
                return
        except Exception:
            pass
        time.sleep(0.25)
    raise RuntimeError("Smoke server did not start in time.")


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    temp_dir = tempfile.TemporaryDirectory(prefix="auth-smoke-")
    temp_db_path = Path(temp_dir.name) / "auth.sqlite3"
    app_server.AUTH_DB_PATH = temp_db_path
    app_server.AUTH_WEBHOOK_SECRET = "smoke-secret-" + secrets.token_hex(12)
    app_server.EVALUATION_CACHE.clear()
    app_server.init_auth_store()

    server = app_server.DualStackServer(("::", 0), app_server.AppHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://localhost:{port}"
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    try:
        wait_for_server(base_url)

        session = request_json(base_url, "GET", "/api/session")
        assert_true(session.status == 200, "Anonymous session check failed.")
        assert_true(session.payload.get("authenticated") is False, "Anonymous session should be false.")

        email = f"smoke-{secrets.token_hex(4)}@example.com"
        password = "SmokeTest123!"
        register = request_json(
            base_url,
            "POST",
            "/api/auth/register",
            {
                "email": email,
                "password": password,
                "full_name": "Smoke Learner",
                "native_language": "Latviešu",
                "exam_target_date": "2026-06-01",
            },
            opener=opener,
        )
        assert_true(register.status == 201, f"Register failed: {register.payload}")
        assert_true(register.payload.get("authenticated") is True, "Register response should authenticate.")
        assert_true(register.payload.get("account", {}).get("email") == email, "Registered email mismatch.")

        session = request_json(base_url, "GET", "/api/session", opener=opener)
        assert_true(session.status == 200 and session.payload.get("authenticated") is True, "Session restore failed.")

        dashboard = request_json(base_url, "GET", "/api/dashboard", opener=opener)
        assert_true(dashboard.status == 200, "Dashboard fetch failed.")
        assert_true(dashboard.payload.get("summary", {}).get("attempts_taken") == 0, "Expected empty dashboard.")

        profile_update = request_json(
            base_url,
            "POST",
            "/api/profile",
            {
                "full_name": "Smoke Learner Updated",
                "native_language": "Latviešu",
                "exam_target_date": "2026-07-15",
                "exam_pack_status": "paid",
            },
            opener=opener,
        )
        assert_true(profile_update.status == 200, f"Profile update failed: {profile_update.payload}")
        assert_true(profile_update.payload.get("profile", {}).get("exam_pack_status") == "paid", "Profile save failed.")

        attempt_payload = {
            "submission": {
                "submission_id": f"attempt_{secrets.token_hex(4)}",
                "exam_id": "01",
                "exam_title": "A2 Mock Exam 01",
                "status": "submitted",
                "submitted_at": "2026-05-02T10:00:00Z",
                "scoring": {
                    "objective_correct": 12,
                    "objective_possible": 15,
                    "manual_review_possible": 0,
                    "by_skill": {
                        "listening": {"objective_correct": 4, "objective_possible": 5},
                        "reading": {"objective_correct": 4, "objective_possible": 5},
                        "writing": {"objective_correct": 2, "objective_possible": 3},
                        "speaking": {"objective_correct": 2, "objective_possible": 2},
                    },
                },
            },
            "evaluation": {
                "evaluation": {
                    "scores": {
                        "total": 12,
                        "passed": False,
                    }
                }
            },
        }
        attempt = request_json(base_url, "POST", "/api/attempts", attempt_payload, opener=opener)
        assert_true(attempt.status == 200, f"Attempt persist failed: {attempt.payload}")

        dashboard = request_json(base_url, "GET", "/api/dashboard", opener=opener)
        assert_true(dashboard.payload.get("summary", {}).get("attempts_taken") == 1, "Attempt count not persisted.")
        assert_true(dashboard.payload.get("summary", {}).get("latest_score") == 12, "Latest score not visible.")

        export = request_json(base_url, "GET", "/api/account/export", opener=opener)
        assert_true(export.status == 200, f"Account export failed: {export.payload}")
        assert_true(len(export.payload.get("attempts", [])) == 1, "Export should include attempt history.")

        webhook_rejected = request_json(
            base_url,
            "POST",
            "/api/webhooks/auth",
            {"event_id": "evt_invalid", "event_type": "account.created", "email": email},
            headers={"X-Auth-Signature": "bad-signature"},
        )
        assert_true(webhook_rejected.status == 401, "Webhook rejection did not return 401.")

        logout = request_json(base_url, "POST", "/api/auth/logout", opener=opener)
        assert_true(logout.status == 200, "Logout failed.")

        session_after_logout = request_json(base_url, "GET", "/api/session", opener=opener)
        assert_true(session_after_logout.payload.get("authenticated") is False, "Logout should clear session.")

        login = request_json(
            base_url,
            "POST",
            "/api/auth/login",
            {"email": email, "password": password},
            opener=opener,
        )
        assert_true(login.status == 200, "Login failed.")

        delete_account = request_json(base_url, "POST", "/api/account/delete", opener=opener)
        assert_true(delete_account.status == 200, f"Delete account failed: {delete_account.payload}")

        session_after_delete = request_json(base_url, "GET", "/api/session", opener=opener)
        assert_true(session_after_delete.payload.get("authenticated") is False, "Deleted account should not restore session.")

        dashboard_after_delete = request_json(base_url, "GET", "/api/dashboard", opener=opener)
        assert_true(dashboard_after_delete.status == 401, "Protected dashboard should reject anonymous access.")

        client_bundle = (app_server.ROOT / "latvian-a2-exam-app" / "app.js").read_text(encoding="utf-8")
        assert_true(app_server.AUTH_WEBHOOK_SECRET not in client_bundle, "Client bundle leaked the webhook secret value.")

        print("Auth/accounts smoke checks passed.")
        return 0
    finally:
        with contextlib.suppress(Exception):
            server.shutdown()
            server.server_close()
        temp_dir.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
