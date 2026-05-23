"""Tests for T-010 — debug routes must require ?debug=1 + admin role.

The helper ``server.require_debug_access`` and the ``/api/debug/*`` dispatcher
must answer with HTTP 404 unless BOTH the ``?debug=1`` query string flag and
an authenticated admin (or superadmin) session are present. A 404 is used
deliberately so anonymous / learner accounts cannot enumerate which debug
surfaces exist.
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

import server


class _FakeHeaders:
    def __init__(self, cookie: str = "") -> None:
        self._cookie = cookie

    def get(self, name: str, default: str = "") -> str:
        if name.lower() == "cookie":
            return self._cookie
        return default


class _FakeHandler:
    """Minimal stand-in for ``SimpleHTTPRequestHandler`` used by debug routes.

    Implements only the surface that ``handle_debug_request`` /
    ``json_response`` rely on: ``path``, ``headers``, ``send_response``,
    ``send_header``, ``end_headers``, and a writeable ``wfile``.
    """

    def __init__(self, path: str, cookie: str = "") -> None:
        self.path = path
        self.headers = _FakeHeaders(cookie=cookie)
        self.wfile = io.BytesIO()
        self.status_code: int | None = None
        self.response_headers: dict[str, str] = {}

    # ``BaseHTTPRequestHandler``-compatible response API.
    def send_response(self, code: int, message: str | None = None) -> None:  # noqa: D401
        self.status_code = code

    def send_header(self, name: str, value: str) -> None:
        self.response_headers[name] = value

    def end_headers(self) -> None:  # noqa: D401 - no-op for tests
        return None

    def json_payload(self) -> dict[str, Any]:
        raw = self.wfile.getvalue().decode("utf-8")
        return json.loads(raw) if raw else {}


def _seed_account(conn: server.sqlite3.Connection, account_id: str, email: str, role: str) -> None:
    conn.execute(
        """
        INSERT INTO accounts (id, email, password_salt, password_hash, status, created_at, deleted_at, role)
        VALUES (?, ?, 'salt', 'hash', 'active', '2026-05-05T00:00:00Z', NULL, ?)
        """,
        (account_id, email, role),
    )


class DebugAccessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "auth.sqlite3"
        self.auth_db_patch = patch.object(server, "AUTH_DB_PATH", self.db_path)
        self.auth_db_patch.start()
        server.init_auth_store()

        with server.db_connection() as conn:
            _seed_account(conn, "acct_admin", "admin@example.test", "admin")
            _seed_account(conn, "acct_learner", "learner@example.test", "user")
            self.admin_token = server.create_session(conn, "acct_admin")
            self.learner_token = server.create_session(conn, "acct_learner")

    def tearDown(self) -> None:
        self.auth_db_patch.stop()
        self.tmpdir.cleanup()

    # ------------------------------------------------------------------
    # require_debug_access — direct helper unit tests.
    # ------------------------------------------------------------------
    def test_require_debug_access_rejects_missing_debug_flag(self) -> None:
        handler = _FakeHandler(
            "/api/debug/session",
            cookie=f"{server.AUTH_SESSION_COOKIE}={self.admin_token}",
        )
        with self.assertRaises(server.DebugAccessDenied):
            server.require_debug_access(handler)

    def test_require_debug_access_rejects_anonymous_with_flag(self) -> None:
        handler = _FakeHandler("/api/debug/session?debug=1")
        with self.assertRaises(server.DebugAccessDenied):
            server.require_debug_access(handler)

    def test_require_debug_access_rejects_learner_with_flag(self) -> None:
        handler = _FakeHandler(
            "/api/debug/session?debug=1",
            cookie=f"{server.AUTH_SESSION_COOKIE}={self.learner_token}",
        )
        with self.assertRaises(server.DebugAccessDenied):
            server.require_debug_access(handler)

    def test_require_debug_access_allows_admin_with_flag(self) -> None:
        handler = _FakeHandler(
            "/api/debug/session?debug=1",
            cookie=f"{server.AUTH_SESSION_COOKIE}={self.admin_token}",
        )
        session = server.require_debug_access(handler)
        self.assertEqual(session["account"]["role"], "admin")

    # ------------------------------------------------------------------
    # handle_debug_request — full route dispatch returning HTTP status.
    # ------------------------------------------------------------------
    def test_debug_route_without_debug_flag_returns_404(self) -> None:
        handler = _FakeHandler(
            "/api/debug/session",
            cookie=f"{server.AUTH_SESSION_COOKIE}={self.admin_token}",
        )
        self.assertTrue(server.handle_debug_request(handler))
        self.assertEqual(handler.status_code, 404)

    def test_debug_route_with_flag_but_non_admin_returns_404(self) -> None:
        handler = _FakeHandler(
            "/api/debug/session?debug=1",
            cookie=f"{server.AUTH_SESSION_COOKIE}={self.learner_token}",
        )
        self.assertTrue(server.handle_debug_request(handler))
        self.assertEqual(handler.status_code, 404)

    def test_debug_route_with_flag_and_admin_returns_200(self) -> None:
        handler = _FakeHandler(
            "/api/debug/session?debug=1",
            cookie=f"{server.AUTH_SESSION_COOKIE}={self.admin_token}",
        )
        self.assertTrue(server.handle_debug_request(handler))
        self.assertEqual(handler.status_code, 200)
        payload = handler.json_payload()
        self.assertEqual(payload["session"]["account_id"], "acct_admin")
        self.assertEqual(payload["session"]["role"], "admin")
        self.assertIn("server", payload)

    def test_unknown_debug_subpath_still_requires_gate_and_404s(self) -> None:
        handler = _FakeHandler(
            "/api/debug/does-not-exist?debug=1",
            cookie=f"{server.AUTH_SESSION_COOKIE}={self.admin_token}",
        )
        self.assertTrue(server.handle_debug_request(handler))
        # Authenticated admin reaches the dispatcher but the path is unrouted.
        self.assertEqual(handler.status_code, 404)

    def test_non_debug_path_is_ignored_by_dispatcher(self) -> None:
        handler = _FakeHandler("/api/session")
        self.assertFalse(server.handle_debug_request(handler))
        self.assertIsNone(handler.status_code)


if __name__ == "__main__":
    unittest.main()
