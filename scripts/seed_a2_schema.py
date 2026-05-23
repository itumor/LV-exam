#!/usr/bin/env python3
"""T-025 — A2 exam-schema seed script.

Idempotently seeds the canonical CEFR level → skill → task-type → exam-part
catalogue used by the readiness dashboard (T-030), daily-mission generator
(T-031), and mock-exam runner (T-033).

Levels seeded:

* **A2** — 4 skills × 15 points each (total 60), min 9 per skill (9/15 rule).
* **B1** — placeholder skills; content lands in T-060.
* **B2** — placeholder skills; content lands in T-060.

Usage
-----

::

    python scripts/seed_a2_schema.py
    python scripts/seed_a2_schema.py --db /path/to/auth.sqlite3
    python scripts/seed_a2_schema.py --json   # emit row counts as JSON

The script is safe to re-run — every insert uses ``INSERT OR IGNORE`` so a
second invocation reports zero rows added. It exits non-zero only on a
fatal SQLite error or an invalid CLI argument.

Exit codes
----------

* ``0`` — success (whether or not new rows were added).
* ``2`` — invalid argument / unparseable ``--db`` path.
* ``1`` — sqlite or import-time error (stderr carries the traceback).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Imported lazily inside main() so the --help path does not pay the cost
# of importing server_app.core (which boots Sentry, dotenv, etc.).


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Idempotently seed the A2/B1/B2 exam schema "
            "(exam_levels, skills, task_types, exam_parts)."
        ),
    )
    parser.add_argument(
        "--db",
        type=str,
        default=None,
        help=(
            "Override the auth SQLite path. Defaults to the value of "
            "server.AUTH_DB_PATH (typically data/auth.sqlite3)."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the row-count summary as a single JSON line.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress the human-readable summary output.",
    )
    return parser.parse_args(argv)


def _open_connection(db_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection with the same pragmas as ``db_connection``."""

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def seed(db_path: Path) -> dict[str, int]:
    """Seed the schema at *db_path* and return the row-count summary."""

    from server_app.services import schema_a2

    with _open_connection(db_path) as conn:
        schema_a2.init_a2_schema_tables(conn)
        counts = schema_a2.ensure_seed_data(conn)
        conn.commit()
    return counts


def _resolve_default_db_path() -> Path:
    """Return the default SQLite path used by the running server."""

    from server_app import core as _core

    raw = getattr(_core, "AUTH_DB_PATH", None)
    if raw is None:
        return _REPO_ROOT / "data" / "auth.sqlite3"
    return Path(raw)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.db:
        db_path = Path(args.db).expanduser().resolve()
    else:
        db_path = _resolve_default_db_path()

    try:
        counts = seed(db_path)
    except sqlite3.Error as exc:
        print(f"sqlite error while seeding {db_path}: {exc}", file=sys.stderr)
        return 1

    payload = {
        "db": str(db_path),
        "inserted": counts,
        "total_inserted": sum(counts.values()),
    }
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    elif not args.quiet:
        added = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        verb = "Seeded" if payload["total_inserted"] > 0 else "Verified"
        print(f"{verb} A2/B1/B2 schema in {db_path}: {added}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
