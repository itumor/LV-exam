"""Integration tests for the T-018 /api/uploads/speaking endpoints.

Spins up the real AppHandler in a background ThreadingHTTPServer and issues
HTTP requests via ``urllib``. Database, auth, and upload paths are all
redirected to a TemporaryDirectory so each test is hermetic.
"""

from __future__ import annotations

import socket
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import server
from audio_uploads import AudioUploadStore


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class SpeakingUploadEndpointTests(unittest.TestCase):
    """End-to-end checks for the new /api/uploads/speaking routes."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp_path = Path(cls._tmp.name)
        cls.db_path = cls.tmp_path / "auth.sqlite3"
        cls.upload_root = cls.tmp_path / "uploads"

        cls._patches = [
            patch.object(server, "AUTH_DB_PATH", cls.db_path),
            patch.object(
                server,
                "T018_SPEAKING_UPLOAD_STORE",
                AudioUploadStore(
                    base_dir=cls.upload_root,
                    max_bytes=4096,
                    allowed_mimes=(
                        "audio/webm",
                        "audio/ogg",
                        "audio/wav",
                        "audio/mpeg",
                    ),
                ),
            ),
        ]
        for p in cls._patches:
            p.start()

        server.init_auth_store()
        # Seed two distinct users so cross-user access can be exercised.
        with server.db_connection() as conn:
            conn.execute(
                """
                INSERT INTO accounts (id, email, password_salt, password_hash,
                                       status, created_at, deleted_at, role)
                VALUES ('acct_alpha', 'alpha@example.test', 'salt', 'hash',
                        'active', '2026-05-05T00:00:00Z', NULL, 'user')
                """
            )
            conn.execute(
                """
                INSERT INTO accounts (id, email, password_salt, password_hash,
                                       status, created_at, deleted_at, role)
                VALUES ('acct_beta', 'beta@example.test', 'salt', 'hash',
                        'active', '2026-05-05T00:00:00Z', NULL, 'user')
                """
            )
            cls.token_alpha = server.create_session(conn, "acct_alpha")
            cls.token_beta = server.create_session(conn, "acct_beta")

        port = _free_port()
        cls.base_url = f"http://127.0.0.1:{port}"
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", port), server.AppHandler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.httpd.shutdown()
        cls.thread.join(timeout=2)
        for p in reversed(cls._patches):
            p.stop()
        cls._tmp.cleanup()

    # ---- helpers ----------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        body: bytes | None = None,
        content_type: str | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, method=method, data=body)
        if token:
            req.add_header(
                "Cookie", f"{server.AUTH_SESSION_COOKIE}={token}"
            )
        if content_type:
            req.add_header("Content-Type", content_type)
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                return (
                    response.status,
                    dict(response.headers.items()),
                    response.read(),
                )
        except urllib.error.HTTPError as error:
            return error.code, dict(error.headers.items()), error.read()

    # ---- tests ------------------------------------------------------------

    def test_post_then_get_roundtrip(self) -> None:
        payload = b"fake-audio-payload-bytes"
        status, _headers, body = self._request(
            "POST",
            "/api/uploads/speaking?attempt_id=att-alpha&task_id=task1",
            token=self.token_alpha,
            body=payload,
            content_type="audio/webm",
        )
        self.assertEqual(status, 200, body)
        import json

        result = json.loads(body)
        self.assertEqual(result["path"], "acct_alpha/att-alpha/task1.webm")
        self.assertEqual(result["mime"], "audio/webm")
        self.assertEqual(result["bytes"], len(payload))

        status, headers, fetched = self._request(
            "GET",
            "/api/uploads/speaking/att-alpha/task1",
            token=self.token_alpha,
        )
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("Content-Type"), "audio/webm")
        self.assertEqual(fetched, payload)

    def test_post_requires_authentication(self) -> None:
        status, _h, _body = self._request(
            "POST",
            "/api/uploads/speaking?attempt_id=att-unauth&task_id=task1",
            body=b"x",
            content_type="audio/webm",
        )
        self.assertEqual(status, 401)

    def test_get_requires_authentication(self) -> None:
        # Seed an upload first so that the route exists and 401 isn't masked
        # by a 404.
        self._request(
            "POST",
            "/api/uploads/speaking?attempt_id=att-secure&task_id=task1",
            token=self.token_alpha,
            body=b"secret-audio",
            content_type="audio/webm",
        )
        status, _h, _body = self._request(
            "GET", "/api/uploads/speaking/att-secure/task1"
        )
        self.assertEqual(status, 401)

    def test_cross_user_retrieval_returns_not_found(self) -> None:
        self._request(
            "POST",
            "/api/uploads/speaking?attempt_id=att-private&task_id=task1",
            token=self.token_alpha,
            body=b"alphas-audio",
            content_type="audio/webm",
        )
        # Beta tries to read Alpha's file via the same path.
        status, _h, _body = self._request(
            "GET",
            "/api/uploads/speaking/att-private/task1",
            token=self.token_beta,
        )
        self.assertEqual(status, 404)

    def test_post_rejects_unsupported_mime(self) -> None:
        status, _h, _body = self._request(
            "POST",
            "/api/uploads/speaking?attempt_id=att-bad-mime&task_id=task1",
            token=self.token_alpha,
            body=b"x",
            content_type="video/mp4",
        )
        self.assertEqual(status, 415)

    def test_post_rejects_path_traversal(self) -> None:
        status, _h, _body = self._request(
            "POST",
            "/api/uploads/speaking?attempt_id=..%2Fescape&task_id=task1",
            token=self.token_alpha,
            body=b"x",
            content_type="audio/webm",
        )
        self.assertEqual(status, 400)

    def test_post_requires_attempt_and_task_ids(self) -> None:
        status, _h, _body = self._request(
            "POST",
            "/api/uploads/speaking",
            token=self.token_alpha,
            body=b"x",
            content_type="audio/webm",
        )
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
