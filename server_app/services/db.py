"""Database abstraction layer (T-021).

This module provides a thin compatibility shim that lets the lvcodex
backend speak to **both** the legacy SQLite store and a Postgres cluster
during the dual-write migration window described in
``docs/postgres-migration.md``.

Design constraints
------------------

* **Zero behaviour change** when ``DATABASE_URL`` is unset. Every helper
  here is a no-op for the SQLite path, and the existing
  :func:`server_app.core.db_connection` keeps producing the same
  ``sqlite3.Connection`` objects the call sites already depend on.
* **Lazy psycopg import.** ``psycopg[binary]>=3.2`` is listed in
  ``requirements.txt`` but importing it at module load would force every
  test run to pay the binary-wheel cost. We resolve the driver only when
  Postgres is actually configured.
* **Schema parity, not ORM.** We do not introduce SQLAlchemy or any
  query builder. The PG schema lives under
  ``migrations/postgres/NNN_<name>.sql`` and is created by
  :func:`apply_postgres_migrations`. The runtime DB-2 (dual-write) hook
  re-issues parameterised SQL with a few well-known SQLite→PG dialect
  fixes (``?`` → ``%s``, ``INSERT OR IGNORE`` → ``ON CONFLICT … DO
  NOTHING``).
* **No reads from PG yet.** Switching reads is gated by
  ``LVCODEX_DB_READ_FROM=postgres`` and is **not** plumbed into the
  legacy call sites in T-021. The cutover playbook adds that wiring in a
  follow-up PR once dual-write has been observed clean in production.

Environment variables
---------------------

============================  ================================================
Variable                      Meaning
============================  ================================================
``DATABASE_URL``              Postgres DSN (e.g. ``postgres://u:p@h:5432/db``).
                              Unset → SQLite only, no PG code path is exercised.
``LVCODEX_DB_DUAL_WRITE``     ``1`` to mirror every write to Postgres after the
                              SQLite write succeeds. Default ``0``.
``LVCODEX_DB_READ_FROM``      ``postgres`` to read from PG when call sites are
                              migrated. Default ``sqlite``. Read in
                              :func:`read_from_postgres` only.
``LVCODEX_DB_DUAL_WRITE_LOG`` ``1`` to log every dual-write failure with the
                              translated SQL. Default ``1`` in non-production
                              and ``0`` in production (failures are swallowed
                              but counted).
============================  ================================================

Public surface
--------------

* :func:`is_postgres_configured`
* :func:`is_dual_write_enabled`
* :func:`read_from_postgres`
* :func:`get_postgres_dsn`
* :func:`pg_connection`         (context manager)
* :func:`translate_sql_to_pg`   (pure function — exported for tests)
* :func:`dual_write_execute`    (best-effort write mirror)
* :func:`apply_postgres_migrations`
* :func:`reset_dual_write_state` (test helper)
* :data:`DUAL_WRITE_STATS`      (dict of {"ok": int, "fail": int})

None of these helpers raise on a misconfigured DSN in dual-write mode —
the SQLite path must remain unaffected by Postgres-side failures.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

__all__ = [
    "DUAL_WRITE_STATS",
    "MIGRATIONS_DIR",
    "apply_postgres_migrations",
    "dual_write_execute",
    "get_postgres_dsn",
    "is_dual_write_enabled",
    "is_postgres_configured",
    "list_migration_files",
    "pg_connection",
    "read_from_postgres",
    "reset_dual_write_state",
    "translate_sql_to_pg",
]


# Module-level logger — uses the stdlib logger so that the structured
# JSON access log from server_app.core is not polluted. Tests assert on
# this logger's records via ``self.assertLogs``.
_LOGGER = logging.getLogger("server_app.db")

# Track dual-write health so a Grafana scraper (T-014) can expose it.
# We intentionally use a plain dict + lock instead of a Prometheus
# metric here to avoid an import cycle with ``server_app.metrics``.
DUAL_WRITE_STATS: dict[str, int] = {"ok": 0, "fail": 0, "skipped": 0}
_STATS_LOCK = threading.Lock()

# Repository root → ``migrations/postgres/``.
_REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = _REPO_ROOT / "migrations" / "postgres"


# ---------------------------------------------------------------------------
# Environment-flag helpers
# ---------------------------------------------------------------------------

def get_postgres_dsn() -> str | None:
    """Return the configured Postgres DSN or ``None`` if absent.

    Accepts both ``postgres://`` and ``postgresql://`` schemes (the
    former is what Fly Postgres emits; ``psycopg`` itself prefers the
    latter, but accepts both, so we don't rewrite the scheme here).
    """
    dsn = os.getenv("DATABASE_URL", "").strip()
    if not dsn:
        return None
    if not (dsn.startswith("postgres://") or dsn.startswith("postgresql://")):
        return None
    return dsn


def is_postgres_configured() -> bool:
    """``True`` when ``DATABASE_URL`` points at a Postgres cluster."""
    return get_postgres_dsn() is not None


def is_dual_write_enabled() -> bool:
    """``True`` when both ``DATABASE_URL`` and ``LVCODEX_DB_DUAL_WRITE=1`` are set."""
    if not is_postgres_configured():
        return False
    return os.getenv("LVCODEX_DB_DUAL_WRITE", "0").strip() in ("1", "true", "yes", "on")


def read_from_postgres() -> bool:
    """``True`` when call sites should read from Postgres.

    Only honoured when ``DATABASE_URL`` is set. Defaults to ``False`` to
    keep the cutover one-way until the operator explicitly flips it.
    """
    if not is_postgres_configured():
        return False
    return os.getenv("LVCODEX_DB_READ_FROM", "sqlite").strip().lower() == "postgres"


# ---------------------------------------------------------------------------
# Lazy psycopg loader
# ---------------------------------------------------------------------------

_PSYCOPG_LOCK = threading.Lock()
_PSYCOPG_MODULE: Any | None = None
_PSYCOPG_IMPORT_FAILED = False


def _load_psycopg() -> Any | None:
    """Return the ``psycopg`` (v3) module, or ``None`` if unavailable.

    The first failed import is cached so we don't pay the
    ``ImportError`` cost on every dual-write call.
    """
    global _PSYCOPG_MODULE, _PSYCOPG_IMPORT_FAILED
    if _PSYCOPG_MODULE is not None:
        return _PSYCOPG_MODULE
    if _PSYCOPG_IMPORT_FAILED:
        return None
    with _PSYCOPG_LOCK:
        if _PSYCOPG_MODULE is not None:
            return _PSYCOPG_MODULE
        if _PSYCOPG_IMPORT_FAILED:
            return None
        try:
            import psycopg  # type: ignore[import-not-found]

            _PSYCOPG_MODULE = psycopg
            return psycopg
        except Exception as exc:  # noqa: BLE001 — any failure means PG-off
            _PSYCOPG_IMPORT_FAILED = True
            _LOGGER.warning("psycopg import failed: %s", exc)
            return None


# ---------------------------------------------------------------------------
# Connection factory
# ---------------------------------------------------------------------------

@contextmanager
def pg_connection(dsn: str | None = None) -> Iterator[Any]:
    """Yield a psycopg v3 connection (autocommit=False, ``%s`` placeholders).

    Used by the dual-write hook and the backfill script. Raises
    ``RuntimeError`` when ``DATABASE_URL`` is unset or psycopg is
    missing — callers in the hot path **must** check
    :func:`is_postgres_configured` first; tests use this directly with
    an explicit DSN.
    """
    target_dsn = dsn or get_postgres_dsn()
    if not target_dsn:
        raise RuntimeError("pg_connection called without DATABASE_URL")
    psycopg = _load_psycopg()
    if psycopg is None:
        raise RuntimeError(
            "psycopg is not installed. Run: pip install 'psycopg[binary]>=3.2'"
        )
    conn = psycopg.connect(target_dsn)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# SQL dialect translation
# ---------------------------------------------------------------------------

# SQLite uses ``?`` for parameters; psycopg uses ``%s``. The translator
# rewrites placeholders **only** when they appear outside string
# literals — we deliberately keep this naive (one-pass scan) because the
# call sites in core.py do not embed ``?`` inside string literals.
_INSERT_OR_IGNORE_RE = re.compile(r"\bINSERT\s+OR\s+IGNORE\b", re.IGNORECASE)
_AUTOINCREMENT_RE = re.compile(r"\bAUTOINCREMENT\b", re.IGNORECASE)
_PRAGMA_RE = re.compile(r"\bPRAGMA\s+\w+\s*=\s*\w+\s*;?", re.IGNORECASE)


def translate_sql_to_pg(sql: str) -> str:
    """Translate a SQLite parameterised statement to a psycopg-friendly form.

    This is **not** a general-purpose dialect translator — it covers the
    five idioms used by the lvcodex write paths:

    1. ``?`` placeholders → ``%s`` placeholders (outside string literals).
    2. ``INSERT OR IGNORE`` → ``INSERT … ON CONFLICT DO NOTHING``.
       Callers using ``ON CONFLICT(col) DO …`` are already PG-compatible.
    3. ``AUTOINCREMENT`` is dropped (PG uses ``SERIAL`` / identity).
    4. ``PRAGMA`` statements are stripped (no PG equivalent).
    5. ``ON CONFLICT(col) DO NOTHING`` already valid in both dialects.

    The returned SQL is safe to pass to ``cursor.execute(sql, params)``.
    """
    if not sql:
        return sql
    # Strip PRAGMA statements outright (they are SQLite-specific).
    sql = _PRAGMA_RE.sub("", sql)
    # Drop AUTOINCREMENT keyword — PG rejects it.
    sql = _AUTOINCREMENT_RE.sub("", sql)
    # INSERT OR IGNORE → INSERT … ON CONFLICT DO NOTHING.
    # The translation appends the ON CONFLICT clause at the end of the
    # statement so we don't have to parse table/column lists.
    if _INSERT_OR_IGNORE_RE.search(sql):
        sql = _INSERT_OR_IGNORE_RE.sub("INSERT", sql)
        # Append only if not already present.
        if "ON CONFLICT" not in sql.upper():
            stripped = sql.rstrip().rstrip(";")
            sql = stripped + " ON CONFLICT DO NOTHING"
    # ``?`` → ``%s`` placeholder rewrite, ignoring single-quoted string
    # literals. Two-pass scan: walk characters, track quote state.
    out: list[str] = []
    i = 0
    in_single = False
    in_double = False
    while i < len(sql):
        ch = sql[i]
        if ch == "'" and not in_double:
            # SQLite escapes a single quote inside a literal as '' — that
            # toggle still ends up balanced.
            in_single = not in_single
            out.append(ch)
        elif ch == '"' and not in_single:
            in_double = not in_double
            out.append(ch)
        elif ch == "?" and not in_single and not in_double:
            out.append("%s")
        else:
            out.append(ch)
        i += 1
    return "".join(out)


# ---------------------------------------------------------------------------
# Dual-write hook
# ---------------------------------------------------------------------------

def _record_stat(key: str) -> None:
    with _STATS_LOCK:
        DUAL_WRITE_STATS[key] = DUAL_WRITE_STATS.get(key, 0) + 1


def reset_dual_write_state() -> None:
    """Reset the dual-write counters. Intended for tests only."""
    with _STATS_LOCK:
        for k in DUAL_WRITE_STATS:
            DUAL_WRITE_STATS[k] = 0


def dual_write_execute(
    sql: str,
    params: Sequence[Any] | Mapping[str, Any] | None = None,
    *,
    dsn: str | None = None,
) -> bool:
    """Mirror a SQLite write to Postgres on a best-effort basis.

    Returns ``True`` when the PG write succeeded, ``False`` otherwise.
    **Never raises** — a Postgres outage must not break the SQLite path
    during the dual-write window. Failures are counted in
    :data:`DUAL_WRITE_STATS` and logged at WARNING level (when
    ``LVCODEX_DB_DUAL_WRITE_LOG=1`` or in non-production environments).

    Idempotency is the caller's responsibility — most write paths in
    ``core.py`` are already idempotent (``INSERT … ON CONFLICT`` /
    explicit UUIDs), so a retry-on-failure backfill is sufficient.
    """
    if not is_dual_write_enabled() and dsn is None:
        _record_stat("skipped")
        return False
    target_dsn = dsn or get_postgres_dsn()
    if not target_dsn:
        _record_stat("skipped")
        return False
    pg_sql = translate_sql_to_pg(sql)
    try:
        with pg_connection(target_dsn) as conn:
            with conn.cursor() as cur:
                if params is None:
                    cur.execute(pg_sql)
                else:
                    cur.execute(pg_sql, params)
        _record_stat("ok")
        return True
    except Exception as exc:  # noqa: BLE001 — see docstring contract
        _record_stat("fail")
        if _should_log_failures():
            _LOGGER.warning(
                "dual_write_failed sql=%r err=%s", pg_sql[:200], exc
            )
        return False


def _should_log_failures() -> bool:
    explicit = os.getenv("LVCODEX_DB_DUAL_WRITE_LOG", "").strip().lower()
    if explicit in ("1", "true", "yes", "on"):
        return True
    if explicit in ("0", "false", "no", "off"):
        return False
    return os.getenv("APP_ENV", "development").lower() != "production"


# ---------------------------------------------------------------------------
# Migration runner
# ---------------------------------------------------------------------------

def list_migration_files(directory: Path | None = None) -> list[Path]:
    """Return migration files in sorted-by-name order.

    Migrations follow the convention ``NNN_<name>.sql`` so a lexicographic
    sort matches the intended apply order.
    """
    target = directory or MIGRATIONS_DIR
    if not target.exists():
        return []
    return sorted(p for p in target.iterdir() if p.suffix == ".sql")


def apply_postgres_migrations(
    dsn: str | None = None,
    *,
    directory: Path | None = None,
) -> list[str]:
    """Apply every ``migrations/postgres/*.sql`` file in lexicographic order.

    Returns the list of filenames that were applied (all of them — the
    migrations are written to be idempotent via ``IF NOT EXISTS``). A
    real production runner would record applied filenames in a
    ``schema_migrations`` table, which migration ``000_baseline.sql``
    creates.
    """
    target_dsn = dsn or get_postgres_dsn()
    if not target_dsn:
        raise RuntimeError(
            "apply_postgres_migrations requires DATABASE_URL or explicit dsn"
        )
    applied: list[str] = []
    files = list_migration_files(directory)
    with pg_connection(target_dsn) as conn:
        with conn.cursor() as cur:
            # Bootstrap the ledger table before any other migration so we
            # can record what we ran.
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    filename TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            for path in files:
                cur.execute(
                    "SELECT 1 FROM schema_migrations WHERE filename = %s",
                    (path.name,),
                )
                if cur.fetchone() is not None:
                    continue
                sql_text = path.read_text(encoding="utf-8")
                cur.execute(sql_text)
                cur.execute(
                    "INSERT INTO schema_migrations (filename) VALUES (%s)",
                    (path.name,),
                )
                applied.append(path.name)
    return applied
