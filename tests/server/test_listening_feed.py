"""T-035 — Vertical listening-feed pagination + quiz-answer tests.

Covers the two endpoints introduced by T-035:

* ``GET  /api/listening-feed`` returns a paginated page of curated
  micro-clips with embedded micro-quizzes. The cursor must be opaque
  and round-trippable, the default page size respected, and the next
  cursor absent on the final page.
* ``POST /api/listening-feed/{clip_id}/answer`` scores one quiz answer,
  returns ``correct`` + ``xp_delta``, and writes a row to
  ``listening_feed_answers``.

The service layer is tested in isolation (no socket bind) and the
dispatch layer is verified through ``AppHandler.do_GET`` / ``do_POST``
with stub handlers so the routing wiring stays under regression test.
"""

from __future__ import annotations

import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from http import HTTPStatus
from pathlib import Path
from unittest.mock import patch

# Ensure repo root is on sys.path so ``import server`` resolves under
# ``python -m unittest`` from arbitrary cwd.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import server  # noqa: E402  (shim → server_app.core)

from server_app.services import listening_feed as feed_service  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


SAMPLE_CLIPS = [
    {
        "id": "feed-fixture-001",
        "audio_url": "data/A1_klausisanas/audio/1_2.mp3",
        "title": "Iepazīšanās",
        "transcript": "Labrīt! Mani sauc Jānis.",
        "translation": "Good morning! My name is Jānis.",
        "difficulty": "A1",
        "category": "greetings",
        "options": ["Labrīt!", "Labdien!", "Labvakar!"],
        "answer": 0,
        "prompt": "Which greeting did you hear?",
        "prompt_lv": "Kuru sveicienu tu dzirdēji?",
        "start": 0,
        "end": 12,
    },
    {
        "id": "feed-fixture-002",
        "audio_url": "data/A1_klausisanas/audio/1_3.mp3",
        "title": "Vārds",
        "transcript": "Mani sauc Sāra.",
        "translation": "My name is Sarah.",
        "difficulty": "A1",
        "category": "people",
        "options": ["Maija", "Sāra", "Deivits"],
        "answer": 1,
        "prompt": "What name did you hear?",
    },
    {
        "id": "feed-fixture-003",
        "audio_url": "data/A1_klausisanas/audio/2_1.mp3",
        "title": "Veikals",
        "transcript": "Es eju uz veikalu.",
        "translation": "I am going to the store.",
        "options": ["banka", "veikals", "bibliotēka"],
        "answer": 1,
    },
    {
        "id": "feed-fixture-004",
        "audio_url": "data/A1_klausisanas/audio/2_6.mp3",
        "title": "Ēdiens",
        "transcript": "Garšīgi.",
        "translation": "Delicious.",
        "options": ["slikti", "garšīgi", "skābi"],
        "answer": 1,
    },
    {
        "id": "feed-fixture-005",
        "audio_url": "data/A1_klausisanas/audio/3_1.mp3",
        "title": "Laiks",
        "transcript": "Šodien ir saule.",
        "translation": "Today it is sunny.",
        "options": ["lietus", "saule", "sniegs"],
        "answer": 1,
    },
    {
        "id": "feed-fixture-006",
        "audio_url": "data/A1_klausisanas/audio/3_2.mp3",
        "title": "Skola",
        "transcript": "Es esmu skolēns.",
        "translation": "I am a pupil.",
        "options": ["skolotājs", "skolēns", "students"],
        "answer": 1,
    },
    {
        "id": "feed-fixture-007",
        "audio_url": "data/A1_klausisanas/audio/3_3.mp3",
        "title": "Ģimene",
        "transcript": "Man ir māte un tēvs.",
        "translation": "I have a mother and a father.",
        "options": ["brālis", "māte", "māsa"],
        "answer": 1,
    },
]


def _write_fixture(tmpdir: Path) -> Path:
    path = tmpdir / "feed-fixture.json"
    path.write_text(json.dumps(SAMPLE_CLIPS), encoding="utf-8")
    return path


class _FixtureMixin:
    """Reset feed cache + redirect the catalogue to a tmpfile fixture."""

    def _install_fixture(self) -> None:
        tmpdir = tempfile.mkdtemp(prefix="lvcodex-feed-")
        self.addCleanup(self._cleanup_tmpdir, tmpdir)
        fixture = _write_fixture(Path(tmpdir))
        os.environ["LVCODEX_LISTENING_FEED_PATH"] = str(fixture)
        # Force a clean catalogue cache so subsequent tests load the
        # fixture, not the production microClips.json.
        feed_service._CACHED_CLIPS = None
        feed_service._CACHED_MTIME = None

    def _cleanup_tmpdir(self, tmpdir: str) -> None:
        os.environ.pop("LVCODEX_LISTENING_FEED_PATH", None)
        feed_service._CACHED_CLIPS = None
        feed_service._CACHED_MTIME = None
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Service-layer tests
# ---------------------------------------------------------------------------


