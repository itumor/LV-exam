"""Unit tests for T-065 — data residency + branded portal subdomain.

Covers the deliverables from the T-065 plan:

* (a) ``TenantConfig`` exposes ``data_region`` + ``portal_subdomain``;
* (b) tenant JSON loads the new fields, coercing invalid values to the
      safe default;
* (c) the residency service pins storage + DB per region and honours
      the ``LVCODEX_STORAGE_ROOT_*`` / ``LVCODEX_DB_URL_*`` env vars;
* (d) cross-region access raises :class:`DataResidencyError`;
* (e) the Fly-region guard rejects a request that landed in the wrong
      region for the resolved tenant;
* (f) ``resolve_tenant`` matches a branded portal subdomain (e.g.
      ``gov-lv.lvcodex.com`` -> ``gov-lv`` tenant);
* (g) ``resolve_tenant_by_subdomain`` direct lookup for admin previewer.
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

import server  # noqa: E402 — exercises the production import chain
from server_app.services import tenant, residency  # noqa: E402
from server_app.services.residency import DataResidencyError  # noqa: E402


# ---------------------------------------------------------------------------
# TenantConfig data_region + portal_subdomain field tests
# ---------------------------------------------------------------------------


class TenantConfigResidencyFieldsTests(unittest.TestCase):
    """Bundled tenant configs populate the new fields with sane defaults."""

    def test_default_tenant_has_eu_region(self) -> None:
        cfg = tenant.get_tenant(tenant.DEFAULT_TENANT_ID)
        self.assertEqual(cfg.data_region, "eu")
        self.assertIsNone(cfg.portal_subdomain)

    def test_acme_tenant_declares_subdomain(self) -> None:
        cfg = tenant.get_tenant("acme-school")
        self.assertEqual(cfg.data_region, "eu")
        self.assertEqual(cfg.portal_subdomain, "acme")

    def test_gov_lv_tenant_is_lv_only(self) -> None:
        cfg = tenant.get_tenant("gov-lv")
        self.assertEqual(cfg.id, "gov-lv")
        self.assertEqual(cfg.data_region, "lv-only")
        self.assertEqual(cfg.portal_subdomain, "gov-lv")

    def test_tenant_dict_includes_new_fields(self) -> None:
        cfg = tenant.get_tenant("gov-lv")
        payload = tenant.tenant_to_dict(cfg)
        self.assertEqual(payload["data_region"], "lv-only")
        self.assertEqual(payload["portal_subdomain"], "gov-lv")

    def test_invalid_data_region_collapses_to_eu(self) -> None:
        # An unknown tag never silently becomes ``lv-only`` — that would
        # be a fail-OPEN posture. We coerce to ``eu`` (safe default).
        cfg = tenant.TenantConfig(
            id="x", name="X", primary_color="#abcdef", data_region="moon"
        )
        self.assertEqual(cfg.data_region, "eu")

    def test_invalid_portal_subdomain_drops_to_none(self) -> None:
        cfg = tenant.TenantConfig(
            id="x", name="X", primary_color="#abcdef",
            portal_subdomain="not.a.subdomain",
        )
        # The constructor accepts whatever the loader passes, but the
        # loader's coercion is what enforces the regex.
        self.assertEqual(
            tenant._coerce_portal_subdomain("not.a.subdomain"), None,
        )
        self.assertEqual(
            tenant._coerce_portal_subdomain("UPPER"), "upper",
        )
        self.assertIsNone(tenant._coerce_portal_subdomain("-leading"))
        self.assertIsNone(tenant._coerce_portal_subdomain("trailing-"))


class TenantFileLoadResidencyTests(unittest.TestCase):
    """Loader honours / coerces residency + subdomain fields on disk."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tenant_dir = Path(self.tmpdir.name)
        (self.tenant_dir / "example.json").write_text(
            json.dumps({
                "id": "default",
                "name": "Temp Default",
                "primary_color": "#abcdef",
                "host_aliases": ["temp.example"],
                "data_region": "eu",
                "portal_subdomain": None,
            }),
            encoding="utf-8",
        )
        (self.tenant_dir / "bad-region.json").write_text(
            json.dumps({
                "id": "bad-region",
                "name": "Bad Region",
                "primary_color": "#abcdef",
                "data_region": "antarctica",
            }),
            encoding="utf-8",
        )
        (self.tenant_dir / "lv-secret.json").write_text(
            json.dumps({
                "id": "lv-secret",
                "name": "LV Secret",
                "primary_color": "#abcdef",
                "data_region": "lv-only",
                "portal_subdomain": "lv-secret",
            }),
            encoding="utf-8",
        )
        self._dir_patch = patch.object(tenant, "TENANT_DIR", self.tenant_dir)
        self._dir_patch.start()
        tenant._TENANT_CACHE.clear()

    def tearDown(self) -> None:
        self._dir_patch.stop()
        tenant._TENANT_CACHE.clear()
        self.tmpdir.cleanup()

    def test_unknown_region_coerces_to_eu(self) -> None:
        cfg = tenant.load_tenant_file("bad-region")
        self.assertIsNotNone(cfg)
        assert cfg is not None
        self.assertEqual(cfg.data_region, "eu")

    def test_lv_only_region_is_preserved(self) -> None:
        cfg = tenant.load_tenant_file("lv-secret")
        self.assertIsNotNone(cfg)
        assert cfg is not None
        self.assertEqual(cfg.data_region, "lv-only")
        self.assertEqual(cfg.portal_subdomain, "lv-secret")


