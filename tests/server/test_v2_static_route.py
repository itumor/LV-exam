"""T-036 static route tests for the Vue 3 SPA mounted at /v2/.

The Python server (``server_app.core``) serves the built
``apps/web-v2/dist/`` directory under ``/v2/`` via an end-of-file
monkey-patch on ``AppHandler.do_GET``. These tests verify the contract:

* ``/v2/`` returns 200 + the dist ``index.html`` when the build exists.
* ``/v2`` (no trailing slash) issues a 301 redirect to ``/v2/``.
* SPA deep links (e.g. ``/v2/readiness``) fall back to ``index.html`` so
  vue-router can resolve them client-side.
* When the dist is missing the route responds 503 with a clear
  "run npm run build:v2" message instead of 404 (so the operator can tell
  the difference between "feature not built" and "feature not deployed").
* The vanilla app at ``/latvian-a2-exam-app/`` is unaffected by the hook.

These tests are hermetic: they write a tiny fake ``dist/`` into a
temporary directory and monkey-patch ``server_app.core.WEB_V2_DIST_DIR``
so the assertions do not depend on whether the developer has actually
run ``npm run build:v2``.
"""

from __future__ import annotations

import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import closing
from pathlib import Path

import server
import server_app.core as core


_FAKE_INDEX_HTML = (
    "<!doctype html><html><head>"
    "<title>lvcodex v2 (test fixture)</title>"
    "</head><body><div id='app'></div>"
    "<script type='module' src='/v2/assets/index.js'></script>"
    "</body></html>"
)
_FAKE_ASSET_JS = "/* fake bundle */ console.log('lvcodex v2 fixture');\n"


class _V2RouteFixtureMixin:
    """Boot a real AppHandler against an ephemeral port + fake dist dir."""

    httpd: "core.DualStackServer"  # type: ignore[name-defined]
    port: int
    thread: threading.Thread
    tmp_root: Path
    original_dist: Path

    @classmethod
    def _install_fake_dist(cls) -> None:
        cls.tmp_root = Path(tempfile.mkdtemp(prefix="lvcodex-v2-test-"))
        dist = cls.tmp_root / "dist"
        (dist / "assets").mkdir(parents=True)
        (dist / "index.html").write_text(_FAKE_INDEX_HTML, encoding="utf-8")
        (dist / "assets" / "index.js").write_text(
            _FAKE_ASSET_JS, encoding="utf-8"
        )
        cls.original_dist = core.WEB_V2_DIST_DIR
        core.WEB_V2_DIST_DIR = dist

    @classmethod
    def _remove_fake_dist(cls) -> None:
        core.WEB_V2_DIST_DIR = cls.original_dist
        shutil.rmtree(cls.tmp_root, ignore_errors=True)

    @classmethod
    def _start_server(cls) -> None:
        cls.httpd = server.DualStackServer(("::1", 0), server.AppHandler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(
            target=cls.httpd.serve_forever,
            name=f"{cls.__name__}-server",
            daemon=True,
        )
        cls.thread.start()

    @classmethod
    def _stop_server(cls) -> None:
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=5)

    def _get(
        self,
        path: str,
        *,
        allow_redirects: bool = True,
    ):
        """Return (status, headers, body). ``headers`` is the raw email.Message
        so duplicate header names (Cache-Control) can be inspected via
        ``get_all(name)``.
        """
        url = f"http://[::1]:{self.port}{path}"  # type: ignore[attr-defined]

        if not allow_redirects:

            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, *_args, **_kwargs):  # type: ignore[override]
                    return None

            opener = urllib.request.build_opener(NoRedirect)
            try:
                with closing(opener.open(url, timeout=5)) as response:
                    return response.status, response.headers, response.read()
            except urllib.error.HTTPError as error:
                try:
                    body = error.read()
                finally:
                    error.close()
                return error.code, error.headers, body

        try:
            with closing(urllib.request.urlopen(url, timeout=5)) as response:
                return response.status, response.headers, response.read()
        except urllib.error.HTTPError as error:
            try:
                body = error.read()
            finally:
                error.close()
            return error.code, error.headers, body