class ListeningFeedPaginationTests(_FixtureMixin, unittest.TestCase):
    def setUp(self) -> None:
        self._install_fixture()

    def test_first_page_returns_default_size_and_next_cursor(self) -> None:
        page = feed_service.build_listening_feed(cursor=None, limit=3)
        self.assertEqual(page["count"], 3)
        self.assertEqual(len(page["clips"]), 3)
        self.assertEqual(page["clips"][0]["id"], "feed-fixture-001")
        self.assertEqual(page["clips"][2]["id"], "feed-fixture-003")
        self.assertIsNotNone(page["next_cursor"])
        self.assertEqual(page["total"], len(SAMPLE_CLIPS))

    def test_second_page_continues_from_cursor(self) -> None:
        first = feed_service.build_listening_feed(cursor=None, limit=3)
        second = feed_service.build_listening_feed(
            cursor=first["next_cursor"], limit=3
        )
        self.assertEqual(second["clips"][0]["id"], "feed-fixture-004")
        self.assertEqual(second["clips"][-1]["id"], "feed-fixture-006")

    def test_final_page_has_no_next_cursor(self) -> None:
        # 3 + 3 + remaining (1) — the last page must NOT carry a cursor.
        page1 = feed_service.build_listening_feed(cursor=None, limit=3)
        page2 = feed_service.build_listening_feed(
            cursor=page1["next_cursor"], limit=3
        )
        page3 = feed_service.build_listening_feed(
            cursor=page2["next_cursor"], limit=3
        )
        self.assertIsNone(page3["next_cursor"])
        self.assertEqual(len(page3["clips"]), 1)
        self.assertEqual(page3["clips"][0]["id"], "feed-fixture-007")

    def test_micro_quiz_payload_omits_correct_answer(self) -> None:
        page = feed_service.build_listening_feed(cursor=None, limit=2)
        for clip in page["clips"]:
            quiz = clip["micro_quiz"]
            self.assertIn("options", quiz)
            self.assertIn("prompt", quiz)
            self.assertNotIn("answer", quiz)
            self.assertNotIn("correct", quiz)
            self.assertNotIn("answer_index", quiz)

    def test_limit_is_clamped_to_max_page_size(self) -> None:
        page = feed_service.build_listening_feed(
            cursor=None, limit=feed_service.MAX_PAGE_SIZE * 10
        )
        self.assertLessEqual(len(page["clips"]), feed_service.MAX_PAGE_SIZE)
        self.assertLessEqual(len(page["clips"]), len(SAMPLE_CLIPS))

    def test_bad_cursor_raises_api_error_with_400(self) -> None:
        from server_app.core import ApiError
        with self.assertRaises(ApiError) as ctx:
            feed_service.build_listening_feed(cursor="not-base64!", limit=3)
        self.assertEqual(ctx.exception.status_code, HTTPStatus.BAD_REQUEST)
        self.assertEqual(ctx.exception.code, "listening_feed_bad_cursor")


# ---------------------------------------------------------------------------
# Answer persistence
# ---------------------------------------------------------------------------


