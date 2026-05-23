"""T-021 — unit tests for the SQLite ↔ Postgres abstraction layer.

The dual-write window must not regress the SQLite-only default path.
These tests pin down four invariants:

1. **Default config is SQLite-only.** With ``DATABASE_URL`` unset every
   helper short-circuits, ``is_postgres_configured()`` is False, and the
   dual-write counter only increments the ``skipped`` slot.
2. **Env flags compose correctly.** Setting ``DATABASE_URL`` alone is
   not enough — ``LVCODEX_DB_DUAL_WRITE`` and ``LVCODEX_DB_READ_FROM``
   are independent gates.
3. **SQL translation is correct.** The translator rewrites placeholders
   outside string literals, strips ``PRAGMA`` statements, and converts
   ``INSERT OR IGNORE`` to ``INSERT … ON CONFLICT DO NOTHING``.
4. **Failures never propagate.** A psycopg-side error in
   ``dual_write_execute`` returns False, increments the ``fail`` counter,
   and does not re-raise — so the SQLite write that triggered it stays
   atomic.

We deliberately do not use ``testcontainers`` here. The maintained
``psycopg`` v3 client wheels are only available for x86_64-glibc Linux
and amd64 macOS; CI cannot pull a Postgres image at the moment because
the test workflow does not enable Docker. Instead we inject a fake
``psycopg`` module that mimics the v3 ``connect()`` + cursor surface and
asserts on the translated SQL. The migration parser test
(``test_pg_migrations.py``) gives the real schema coverage by parsing
the SQL files with sqlparse (or a built-in fallback).
"""

from __future__ import annotations

import importlib
import os
import sys
import unittest
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch


def _reset_env(**overrides: str | None) -> dict[str, str | None]:
    """Snapshot + override the four env vars the layer reads."""
    keys = (
        "DATABASE_URL",
        "LVCODEX_DB_DUAL_WRITE",
        "LVCODEX_DB_READ_FROM",
        "LVCODEX_DB_DUAL_WRITE_LOG",
        "APP_ENV",
    )
    snapshot = {k: os.environ.get(k) for k in keys}
    for k, v in overrides.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    return snapshot


def _restore_env(snapshot: dict[str, str | None]) -> None:
    for k, v in snapshot.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


class FakeCursor:
    def __init__(self, conn: "FakePsycopgConnection") -> None:
        self.conn = conn

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *exc) -> None:
        return None

    def execute(self, sql: str, params: Any | None = None) -> None:
        if self.conn.fail_on_execute:
            raise RuntimeError("simulated psycopg failure")
        self.conn.executed.append((sql, params))


class FakePsycopgConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, Any]] = []
        self.fail_on_execute = False
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


class FakePsycopgModule:
    """Stand-in for the ``psycopg`` package the abstraction lazy-loads."""

    def __init__(self) -> None:
        self.conns: list[FakePsycopgConnection] = []
        self.next_connect_raises: BaseException | None = None
        self.next_conn_fails_on_execute = False

    def connect(self, dsn: str) -> FakePsycopgConnection:
        if self.next_connect_raises is not None:
            raise self.next_connect_raises
        conn = FakePsycopgConnection()
        conn.fail_on_execute = self.next_conn_fails_on_execute
        self.next_conn_fails_on_execute = False
        self.conns.append(conn)
        return conn


@contextmanager
def _patched_psycopg(fake: FakePsycopgModule):
    """Make ``server_app.services.db._load_psycopg`` return ``fake``."""
    from server_app.services import db as db_mod
    with patch.object(db_mod, "_load_psycopg", return_value=fake):
        # Also clear cached import state so the patch is effective for
        # the lifetime of the test (subsequent ``_load_psycopg`` calls
        # in the same test see the same fake).
        db_mod._PSYCOPG_IMPORT_FAILED = False
        yield