# ---------------------------------------------------------------------------
# Portal subdomain resolution via Host: header
# ---------------------------------------------------------------------------


class PortalSubdomainResolutionTests(unittest.TestCase):
    """resolve_tenant + resolve_tenant_by_subdomain wire up the new field."""

    def setUp(self) -> None:
        self._old_force = os.environ.pop("LVCODEX_FORCE_TENANT", None)

    def tearDown(self) -> None:
        if self._old_force is not None:
            os.environ["LVCODEX_FORCE_TENANT"] = self._old_force
        else:
            os.environ.pop("LVCODEX_FORCE_TENANT", None)

    def test_resolve_tenant_matches_portal_subdomain_against_parent(self) -> None:
        cfg = tenant.resolve_tenant("gov-lv.lvcodex.com")
        self.assertEqual(cfg.id, "gov-lv")

    def test_resolve_tenant_matches_acme_subdomain(self) -> None:
        # ``acme.localhost`` should resolve to acme-school because the
        # default tenant declares ``localhost`` as a host_alias.
        cfg = tenant.resolve_tenant("acme.localhost")
        self.assertEqual(cfg.id, "acme-school")

    def test_resolve_tenant_rejects_subdomain_on_unknown_parent(self) -> None:
        # ``gov-lv.evil.example`` must NOT resolve to gov-lv — the
        # parent is not a platform host.
        cfg = tenant.resolve_tenant("gov-lv.evil.example")
        self.assertEqual(cfg.id, "default")

    def test_resolve_tenant_by_subdomain_direct_lookup(self) -> None:
        cfg = tenant.resolve_tenant_by_subdomain("gov-lv")
        self.assertIsNotNone(cfg)
        assert cfg is not None
        self.assertEqual(cfg.id, "gov-lv")

    def test_resolve_tenant_by_subdomain_unknown_returns_none(self) -> None:
        self.assertIsNone(tenant.resolve_tenant_by_subdomain("nope"))

    def test_resolve_tenant_by_subdomain_rejects_invalid_label(self) -> None:
        self.assertIsNone(tenant.resolve_tenant_by_subdomain(""))
        self.assertIsNone(tenant.resolve_tenant_by_subdomain("bad..label"))
        self.assertIsNone(tenant.resolve_tenant_by_subdomain("-bad"))

    def test_resolve_tenant_subdomain_is_case_insensitive(self) -> None:
        cfg = tenant.resolve_tenant("GOV-LV.LVCodex.com")
        self.assertEqual(cfg.id, "gov-lv")

    def test_resolve_tenant_explicit_alias_wins_over_subdomain(self) -> None:
        # ``exam.acme-school.example`` is an explicit alias of acme-school
        # AND would not match the subdomain rule (parent is not a default
        # alias). The explicit alias must still win.
        cfg = tenant.resolve_tenant("exam.acme-school.example")
        self.assertEqual(cfg.id, "acme-school")


# ---------------------------------------------------------------------------
# Residency service — storage + DB pinning per region
# ---------------------------------------------------------------------------


