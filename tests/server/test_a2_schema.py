"""Unit tests for T-025 — A2 exam schema tables + 9/15 pass logic.

Covers the T-025 deliverables:

* (a) ``server_app.services.schema_a2.init_a2_schema_tables`` creates the
  four canonical tables (exam_levels, skills, task_types, exam_parts).
* (b) ``ensure_seed_data`` is idempotent — second invocation reports zero
  inserted rows and leaves the row counts unchanged.
* (c) ``is_passing`` enforces the 9/15-per-skill A2 pass rule, including
  the dashboard-friendly nested-dict shapes used by
  ``compute_objective_score``.
* (d) The end-of-core.py admin hook serves ``GET /api/admin/schema`` with
  the documented level + skills + task_types payload and refuses
  non-admin sessions with a 401.
* (e) ``scripts/seed_a2_schema.py`` runs as an idempotent CLI against a
  caller-supplied SQLite path.
* (f) The Postgres migration ``003_a2_schema.sql`` defines the same four
  tables as the SQLite migration so the dual-write hook keeps parity.
"""

from __future__ import annotations

import importlib.util
import io
import json
import re
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server  # noqa: E402 — exercises the production import chain
from server_app.services import schema_a2  # noqa: E402


def _load_seed_script():
    """Load scripts/seed_a2_schema.py as an importable module."""

    if "seed_a2_schema" in sys.modules:
        return sys.modules["seed_a2_schema"]
    spec = importlib.util.spec_from_file_location(
        "seed_a2_schema",
        ROOT / "scripts" / "seed_a2_schema.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["seed_a2_schema"] = module
    spec.loader.exec_module(module)
    return module


def _admin_session(account_id: str = "acct_admin_t025") -> dict[str, object]:
    return {
        "account": {
            "id": account_id,
            "email": "admin@example.test",
            "status": "active",
            "role": "admin",
            "created_at": "2026-05-05T00:00:00Z",
            "deleted_at": None,
        }
    }


# ---------------------------------------------------------------------------
# Service-layer tests: schema, seeding, pass rule.
# ---------------------------------------------------------------------------


class A2SchemaServiceTests(unittest.TestCase):
    """Direct tests of server_app.services.schema_a2."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "auth.sqlite3"
        self.auth_db_patch = patch.object(server, "AUTH_DB_PATH", self.db_path)
        self.auth_db_patch.start()
        server.init_auth_store()

    def tearDown(self) -> None:
        self.auth_db_patch.stop()
        self.tmpdir.cleanup()

    def test_tables_created_after_init(self) -> None:
        with server.db_connection() as conn:
            tables = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        for required in ("exam_levels", "skills", "task_types", "exam_parts"):
            self.assertIn(required, tables, f"missing T-025 table: {required}")

    def test_seed_populates_a2_b1_b2_levels(self) -> None:
        with server.db_connection() as conn:
            counts = schema_a2.ensure_seed_data(conn)
            level_codes = {
                row["code"]
                for row in conn.execute("SELECT code FROM exam_levels").fetchall()
            }
        self.assertEqual(level_codes, {"A2", "B1", "B2"})
        self.assertEqual(counts["levels"], 3)
        # 4 skills × 3 levels.
        self.assertEqual(counts["skills"], 12)
        # 11 task_types covering all 4 A2 skills.
        self.assertGreaterEqual(counts["task_types"], 8)
        # 4 exam_parts for the built-in A2 exam.
        self.assertEqual(counts["exam_parts"], 4)

    def test_seed_is_idempotent(self) -> None:
        with server.db_connection() as conn:
            first = schema_a2.ensure_seed_data(conn)
            second = schema_a2.ensure_seed_data(conn)
            third = schema_a2.ensure_seed_data(conn)
            level_count = conn.execute(
                "SELECT COUNT(*) AS n FROM exam_levels"
            ).fetchone()["n"]
            skill_count = conn.execute(
                "SELECT COUNT(*) AS n FROM skills"
            ).fetchone()["n"]
            task_type_count = conn.execute(
                "SELECT COUNT(*) AS n FROM task_types"
            ).fetchone()["n"]
            part_count = conn.execute(
                "SELECT COUNT(*) AS n FROM exam_parts"
            ).fetchone()["n"]
        self.assertGreater(first["levels"], 0, "first run should insert rows")
        for key in ("levels", "skills", "task_types", "exam_parts"):
            self.assertEqual(
                second[key], 0,
                f"second run must insert 0 {key} rows (got {second[key]})",
            )
            self.assertEqual(
                third[key], 0,
                f"third run must insert 0 {key} rows (got {third[key]})",
            )
        # Row counts must be stable across re-runs.
        self.assertEqual(level_count, 3)
        self.assertEqual(skill_count, 12)
        self.assertEqual(task_type_count, 11)
        self.assertEqual(part_count, 4)

    def test_seed_a2_total_points_matches_constant(self) -> None:
        with server.db_connection() as conn:
            schema_a2.ensure_seed_data(conn)
            row = conn.execute(
                "SELECT total_points, min_per_skill FROM exam_levels WHERE code='A2'"
            ).fetchone()
            sum_max = conn.execute(
                "SELECT COALESCE(SUM(s.max_points), 0) AS n FROM skills s "
                "JOIN exam_levels l ON l.id = s.level_id WHERE l.code='A2'"
            ).fetchone()["n"]
        self.assertEqual(row["total_points"], schema_a2.A2_TOTAL_POINTS)
        self.assertEqual(row["min_per_skill"], schema_a2.A2_MIN_PER_SKILL)
        self.assertEqual(
            sum_max, schema_a2.A2_TOTAL_POINTS,
            "sum of A2 skill max_points must equal level total_points",
        )

    def test_build_schema_response_shape(self) -> None:
        with server.db_connection() as conn:
            schema_a2.ensure_seed_data(conn)
            payload = schema_a2.build_schema_response(conn, "A2")
        self.assertIsNotNone(payload["level"])
        self.assertEqual(payload["level"]["code"], "A2")
        self.assertEqual(payload["level"]["total_points"], 60)
        self.assertEqual(payload["level"]["min_per_skill"], 9)
        codes = [s["code"] for s in payload["skills"]]
        self.assertEqual(codes, list(schema_a2.A2_SKILLS))
        for skill in payload["skills"]:
            self.assertIn("task_types", skill)
            self.assertEqual(skill["max_points"], schema_a2.A2_SKILL_MAX_POINTS)

    def test_build_schema_response_returns_empty_when_level_missing(self) -> None:
        # Schema present (init runs on db_connection) but the level row is
        # not yet seeded — should hand back an explicit empty envelope.
        with server.db_connection() as conn:
            payload = schema_a2.build_schema_response(conn, "A2")
        self.assertIsNone(payload["level"])
        self.assertEqual(payload["skills"], [])


# ---------------------------------------------------------------------------
# 9/15-per-skill pass-rule tests.
# ---------------------------------------------------------------------------


class A2PassRuleTests(unittest.TestCase):
    """Tests for ``schema_a2.is_passing`` — the canonical 9/15 predicate."""

    def test_all_skills_at_threshold_passes(self) -> None:
        self.assertTrue(
            schema_a2.is_passing(
                {"listening": 9, "reading": 9, "writing": 9, "speaking": 9}
            )
        )

    def test_above_threshold_passes(self) -> None:
        self.assertTrue(
            schema_a2.is_passing(
                {"listening": 12, "reading": 13, "writing": 15, "speaking": 11}
            )
        )

    def test_one_skill_below_threshold_fails(self) -> None:
        self.assertFalse(
            schema_a2.is_passing(
                {"listening": 8, "reading": 14, "writing": 12, "speaking": 10}
            )
        )

    def test_missing_skill_fails(self) -> None:
        self.assertFalse(
            schema_a2.is_passing(
                {"listening": 12, "reading": 13, "writing": 11}
            ),
            "missing speaking skill must fail the 9/15 rule",
        )

    def test_empty_mapping_fails(self) -> None:
        self.assertFalse(schema_a2.is_passing({}))

    def test_non_mapping_input_fails(self) -> None:
        self.assertFalse(schema_a2.is_passing(None))  # type: ignore[arg-type]
        self.assertFalse(schema_a2.is_passing([9, 9, 9, 9]))  # type: ignore[arg-type]

    def test_accepts_nested_objective_correct_shape(self) -> None:
        scores = {
            "listening": {"objective_correct": 12, "objective_possible": 15},
            "reading": {"objective_correct": 11, "objective_possible": 15},
            "writing": {"objective_correct": 10, "objective_possible": 15},
            "speaking": {"objective_correct": 9, "objective_possible": 15},
        }
        self.assertTrue(schema_a2.is_passing(scores))

    def test_nested_points_below_threshold_fails(self) -> None:
        scores = {
            "listening": {"points": 12},
            "reading": {"points": 11},
            "writing": {"points": 5},  # below 9
            "speaking": {"points": 10},
        }
        self.assertFalse(schema_a2.is_passing(scores))

    def test_bool_does_not_masquerade_as_points(self) -> None:
        scores = {"listening": True, "reading": True, "writing": True, "speaking": True}
        # ``bool`` is a subclass of int but we must reject it explicitly so a
        # stray ``True`` never counts as 1 point.
        self.assertFalse(schema_a2.is_passing(scores))

    def test_min_per_skill_override(self) -> None:
        scores = {"listening": 12, "reading": 12, "writing": 12, "speaking": 12}
        # B1 uses min_per_skill=12 in the seeded level row.
        self.assertTrue(schema_a2.is_passing(scores, min_per_skill=12))
        self.assertFalse(schema_a2.is_passing(scores, min_per_skill=13))

    def test_would_pass_exam_dashboard_wrapper(self) -> None:
        # The dashboard surfaces an objective_correct shape — must still pass.
        self.assertTrue(
            schema_a2.would_pass_exam(
                {
                    "listening": {"objective_correct": 9},
                    "reading": {"objective_correct": 9},
                    "writing": {"objective_correct": 9},
                    "speaking": {"objective_correct": 9},
                }
            )
        )
        self.assertFalse(schema_a2.would_pass_exam(None))
        self.assertFalse(schema_a2.would_pass_exam({}))


# ---------------------------------------------------------------------------
# Admin endpoint tests (T-025 hook installed on AppHandler).
# ---------------------------------------------------------------------------


class _StubHandler:
    """Minimal AppHandler stand-in that records the response."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.command = "GET"
        # Required by the T-015 rate-limit hook.
        self.client_address = ("127.0.0.1", 0)
        self.headers: dict[str, str] = {}
        self.rfile = io.BytesIO()
        self.wfile = io.BytesIO()
        self.responses: list[int] = []
        self.headers_out: list[tuple[str, str]] = []

    def send_response(self, code, message=None):  # noqa: D401, ANN001
        self.responses.append(int(code))

    def send_header(self, key, value):  # noqa: D401, ANN001
        self.headers_out.append((str(key), str(value)))

    def end_headers(self):  # noqa: D401
        pass

    def get_status(self) -> int:
        return self.responses[0] if self.responses else 0

    def body_json(self) -> dict:
        raw = self.wfile.getvalue().decode("utf-8")
        if not raw:
            return {}
        return json.loads(raw)


class AdminSchemaRouteTests(unittest.TestCase):
    """End-to-end tests of the T-025 admin-route hook."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "auth.sqlite3"
        self.auth_db_patch = patch.object(server, "AUTH_DB_PATH", self.db_path)
        self.auth_db_patch.start()
        server.init_auth_store()
        with server.db_connection() as conn:
            schema_a2.ensure_seed_data(conn)

    def tearDown(self) -> None:
        self.auth_db_patch.stop()
        self.tmpdir.cleanup()

    def test_admin_schema_returns_full_payload(self) -> None:
        handler = _StubHandler("/api/admin/schema")
        with patch.object(server, "require_admin_session",
                          return_value=_admin_session()):
            server.AppHandler.do_GET(handler)  # type: ignore[arg-type]
        self.assertEqual(handler.get_status(), 200)
        payload = handler.body_json()
        self.assertIsNotNone(payload["level"])
        self.assertEqual(payload["level"]["code"], "A2")
        self.assertEqual(payload["level"]["min_per_skill"], 9)
        self.assertEqual(payload["level"]["total_points"], 60)
        codes = [s["code"] for s in payload["skills"]]
        self.assertEqual(codes, ["listening", "reading", "writing", "speaking"])
        for skill in payload["skills"]:
            self.assertEqual(skill["max_points"], 15)
            self.assertIsInstance(skill.get("task_types"), list)
            for tt in skill["task_types"]:
                self.assertIn("code", tt)
                self.assertIn("format", tt)
                self.assertIn("max_points", tt)

    def test_admin_schema_level_query_param(self) -> None:
        handler = _StubHandler("/api/admin/schema?level=B1")
        with patch.object(server, "require_admin_session",
                          return_value=_admin_session()):
            server.AppHandler.do_GET(handler)  # type: ignore[arg-type]
        self.assertEqual(handler.get_status(), 200)
        payload = handler.body_json()
        self.assertIsNotNone(payload["level"])
        self.assertEqual(payload["level"]["code"], "B1")

    def test_admin_schema_unknown_level_returns_empty_envelope(self) -> None:
        handler = _StubHandler("/api/admin/schema?level=C1")
        with patch.object(server, "require_admin_session",
                          return_value=_admin_session()):
            server.AppHandler.do_GET(handler)  # type: ignore[arg-type]
        self.assertEqual(handler.get_status(), 200)
        payload = handler.body_json()
        self.assertIsNone(payload["level"])
        self.assertEqual(payload["skills"], [])

    def test_admin_schema_rejects_non_admin(self) -> None:
        handler = _StubHandler("/api/admin/schema")
        with patch.object(server, "require_admin_session",
                          side_effect=PermissionError("admin only")):
            server.AppHandler.do_GET(handler)  # type: ignore[arg-type]
        self.assertEqual(handler.get_status(), 401)

    def test_admin_schema_route_listed_in_routes_table(self) -> None:
        from server_app.routes import admin as admin_routes
        self.assertIn(("GET", "/api/admin/schema"), admin_routes.ROUTES)


# ---------------------------------------------------------------------------
# Seed-script tests.
# ---------------------------------------------------------------------------


class SeedScriptTests(unittest.TestCase):
    """Tests for scripts/seed_a2_schema.py — must be idempotent + scriptable."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.script = _load_seed_script()

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "seed_a2.sqlite3"

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_seed_script_first_run_inserts_rows(self) -> None:
        rc = self.script.main(["--db", str(self.db_path), "--json"])
        self.assertEqual(rc, 0)
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            level_count = conn.execute(
                "SELECT COUNT(*) AS n FROM exam_levels"
            ).fetchone()["n"]
        self.assertEqual(level_count, 3)

    def test_seed_script_is_idempotent(self) -> None:
        # First run inserts; subsequent runs must report zero inserts.
        first_rc = self.script.main(
            ["--db", str(self.db_path), "--quiet"]
        )
        self.assertEqual(first_rc, 0)
        # Capture the JSON output of a re-run.
        buf = io.StringIO()
        with redirect_stdout(buf):
            second_rc = self.script.main(
                ["--db", str(self.db_path), "--json"]
            )
        self.assertEqual(second_rc, 0)
        payload = json.loads(buf.getvalue().strip())
        self.assertEqual(payload["total_inserted"], 0)
        for key in ("levels", "skills", "task_types", "exam_parts"):
            self.assertEqual(
                payload["inserted"][key], 0,
                f"second run must insert 0 {key} rows",
            )
        # Row counts must be unchanged.
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            self.assertEqual(
                conn.execute("SELECT COUNT(*) AS n FROM exam_levels").fetchone()["n"],
                3,
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) AS n FROM skills").fetchone()["n"],
                12,
            )

    def test_seed_script_creates_parent_dir(self) -> None:
        nested = Path(self.tmpdir.name) / "nested" / "dir" / "auth.sqlite3"
        rc = self.script.main(["--db", str(nested), "--quiet"])
        self.assertEqual(rc, 0)
        self.assertTrue(nested.exists())

    def test_seed_script_help_does_not_touch_db(self) -> None:
        with self.assertRaises(SystemExit) as ctx, \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.script.main(["--help"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertFalse(self.db_path.exists())


# ---------------------------------------------------------------------------
# Postgres-migration parity tests (file-only — no live PG required).
# ---------------------------------------------------------------------------


class PostgresMigrationParityTests(unittest.TestCase):
    """Ensure the PG migration declares the same tables as the SQLite one."""

    _A2_TABLES = ("exam_levels", "skills", "task_types", "exam_parts")

    def setUp(self) -> None:
        self.sqlite_path = ROOT / "migrations" / "sqlite" / "001_a2_schema.sql"
        self.postgres_path = ROOT / "migrations" / "postgres" / "003_a2_schema.sql"

    def _table_names(self, sql_path: Path) -> set[str]:
        text = sql_path.read_text(encoding="utf-8")
        matches = re.findall(
            r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+([a-zA-Z_][a-zA-Z0-9_]*)",
            text,
            flags=re.IGNORECASE,
        )
        return {m.lower() for m in matches}

    def test_both_migrations_exist(self) -> None:
        self.assertTrue(self.sqlite_path.exists(), str(self.sqlite_path))
        self.assertTrue(self.postgres_path.exists(), str(self.postgres_path))

    def test_both_migrations_declare_same_a2_tables(self) -> None:
        sqlite_tables = self._table_names(self.sqlite_path)
        postgres_tables = self._table_names(self.postgres_path)
        expected = set(self._A2_TABLES)
        self.assertTrue(
            expected.issubset(sqlite_tables),
            f"SQLite migration missing T-025 tables: {expected - sqlite_tables}",
        )
        self.assertTrue(
            expected.issubset(postgres_tables),
            f"Postgres migration missing T-025 tables: {expected - postgres_tables}",
        )

    def test_postgres_migration_is_idempotent(self) -> None:
        text = self.postgres_path.read_text(encoding="utf-8")
        # Strip comments so prose doesn't false-positive.
        stripped = re.sub(r"--[^\n]*", "", text)
        bad = re.findall(
            r"CREATE\s+TABLE\s+(?!IF\s+NOT\s+EXISTS)([a-zA-Z_][a-zA-Z0-9_]*)",
            stripped,
            flags=re.IGNORECASE,
        )
        self.assertEqual(
            bad, [], f"PG migration has CREATE TABLE without IF NOT EXISTS: {bad}"
        )


if __name__ == "__main__":
    unittest.main()