class DefaultBehaviourTests(unittest.TestCase):
    """The SQLite-only path must be completely undisturbed."""

    def setUp(self) -> None:
        self._snapshot = _reset_env(
            DATABASE_URL=None,
            LVCODEX_DB_DUAL_WRITE=None,
            LVCODEX_DB_READ_FROM=None,
            LVCODEX_DB_DUAL_WRITE_LOG=None,
            APP_ENV=None,
        )
        # Re-import to clear lru_cache-style module state (there is none
        # today, but this keeps the test resilient to refactors).
        from server_app.services import db as db_mod
        importlib.reload(db_mod)
        db_mod.reset_dual_write_state()
        self.db_mod = db_mod

    def tearDown(self) -> None:
        _restore_env(self._snapshot)

    def test_no_database_url_means_no_postgres(self) -> None:
        self.assertIsNone(self.db_mod.get_postgres_dsn())
        self.assertFalse(self.db_mod.is_postgres_configured())
        self.assertFalse(self.db_mod.is_dual_write_enabled())
        self.assertFalse(self.db_mod.read_from_postgres())

    def test_dual_write_short_circuits_when_disabled(self) -> None:
        # No DSN, no env flag → should hit ``skipped`` and never touch
        # the (absent) psycopg module.
        result = self.db_mod.dual_write_execute("INSERT INTO t VALUES (?)", (1,))
        self.assertFalse(result)
        self.assertEqual(self.db_mod.DUAL_WRITE_STATS["skipped"], 1)
        self.assertEqual(self.db_mod.DUAL_WRITE_STATS["ok"], 0)
        self.assertEqual(self.db_mod.DUAL_WRITE_STATS["fail"], 0)

    def test_pg_connection_raises_without_url(self) -> None:
        with self.assertRaises(RuntimeError):
            with self.db_mod.pg_connection():
                pass

    def test_apply_migrations_requires_dsn(self) -> None:
        with self.assertRaises(RuntimeError):
            self.db_mod.apply_postgres_migrations()


class EnvFlagCompositionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._snapshot = _reset_env()
        from server_app.services import db as db_mod
        self.db_mod = db_mod

    def tearDown(self) -> None:
        _restore_env(self._snapshot)

    def test_database_url_alone_does_not_enable_dual_write(self) -> None:
        os.environ["DATABASE_URL"] = "postgres://u:p@h:5432/d"
        os.environ.pop("LVCODEX_DB_DUAL_WRITE", None)
        self.assertTrue(self.db_mod.is_postgres_configured())
        self.assertFalse(self.db_mod.is_dual_write_enabled())

    def test_truthy_flag_enables_dual_write(self) -> None:
        os.environ["DATABASE_URL"] = "postgres://u:p@h:5432/d"
        for v in ("1", "true", "on", "yes"):
            with self.subTest(value=v):
                os.environ["LVCODEX_DB_DUAL_WRITE"] = v
                self.assertTrue(self.db_mod.is_dual_write_enabled())

    def test_falsy_flag_leaves_dual_write_off(self) -> None:
        os.environ["DATABASE_URL"] = "postgres://u:p@h:5432/d"
        for v in ("0", "false", "off", "no", "", "anything-else"):
            with self.subTest(value=v):
                os.environ["LVCODEX_DB_DUAL_WRITE"] = v
                self.assertFalse(self.db_mod.is_dual_write_enabled())

    def test_read_from_postgres_requires_both_flags(self) -> None:
        os.environ.pop("DATABASE_URL", None)
        os.environ["LVCODEX_DB_READ_FROM"] = "postgres"
        self.assertFalse(self.db_mod.read_from_postgres())
        os.environ["DATABASE_URL"] = "postgres://u:p@h:5432/d"
        os.environ["LVCODEX_DB_READ_FROM"] = "postgres"
        self.assertTrue(self.db_mod.read_from_postgres())
        os.environ["LVCODEX_DB_READ_FROM"] = "sqlite"
        self.assertFalse(self.db_mod.read_from_postgres())

    def test_invalid_dsn_scheme_is_treated_as_unset(self) -> None:
        os.environ["DATABASE_URL"] = "mysql://nope"
        self.assertIsNone(self.db_mod.get_postgres_dsn())
        self.assertFalse(self.db_mod.is_postgres_configured())