class StoragePinningTests(unittest.TestCase):
    """tenant_storage_root + storage_root respect the env override and region."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmpdir.name)
        self._cleanup_env = {}
        for var in residency.REGION_STORAGE_ENV_VARS.values():
            self._cleanup_env[var] = os.environ.pop(var, None)

    def tearDown(self) -> None:
        for var, value in self._cleanup_env.items():
            if value is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = value
        self.tmpdir.cleanup()

    def test_storage_root_uses_default_layout_when_env_unset(self) -> None:
        root = residency.storage_root("eu")
        self.assertTrue(str(root).endswith("/data/eu"))
        self.assertTrue(root.is_dir())

    def test_storage_root_honours_env_override(self) -> None:
        override = self.tmp_path / "eu-storage"
        os.environ["LVCODEX_STORAGE_ROOT_EU"] = str(override)
        root = residency.storage_root("eu")
        self.assertEqual(root, override.resolve())
        self.assertTrue(root.is_dir())

    def test_tenant_storage_root_pins_to_region_subdir(self) -> None:
        # Acme is EU; gov-lv is lv-only — they MUST land in different
        # storage trees so neither can read the other.
        acme_root = residency.tenant_storage_root("acme-school")
        gov_root = residency.tenant_storage_root("gov-lv")
        self.assertIn("/eu/", str(acme_root))
        self.assertIn("/lv-only/", str(gov_root))
        # The lv-only path must NOT collapse to ``data/eu/...``.
        self.assertNotIn("/eu/", str(gov_root))

    def test_tenant_storage_root_per_tenant_subdir(self) -> None:
        root = residency.tenant_storage_root("gov-lv")
        self.assertTrue(str(root).endswith("/lv-only/gov-lv"))

    def test_unknown_region_string_collapses_to_eu(self) -> None:
        # A direct call with an unknown string falls back to ``eu`` so
        # mis-typed callers cannot widen the allowed set.
        root = residency.storage_root("moon")
        self.assertTrue(str(root).endswith("/data/eu"))


class DbPinningTests(unittest.TestCase):
    """tenant_db_url honours the LVCODEX_DB_URL_<REGION> env vars."""

    def setUp(self) -> None:
        self._old = {}
        for var in list(residency.REGION_DB_ENV_VARS.values()) + ["DATABASE_URL"]:
            self._old[var] = os.environ.pop(var, None)

    def tearDown(self) -> None:
        for var, value in self._old.items():
            if value is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = value

    def test_eu_tenant_uses_database_url_when_no_eu_override(self) -> None:
        os.environ["DATABASE_URL"] = "postgres://pg.fra.example/db"
        self.assertEqual(
            residency.tenant_db_url("acme-school"),
            "postgres://pg.fra.example/db",
        )

    def test_lv_only_tenant_does_not_inherit_database_url(self) -> None:
        # A government tenant must NEVER silently fall back to the EU
        # DATABASE_URL. The pinned env var must be explicit.
        os.environ["DATABASE_URL"] = "postgres://pg.fra.example/db"
        self.assertIsNone(residency.tenant_db_url("gov-lv"))

    def test_lv_only_tenant_uses_lv_url(self) -> None:
        os.environ["LVCODEX_DB_URL_LV_ONLY"] = "postgres://pg.lv.example/db"
        self.assertEqual(
            residency.tenant_db_url("gov-lv"),
            "postgres://pg.lv.example/db",
        )

    def test_us_tenant_uses_us_url(self) -> None:
        os.environ["LVCODEX_DB_URL_US"] = "postgres://pg.iad.example/db"
        # We don't have a US tenant config bundled; build one inline.
        cfg = tenant.TenantConfig(
            id="acme-us", name="ACME US", primary_color="#abcdef",
            data_region="us",
        )
        self.assertEqual(
            residency.tenant_db_url(cfg),
            "postgres://pg.iad.example/db",
        )


# ---------------------------------------------------------------------------
# Fly region guard + cross-region rejection
# ---------------------------------------------------------------------------


class FlyRegionGuardTests(unittest.TestCase):
    """fly_region_allowed + resolve_residency_for_request enforce the pool."""

    def setUp(self) -> None:
        self._old_region = os.environ.pop("FLY_REGION", None)

    def tearDown(self) -> None:
        if self._old_region is not None:
            os.environ["FLY_REGION"] = self._old_region
        else:
            os.environ.pop("FLY_REGION", None)

    def test_eu_tenant_in_fra_is_allowed(self) -> None:
        self.assertTrue(residency.fly_region_allowed("acme-school", "fra"))
        self.assertTrue(residency.fly_region_allowed("acme-school", "lhr"))

    def test_eu_tenant_in_iad_is_rejected(self) -> None:
        self.assertFalse(residency.fly_region_allowed("acme-school", "iad"))

    def test_lv_only_tenant_outside_waw_is_rejected(self) -> None:
        self.assertFalse(residency.fly_region_allowed("gov-lv", "fra"))
        self.assertFalse(residency.fly_region_allowed("gov-lv", "lhr"))
        self.assertFalse(residency.fly_region_allowed("gov-lv", "iad"))

    def test_lv_only_tenant_in_waw_is_allowed(self) -> None:
        self.assertTrue(residency.fly_region_allowed("gov-lv", "waw"))

    def test_empty_fly_region_is_permissive(self) -> None:
        # Running outside Fly (tests, dev box) — the residency contract
        # is enforced by the data layer in that case, not the network
        # edge. Otherwise no test could ever execute.
        self.assertTrue(residency.fly_region_allowed("gov-lv", ""))
        self.assertTrue(residency.fly_region_allowed("gov-lv", None))

    def test_resolve_residency_rejects_gov_lv_in_fra(self) -> None:
        with self.assertRaises(DataResidencyError) as ctx:
            residency.resolve_residency_for_request(
                "gov-lv.lvcodex.com", fly_region="fra",
            )
        self.assertEqual(ctx.exception.tenant_id, "gov-lv")
        self.assertEqual(ctx.exception.expected_region, "lv-only")
        self.assertEqual(ctx.exception.actual_region, "fra")
        self.assertEqual(ctx.exception.reason, "unsupported_fly_region")

    def test_resolve_residency_allows_gov_lv_in_waw(self) -> None:
        summary = residency.resolve_residency_for_request(
            "gov-lv.lvcodex.com", fly_region="waw",
        )
        self.assertEqual(summary["tenant_id"], "gov-lv")
        self.assertEqual(summary["data_region"], "lv-only")
        self.assertEqual(summary["fly_region"], "waw")

    def test_resolve_residency_default_tenant_skips_region_check(self) -> None:
        # The default tenant is permitted everywhere — otherwise an
        # operator change to ``FLY_REGION=sin`` would 500 every
        # unauthenticated request to ``/api/tenant``.
        summary = residency.resolve_residency_for_request(
            "unknown.example.com", fly_region="sin",
        )
        self.assertEqual(summary["tenant_id"], "default")


class CrossRegionRejectionTests(unittest.TestCase):
    """assert_same_region refuses an EU-region tenant reading lv-only data."""

    def test_same_region_is_allowed(self) -> None:
        residency.assert_same_region("acme-school", "acme-school")  # no raise

    def test_eu_admin_cannot_touch_lv_only_tenant(self) -> None:
        with self.assertRaises(DataResidencyError) as ctx:
            residency.assert_same_region("acme-school", "gov-lv")
        self.assertEqual(ctx.exception.tenant_id, "gov-lv")
        self.assertEqual(ctx.exception.expected_region, "lv-only")
        self.assertEqual(ctx.exception.actual_region, "eu")
        self.assertEqual(ctx.exception.reason, "cross_region_access")

    def test_lv_only_cannot_touch_eu_tenant(self) -> None:
        with self.assertRaises(DataResidencyError):
            residency.assert_same_region("gov-lv", "acme-school")

    def test_default_tenant_cannot_touch_lv_only_tenant(self) -> None:
        # The default tenant is EU; gov-lv is lv-only — even a public
        # surface check must refuse to merge their data layers.
        with self.assertRaises(DataResidencyError):
            residency.assert_same_region("default", "gov-lv")


class ResidencySummaryTests(unittest.TestCase):
    """residency_for_tenant exposes the operator-visible posture."""

    def test_gov_lv_summary(self) -> None:
        summary = residency.residency_for_tenant("gov-lv")
        self.assertEqual(summary["data_region"], "lv-only")
        self.assertEqual(summary["fly_regions"], ["waw"])
        self.assertEqual(summary["portal_subdomain"], "gov-lv")
        self.assertIn("/lv-only/gov-lv", summary["storage_root"])

    def test_default_tenant_summary(self) -> None:
        summary = residency.residency_for_tenant(tenant.DEFAULT_TENANT_ID)
        self.assertEqual(summary["data_region"], "eu")
        self.assertCountEqual(summary["fly_regions"], ["fra", "lhr"])
        self.assertIsNone(summary["portal_subdomain"])


# ---------------------------------------------------------------------------
# HTTP-level test against GET /api/tenant — residency fields surfaced
# ---------------------------------------------------------------------------


class _StubHandler:
    """Minimal AppHandler stand-in mirroring test_tenant.py."""

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


class TenantApiResidencyShapeTests(unittest.TestCase):
    """The ``GET /api/tenant`` response carries the new fields."""

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

    def test_default_response_includes_eu_region(self) -> None:
        handler = _StubHandler("/api/tenant", host="unknown.example.com")
        server.AppHandler.do_GET(handler)  # type: ignore[arg-type]
        body = handler.get_body()
        self.assertEqual(body["data_region"], "eu")
        self.assertIsNone(body["portal_subdomain"])

    def test_gov_lv_resolution_via_subdomain(self) -> None:
        handler = _StubHandler("/api/tenant", host="gov-lv.lvcodex.com")
        server.AppHandler.do_GET(handler)  # type: ignore[arg-type]
        body = handler.get_body()
        self.assertEqual(body["id"], "gov-lv")
        self.assertEqual(body["data_region"], "lv-only")
        self.assertEqual(body["portal_subdomain"], "gov-lv")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
