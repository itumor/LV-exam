"""Unit tests for T-044 — white-label tenant resolution + theme.

Covers the deliverables from the T-044 plan:
- (a) ``resolve_tenant(host_header)`` returns the expected tenant config
  for the bundled examples (default + acme-school),
- (b) custom_domains DB lookup wins over the JSON ``host_aliases`` list,
- (c) fallback chain: env override -> DB -> host_aliases -> default,
- (d) ``build_css_variables`` emits the keys the v2 SPA expects,
- (e) the HTTP ``GET /api/tenant`` endpoint serves the resolved config,
- (f) malformed / missing tenant files degrade gracefully to the default.
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

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server  # noqa: E402  -- exercises the production import chain
from server_app.services import tenant  # noqa: E402


# ---------------------------------------------------------------------------
# Direct service tests — no HTTP, no DB unless explicitly opened.
# ---------------------------------------------------------------------------


class TenantConfigLoadTests(unittest.TestCase):
    """``load_tenant_file`` + the bundled ``tenants/*.json`` files."""

    def test_default_tenant_loads(self) -> None:
        cfg = tenant.load_tenant_file(tenant.DEFAULT_TENANT_ID)
        self.assertIsNotNone(cfg)
        assert cfg is not None  # for type checker
        self.assertEqual(cfg.id, "default")
        self.assertEqual(cfg.name, "lvcodex")
        # Default primary colour must be a valid CSS hex literal.
        self.assertRegex(cfg.primary_color, r"^#[0-9a-fA-F]{3,8}$")
        # Default tenant always claims ``localhost`` so local previews work.
        self.assertIn("localhost", cfg.host_aliases)

    def test_acme_school_tenant_loads(self) -> None:
        cfg = tenant.load_tenant_file("acme-school")
        self.assertIsNotNone(cfg)
        assert cfg is not None
        self.assertEqual(cfg.id, "acme-school")
        self.assertEqual(cfg.primary_color, "#dc2626")
        self.assertEqual(cfg.custom_domain, "exam.acme-school.example")

    def test_missing_tenant_returns_none(self) -> None:
        self.assertIsNone(tenant.load_tenant_file("does-not-exist"))

    def test_invalid_tenant_id_returns_none(self) -> None:
        # Capital letters + slashes are rejected outright.
        self.assertIsNone(tenant.load_tenant_file("BadID"))
        self.assertIsNone(tenant.load_tenant_file("../etc/passwd"))

    def test_list_tenants_includes_bundled_examples(self) -> None:
        ids = {t.id for t in tenant.list_tenants()}
        self.assertIn("default", ids)
        self.assertIn("acme-school", ids)

    def test_get_tenant_falls_back_to_default(self) -> None:
        cfg = tenant.get_tenant("does-not-exist")
        self.assertEqual(cfg.id, "default")


class TenantConfigFromTempDirTests(unittest.TestCase):
    """Force-load a tenant from a temp dir to test malformed-JSON behaviour."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tenant_dir = Path(self.tmpdir.name)
        # ``example.json`` is the on-disk filename for the default tenant.
        (self.tenant_dir / "example.json").write_text(
            json.dumps({
                "id": "default",
                "name": "Temp Default",
                "primary_color": "#abcdef",
                "host_aliases": ["temp-default.example"],
            }),
            encoding="utf-8",
        )
        # A malformed JSON file: must NOT crash list_tenants() / get_tenant.
        (self.tenant_dir / "broken.json").write_text(
            "{not valid json", encoding="utf-8"
        )
        # A file with mismatched id-vs-filename: must be rejected.
        (self.tenant_dir / "mismatch.json").write_text(
            json.dumps({"id": "actually-something-else", "name": "x",
                        "primary_color": "#aaaaaa"}),
            encoding="utf-8",
        )
        self._dir_patch = patch.object(tenant, "TENANT_DIR", self.tenant_dir)
        self._dir_patch.start()
        # Cached loads from the real ``tenants/`` dir must be invalidated.
        tenant._TENANT_CACHE.clear()

    def tearDown(self) -> None:
        self._dir_patch.stop()
        tenant._TENANT_CACHE.clear()
        self.tmpdir.cleanup()

    def test_malformed_json_does_not_crash(self) -> None:
        self.assertIsNone(tenant.load_tenant_file("broken"))

    def test_mismatched_id_is_rejected(self) -> None:
        self.assertIsNone(tenant.load_tenant_file("mismatch"))

    def test_resolve_falls_back_when_alias_unknown(self) -> None:
        cfg = tenant.resolve_tenant("totally.unknown.host")
        self.assertEqual(cfg.id, "default")
        self.assertEqual(cfg.primary_color, "#abcdef")


class TenantCssVariableTests(unittest.TestCase):
    """``build_css_variables`` emits the keys the v2 SPA expects."""

    def test_keys_match_spa_stylesheet(self) -> None:
        cfg = tenant.get_tenant("acme-school")
        vars_ = tenant.build_css_variables(cfg)
        # These variables are declared in apps/web-v2/src/styles.css and
        # consumed by ``useTenant`` to repaint the document.
        for key in (
            "--color-accent",
            "--color-accent-hover",
            "--color-bg",
            "--color-text",
            "--tenant-id",
            "--tenant-name",
        ):
            self.assertIn(key, vars_)
        self.assertEqual(vars_["--color-accent"], "#dc2626")
        self.assertEqual(vars_["--tenant-id"], "acme-school")
        self.assertEqual(vars_["--tenant-name"], "ACME Language School")

    def test_payload_serialization_includes_css_variables(self) -> None:
        cfg = tenant.get_tenant("default")
        payload = tenant.tenant_to_dict(cfg)
        self.assertIn("css_variables", payload)
        # Every CSS var key must be a string and start with the ``--`` prefix.
        for k, v in payload["css_variables"].items():
            self.assertTrue(k.startswith("--"), f"bad key: {k}")
            self.assertIsInstance(v, str)


# ---------------------------------------------------------------------------
# resolve_tenant + custom_domains table tests
# ---------------------------------------------------------------------------


class ResolveTenantTests(unittest.TestCase):
    """resolve_tenant fallback chain: env -> DB -> aliases -> default."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "auth.sqlite3"
        self.auth_db_patch = patch.object(server, "AUTH_DB_PATH", self.db_path)
        self.auth_db_patch.start()
        server.init_auth_store()
        # Ensure no stale env override leaks between tests.
        self._old_force = os.environ.pop("LVCODEX_FORCE_TENANT", None)

    def tearDown(self) -> None:
        if self._old_force is not None:
            os.environ["LVCODEX_FORCE_TENANT"] = self._old_force
        else:
            os.environ.pop("LVCODEX_FORCE_TENANT", None)
        self.auth_db_patch.stop()
        self.tmpdir.cleanup()

    def test_host_alias_resolves_to_acme(self) -> None:
        cfg = tenant.resolve_tenant("exam.acme-school.example")
        self.assertEqual(cfg.id, "acme-school")

    def test_unknown_host_falls_back_to_default(self) -> None:
        cfg = tenant.resolve_tenant("unknown.example.com")
        self.assertEqual(cfg.id, "default")

    def test_blank_host_falls_back_to_default(self) -> None:
        self.assertEqual(tenant.resolve_tenant("").id, "default")
        self.assertEqual(tenant.resolve_tenant(None).id, "default")

    def test_host_normalisation_strips_port_and_lowercases(self) -> None:
        cfg = tenant.resolve_tenant("EXAM.ACME-school.example:8443")
        self.assertEqual(cfg.id, "acme-school")

    def test_force_env_override_wins(self) -> None:
        os.environ["LVCODEX_FORCE_TENANT"] = "acme-school"
        cfg = tenant.resolve_tenant("totally.unrelated.host")
        self.assertEqual(cfg.id, "acme-school")

    def test_force_env_override_invalid_id_falls_through(self) -> None:
        os.environ["LVCODEX_FORCE_TENANT"] = "BAD::id"
        cfg = tenant.resolve_tenant("totally.unrelated.host")
        # Bad override is ignored, so the host-alias / default chain runs.
        self.assertEqual(cfg.id, "default")

    def test_custom_domain_db_lookup_wins_over_aliases(self) -> None:
        with server.db_connection() as conn:
            tenant.register_custom_domain(conn, "branded.example.com", "acme-school")
            cfg = tenant.resolve_tenant("branded.example.com", conn=conn)
        self.assertEqual(cfg.id, "acme-school")

    def test_custom_domain_db_lookup_overrides_default_alias(self) -> None:
        # ``localhost`` is a host_alias of the default tenant. A custom_domains
        # row should override it.
        with server.db_connection() as conn:
            tenant.register_custom_domain(conn, "localhost", "acme-school")
            cfg = tenant.resolve_tenant("localhost", conn=conn)
        self.assertEqual(cfg.id, "acme-school")

    def test_remove_custom_domain_restores_default(self) -> None:
        with server.db_connection() as conn:
            tenant.register_custom_domain(conn, "to-remove.example", "acme-school")
            removed = tenant.remove_custom_domain(conn, "to-remove.example")
            cfg = tenant.resolve_tenant("to-remove.example", conn=conn)
        self.assertTrue(removed)
        self.assertEqual(cfg.id, "default")

    def test_register_custom_domain_rejects_invalid_tenant_id(self) -> None:
        with server.db_connection() as conn:
            with self.assertRaises(ValueError):
                tenant.register_custom_domain(conn, "x.example", "BAD!ID")

    def test_register_custom_domain_rejects_blank_host(self) -> None:
        with server.db_connection() as conn:
            with self.assertRaises(ValueError):
                tenant.register_custom_domain(conn, "", "acme-school")

    def test_register_custom_domain_updates_existing_row(self) -> None:
        with server.db_connection() as conn:
            tenant.register_custom_domain(conn, "shared.example", "default")
            tenant.register_custom_domain(conn, "shared.example", "acme-school")
            cfg = tenant.resolve_tenant("shared.example", conn=conn)
        self.assertEqual(cfg.id, "acme-school")


# ---------------------------------------------------------------------------
# HTTP-level test against the GET /api/tenant hook installed in core.py.
# ---------------------------------------------------------------------------


class _StubHandler:
    """Minimal AppHandler stand-in that records the response.

    Mirrors the stub used by tests/server/test_exam_versions.py so we
    exercise the same dispatch chain (rate-limit -> metrics -> debug ->
    tenant) that production runs.
    """

    def __init__(self, path: str, *, host: str | None = None) -> None:
        self.path = path
        self.command = "GET"
        self.client_address = ("127.0.0.1", 0)
        self.headers: dict[str, str] = {}
        if host is not None:
            self.headers["Host"] = host
        self.rfile = io.BytesIO(b"")
        self.wfile = io.BytesIO()
        self.responses: list[int] = []
        self.headers_out: list[tuple[str, str]] = []

    def send_response(self, code, message=None):
        self.responses.append(int(code))

    def send_header(self, key, value):
        self.headers_out.append((str(key), str(value)))

    def end_headers(self):
        pass

    def get_status(self) -> int:
        return self.responses[0] if self.responses else 0

    def get_body(self) -> dict:
        return json.loads(self.wfile.getvalue().decode("utf-8"))


class TenantHttpRouteTests(unittest.TestCase):
    """End-to-end tests of the ``GET /api/tenant`` hook."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "auth.sqlite3"
        self.auth_db_patch = patch.object(server, "AUTH_DB_PATH", self.db_path)
        self.auth_db_patch.start()
        server.init_auth_store()
        self._old_force = os.environ.pop("LVCODEX_FORCE_TENANT", None)

    def tearDown(self) -> None:
        if self._old_force is not None:
            os.environ["LVCODEX_FORCE_TENANT"] = self._old_force
        else:
            os.environ.pop("LVCODEX_FORCE_TENANT", None)
        self.auth_db_patch.stop()
        self.tmpdir.cleanup()

    def test_get_api_tenant_returns_default_for_unknown_host(self) -> None:
        handler = _StubHandler("/api/tenant", host="unknown.example.com")
        server.AppHandler.do_GET(handler)  # type: ignore[arg-type]
        self.assertEqual(handler.get_status(), 200)
        body = handler.get_body()
        self.assertEqual(body["id"], "default")
        self.assertIn("css_variables", body)
        self.assertIn("--color-accent", body["css_variables"])

    def test_get_api_tenant_returns_acme_for_alias(self) -> None:
        handler = _StubHandler("/api/tenant", host="exam.acme-school.example")
        server.AppHandler.do_GET(handler)  # type: ignore[arg-type]
        self.assertEqual(handler.get_status(), 200)
        body = handler.get_body()
        self.assertEqual(body["id"], "acme-school")
        self.assertEqual(body["primary_color"], "#dc2626")

    def test_get_api_tenant_respects_db_mapping(self) -> None:
        with server.db_connection() as conn:
            tenant.register_custom_domain(conn, "schoolportal.example", "acme-school")
        handler = _StubHandler("/api/tenant", host="schoolportal.example")
        server.AppHandler.do_GET(handler)  # type: ignore[arg-type]
        self.assertEqual(handler.get_status(), 200)
        body = handler.get_body()
        self.assertEqual(body["id"], "acme-school")

    def test_get_api_tenant_handles_missing_host_header(self) -> None:
        handler = _StubHandler("/api/tenant")
        server.AppHandler.do_GET(handler)  # type: ignore[arg-type]
        self.assertEqual(handler.get_status(), 200)
        body = handler.get_body()
        # No Host header -> default tenant.
        self.assertEqual(body["id"], "default")

    def test_get_api_tenant_emits_application_json(self) -> None:
        handler = _StubHandler("/api/tenant", host="unknown.example.com")
        server.AppHandler.do_GET(handler)  # type: ignore[arg-type]
        content_types = [v for k, v in handler.headers_out
                         if k.lower() == "content-type"]
        self.assertTrue(content_types, "no Content-Type header emitted")
        self.assertTrue(
            any("application/json" in v for v in content_types),
            f"Content-Type should be JSON, got: {content_types}",
        )

    def test_get_api_tenant_payload_shape(self) -> None:
        handler = _StubHandler("/api/tenant", host="unknown.example.com")
        server.AppHandler.do_GET(handler)  # type: ignore[arg-type]
        body = handler.get_body()
        for required_key in (
            "id", "name", "primary_color", "secondary_color",
            "background_color", "text_color", "logo_url", "favicon_url",
            "support_email", "custom_domain", "host_aliases", "css_variables",
        ):
            self.assertIn(required_key, body, f"missing key {required_key}")


# ---------------------------------------------------------------------------
# Route module audit hook — ensures /api/tenant is registered in the
# modularization audit list assembled by server_app.routes.__init__.
# ---------------------------------------------------------------------------


class TenantRouteModuleTests(unittest.TestCase):
    """The tenant route must appear in server_app.routes.ROUTES."""

    def test_route_registered_in_audit_list(self) -> None:
        from server_app.routes import ROUTES

        documented = {(m, p) for m, p, _o in ROUTES}
        self.assertIn(("GET", "/api/tenant"), documented)

    def test_route_owner_is_tenant_module(self) -> None:
        from server_app.routes import ROUTES

        owners = {
            (m, p): owner for m, p, owner in ROUTES
        }
        self.assertEqual(owners[("GET", "/api/tenant")], "tenant")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