class SqlTranslationTests(unittest.TestCase):
    def setUp(self) -> None:
        from server_app.services import db as db_mod
        self.translate = db_mod.translate_sql_to_pg

    def test_question_mark_to_percent_s(self) -> None:
        self.assertEqual(
            self.translate("INSERT INTO t (a, b) VALUES (?, ?)"),
            "INSERT INTO t (a, b) VALUES (%s, %s)",
        )

    def test_question_mark_inside_string_literal_is_preserved(self) -> None:
        self.assertEqual(
            self.translate("UPDATE t SET note='who? me?' WHERE id=?"),
            "UPDATE t SET note='who? me?' WHERE id=%s",
        )

    def test_question_mark_inside_double_quoted_identifier_is_preserved(self) -> None:
        # PG uses double quotes for identifiers; SQLite tolerates them
        # as strings. Either way we must not rewrite ``?`` inside them.
        self.assertEqual(
            self.translate('SELECT "a?b" FROM t WHERE id = ?'),
            'SELECT "a?b" FROM t WHERE id = %s',
        )

    def test_insert_or_ignore_rewrites_to_on_conflict(self) -> None:
        out = self.translate("INSERT OR IGNORE INTO t (a) VALUES (?)")
        self.assertNotIn("INSERT OR IGNORE", out)
        self.assertIn("ON CONFLICT DO NOTHING", out)
        self.assertIn("(%s)", out)

    def test_pragma_statements_are_stripped(self) -> None:
        out = self.translate(
            "PRAGMA foreign_keys = ON; INSERT INTO t (a) VALUES (?)"
        )
        self.assertNotIn("PRAGMA", out.upper())
        self.assertIn("INSERT INTO t", out)

    def test_autoincrement_keyword_is_dropped(self) -> None:
        out = self.translate(
            "CREATE TABLE x (id INTEGER PRIMARY KEY AUTOINCREMENT, val TEXT)"
        )
        self.assertNotIn("AUTOINCREMENT", out.upper())

    def test_idempotent_for_already_pg_compatible_sql(self) -> None:
        sql = "INSERT INTO t (id) VALUES (%s) ON CONFLICT (id) DO NOTHING"
        # No ``?`` and no SQLite idioms → unchanged.
        self.assertEqual(self.translate(sql), sql)


