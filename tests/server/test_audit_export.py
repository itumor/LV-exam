"""Unit tests for T-043 — audit-log export (CSV + JSON) for org admins.

Covers the four deliverables called out in the T-043 task card:

1. ``server_app.services.audit_export`` query / render layer:
   * table is created idempotently,
   * insert + query round-trip preserves all columns,
   * the ``[from, to]`` date filter excludes rows outside the window,
   * the CSV writer emits the documented header order and neutralises
     leading-``=`` formula-injection characters,
   * the JSON renderer produces the ``{count, events: [...]}`` envelope.

2. ``GET /api/admin/audit-export`` route hook on ``AppHandler``:
   * authn / admin role required,
   * org-membership check rejects an admin requesting a foreign org,
   * superadmin can export any org,
   * CSV is the default response, JSON is selected by ``format=json``
     and by ``Accept: application/json``.

3. T-015 rate-limit integration:
   * the second call within the configured window returns 429 with a
     ``Retry-After`` header.

The hook is installed at import time on ``AppHandler`` via the
end-of-file block in ``server_app.core`` so we exercise the same
surface a real HTTP client would hit.
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import server  # noqa: E402 — production import chain
from server_app.services import audit_export  # noqa: E402


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------


def _session(
    role: str = "admin",
    *,
    account_id: str = "acct_actor",
    org_id: str | None = None,
) -> dict[str, object]:
    return {
        "account": {
            "id": account_id,
            "email": f"{role}@example.test",
            "status": "active",
            "role": role,
            "org_id": org_id,
            "created_at": "2026-05-05T00:00:00Z",
            "deleted_at": None,
        }
    }


# ---------------------------------------------------------------------------
# HTTP stub handler (mirrors the StubHandler pattern in test_a2_schema.py)
# ---------------------------------------------------------------------------


class _StubHeaders:
    def __init__(self, mapping: dict[str, str] | None = None) -> None:
        self._data = {k.lower(): v for k, v in (mapping or {}).items()}

    def get(self, key: str, default: str = "") -> str:
        return self._data.get(key.lower(), default)


class _StubHandler:
    """Minimal AppHandler stand-in that captures the wire response."""

    def __init__(
        self,
        path: str,
        *,
        accept: str | None = None,
        cookie: str | None = None,
        client_ip: str = "127.0.0.1",
    ) -> None:
        headers: dict[str, str] = {}
        if accept is not None:
            headers["Accept"] = accept
        if cookie is not None:
            headers["Cookie"] = cookie
        self.path = path
        self.command = "GET"
        self.headers = _StubHeaders(headers)
        self.client_address = (client_ip, 0)
        self.rfile = io.BytesIO()
        self.wfile = io.BytesIO()
        self._response_status: int | None = None
        self._response_headers: list[tuple[str, str]] = []

    def send_response(self, status, message=None):  # noqa: D401, ANN001
        self._response_status = int(status)

    def send_header(self, name, value):  # noqa: D401, ANN001
        self._response_headers.append((str(name), str(value)))

    def end_headers(self):  # noqa: D401
        pass

    @property
    def status(self) -> int | None:
        return self._response_status

    def header(self, name: str) -> str | None:
        for key, value in self._response_headers:
            if key.lower() == name.lower():
                return value
        return None

    @property
    def body(self) -> bytes:
        return self.wfile.getvalue()

    def body_text(self) -> str:
        return self.body.decode("utf-8")

    def body_json(self) -> dict:
        raw = self.body_text()
        if not raw:
            return {}
        return json.loads(raw)


def _dispatch(handler: _StubHandler) -> None:
    """Invoke the same do_GET wrapper a real HTTP request would hit."""

    server.AppHandler.do_GET(handler)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Service-layer tests
# ---------------------------------------------------------------------------


class AuditExportServiceTests(unittest.TestCase):
    """Direct tests of ``server_app.services.audit_export``."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "auth.sqlite3"
        self.auth_db_patch = patch.object(server, "AUTH_DB_PATH", self.db_path)
        self.auth_db_patch.start()
        server.init_auth_store()
        with server.db_connection() as conn:
            audit_export.init_audit_events_table(conn)

    def tearDown(self) -> None:
        self.auth_db_patch.stop()
        self.tmpdir.cleanup()

    def test_table_created_idempotently(self) -> None:
        # Double-init must not throw and must not duplicate rows.
        with server.db_connection() as conn:
            audit_export.init_audit_events_table(conn)
            audit_export.init_audit_events_table(conn)
            tables = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        self.assertIn("audit_events", tables)

    def test_round_trip_preserves_columns(self) -> None:
        with server.db_connection() as conn:
            inserted = audit_export.record_audit_event(
                conn,
                org_id="Acme",
                event="login.success",
                account_id="acct_x",
                occurred_at="2026-05-10T12:00:00Z",
                source_ip="10.0.0.1",
                user_agent="curl/8.0",
                payload={"ip": "10.0.0.1", "ua": "curl"},
            )
            rows = audit_export.query_audit_events(
                conn,
                org_id="acme",
                from_date="2026-05-10",
                to_date="2026-05-10",
            )
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["id"], inserted["id"])
        # org_id is normalised to lower-case on insert.
        self.assertEqual(row["org_id"], "acme")
        self.assertEqual(row["account_id"], "acct_x")
        self.assertEqual(row["event"], "login.success")
        self.assertEqual(row["occurred_at"], "2026-05-10T12:00:00Z")
        self.assertEqual(row["payload"], {"ip": "10.0.0.1", "ua": "curl"})

    def test_date_filter_excludes_out_of_window_rows(self) -> None:
        with server.db_connection() as conn:
            for occurred_at in (
                "2026-05-01T00:00:00Z",
                "2026-05-05T12:00:00Z",
                "2026-05-10T23:59:00Z",
                "2026-05-11T00:00:01Z",
            ):
                audit_export.record_audit_event(
                    conn,
                    org_id="acme",
                    event="evt",
                    occurred_at=occurred_at,
                )
            rows = audit_export.query_audit_events(
                conn,
                org_id="acme",
                from_date="2026-05-05",
                to_date="2026-05-10",
            )
        kept = [r["occurred_at"] for r in rows]
        self.assertEqual(
            kept,
            ["2026-05-05T12:00:00Z", "2026-05-10T23:59:00Z"],
        )

    def test_query_rejects_bad_dates(self) -> None:
        with server.db_connection() as conn:
            with self.assertRaises(audit_export.AuditExportError):
                audit_export.query_audit_events(
                    conn, org_id="acme", from_date="bogus", to_date="2026-05-10"
                )
            with self.assertRaises(audit_export.AuditExportError):
                audit_export.query_audit_events(
                    conn, org_id="acme", from_date="2026-05-10", to_date="2026-05-01"
                )
            with self.assertRaises(audit_export.AuditExportError):
                audit_export.query_audit_events(
                    conn, org_id="", from_date="2026-05-01", to_date="2026-05-02"
                )

    def test_csv_header_order_and_payload_field(self) -> None:
        rows = [
            {
                "id": "ae_1",
                "org_id": "acme",
                "account_id": "acct_x",
                "event": "login.success",
                "occurred_at": "2026-05-10T12:00:00Z",
                "source_ip": "10.0.0.1",
                "user_agent": "curl/8.0",
                "payload": {"a": 1, "b": "two"},
            }
        ]
        text = audit_export.render_csv(rows)
        lines = text.splitlines()
        self.assertEqual(
            lines[0],
            "id,occurred_at,org_id,account_id,event,source_ip,user_agent,payload",
        )
        # Row 1 starts with the id and ends with the JSON payload column.
        self.assertTrue(lines[1].startswith("ae_1,2026-05-10T12:00:00Z,acme,acct_x"))
        self.assertIn('"{""a"": 1, ""b"": ""two""}"', lines[1])

    def test_csv_neutralises_formula_injection(self) -> None:
        rows = [
            {
                "id": "ae_2",
                "org_id": "acme",
                "account_id": "=cmd|' /C calc'!A0",  # classic attack
                "event": "+SUM(A1:A9)",
                "occurred_at": "2026-05-10T12:00:00Z",
                "source_ip": "-1.2.3.4",
                "user_agent": "@evil",
                "payload": {},
            }
        ]
        text = audit_export.render_csv(rows)
        # Every dangerous cell must be prefixed by a single quote.
        self.assertIn("'=cmd|", text)
        self.assertIn("'+SUM(A1:A9)", text)
        self.assertIn("'-1.2.3.4", text)
        self.assertIn("'@evil", text)

    def test_json_envelope_shape(self) -> None:
        rows = [
            {
                "id": "ae_1",
                "org_id": "acme",
                "account_id": "acct_x",
                "event": "login.success",
                "occurred_at": "2026-05-10T12:00:00Z",
                "source_ip": "",
                "user_agent": "",
                "payload": {"k": "v"},
            }
        ]
        out = audit_export.render_json(rows)
        self.assertEqual(out["count"], 1)
        self.assertEqual(len(out["events"]), 1)
        event = out["events"][0]
        for key in (
            "id",
            "org_id",
            "account_id",
            "event",
            "occurred_at",
            "source_ip",
            "user_agent",
            "payload",
        ):
            self.assertIn(key, event)


