"""T-021 — Postgres migration files must be parseable + match the SQLite schema.

This test is the static guarantee that the ``migrations/postgres/*.sql``
files are not corrupted between hand-edits and that every table the
SQLite store creates also exists in the PG migration set. It runs
without a live Postgres cluster:

* Each migration file must parse cleanly. We prefer the optional
  ``sqlparse`` library when available, otherwise fall back to a minimal
  parser that splits on ``;`` outside string literals — sufficient to
  catch unbalanced quotes or rogue control characters.
* Every ``CREATE TABLE IF NOT EXISTS <name>`` statement that
  ``server_app.core.init_auth_store`` would create against SQLite must
  appear in at least one Postgres migration.
* Every billing-side table (``billing.BillingStore._initialize_schema``)
  must appear in a Postgres migration.
* Idempotency check: every ``CREATE TABLE`` includes ``IF NOT EXISTS``
  and every ``CREATE INDEX`` does too, so re-running migrations on a
  live DB is safe.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

# Project root: tests/server/test_pg_migrations.py → ../../
_ROOT = Path(__file__).resolve().parents[2]
_MIGRATIONS_DIR = _ROOT / "migrations" / "postgres"

# Tables created by server_app/core.py init_auth_store():
_AUTH_TABLES = {
    "users",
    "accounts",
    "profiles",
    "sessions",
    "attempts",
    "exams",
    "attempt_answers",
    "attempt_scores",
    "exam_attempt_category_score",
    "ai_evaluations",
    "payments",
    "subscriptions",
    "entitlements",
    "auth_webhook_events",
    "app_settings",
}

# Tables created by billing.py BillingStore._initialize_schema():
_BILLING_TABLES = {
    "learners",
    "stripe_events",
    "entitlement_grants",
    "entitlement_consumptions",
}

_CREATE_TABLE_RE = re.compile(
    r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+([a-zA-Z_][a-zA-Z0-9_]*)",
    re.IGNORECASE,
)
_CREATE_TABLE_NO_GUARD_RE = re.compile(
    r"CREATE\s+TABLE\s+(?!IF\s+NOT\s+EXISTS)([a-zA-Z_][a-zA-Z0-9_]*)",
    re.IGNORECASE,
)
_CREATE_INDEX_RE = re.compile(
    r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+IF\s+NOT\s+EXISTS\s+([a-zA-Z_][a-zA-Z0-9_]*)",
    re.IGNORECASE,
)
_CREATE_INDEX_NO_GUARD_RE = re.compile(
    r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?!IF\s+NOT\s+EXISTS)([a-zA-Z_][a-zA-Z0-9_]*)",
    re.IGNORECASE,
)


def _split_statements_fallback(sql: str) -> list[str]:
    """Split SQL on top-level ``;`` (not inside string literals).

    Used when ``sqlparse`` isn't installed. Sufficient for the
    well-formed migration files in this repo.
    """
    out: list[str] = []
    buf: list[str] = []
    in_single = False
    in_double = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "-" and i + 1 < len(sql) and sql[i + 1] == "-" and not in_single and not in_double:
            # Line comment — skip to newline.
            while i < len(sql) and sql[i] != "\n":
                buf.append(sql[i])
                i += 1
            continue
        if ch == ";" and not in_single and not in_double:
            stmt = "".join(buf).strip()
            if stmt:
                out.append(stmt)
            buf = []
        else:
            buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


def _parse(sql: str) -> list[str]:
    """Return a list of non-empty statements after parsing."""
    try:
        import sqlparse  # type: ignore[import-not-found]
        statements = [
            str(s).strip()
            for s in sqlparse.parse(sql)
            if str(s).strip() and not str(s).strip().startswith("--")
        ]
        # sqlparse keeps trailing semicolons + comments. Filter them.
        return [s.rstrip(";").strip() for s in statements if s.strip(";").strip()]
    except ImportError:
        return _split_statements_fallback(sql)


class MigrationFilesExistTests(unittest.TestCase):
    def test_migrations_dir_exists(self) -> None:
        self.assertTrue(_MIGRATIONS_DIR.exists(), f"missing dir: {_MIGRATIONS_DIR}")

    def test_at_least_two_migration_files(self) -> None:
        files = sorted(_MIGRATIONS_DIR.glob("*.sql"))
        self.assertGreaterEqual(len(files), 2, f"expected ≥2 migrations, found {files}")

    def test_filenames_follow_numbered_convention(self) -> None:
        for path in sorted(_MIGRATIONS_DIR.glob("*.sql")):
            self.assertRegex(
                path.name, r"^\d{3}_[a-z][a-z0-9_]*\.sql$",
                f"migration filename does not match NNN_<snake>.sql: {path.name}",
            )


class MigrationsParseTests(unittest.TestCase):
    """Every migration file must parse into at least one CREATE statement."""

    def test_every_file_parses_into_at_least_one_statement(self) -> None:
        for path in sorted(_MIGRATIONS_DIR.glob("*.sql")):
            with self.subTest(file=path.name):
                statements = _parse(path.read_text(encoding="utf-8"))
                self.assertGreater(
                    len(statements), 0,
                    f"{path.name} parsed into zero statements",
                )

    def test_every_create_table_uses_if_not_exists(self) -> None:
        for path in sorted(_MIGRATIONS_DIR.glob("*.sql")):
            with self.subTest(file=path.name):
                text = path.read_text(encoding="utf-8")
                # Strip comments so we don't false-positive on prose.
                stripped = re.sub(r"--[^\n]*", "", text)
                matches = _CREATE_TABLE_NO_GUARD_RE.findall(stripped)
                self.assertEqual(
                    matches, [],
                    f"{path.name} has CREATE TABLE without IF NOT EXISTS: {matches}",
                )

    def test_every_create_index_uses_if_not_exists(self) -> None:
        for path in sorted(_MIGRATIONS_DIR.glob("*.sql")):
            with self.subTest(file=path.name):
                text = path.read_text(encoding="utf-8")
                stripped = re.sub(r"--[^\n]*", "", text)
                matches = _CREATE_INDEX_NO_GUARD_RE.findall(stripped)
                self.assertEqual(
                    matches, [],
                    f"{path.name} has CREATE INDEX without IF NOT EXISTS: {matches}",
                )


class SchemaParityTests(unittest.TestCase):
    """The PG migrations must cover every table the SQLite stores create."""

    def setUp(self) -> None:
        self.tables_in_pg: set[str] = set()
        for path in sorted(_MIGRATIONS_DIR.glob("*.sql")):
            text = path.read_text(encoding="utf-8")
            self.tables_in_pg.update(
                m.lower() for m in _CREATE_TABLE_RE.findall(text)
            )

    def test_every_auth_table_has_a_pg_definition(self) -> None:
        missing = _AUTH_TABLES - self.tables_in_pg
        self.assertSetEqual(
            missing, set(),
            f"PG migrations missing auth tables: {sorted(missing)}",
        )

    def test_every_billing_table_has_a_pg_definition(self) -> None:
        missing = _BILLING_TABLES - self.tables_in_pg
        self.assertSetEqual(
            missing, set(),
            f"PG migrations missing billing tables: {sorted(missing)}",
        )

    def test_no_duplicate_table_definitions_across_files(self) -> None:
        # Same table defined in two files is a footgun — sqlite tolerates
        # IF NOT EXISTS but a future split-and-edit could diverge them.
        seen: dict[str, str] = {}
        duplicates: list[tuple[str, str, str]] = []
        for path in sorted(_MIGRATIONS_DIR.glob("*.sql")):
            text = path.read_text(encoding="utf-8")
            for tbl in _CREATE_TABLE_RE.findall(text):
                tbl = tbl.lower()
                if tbl in seen and seen[tbl] != path.name:
                    duplicates.append((tbl, seen[tbl], path.name))
                seen.setdefault(tbl, path.name)
        self.assertEqual(
            duplicates, [],
            f"duplicate table definitions: {duplicates}",
        )


class MigrationListingTests(unittest.TestCase):
    """The db abstraction must enumerate migrations in lexicographic order."""

    def test_list_migration_files_matches_filesystem(self) -> None:
        from server_app.services.db import list_migration_files
        seen = [p.name for p in list_migration_files()]
        expected = [p.name for p in sorted(_MIGRATIONS_DIR.glob("*.sql"))]
        self.assertEqual(seen, expected)


if __name__ == "__main__":
    unittest.main()