class ListeningFeedAnswerTests(_FixtureMixin, unittest.TestCase):
    def setUp(self) -> None:
        self._install_fixture()
        tmpdir = tempfile.mkdtemp(prefix="lvcodex-feed-db-")
        self.addCleanup(self._cleanup_db_dir, tmpdir)
        self.db_path = Path(tmpdir) / "auth.sqlite3"
        # Bootstrap the minimal DDL we need — the table DDL is created
        # by the service on demand, but tests rely on a sqlite file that
        # exists and is empty.
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        sqlite3.connect(self.db_path).close()

        # Re-arm the once-flag so the DDL re-applies against this DB.
        feed_service._reset_ddl_cache_for_tests()

        # Patch ``db_connection`` for both the service module and core.
        self._db_env_patch = patch.dict(
            os.environ, {"AUTH_DB_PATH": str(self.db_path)}
        )
        self._db_env_patch.start()
        self.addCleanup(self._db_env_patch.stop)

    def _cleanup_db_dir(self, tmpdir: str) -> None:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)

    def test_correct_answer_returns_xp_correct(self) -> None:
        result = feed_service.record_quiz_answer(
            "feed-fixture-001", 0, account_id=None
        )
        self.assertTrue(result["correct"])
        self.assertEqual(result["xp_delta"], feed_service.XP_CORRECT)
        self.assertEqual(result["correct_index"], 0)
        self.assertEqual(result["answer_index"], 0)

    def test_wrong_answer_returns_xp_incorrect(self) -> None:
        result = feed_service.record_quiz_answer(
            "feed-fixture-002", 0, account_id=None
        )
        self.assertFalse(result["correct"])
        self.assertEqual(result["xp_delta"], feed_service.XP_INCORRECT)
        self.assertEqual(result["correct_index"], 1)

    def test_answer_row_is_persisted(self) -> None:
        feed_service.record_quiz_answer(
            "feed-fixture-001", 0, account_id="acct_test"
        )
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT clip_id, quiz_answer_index, is_correct, xp_delta, account_id "
                "FROM listening_feed_answers"
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "feed-fixture-001")
        self.assertEqual(row[1], 0)
        self.assertEqual(row[2], 1)
        self.assertEqual(row[3], feed_service.XP_CORRECT)
        self.assertEqual(row[4], "acct_test")

    def test_unknown_clip_raises_404(self) -> None:
        from server_app.core import ApiError
        with self.assertRaises(ApiError) as ctx:
            feed_service.record_quiz_answer(
                "feed-fixture-missing", 0, account_id=None
            )
        self.assertEqual(ctx.exception.status_code, HTTPStatus.NOT_FOUND)
        self.assertEqual(ctx.exception.code, "listening_feed_clip_not_found")

    def test_out_of_range_answer_raises_400(self) -> None:
        from server_app.core import ApiError
        with self.assertRaises(ApiError) as ctx:
            feed_service.record_quiz_answer(
                "feed-fixture-001", 99, account_id=None
            )
        self.assertEqual(ctx.exception.status_code, HTTPStatus.BAD_REQUEST)
        self.assertEqual(ctx.exception.code, "listening_feed_bad_answer")

    def test_negative_answer_raises_400(self) -> None:
        from server_app.core import ApiError
        with self.assertRaises(ApiError) as ctx:
            feed_service.record_quiz_answer(
                "feed-fixture-001", -1, account_id=None
            )
        self.assertEqual(ctx.exception.status_code, HTTPStatus.BAD_REQUEST)
        self.assertEqual(ctx.exception.code, "listening_feed_bad_answer")


# ---------------------------------------------------------------------------
# Route registration audit
# ---------------------------------------------------------------------------


class ListeningFeedRouteAuditTests(unittest.TestCase):
    def test_routes_module_declares_both_endpoints(self) -> None:
        from server_app.routes import listening_feed as route_module
        documented = set(route_module.ROUTES)
        self.assertIn(("GET", "/api/listening-feed"), documented)
        self.assertIn(
            ("POST", "/api/listening-feed/<clip_id>/answer"),
            documented,
        )

    def test_routes_registry_includes_listening_feed_owner(self) -> None:
        from server_app.routes import ROUTES
        owners = {owner for _m, _p, owner in ROUTES}
        self.assertIn("listening_feed", owners)


# ---------------------------------------------------------------------------
# HTTP handler smoke tests
# ---------------------------------------------------------------------------


class _RecordingHandler:
    """Just enough of AppHandler for the dispatchers to write a response.

    We can't lazily build a full :class:`AppHandler` here because it
    inherits from :class:`http.server.BaseHTTPRequestHandler` whose
    ``__init__`` drives the socket. Instead, we instantiate via
    ``__new__`` and fill in the attributes the dispatcher reads.
    """

    def __init__(self, *, method: str, path: str, body: bytes = b"") -> None:
        from server import AppHandler
        self.handler = AppHandler.__new__(AppHandler)
        self.handler.command = method
        self.handler.path = path
        self.handler.client_address = ("127.0.0.1", 0)
        self.handler.headers = _Headers({"Content-Length": str(len(body))})
        self.handler.rfile = io.BytesIO(body)
        self.handler.wfile = io.BytesIO()
        self.handler.server = None
        self.handler.requestline = f"{method} {path} HTTP/1.1"
        self.handler.request_version = "HTTP/1.1"
        self.handler.close_connection = True
        self.status: int | None = None
        self.response_headers: dict[str, str] = {}
        self.handler.send_response = self._send_response  # type: ignore[assignment]
        self.handler.send_header = self._send_header  # type: ignore[assignment]
        self.handler.end_headers = lambda: None  # type: ignore[assignment]
        self.handler.log_request = lambda *_a, **_k: None  # type: ignore[assignment]
        self.handler.log_message = lambda *_a, **_k: None  # type: ignore[assignment]
        self.handler.log_error = lambda *_a, **_k: None  # type: ignore[assignment]

    def _send_response(self, status: int, _msg: str | None = None) -> None:
        self.status = int(status)

    def _send_header(self, name: str, value: str) -> None:
        self.response_headers[name] = str(value)

    def body(self) -> dict[str, object]:
        raw = self.handler.wfile.getvalue()
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))


