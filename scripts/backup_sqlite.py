#!/usr/bin/env python3
"""Create and verify SQLite backups for local production stores."""

from __future__ import annotations

import argparse
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCES = {
    "auth": Path(os.getenv("AUTH_DB_PATH", str(ROOT / ".multica" / "auth.sqlite3"))),
    "billing": Path(os.getenv("BILLING_DB_PATH", str(ROOT / "data" / "billing.sqlite3"))),
}


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def backup_database(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as src, sqlite3.connect(destination) as dst:
        src.backup(dst)


def verify_database(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        result = conn.execute("PRAGMA integrity_check").fetchone()
    if result is None or result[0] != "ok":
        raise RuntimeError(f"Integrity check failed for {path}: {result}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(ROOT / "backups"), help="Directory for backup files.")
    parser.add_argument("--verify-only", action="store_true", help="Verify source databases without writing backups.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    created: list[Path] = []
    for name, source in DEFAULT_SOURCES.items():
        if not source.exists():
            print(f"skip {name}: {source} does not exist")
            continue
        verify_database(source)
        if args.verify_only:
            print(f"verified {name}: {source}")
            continue
        destination = output_dir / f"{name}-{timestamp()}.sqlite3"
        backup_database(source, destination)
        verify_database(destination)
        created.append(destination)
        print(f"backed up {name}: {destination}")

    if not created and not args.verify_only:
        print("no SQLite databases found to back up")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
