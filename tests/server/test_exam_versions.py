"""Unit tests for T-037 — content versioning + rapid update pipeline.

Covers the deliverables from the T-037 plan:
- (a) schema validates the version field format (YYYY.MM.N),
- (b) service-layer status transitions (draft -> published -> archived),
- (c) learners only see the currently-published version,
- (d) admins see drafts via the admin-only versions endpoint,
- (e) backward compat: exams without a version field still work (1.0.0),
- (f) the update_exam_content.py script's --dry-run rejects invalid input.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server  # noqa: E402  -- exercises the same import chain as production
from server_app.services import exam_versions  # noqa: E402


# ---------------------------------------------------------------------------
# Validator module loader (shared with T-017's tests).
# ---------------------------------------------------------------------------


def _load_validator_module():
    if "validate_exam_content" in sys.modules:
        return sys.modules["validate_exam_content"]
    spec = importlib.util.spec_from_file_location(
        "validate_exam_content",
        ROOT / "scripts" / "validate_exam_content.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["validate_exam_content"] = module
    spec.loader.exec_module(module)
    return module


def _load_update_script_module():
    """Load scripts/update_exam_content.py as a module for in-process testing."""

    if "update_exam_content" in sys.modules:
        return sys.modules["update_exam_content"]
    spec = importlib.util.spec_from_file_location(
        "update_exam_content",
        ROOT / "scripts" / "update_exam_content.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["update_exam_content"] = module
    spec.loader.exec_module(module)
    return module


def _minimal_valid_manifest(version: str | None = "2026.05.0") -> dict:
    """Return a minimal manifest that satisfies schemas/exam.schema.json."""

    def section(skill: str, allocation: dict[str, int]):
        tasks = []
        for task_key, pts in allocation.items():
            tasks.append({
                "task_key": task_key,
                "title": f"{task_key} title",
                "scoring_mode": "objective",
                "points_max": pts,
                "instruction": "test instruction",
                "questions": [
                    {
                        "number": 1,
                        "prompt": "Sample prompt",
                        "kind": "objective",
                        "options": [
                            {"label": "a", "text": "A"},
                            {"label": "b", "text": "B"},
                        ],
                        "correct_answers": ["a"],
                    }
                ],
            })
        return {
            "skill": skill,
            "title": f"{skill} section",
            "points_max": 15,
            "minutes": 25,
            "tasks": tasks,
        }

    manifest = {
        "schema_version": "1.0",
        "exam_id": "test-001",
        "slug": "test-001",
        "title": "Test Exam",
        "level": "A2",
        "language": "lv",
        "status": "draft",
        "content_version": 1,
        "scoring": {
            "total_points": 60,
            "skill_points": {
                "listening": 15,
                "reading": 15,
                "writing": 15,
                "speaking": 15,
            },
            "minimum_per_skill": 9,
            "task_point_allocation": {
                "listening": {"task1": 6, "task2": 4, "task3": 5},
                "reading":   {"task1": 4, "task2": 6, "task3": 5},
                "writing":   {"task1": 4, "task2": 5, "task3": 6},
                "speaking":  {"task1": 10, "task2": 3, "task3": 2},
            },
        },
        "sections": [
            section("listening", {"task1": 6, "task2": 4, "task3": 5}),
            section("reading",   {"task1": 4, "task2": 6, "task3": 5}),
            section("writing",   {"task1": 4, "task2": 5, "task3": 6}),
            section("speaking",  {"task1": 10, "task2": 3, "task3": 2}),
        ],
    }
    if version is not None:
        manifest["version"] = version
    return manifest


# ---------------------------------------------------------------------------
# (a) Schema-level version-field tests.
# ---------------------------------------------------------------------------


class ExamSchemaVersionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = _load_validator_module()
        cls.schema = cls.module.load_schema()
        cls.validator = cls.module.build_validator(cls.schema)

    def _errors(self, manifest: dict) -> list[str]:
        return [self.module._format_error(e) for e in self.validator.iter_errors(manifest)]

    def test_well_formed_version_passes(self) -> None:
        manifest = _minimal_valid_manifest(version="2026.05.0")
        self.assertEqual(self._errors(manifest), [])

    def test_version_field_is_optional_backward_compat(self) -> None:
        manifest = _minimal_valid_manifest(version=None)
        manifest.pop("version", None)
        self.assertEqual(self._errors(manifest), [])

    def test_malformed_version_fails(self) -> None:
        manifest = _minimal_valid_manifest(version="v2026.05.0")  # leading v
        errors = self._errors(manifest)
        self.assertTrue(any("/version" in e for e in errors),
                        f"malformed version should be rejected; got {errors}")

    def test_version_with_invalid_month_fails(self) -> None:
        manifest = _minimal_valid_manifest(version="2026.13.0")
        errors = self._errors(manifest)
        self.assertTrue(any("/version" in e for e in errors),
                        f"month 13 should be rejected; got {errors}")

    def test_version_with_dashes_fails(self) -> None:
        manifest = _minimal_valid_manifest(version="2026-05-0")
        errors = self._errors(manifest)
        self.assertTrue(any("/version" in e for e in errors),
                        f"dash-separated version should be rejected; got {errors}")

    def test_legacy_semver_1_0_0_fails_schema(self) -> None:
        # The grandfathered "1.0.0" is NOT considered a valid CalVer.
        # It is only ever served by the runtime as the *missing-version*
        # default, never written into a manifest payload.
        manifest = _minimal_valid_manifest(version="1.0.0")
        errors = self._errors(manifest)
        self.assertTrue(any("/version" in e for e in errors))


# ---------------------------------------------------------------------------
# (b)-(e) Service + HTTP behaviour tests (need a real SQLite DB).
# ---------------------------------------------------------------------------


def _session(role: str, account_id: str = "acct_actor") -> dict[str, object]:
    return {
        "account": {
            "id": account_id,
            "email": f"{role}@example.test",
            "status": "active",
            "role": role,
            "created_at": "2026-05-05T00:00:00Z",
            "deleted_at": None,
        }
    }


class ExamVersionsServiceTests(unittest.TestCase):
    """Direct tests of server_app.services.exam_versions."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "auth.sqlite3"
        self.auth_db_patch = patch.object(server, "AUTH_DB_PATH", self.db_path)
        self.auth_db_patch.start()
        server.init_auth_store()

    def tearDown(self) -> None:
        self.auth_db_patch.stop()
        self.tmpdir.cleanup()

    def test_table_exists_after_init(self) -> None:
        with server.db_connection() as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='exam_versions'"
            ).fetchone()
            self.assertIsNotNone(row, "exam_versions table must exist after init")

    def test_is_valid_version(self) -> None:
        self.assertTrue(exam_versions.is_valid_version("2026.05.0"))
        self.assertTrue(exam_versions.is_valid_version("2026.05.42"))
        self.assertFalse(exam_versions.is_valid_version(""))
        self.assertFalse(exam_versions.is_valid_version(None))
        self.assertFalse(exam_versions.is_valid_version("1.0.0"))
        self.assertFalse(exam_versions.is_valid_version("2026.13.0"))
        self.assertFalse(exam_versions.is_valid_version("v2026.05.0"))

    def test_create_draft_rejects_bad_version(self) -> None:
        with server.db_connection() as conn:
            with self.assertRaises(exam_versions.ExamVersionError):
                exam_versions.create_draft(conn, "01", "1.0.0", {"hello": "world"})

    def test_get_current_version_falls_back_to_grandfathered(self) -> None:
        with server.db_connection() as conn:
            current = exam_versions.get_current_version(conn, "01")
        self.assertEqual(current, "1.0.0")

    def test_publish_archives_previous_published(self) -> None:
        with server.db_connection() as conn:
            exam_versions.create_draft(conn, "01", "2026.05.0", {"k": "v1"})
            exam_versions.publish_version(conn, "01", "2026.05.0")
            exam_versions.create_draft(conn, "01", "2026.05.1", {"k": "v2"})
            exam_versions.publish_version(conn, "01", "2026.05.1")
            current = exam_versions.get_current_version(conn, "01")
            rows = exam_versions.list_versions(conn, "01")
        self.assertEqual(current, "2026.05.1")
        statuses = {r["version"]: r["status"] for r in rows}
        self.assertEqual(statuses["2026.05.0"], "archived")
        self.assertEqual(statuses["2026.05.1"], "published")
        published_count = sum(1 for r in rows if r["status"] == "published")
        self.assertEqual(published_count, 1,
                         "exactly one row may be published per exam")

    def test_publish_idempotent(self) -> None:
        with server.db_connection() as conn:
            exam_versions.create_draft(conn, "01", "2026.05.0", {})
            first = exam_versions.publish_version(conn, "01", "2026.05.0")
            second = exam_versions.publish_version(conn, "01", "2026.05.0")
        self.assertEqual(first["status"], "published")
        self.assertEqual(second["status"], "published")
        self.assertEqual(first["published_at"], second["published_at"])

    def test_re_publish_archived_for_rollback(self) -> None:
        with server.db_connection() as conn:
            exam_versions.create_draft(conn, "01", "2026.05.0", {})
            exam_versions.publish_version(conn, "01", "2026.05.0")
            exam_versions.create_draft(conn, "01", "2026.05.1", {})
            exam_versions.publish_version(conn, "01", "2026.05.1")
            # Roll back to 2026.05.0 (currently archived).
            rolled = exam_versions.publish_version(conn, "01", "2026.05.0")
            current = exam_versions.get_current_version(conn, "01")
        self.assertEqual(rolled["status"], "published")
        self.assertEqual(current, "2026.05.0")

    def test_publish_unknown_version_raises_not_found(self) -> None:
        with server.db_connection() as conn:
            with self.assertRaises(exam_versions.ExamVersionError) as ctx:
                exam_versions.publish_version(conn, "01", "2026.05.0")
        self.assertTrue(ctx.exception.not_found)

    def test_cannot_re_draft_published(self) -> None:
        with server.db_connection() as conn:
            exam_versions.create_draft(conn, "01", "2026.05.0", {})
            exam_versions.publish_version(conn, "01", "2026.05.0")
            with self.assertRaises(exam_versions.ExamVersionError):
                exam_versions.create_draft(conn, "01", "2026.05.0", {})

    def test_list_drafts_excludes_published(self) -> None:
        with server.db_connection() as conn:
            exam_versions.create_draft(conn, "01", "2026.05.0", {})
            exam_versions.create_draft(conn, "02", "2026.05.0", {})
            exam_versions.publish_version(conn, "02", "2026.05.0")
            drafts = exam_versions.list_drafts(conn)
        exam_ids = {d["exam_id"] for d in drafts}
        statuses = {d["status"] for d in drafts}
        self.assertEqual(exam_ids, {"01"})
        self.assertEqual(statuses, {"draft"})

    def test_create_draft_can_refresh_payload(self) -> None:
        with server.db_connection() as conn:
            exam_versions.create_draft(conn, "01", "2026.05.0", {"a": 1})
            exam_versions.create_draft(conn, "01", "2026.05.0", {"a": 2})
            row = exam_versions.get_version(conn, "01", "2026.05.0")
        self.assertEqual(row["payload"], {"a": 2})
        self.assertEqual(row["status"], "draft")


