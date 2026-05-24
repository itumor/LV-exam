"""Tests for the T-011 legal pages (Terms, Privacy, Cookies, Refund, DPA).

The server exposes each policy as an HTML page under `/legal/<slug>`. The
HTML is rendered from the markdown source in the repo's `legal/` directory.

These tests boot the real `AppHandler` against an ephemeral port so they
exercise both the routing layer (the early-dispatch hook in `do_GET`) and
the markdown-to-HTML rendering helper.
"""

from __future__ import annotations

import threading
import unittest
import urllib.error
import urllib.request
from contextlib import closing

import server


EXPECTED_PAGES: dict[str, dict[str, object]] = {
    "/legal/terms": {
        "title": "Terms of Service",
        "must_include": ["Terms of Service", "Last updated: 2026-05-23"],
    },
    "/legal/privacy": {
        "title": "Privacy Policy",
        "must_include": ["Privacy Policy", "GDPR", "Data Protection Officer"],
    },
    "/legal/cookies": {
        "title": "Cookie Policy",
        "must_include": ["Cookie Policy", "cookies_acknowledged"],
    },
    "/legal/refund": {
        "title": "Refund Policy",
        "must_include": ["Refund Policy", "7 days"],
    },
    "/legal/dpa": {
        "title": "Data Processing Agreement",
        "must_include": [
            "Data Processing Agreement",
            "Standard Contractual Clauses",
        ],
    },
}


class LegalRoutesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.httpd = server.DualStackServer(("::1", 0), server.AppHandler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(
            target=cls.httpd.serve_forever, name="legal-routes-test", daemon=True
        )
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=5)

    def _get(self, path: str) -> tuple[int, str, str]:
        url = f"http://[::1]:{self.port}{path}"
        with closing(urllib.request.urlopen(url, timeout=5)) as response:
            body = response.read().decode("utf-8")
            return response.status, response.headers.get("Content-Type", ""), body

    def test_all_legal_routes_respond_200(self) -> None:
        for path in EXPECTED_PAGES:
            with self.subTest(path=path):
                status, _ctype, _body = self._get(path)
                self.assertEqual(status, 200, f"{path} returned {status}")

    def test_each_route_serves_html_with_expected_content(self) -> None:
        for path, spec in EXPECTED_PAGES.items():
            with self.subTest(path=path):
                _status, content_type, body = self._get(path)
                self.assertTrue(
                    content_type.startswith("text/html"),
                    f"{path} content-type was {content_type!r}",
                )
                self.assertIn("<title>", body)
                self.assertIn(str(spec["title"]), body)
                for needle in spec["must_include"]:  # type: ignore[union-attr]
                    self.assertIn(
                        needle,
                        body,
                        f"{path} missing expected text: {needle!r}",
                    )

    def test_pages_include_cross_links_to_other_legal_pages(self) -> None:
        _status, _ctype, body = self._get("/legal/privacy")
        for path in EXPECTED_PAGES:
            self.assertIn(
                f'href="{path}"',
                body,
                f"privacy page missing cross-link to {path}",
            )

    def test_unknown_legal_slug_does_not_short_circuit_static(self) -> None:
        # A path under /legal that is not registered must fall through to
        # the normal handler (which will respond 404 because no static file
        # matches). We accept any non-200 response here — the contract is
        # just that the legal dispatcher does not pretend to handle it.
        url = f"http://[::1]:{self.port}/legal/does-not-exist"
        try:
            with closing(urllib.request.urlopen(url, timeout=5)) as response:
                status = response.status
        except urllib.error.HTTPError as error:
            status = error.code
            error.close()
        self.assertNotEqual(status, 200)


if __name__ == "__main__":
    unittest.main()