class _Headers:
    """Stand-in for http.client.HTTPMessage exposing ``.get``."""

    def __init__(self, mapping: dict[str, str]) -> None:
        self._data = {k.lower(): v for k, v in mapping.items()}

    def get(self, key: str, default: str = "") -> str:
        return self._data.get(key.lower(), default)


class ListeningFeedHandlerTests(_FixtureMixin, unittest.TestCase):
    def setUp(self) -> None:
        self._install_fixture()
        tmpdir = tempfile.mkdtemp(prefix="lvcodex-feed-handler-")
        self.addCleanup(self._cleanup_db_dir, tmpdir)
        self.db_path = Path(tmpdir) / "auth.sqlite3"
        sqlite3.connect(self.db_path).close()
        feed_service._reset_ddl_cache_for_tests()
        self._db_env_patch = patch.dict(
            os.environ, {"AUTH_DB_PATH": str(self.db_path)}
        )
        self._db_env_patch.start()
        self.addCleanup(self._db_env_patch.stop)

    def _cleanup_db_dir(self, tmpdir: str) -> None:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)

    def test_get_listening_feed_returns_200_and_clips(self) -> None:
        handler = _RecordingHandler(method="GET", path="/api/listening-feed?limit=3")
        handler.handler.do_GET()
        self.assertEqual(handler.status, int(HTTPStatus.OK))
        body = handler.body()
        self.assertIn("clips", body)
        self.assertEqual(len(body["clips"]), 3)
        self.assertIn("next_cursor", body)

    def test_get_listening_feed_paginates_via_cursor(self) -> None:
        h1 = _RecordingHandler(method="GET", path="/api/listening-feed?limit=3")
        h1.handler.do_GET()
        page1 = h1.body()
        cursor = page1["next_cursor"]
        self.assertIsNotNone(cursor)
        from urllib.parse import quote
        h2 = _RecordingHandler(
            method="GET",
            path="/api/listening-feed?cursor=" + quote(cursor, safe=""),
        )
        h2.handler.do_GET()
        page2 = h2.body()
        self.assertEqual(h2.status, int(HTTPStatus.OK))
        first_page_ids = [c["id"] for c in page1["clips"]]
        second_page_ids = [c["id"] for c in page2["clips"]]
        self.assertFalse(set(first_page_ids) & set(second_page_ids))

    def test_post_answer_returns_correctness_and_xp(self) -> None:
        body = json.dumps({"quiz_answer_index": 0}).encode("utf-8")
        handler = _RecordingHandler(
            method="POST",
            path="/api/listening-feed/feed-fixture-001/answer",
            body=body,
        )
        handler.handler.do_POST()
        self.assertEqual(handler.status, int(HTTPStatus.OK))
        result = handler.body()
        self.assertTrue(result["correct"])
        self.assertEqual(result["xp_delta"], feed_service.XP_CORRECT)
        self.assertEqual(result["clip_id"], "feed-fixture-001")

    def test_post_answer_missing_field_returns_400(self) -> None:
        body = json.dumps({}).encode("utf-8")
        handler = _RecordingHandler(
            method="POST",
            path="/api/listening-feed/feed-fixture-001/answer",
            body=body,
        )
        handler.handler.do_POST()
        self.assertEqual(handler.status, int(HTTPStatus.BAD_REQUEST))
        err = handler.body()
        self.assertEqual(err["error"]["code"], "listening_feed_bad_answer")

    def test_post_answer_unknown_clip_returns_404(self) -> None:
        body = json.dumps({"quiz_answer_index": 0}).encode("utf-8")
        handler = _RecordingHandler(
            method="POST",
            path="/api/listening-feed/feed-fixture-missing/answer",
            body=body,
        )
        handler.handler.do_POST()
        self.assertEqual(handler.status, int(HTTPStatus.NOT_FOUND))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
