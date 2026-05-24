"""T-061 — Mobile PWA + offline listening tests.

Asserts:

* The PWA manifest files for ``latvian-a2-exam-app/`` and
  ``apps/web-v2/public/`` are valid JSON and carry the keys required by
  installable PWAs (``name``, ``start_url``, ``display=standalone``,
  ``theme_color``, ``icons[]`` with at least one 192-or-larger entry).
* The service worker files exist and contain the routing rules the
  T-061 spec promises (audio LRU, stale-while-revalidate for the
  listening-feed API, cache-first for the app shell).
* The static-asset gate (``is_public_static_path``) lets the browser
  fetch ``manifest.webmanifest`` and ``sw.js`` under
  ``/latvian-a2-exam-app/`` — without this, registering the SW from
  HTML would 404 in production.
* The listening-feed HTML embeds the iOS PWA meta tags and registers
  the service worker.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import server  # noqa: E402  (shim → server_app.core)
from server_app import core as server_core  # noqa: E402


# ---------------------------------------------------------------------------
# File-system constants
# ---------------------------------------------------------------------------

A2_APP_DIR = _REPO_ROOT / "latvian-a2-exam-app"
WEB_V2_PUBLIC_DIR = _REPO_ROOT / "apps" / "web-v2" / "public"
LISTENING_WEB_DIR = _REPO_ROOT / "latvian-listening-library" / "web"


# ---------------------------------------------------------------------------
# Manifest validity
# ---------------------------------------------------------------------------


class PwaManifestValidityTests(unittest.TestCase):
    """Both manifests must be installable per the W3C manifest spec."""

    REQUIRED_KEYS = ("name", "short_name", "start_url", "display", "icons")

    def _assert_manifest_valid(self, manifest_path: Path, *, scope: str) -> None:
        self.assertTrue(
            manifest_path.is_file(),
            f"Expected PWA manifest at {manifest_path}",
        )
        with manifest_path.open(encoding="utf-8") as fh:
            data = json.load(fh)

        for key in self.REQUIRED_KEYS:
            self.assertIn(key, data, f"{manifest_path} missing key {key!r}")

        # Display must be one of the standalone-friendly modes.
        self.assertIn(
            data["display"],
            {"standalone", "fullscreen", "minimal-ui"},
            f"{manifest_path} display={data['display']!r} is not installable",
        )

        # Theme color must be a CSS color string.
        self.assertIn("theme_color", data)
        self.assertTrue(
            isinstance(data["theme_color"], str)
            and data["theme_color"].startswith("#"),
            f"{manifest_path} theme_color must be a CSS hex string",
        )

        # At least one icon ≥ 192x192 (Chrome's installability rule).
        sizes = {icon.get("sizes", "") for icon in data["icons"]}
        has_large = any(
            "any" in size
            or any(
                int(part.split("x")[0]) >= 192
                for part in size.split()
                if "x" in part and part.split("x")[0].isdigit()
            )
            for size in sizes
        )
        self.assertTrue(
            has_large,
            f"{manifest_path} icons[] must contain at least one 192+ entry; "
            f"got sizes={sizes}",
        )

        # Scope must match the deployed mount point so the SW can claim
        # the right URL prefix.
        self.assertEqual(
            data.get("scope"),
            scope,
            f"{manifest_path} scope={data.get('scope')!r} != expected {scope!r}",
        )

    def test_a2_exam_app_manifest(self) -> None:
        self._assert_manifest_valid(
            A2_APP_DIR / "manifest.webmanifest",
            scope="/latvian-a2-exam-app/",
        )

    def test_web_v2_manifest(self) -> None:
        self._assert_manifest_valid(
            WEB_V2_PUBLIC_DIR / "manifest.webmanifest",
            scope="/v2/",
        )

    def test_listening_library_manifest_remains_valid(self) -> None:
        # Pre-existing manifest must still be valid after the T-061 SW
        # rewrite — guards against accidental regression.
        manifest_path = LISTENING_WEB_DIR / "manifest.json"
        self.assertTrue(manifest_path.is_file())
        with manifest_path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        for key in self.REQUIRED_KEYS:
            self.assertIn(key, data)
        self.assertIn(data["display"], {"standalone", "fullscreen", "minimal-ui"})


# ---------------------------------------------------------------------------
# Service-worker source assertions (without a JS runtime)
# ---------------------------------------------------------------------------


class PwaServiceWorkerSourceTests(unittest.TestCase):
    """Hard-codes the routing rules T-061 promises into the SW sources."""

    A2_SW = A2_APP_DIR / "sw.js"
    V2_SW = WEB_V2_PUBLIC_DIR / "sw.js"
    LISTENING_SW = LISTENING_WEB_DIR / "sw.js"

    def test_all_service_workers_exist(self) -> None:
        for path in (self.A2_SW, self.V2_SW, self.LISTENING_SW):
            self.assertTrue(path.is_file(), f"missing SW {path}")

    def test_audio_cache_caps_at_50(self) -> None:
        for path in (self.A2_SW, self.V2_SW, self.LISTENING_SW):
            text = path.read_text(encoding="utf-8")
            self.assertIn(
                "MAX_CLIP_CACHE = 50",
                text,
                f"{path} must cap the listening-audio cache at 50 clips",
            )

    def test_audio_route_handled_cache_first(self) -> None:
        for path in (self.A2_SW, self.V2_SW, self.LISTENING_SW):
            text = path.read_text(encoding="utf-8")
            self.assertIn(
                "handleAudio",
                text,
                f"{path} must define a cache-first audio handler",
            )
            self.assertIn(
                "trimAudioCache",
                text,
                f"{path} must evict old audio entries",
            )

    def test_listening_feed_api_is_stale_while_revalidate(self) -> None:
        for path in (self.A2_SW, self.V2_SW, self.LISTENING_SW):
            text = path.read_text(encoding="utf-8")
            self.assertIn("/api/listening-feed", text)
            self.assertIn("staleWhileRevalidate", text)

    def test_install_step_precaches_app_shell(self) -> None:
        for path in (self.A2_SW, self.V2_SW, self.LISTENING_SW):
            text = path.read_text(encoding="utf-8")
            self.assertIn("STATIC_ASSETS", text)
            self.assertIn('addEventListener("install"', text)

    def test_activate_cleans_old_caches(self) -> None:
        for path in (self.A2_SW, self.V2_SW, self.LISTENING_SW):
            text = path.read_text(encoding="utf-8")
            self.assertIn('addEventListener("activate"', text)
            self.assertIn("caches.delete", text)


# ---------------------------------------------------------------------------
# Server-side: manifest + sw.js must be reachable as public statics
# ---------------------------------------------------------------------------


class PwaStaticGateTests(unittest.TestCase):
    """The static-asset gate must allow .webmanifest + .js + .json."""

    def test_manifest_webmanifest_under_a2_app_is_public(self) -> None:
        self.assertTrue(
            server_core.is_public_static_path(
                "/latvian-a2-exam-app/manifest.webmanifest"
            )
        )

    def test_sw_js_under_a2_app_is_public(self) -> None:
        self.assertTrue(
            server_core.is_public_static_path("/latvian-a2-exam-app/sw.js")
        )

    def test_icon_under_a2_app_is_public(self) -> None:
        self.assertTrue(
            server_core.is_public_static_path("/latvian-a2-exam-app/icon.svg")
        )

    def test_listening_library_sw_is_public(self) -> None:
        self.assertTrue(
            server_core.is_public_static_path(
                "/latvian-listening-library/web/sw.js"
            )
        )

    def test_listening_library_manifest_is_public(self) -> None:
        self.assertTrue(
            server_core.is_public_static_path(
                "/latvian-listening-library/web/manifest.json"
            )
        )

    def test_traversal_is_blocked(self) -> None:
        self.assertFalse(
            server_core.is_public_static_path(
                "/latvian-a2-exam-app/../server.py"
            )
        )


# ---------------------------------------------------------------------------
# HTML wiring
# ---------------------------------------------------------------------------


class PwaHtmlWiringTests(unittest.TestCase):
    """Check that each entry-point HTML page actually wires the PWA."""

    def _read(self, rel: str) -> str:
        return (_REPO_ROOT / rel).read_text(encoding="utf-8")

    def test_a2_exam_app_registers_sw_and_manifest(self) -> None:
        html = self._read("latvian-a2-exam-app/index.html")
        self.assertIn('rel="manifest"', html)
        self.assertIn("manifest.webmanifest", html)
        self.assertIn("serviceWorker", html)
        self.assertIn("/latvian-a2-exam-app/sw.js", html)
        # iOS meta tags
        self.assertIn('name="apple-mobile-web-app-capable"', html)
        self.assertIn('name="apple-mobile-web-app-title"', html)
        self.assertIn('rel="apple-touch-icon"', html)
        # Theme color
        self.assertIn('name="theme-color"', html)
        # Install prompt UI
        self.assertIn('id="pwa-install-banner"', html)
        self.assertIn("beforeinstallprompt", html)

    def test_web_v2_index_registers_sw_and_manifest(self) -> None:
        html = self._read("apps/web-v2/index.html")
        self.assertIn('rel="manifest"', html)
        self.assertIn("/v2/manifest.webmanifest", html)
        self.assertIn("/v2/sw.js", html)
        self.assertIn('name="apple-mobile-web-app-capable"', html)
        self.assertIn('rel="apple-touch-icon"', html)
        self.assertIn('id="pwa-install-banner"', html)

    def test_listening_feed_html_registers_sw_and_offline_pill(self) -> None:
        html = self._read("latvian-listening-library/web/feed.html")
        self.assertIn('rel="manifest"', html)
        self.assertIn('id="feed-offline-pill"', html)
        self.assertIn("/latvian-listening-library/web/sw.js", html)
        self.assertIn('name="apple-mobile-web-app-capable"', html)
        self.assertIn('id="pwa-install-banner"', html)


if __name__ == "__main__":
    unittest.main()