# ---------------------------------------------------------------------------
# HTTP-level tests via stub handler — exercise the end-of-file hook.
# ---------------------------------------------------------------------------


class _StubHandler:
    """Minimal AppHandler stand-in that records the response."""

    def __init__(self, path: str, *, session: dict | None = None,
                 body: bytes | None = None) -> None:
        self.path = path
        self.command = "POST" if body is not None else "GET"
        # ``client_address`` is required by the T-015 rate-limit hook; ``headers``
        # must implement ``.get`` (mapping API).
        self.client_address = ("127.0.0.1", 0)
        self.headers: dict[str, str] = {}
        if body is not None:
            self.headers["Content-Length"] = str(len(body))
        self.rfile = io.BytesIO(body or b"")
        self.wfile = io.BytesIO()
        self.responses: list[int] = []
        self.headers_out: list[tuple[str, str]] = []
        self._session = session

    def send_response(self, code, message=None):
        self.responses.append(int(code))

    def send_header(self, key, value):
        self.headers_out.append((str(key), str(value)))

    def end_headers(self):
        pass

    def get_status(self) -> int:
        return self.responses[0] if self.responses else 0


class ExamVersionsHttpHookTests(unittest.TestCase):
    """End-to-end tests of the T-037 hook installed on AppHandler."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "auth.sqlite3"
        self.auth_db_patch = patch.object(server, "AUTH_DB_PATH", self.db_path)
        self.auth_db_patch.start()
        server.init_auth_store()
        with server.db_connection() as conn:
            conn.execute(
                "INSERT INTO accounts (id, email, password_salt, password_hash, "
                "status, created_at, deleted_at, role) "
                "VALUES ('acct_admin', 'admin@example.test', 's', 'h', "
                "'active', '2026-05-01T00:00:00Z', NULL, 'admin')"
            )
            conn.execute(
                "INSERT INTO accounts (id, email, password_salt, password_hash, "
                "status, created_at, deleted_at, role) "
                "VALUES ('acct_learner', 'learner@example.test', 's', 'h', "
                "'active', '2026-05-01T00:00:00Z', NULL, 'user')"
            )
            # Pre-populate one draft and one published version for exam 01.
            exam_versions.create_draft(conn, "01", "2026.05.0", {"k": "v1"})
            exam_versions.publish_version(conn, "01", "2026.05.0")
            # Plus an unpublished draft for exam 01 to exercise list-drafts.
            exam_versions.create_draft(conn, "01", "2026.05.1", {"k": "v2"})

    def tearDown(self) -> None:
        self.auth_db_patch.stop()
        self.tmpdir.cleanup()

    # ----- POST /api/admin/exams/<id>/publish -------------------------------

    def test_publish_route_requires_admin(self) -> None:
        body = json.dumps({"version": "2026.05.1"}).encode("utf-8")
        handler = _StubHandler("/api/admin/exams/01/publish", body=body)
        with patch.object(server, "require_admin_session",
                          side_effect=PermissionError("admin only")):
            server.AppHandler.do_POST(handler)  # type: ignore[arg-type]
        self.assertEqual(handler.get_status(), 401)

    def test_publish_route_rejects_bad_version(self) -> None:
        body = json.dumps({"version": "v2026.05.1"}).encode("utf-8")
        handler = _StubHandler("/api/admin/exams/01/publish", body=body)
        with patch.object(server, "require_admin_session",
                          return_value=_session("admin")):
            server.AppHandler.do_POST(handler)  # type: ignore[arg-type]
        self.assertEqual(handler.get_status(), 400)

    def test_publish_route_flips_status(self) -> None:
        body = json.dumps({"version": "2026.05.1"}).encode("utf-8")
        handler = _StubHandler("/api/admin/exams/01/publish", body=body)
        with patch.object(server, "require_admin_session",
                          return_value=_session("admin")):
            server.AppHandler.do_POST(handler)  # type: ignore[arg-type]
        self.assertEqual(handler.get_status(), 200)
        with server.db_connection() as conn:
            current = exam_versions.get_current_version(conn, "01")
        self.assertEqual(current, "2026.05.1")

    def test_publish_route_404_on_unknown_version(self) -> None:
        body = json.dumps({"version": "2026.06.0"}).encode("utf-8")
        handler = _StubHandler("/api/admin/exams/01/publish", body=body)
        with patch.object(server, "require_admin_session",
                          return_value=_session("admin")):
            server.AppHandler.do_POST(handler)  # type: ignore[arg-type]
        self.assertEqual(handler.get_status(), 404)

    # ----- GET /api/admin/exams/<id>/versions  ------------------------------

    def test_versions_list_admin_sees_drafts(self) -> None:
        handler = _StubHandler("/api/admin/exams/01/versions")
        with patch.object(server, "require_admin_session",
                          return_value=_session("admin")):
            server.AppHandler.do_GET(handler)  # type: ignore[arg-type]
        self.assertEqual(handler.get_status(), 200)
        body = handler.wfile.getvalue().decode("utf-8")
        payload = json.loads(body)
        statuses = {v["version"]: v["status"] for v in payload["versions"]}
        self.assertEqual(statuses["2026.05.0"], "published")
        self.assertEqual(statuses["2026.05.1"], "draft")
        self.assertEqual(payload["current_version"], "2026.05.0")

    def test_versions_list_rejects_learner(self) -> None:
        handler = _StubHandler("/api/admin/exams/01/versions")
        with patch.object(server, "require_admin_session",
                          side_effect=PermissionError("admin only")):
            server.AppHandler.do_GET(handler)  # type: ignore[arg-type]
        self.assertEqual(handler.get_status(), 401)

    # ----- GET /api/exams/<id>/content X-Exam-Version header ----------------

    def test_content_route_sends_current_version_header(self) -> None:
        handler = _StubHandler("/api/exams/01/content")
        # The upstream content loader needs the markdown to exist; we let
        # the real implementation return whatever it does (200 with body,
        # or 404). Either way the header must be present.
        server.AppHandler.do_GET(handler)  # type: ignore[arg-type]
        keys = [k for (k, _v) in handler.headers_out]
        self.assertIn("X-Exam-Version", keys)
        value = next(v for (k, v) in handler.headers_out if k == "X-Exam-Version")
        self.assertEqual(value, "2026.05.0")

    def test_content_route_grandfathered_version_for_unknown_exam(self) -> None:
        handler = _StubHandler("/api/exams/99/content")
        server.AppHandler.do_GET(handler)  # type: ignore[arg-type]
        # The exam doesn't exist but the version header still has to be set
        # — this is the backward-compat contract for exams with no row.
        value = next(
            (v for (k, v) in handler.headers_out if k == "X-Exam-Version"),
            None,
        )
        self.assertEqual(value, "1.0.0",
                         "exams without a versions row report 1.0.0")


# ---------------------------------------------------------------------------
# (f) update_exam_content.py --dry-run tests.
# ---------------------------------------------------------------------------


class UpdateExamContentScriptTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.script = _load_update_script_module()

    def _shipped_markdown(self) -> Path:
        # We can't easily synthesize a markdown that import_exam_markdown
        # accepts, so reuse the shipped exam_01 markdown source. This also
        # gives us realistic schema coverage.
        return ROOT / "codex" / "A2_Mock_Exam_01.md"

    def test_dry_run_rejects_bad_version(self) -> None:
        md = self._shipped_markdown()
        argv = ["--exam-id", "01", "--version", "1.0.0", "--markdown", str(md), "--dry-run"]
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            rc = self.script.main(argv)
        self.assertEqual(rc, 1)
        self.assertIn("YYYY.MM.N", stderr.getvalue())

    def test_dry_run_passes_for_valid_version_and_markdown(self) -> None:
        md = self._shipped_markdown()
        argv = ["--exam-id", "01", "--version", "2026.05.0",
                "--markdown", str(md), "--dry-run"]
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            rc = self.script.main(argv)
        # exam_01.md should satisfy schema + version format. If the shipped
        # markdown ever drifts, the assertion will surface real validation
        # errors rather than masking them.
        self.assertEqual(
            rc,
            0,
            f"dry-run should succeed for shipped exam_01.md; stderr={stderr.getvalue()}",
        )


if __name__ == "__main__":
    unittest.main()