# ---------------------------------------------------------------------------
# Permission helper
# ---------------------------------------------------------------------------


class CanExportOrgTests(unittest.TestCase):
    def test_superadmin_allowed_for_any_org(self) -> None:
        self.assertTrue(
            audit_export.can_export_org(_session("superadmin"), "anyorg")
        )
        self.assertTrue(
            audit_export.can_export_org(_session("superadmin"), "OtherOrg")
        )

    def test_admin_allowed_only_for_own_org(self) -> None:
        actor = _session("admin", org_id="acme")
        self.assertTrue(audit_export.can_export_org(actor, "Acme"))
        self.assertFalse(audit_export.can_export_org(actor, "globex"))

    def test_admin_without_org_membership_is_denied(self) -> None:
        actor = _session("admin", org_id=None)
        self.assertFalse(audit_export.can_export_org(actor, "acme"))

    def test_user_role_denied(self) -> None:
        self.assertFalse(
            audit_export.can_export_org(
                _session("user", org_id="acme"), "acme"
            )
        )


# ---------------------------------------------------------------------------
# HTTP route tests
# ---------------------------------------------------------------------------


class AuditExportRouteTests(unittest.TestCase):
    """End-to-end tests of the T-043 admin route hook on ``AppHandler``."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "auth.sqlite3"
        self.auth_db_patch = patch.object(server, "AUTH_DB_PATH", self.db_path)
        self.auth_db_patch.start()
        server.init_auth_store()

        # Insert a stable corpus of events spanning two orgs + a date
        # window so each test can pull a known slice.
        with server.db_connection() as conn:
            audit_export.init_audit_events_table(conn)
            for occurred_at, event in (
                ("2026-05-01T00:00:00Z", "login.success"),
                ("2026-05-05T08:00:00Z", "login.failure"),
                ("2026-05-10T12:00:00Z", "seat.added"),
            ):
                audit_export.record_audit_event(
                    conn,
                    org_id="acme",
                    account_id="acct_acme_user",
                    event=event,
                    occurred_at=occurred_at,
                    source_ip="10.0.0.1",
                    user_agent="curl/8.0",
                    payload={"event": event},
                )
            # A noise row in a different org — must never appear in an
            # acme-scoped export.
            audit_export.record_audit_event(
                conn,
                org_id="globex",
                event="seat.added",
                occurred_at="2026-05-05T08:00:00Z",
                payload={"event": "seat.added"},
            )

        # Reset the shared in-process rate-limit buckets so the first
        # call of every test starts from a fresh bucket.
        server.RATE_LIMIT_BUCKETS.clear()
        # Explicit envs so the limit/window are deterministic in tests
        # AND tighter than the production default of 20/min.
        os.environ["AUDIT_EXPORT_RATE_LIMIT_PER_MINUTE"] = "1"
        os.environ["AUDIT_EXPORT_RATE_LIMIT_WINDOW_SECONDS"] = "60"

    def tearDown(self) -> None:
        self.auth_db_patch.stop()
        self.tmpdir.cleanup()
        os.environ.pop("AUDIT_EXPORT_RATE_LIMIT_PER_MINUTE", None)
        os.environ.pop("AUDIT_EXPORT_RATE_LIMIT_WINDOW_SECONDS", None)

    # ------------------------------------------------------------------ csv

    def test_admin_csv_export_returns_only_own_org(self) -> None:
        handler = _StubHandler(
            "/api/admin/audit-export?org_id=acme&from=2026-05-01&to=2026-05-10"
        )
        with patch.object(
            server,
            "require_admin_session",
            return_value=_session("admin", org_id="acme"),
        ):
            _dispatch(handler)
        self.assertEqual(handler.status, 200)
        self.assertEqual(
            handler.header("Content-Type"), "text/csv; charset=utf-8"
        )
        self.assertIn(
            'attachment; filename="audit-acme-2026-05-01-to-2026-05-10.csv"',
            handler.header("Content-Disposition") or "",
        )
        text = handler.body_text()
        lines = text.splitlines()
        # Header + 3 rows from the acme org. Zero rows from globex.
        self.assertEqual(len(lines), 4)
        self.assertEqual(
            lines[0],
            "id,occurred_at,org_id,account_id,event,source_ip,user_agent,payload",
        )
        for line in lines[1:]:
            self.assertIn(",acme,", line)
        self.assertNotIn("globex", text)

    # ------------------------------------------------------------------ json

    def test_json_via_accept_header(self) -> None:
        handler = _StubHandler(
            "/api/admin/audit-export?org_id=acme&from=2026-05-01&to=2026-05-10",
            accept="application/json",
        )
        with patch.object(
            server,
            "require_admin_session",
            return_value=_session("admin", org_id="acme"),
        ):
            _dispatch(handler)
        self.assertEqual(handler.status, 200)
        self.assertEqual(
            handler.header("Content-Type"), "application/json; charset=utf-8"
        )
        payload = handler.body_json()
        self.assertEqual(payload["count"], 3)
        self.assertEqual(len(payload["events"]), 3)
        events = sorted(e["event"] for e in payload["events"])
        self.assertEqual(
            events, ["login.failure", "login.success", "seat.added"]
        )
        for evt in payload["events"]:
            self.assertEqual(evt["org_id"], "acme")
            self.assertIsInstance(evt["payload"], dict)

    def test_json_via_format_param_wins_over_accept(self) -> None:
        handler = _StubHandler(
            "/api/admin/audit-export?org_id=acme&from=2026-05-01&to=2026-05-10&format=json",
            accept="text/csv",
        )
        with patch.object(
            server,
            "require_admin_session",
            return_value=_session("admin", org_id="acme"),
        ):
            _dispatch(handler)
        self.assertEqual(handler.status, 200)
        self.assertEqual(
            handler.header("Content-Type"), "application/json; charset=utf-8"
        )

    # ------------------------------------------------------------------ filtering

    def test_date_window_filters_rows(self) -> None:
        handler = _StubHandler(
            "/api/admin/audit-export?org_id=acme&from=2026-05-05&to=2026-05-09&format=json",
        )
        with patch.object(
            server,
            "require_admin_session",
            return_value=_session("admin", org_id="acme"),
        ):
            _dispatch(handler)
        self.assertEqual(handler.status, 200)
        payload = handler.body_json()
        # Only the 2026-05-05 event falls in [2026-05-05, 2026-05-09].
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["events"][0]["occurred_at"], "2026-05-05T08:00:00Z")

    # ------------------------------------------------------------------ permission

    def test_admin_denied_for_foreign_org(self) -> None:
        handler = _StubHandler(
            "/api/admin/audit-export?org_id=globex&from=2026-05-01&to=2026-05-10",
        )
        with patch.object(
            server,
            "require_admin_session",
            return_value=_session("admin", org_id="acme"),
        ):
            _dispatch(handler)
        self.assertEqual(handler.status, 403)
        self.assertEqual(handler.body_json()["error"], "forbidden")

    def test_superadmin_can_export_any_org(self) -> None:
        handler = _StubHandler(
            "/api/admin/audit-export?org_id=globex&from=2026-05-01&to=2026-05-10&format=json",
        )
        with patch.object(
            server,
            "require_admin_session",
            return_value=_session("superadmin"),
        ):
            _dispatch(handler)
        self.assertEqual(handler.status, 200)
        payload = handler.body_json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["events"][0]["org_id"], "globex")

    def test_non_admin_rejected_at_role_gate(self) -> None:
        # ``require_admin_session`` raises ApiError(403) for non-admins; we
        # simulate that by patching it to raise and asserting the route
        # surfaces the structured error.
        handler = _StubHandler(
            "/api/admin/audit-export?org_id=acme&from=2026-05-01&to=2026-05-10",
        )
        forbidden = server.ApiError(403, "admin_required", "Admin access is required.")
        with patch.object(server, "require_admin_session", side_effect=forbidden):
            _dispatch(handler)
        self.assertEqual(handler.status, 403)
        body = handler.body_json()
        self.assertEqual(body["error"]["code"], "admin_required")

    # ------------------------------------------------------------------ validation

    def test_bad_date_returns_400(self) -> None:
        handler = _StubHandler(
            "/api/admin/audit-export?org_id=acme&from=bogus&to=2026-05-10",
        )
        with patch.object(
            server,
            "require_admin_session",
            return_value=_session("admin", org_id="acme"),
        ):
            _dispatch(handler)
        self.assertEqual(handler.status, 400)
        self.assertIn("from", handler.body_json()["error"].lower())

    def test_missing_org_returns_400(self) -> None:
        handler = _StubHandler(
            "/api/admin/audit-export?from=2026-05-01&to=2026-05-10",
        )
        with patch.object(
            server,
            "require_admin_session",
            return_value=_session("admin", org_id="acme"),
        ):
            _dispatch(handler)
        self.assertEqual(handler.status, 400)
        self.assertIn("org_id", handler.body_json()["error"].lower())

    # ------------------------------------------------------------------ rate limit

    def test_second_call_within_window_returns_429(self) -> None:
        first = _StubHandler(
            "/api/admin/audit-export?org_id=acme&from=2026-05-01&to=2026-05-10",
        )
        second = _StubHandler(
            "/api/admin/audit-export?org_id=acme&from=2026-05-01&to=2026-05-10",
        )
        with patch.object(
            server,
            "require_admin_session",
            return_value=_session("admin", org_id="acme"),
        ):
            _dispatch(first)
            _dispatch(second)
        self.assertEqual(first.status, 200)
        self.assertEqual(second.status, 429)
        retry_after = second.header("Retry-After")
        self.assertIsNotNone(retry_after)
        self.assertGreaterEqual(int(retry_after), 1)

    def test_rate_limit_keyed_per_session(self) -> None:
        """Two different sessions must NOT share a rate-limit bucket."""

        first = _StubHandler(
            "/api/admin/audit-export?org_id=acme&from=2026-05-01&to=2026-05-10",
            cookie="a2_session=alpha",
        )
        second = _StubHandler(
            "/api/admin/audit-export?org_id=acme&from=2026-05-01&to=2026-05-10",
            cookie="a2_session=beta",
            client_ip="10.0.0.99",
        )
        with patch.object(
            server,
            "require_admin_session",
            return_value=_session("admin", org_id="acme"),
        ):
            _dispatch(first)
            _dispatch(second)
        self.assertEqual(first.status, 200)
        self.assertEqual(second.status, 200)


if __name__ == "__main__":
    unittest.main()