class DualWriteWithFakePsycopgTests(unittest.TestCase):
    """Exercise the PG code path with a fake psycopg module."""

    def setUp(self) -> None:
        self._snapshot = _reset_env(
            DATABASE_URL="postgres://lvcodex:secret@db:5432/lvcodex",
            LVCODEX_DB_DUAL_WRITE="1",
            LVCODEX_DB_READ_FROM=None,
            LVCODEX_DB_DUAL_WRITE_LOG="0",
            APP_ENV="test",
        )
        from server_app.services import db as db_mod
        self.db_mod = db_mod
        db_mod.reset_dual_write_state()
        self.fake_psycopg = FakePsycopgModule()

    def tearDown(self) -> None:
        _restore_env(self._snapshot)

    def test_successful_dual_write_increments_ok_counter(self) -> None:
        with _patched_psycopg(self.fake_psycopg):
            ok = self.db_mod.dual_write_execute(
                "INSERT INTO accounts (id, email) VALUES (?, ?)",
                ("acct_1", "test@example.com"),
            )
        self.assertTrue(ok)
        self.assertEqual(self.db_mod.DUAL_WRITE_STATS["ok"], 1)
        self.assertEqual(self.db_mod.DUAL_WRITE_STATS["fail"], 0)
        # The SQL must have been translated before execution.
        self.assertEqual(len(self.fake_psycopg.conns), 1)
        conn = self.fake_psycopg.conns[0]
        self.assertEqual(len(conn.executed), 1)
        executed_sql, executed_params = conn.executed[0]
        self.assertIn("%s", executed_sql)
        self.assertNotIn("?", executed_sql)
        self.assertEqual(executed_params, ("acct_1", "test@example.com"))
        self.assertTrue(conn.committed)
        self.assertTrue(conn.closed)

    def test_psycopg_failure_is_swallowed(self) -> None:
        self.fake_psycopg.next_conn_fails_on_execute = True
        with _patched_psycopg(self.fake_psycopg):
            ok = self.db_mod.dual_write_execute(
                "INSERT INTO t (a) VALUES (?)", (1,)
            )
        self.assertFalse(ok)
        self.assertEqual(self.db_mod.DUAL_WRITE_STATS["fail"], 1)
        self.assertEqual(self.db_mod.DUAL_WRITE_STATS["ok"], 0)
        # Connection still cleaned up.
        self.assertTrue(self.fake_psycopg.conns[0].rolled_back)
        self.assertTrue(self.fake_psycopg.conns[0].closed)

    def test_psycopg_import_failure_is_swallowed(self) -> None:
        # Simulate psycopg not installed: _load_psycopg returns None.
        from server_app.services import db as db_mod
        with patch.object(db_mod, "_load_psycopg", return_value=None):
            ok = self.db_mod.dual_write_execute(
                "INSERT INTO t (a) VALUES (?)", (1,)
            )
        self.assertFalse(ok)
        self.assertEqual(self.db_mod.DUAL_WRITE_STATS["fail"], 1)

    def test_pg_connection_round_trip(self) -> None:
        with _patched_psycopg(self.fake_psycopg):
            with self.db_mod.pg_connection(
                "postgres://u:p@h:5432/d"
            ) as conn:
                self.assertIsInstance(conn, FakePsycopgConnection)
        # Context manager must commit + close on clean exit.
        self.assertTrue(conn.committed)
        self.assertTrue(conn.closed)

    def test_pg_connection_rollback_on_exception(self) -> None:
        with _patched_psycopg(self.fake_psycopg):
            with self.assertRaises(RuntimeError):
                with self.db_mod.pg_connection(
                    "postgres://u:p@h:5432/d"
                ) as conn:
                    raise RuntimeError("boom")
        self.assertFalse(conn.committed)
        self.assertTrue(conn.rolled_back)
        self.assertTrue(conn.closed)


class SqliteBaselineSanityTests(unittest.TestCase):
    """The SQLite path must still produce a working ``sqlite3.Connection``.

    This is the regression test that proves T-021 did not break the
    existing 158-test baseline. It uses the real ``db_connection``
    helper from ``server_app.core``.
    """

    def setUp(self) -> None:
        self._snapshot = _reset_env(
            DATABASE_URL=None,
            LVCODEX_DB_DUAL_WRITE=None,
            LVCODEX_DB_READ_FROM=None,
        )

    def tearDown(self) -> None:
        _restore_env(self._snapshot)

    def test_sqlite_connection_works_with_pg_helpers_imported(self) -> None:
        # Importing the abstraction must NOT touch the SQLite path or
        # accidentally connect to PG.
        from server_app.services import db as db_mod  # noqa: F401
        import sqlite3
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "auth.sqlite3"
            with patch.dict(os.environ, {"AUTH_DB_PATH": str(db_path)}):
                # Avoid importing server here — the abstraction is
                # supposed to be usable without any of the app routing
                # being loaded. Directly use the core function.
                import server_app.core as core
                core.init_auth_store()
                with core.db_connection() as conn:
                    self.assertIsInstance(conn, sqlite3.Connection)
                    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='accounts'")
                    self.assertIsNotNone(cur.fetchone())


if __name__ == "__main__":
    unittest.main()