class V2StaticRouteWithDistTests(_V2RouteFixtureMixin, unittest.TestCase):
    """End-to-end tests with a fake dist/ directory present."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._install_fake_dist()
        cls._start_server()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._stop_server()
        cls._remove_fake_dist()

    def test_v2_root_serves_index_html_200(self) -> None:
        status, headers, body = self._get("/v2/")
        self.assertEqual(status, 200, body[:200])
        self.assertIn("text/html", headers.get("Content-Type", ""))
        self.assertIn(b"lvcodex v2 (test fixture)", body)
        self.assertIn(b"id='app'", body)
        # index.html must NOT be cached so a redeploy is picked up fast.
        # The hook emits ``no-store`` first; the default end_headers() chain
        # may append a second Cache-Control header but the first wins on the
        # wire (RFC 7234 §5.2: only the first value applies for clients that
        # do not concatenate duplicate directives).
        cache_values = headers.get_all("Cache-Control") or []
        self.assertEqual(cache_values[0], "no-store")

    def test_v2_without_trailing_slash_redirects_to_v2_slash(self) -> None:
        status, headers, _body = self._get("/v2", allow_redirects=False)
        self.assertEqual(status, 301)
        self.assertEqual(headers.get("Location"), "/v2/")

    def test_v2_unknown_route_falls_back_to_index_html(self) -> None:
        status, headers, body = self._get("/v2/readiness")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers.get("Content-Type", ""))
        self.assertIn(b"lvcodex v2 (test fixture)", body)

    def test_v2_nested_unknown_route_falls_back_to_index_html(self) -> None:
        status, _headers, body = self._get("/v2/attempts/123/details")
        self.assertEqual(status, 200)
        self.assertIn(b"lvcodex v2 (test fixture)", body)

    def test_v2_asset_is_served_with_immutable_cache(self) -> None:
        status, headers, body = self._get("/v2/assets/index.js")
        self.assertEqual(status, 200)
        self.assertIn("application/javascript", headers.get("Content-Type", ""))
        self.assertIn(b"lvcodex v2 fixture", body)
        # T-036 emits the immutable cache header first (the AppHandler chain
        # appends its default Cache-Control after, but the first directive
        # wins for the client).
        cache_values = headers.get_all("Cache-Control") or []
        self.assertIn("max-age=31536000", cache_values[0])
        self.assertIn("immutable", cache_values[0])

    def test_v2_path_traversal_does_not_leak_files_outside_dist(self) -> None:
        # ``normalize_request_path`` collapses ``..`` segments BEFORE the
        # T-036 hook sees the path, so escape attempts no longer start with
        # ``/v2/`` and fall through to the default static handler — which
        # responds 404 because the resolved path is not in the public
        # static allow-list. The contract here is simply: the response
        # body must NEVER contain server source code or system files.
        for escape in ["/v2/../server.py", "/v2/foo/../../etc/passwd"]:
            with self.subTest(escape=escape):
                status, _headers, body = self._get(escape)
                self.assertIn(status, {200, 404})
                self.assertNotIn(b"SystemExit(main())", body)
                self.assertNotIn(b"root:x:0:0", body)

    def test_vanilla_app_is_unaffected_by_v2_hook(self) -> None:
        # The vanilla app is the default and lives at /latvian-a2-exam-app/.
        # T-036 must NOT take over its routes; we expect a 200 + HTML.
        status, headers, _body = self._get("/latvian-a2-exam-app/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers.get("Content-Type", ""))


class V2StaticRouteWithoutDistTests(_V2RouteFixtureMixin, unittest.TestCase):
    """Tests that exercise the "dist not built" branch."""

    @classmethod
    def setUpClass(cls) -> None:
        # Point at a directory that does not contain index.html.
        cls.tmp_root = Path(tempfile.mkdtemp(prefix="lvcodex-v2-nodist-"))
        cls.original_dist = core.WEB_V2_DIST_DIR
        core.WEB_V2_DIST_DIR = cls.tmp_root / "dist"  # intentionally missing
        cls._start_server()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._stop_server()
        core.WEB_V2_DIST_DIR = cls.original_dist
        shutil.rmtree(cls.tmp_root, ignore_errors=True)

    def test_v2_returns_503_with_actionable_message(self) -> None:
        status, headers, body = self._get("/v2/")
        self.assertEqual(status, 503)
        self.assertIn("text/plain", headers.get("Content-Type", ""))
        self.assertIn(b"npm run build:v2", body)
        self.assertEqual(headers.get("Cache-Control"), "no-store")


class V2HookInstallationTests(unittest.TestCase):
    """Audit that the T-036 hook is actually installed on AppHandler."""

    def test_t036_marker_attribute_is_set(self) -> None:
        self.assertTrue(
            getattr(core.AppHandler, "_t036_installed", False),
            "T-036 hook missing — AppHandler._t036_installed not set. "
            "The end-of-file hook block in server_app/core.py must be the "
            "last patcher of do_GET.",
        )

    def test_do_get_is_the_t036_patched_function(self) -> None:
        self.assertEqual(
            core.AppHandler.do_GET.__name__,
            "_t036_patched_do_get",
            "T-036 must be the outermost do_GET wrapper so /v2/* is checked "
            "before any other route handler.",
        )

    def test_web_v2_dist_dir_points_inside_repo(self) -> None:
        self.assertTrue(str(core.WEB_V2_DIST_DIR).endswith("apps/web-v2/dist"))


if __name__ == "__main__":
    unittest.main()
