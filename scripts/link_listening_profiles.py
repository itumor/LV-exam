#!/usr/bin/env python3
"""T-023 migration — link legacy listening-library profiles to unified accounts.

The listening-library used to ship without server-side identity: progress
was stored client-side under a free-form identifier (typically the user's
email, occasionally a UUID stored in ``localStorage``). After T-023 every
user has a single unified account on the lvcodex server. This script
walks an export of legacy listening profiles and inserts a row into
``listening_profile_links`` for every legacy identifier that matches an
account by email.

Input format
============

A JSON file with one record per legacy listening profile::

    [
        {"listening_profile_id": "alice@example.com", "email": "alice@example.com"},
        {"listening_profile_id": "uuid-abc-123", "email": "bob@example.com"}
    ]

The optional ``email`` field is used to match against ``accounts.email``.
If absent the script falls back to treating ``listening_profile_id`` as an
email when it contains an ``@``.

Output
======

Prints a JSON summary on stdout::

    {
        "total": 17,
        "linked": 12,
        "already_linked": 3,
        "unmatched": 2,
        "errors": []
    }

Exits non-zero if at least one record raises an unexpected error. Records
that cannot be matched to an account are *not* errors — they end up in
``unmatched``.

Usage
=====

::

    python3 scripts/link_listening_profiles.py path/to/legacy-profiles.json
    python3 scripts/link_listening_profiles.py --dry-run profiles.json
    python3 scripts/link_listening_profiles.py --auth-db /tmp/auth.sqlite3 profiles.json
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

# Make the project root importable when this script is invoked from the
# repository root or via ``python scripts/...``.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _normalize_email(value: str | None) -> str:
    return (value or "").strip().lower()


def _record_email(record: dict) -> str:
    explicit = _normalize_email(record.get("email"))
    if explicit:
        return explicit
    legacy = _normalize_email(record.get("listening_profile_id"))
    if "@" in legacy:
        return legacy
    return ""


def _find_account_id(conn: sqlite3.Connection, email: str) -> str | None:
    if not email:
        return None
    row = conn.execute(
        "SELECT id FROM accounts WHERE email = ? AND deleted_at IS NULL",
        (email,),
    ).fetchone()
    if row is None:
        return None
    return row["id"]


def _load_records(path: Path) -> list[dict]:
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, list):
        raise SystemExit(
            f"{path}: expected a JSON array of profile records, got {type(data).__name__}"
        )
    return data


def link_records(
    records: list[dict], *, auth_db: Path | None = None, dry_run: bool = False
) -> dict:
    """Link every legacy listening profile in ``records`` to an account.

    Used both by the CLI entrypoint and by tests. Returns the same shape
    that the CLI prints to stdout.
    """

    # Imports are inside the function so the help text remains usable even
    # when the auth-store dependencies are missing in CI sandboxes.
    if auth_db is not None:
        os.environ.setdefault("AUTH_DB_PATH", str(auth_db))
    from server_app import core as _core
    from server_app.services import auth_store

    if auth_db is not None:
        _core.AUTH_DB_PATH = Path(auth_db)

    summary: dict = {
        "total": len(records),
        "linked": 0,
        "already_linked": 0,
        "unmatched": 0,
        "errors": [],
    }

    with auth_store.db_connection() as conn:
        auth_store.ensure_listening_profile_links_table(conn)
        for index, record in enumerate(records):
            try:
                if not isinstance(record, dict):
                    raise ValueError(
                        f"record {index}: expected an object, got {type(record).__name__}"
                    )
                listening_profile_id = (
                    str(record.get("listening_profile_id") or "").strip()
                )
                if not listening_profile_id:
                    raise ValueError(
                        f"record {index}: missing listening_profile_id"
                    )
                email = _record_email(record)
                account_id = _find_account_id(conn, email)
                if account_id is None:
                    summary["unmatched"] += 1
                    continue
                if dry_run:
                    summary["linked"] += 1
                    continue
                result = auth_store.link_listening_profile(
                    account_id, listening_profile_id, conn=conn
                )
                if result["created"]:
                    summary["linked"] += 1
                else:
                    summary["already_linked"] += 1
            except Exception as error:  # pragma: no cover — defensive
                summary["errors"].append(
                    {"index": index, "error": str(error), "record": record}
                )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "input",
        type=Path,
        help="Path to a JSON file with the legacy listening-profile records.",
    )
    parser.add_argument(
        "--auth-db",
        type=Path,
        default=None,
        help="Override the auth SQLite path (defaults to .multica/auth.sqlite3).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write any rows; report what would change.",
    )
    args = parser.parse_args(argv)

    if not args.input.exists():
        parser.error(f"input file not found: {args.input}")

    records = _load_records(args.input)
    summary = link_records(records, auth_db=args.auth_db, dry_run=args.dry_run)
    json.dump(summary, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 1 if summary["errors"] else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
