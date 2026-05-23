"""T-028 — /healthz must expose the Fly region for multi-region monitoring.

The cross-region monitoring workflow
(``.github/workflows/region-health.yml``) hits each region's
``<region>.<app>.fly.dev/healthz`` and asserts that the response body's
``region`` field matches the region in the URL. That contract is
enforced here at the handler level so an accidental regression breaks
CI before it reaches production.
"""

from __future__ import annotations

import io
import json
import sys
import unittest
from http import HTTPStatus
from pathlib import Path
from unittest.mock import patch

# Ensure repo root is on sys.path so ``import server`` works under
# ``python -m unittest`` from arbitrary cwd.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import server  # noqa: E402  (shim that aliases to server_app.core)


class StubRequest:
    """Just enough of socket.socket for BaseHTTPRequestHandler bootstrap."""

    def __init__(self, payload: bytes) -> None:
        self._buf = io.BytesIO(payload)

    def makefile(self, mode: str, *args, **kwargs):  # noqa: D401 - matches API
        return self._buf

    def sendall(self, *_args, **_kwargs) -> None:
        return None


def _invoke_healthz() -> tuple[int, dict[str, object]]:
    """Drive AppHandler.do_GET against /healthz and return (status, body)."""

    request_line = b"GET /healthz HTTP/1.1\r\nHost: localhost\r\n\r\n"
    request = StubRequest(request_line)

    # BaseHTTPRequestHandler invokes do_GET in __init__; build a handler
    # without going through the real server loop.
    handler = server.AppHandler.__new__(server.AppHandler)
    handler.rfile = io.BytesIO(request_line)
    handler.wfile = io.BytesIO()
    handler.request = request
    handler.client_address = ("127.0.0.1", 0)
    handler.server = None  # not used by /healthz
    handler.requestline = "GET /healthz HTTP/1.1"
    handler.command = "GET"
    handler.path = "/healthz"
    handler.request_version = "HTTP/1.1"
    handler.headers = {}
    handler.close_connection = True

    # Capture response status + body via send_response / wfile.
    captured: dict[str, object] = {"status": None}

    def _send_response(status: int, message: str | None = None) -> None:
        captured["status"] = int(status)

    def _send_header(*_args, **_kwargs) -> None:
        return None

    def _end_headers() -> None:
        return None

    handler.send_response = _send_response  # type: ignore[assignment]
    handler.send_header = _send_header  # type: ignore[assignment]
    handler.end_headers = _end_headers  # type: ignore[assignment]

    handler.do_GET()

    raw = handler.wfile.getvalue()
    body = json.loads(raw.decode("utf-8")) if raw else {}
    status = int(captured["status"] or 0)
    return status, body


class HealthzRegionTests(unittest.TestCase):
    def test_healthz_returns_region_from_fly_region_env(self) -> None:
        with patch.dict("os.environ", {"FLY_REGION": "lhr"}, clear=False):
            status, body = _invoke_healthz()
        self.assertEqual(status, int(HTTPStatus.OK))
        self.assertEqual(body.get("status"), "ok")
        self.assertEqual(body.get("region"), "lhr")

    def test_healthz_returns_region_for_warm_standby(self) -> None:
        with patch.dict("os.environ", {"FLY_REGION": "fra"}, clear=False):
            status, body = _invoke_healthz()
        self.assertEqual(status, int(HTTPStatus.OK))
        self.assertEqual(body.get("region"), "fra")

    def test_healthz_falls_back_to_lvcodex_region_env(self) -> None:
        # Local/dev parity: FLY_REGION is only set on Fly machines, but
        # devs can override the field with LVCODEX_REGION to exercise
        # the multi-region monitor against a local stack.
        env = {"LVCODEX_REGION": "dev-local"}
        # Make sure FLY_REGION is unset for this case.
        with patch.dict("os.environ", env, clear=False):
            import os as _os
            _os.environ.pop("FLY_REGION", None)
            status, body = _invoke_healthz()
        self.assertEqual(status, int(HTTPStatus.OK))
        self.assertEqual(body.get("region"), "dev-local")

    def test_healthz_returns_unknown_when_no_region_env(self) -> None:
        # When neither env var is set the field is still present so the
        # monitoring workflow can produce a deterministic alert payload.
        import os as _os
        env = dict(_os.environ)
        env.pop("FLY_REGION", None)
        env.pop("LVCODEX_REGION", None)
        with patch.dict("os.environ", env, clear=True):
            status, body = _invoke_healthz()
        self.assertEqual(status, int(HTTPStatus.OK))
        self.assertIn("region", body)
        self.assertEqual(body["region"], "unknown")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
