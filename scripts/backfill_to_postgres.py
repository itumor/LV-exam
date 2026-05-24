#!/usr/bin/env python3
"""T-021 — backfill historical SQLite rows into the Postgres cluster.

Usage::

    python3 scripts/backfill_to_postgres.py \
        --auth-db /app/data/auth.sqlite3 \
        --billing-db /app/data/billing.sqlite3 \
        --dsn "postgres://lvcodex:***@db.fly.dev:5432/lvcodex" \
        --batch-size 500

The script is **idempotent**: it uses ``INSERT … ON CONFLICT DO NOTHING``
for every row. Re-running it after a failed run will skip already-copied
rows and resume.

Process used by the cutover playbook (docs/postgres-migration.md):

1. Enable dual-write: set ``LVCODEX_DB_DUAL_WRITE=1`` and redeploy. From
   that point forward, every new write hits both stores.
2. Run this script to backfill historical rows that existed before the
   dual-write window opened.
3. Verify row counts match between SQLite and Postgres.
4. Flip ``LVCODEX_DB_READ_FROM=postgres`` to switch reads.
5. Disable dual-write once stable.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Iterable, Sequence

# Allow ``python scripts/backfill_to_postgres.py`` to find server_app.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from server_app.services import db as db_layer  # noqa: E402


AUTH_TABLES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("accounts", ("id", "email", "password_salt", "password_hash", "status", "role", "created_at", "deleted_at")),
    ("users", ("id", "account_id", "email", "display_name", "status", "role", "created_at", "updated_at")),
    ("profiles", ("account_id", "full_name", "native_language", "exam_target_date", "exam_pack_status", "updated_at")),
    ("sessions", ("token", "account_id", "created_at", "expires_at", "revoked_at", "last_seen_at")),
    ("exams", ("id", "title", "content_version", "status", "manifest_payload", "answer_key_payload", "created_at", "updated_at")),
    ("attempts", (
        "id", "account_id", "exam_id", "exam_title", "status", "submitted_at",
        "score_total", "score_payload", "submission_payload", "content_version",
        "exam_snapshot_payload", "answer_payload", "started_at", "expires_at",
        "scored_at", "created_at", "updated_at",
    )),
    ("attempt_answers", (
        "id", "attempt_id", "account_id", "skill", "task_key", "item_index",
        "answer_payload", "created_at", "updated_at",
    )),
    ("attempt_scores", (
        "id", "attempt_id", "account_id", "scoring_version", "score_total",
        "score_payload", "created_at",
    )),
    ("exam_attempt_category_score", (
        "id", "attempt_id", "account_id", "category", "score_0_to_15",
        "passed_boolean", "created_at",
    )),
    ("ai_evaluations", (
        "id", "attempt_id", "account_id", "provider", "model", "status",
        "evaluation_payload", "created_at",
    )),
    ("payments", (
        "id", "account_id", "provider", "provider_reference", "status",
        "amount_cents", "currency", "payload", "created_at",
    )),
    ("subscriptions", (
        "id", "account_id", "provider", "provider_reference", "status",
        "current_period_end", "payload", "created_at", "updated_at",
    )),
    ("entitlements", (
        "id", "account_id", "entitlement_type", "source_reference",
        "starts_at", "expires_at", "consumed_at", "payload", "created_at",
    )),
    ("auth_webhook_events", ("event_id", "event_type", "payload", "created_at")),
    ("app_settings", ("key", "value", "updated_at")),
)

BILLING_TABLES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("learners", ("learner_id", "email", "name", "status", "created_at", "updated_at")),
    ("stripe_events", ("event_id", "event_type", "learner_id", "created_at", "payload_json")),
    ("entitlement_grants", (
        "grant_id", "learner_id", "grant_type", "product_key", "quantity",
        "exam_id", "customer_id", "source_reference", "expires_at",
        "revoked_at", "source_event_id", "created_at", "metadata_json",
    )),
    ("entitlement_consumptions", (
        "consumption_id", "learner_id", "consumption_type", "product_key",
        "quantity", "exam_id", "customer_id", "source_reference",
        "source_event_id", "created_at", "metadata_json",
    )),
)


def _open_sqlite(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _row_values(row: sqlite3.Row, columns: Sequence[str]) -> tuple:
    values: list = []
    for col in columns:
        try:
            v = row[col]
        except (IndexError, KeyError):
            v = None
        values.append(v)
    return tuple(values)


def _chunked(seq: Iterable, size: int) -> Iterable[list]:
    batch: list = []
    for item in seq:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def backfill_table(
    sqlite_conn: sqlite3.Connection,
    pg_conn,  # psycopg.Connection
    table: str,
    columns: Sequence[str],
    *,
    batch_size: int = 500,
    log_fn=print,
) -> tuple[int, int]:
    """Copy every row of ``table`` from SQLite to PG. Returns (read, inserted)."""
    select_cols = ", ".join(columns)
    try:
        rows = sqlite_conn.execute(f"SELECT {select_cols} FROM {table}").fetchall()
    except sqlite3.OperationalError as exc:
        log_fn(f"  [{table}] skipped: {exc}")
        return (0, 0)
    if not rows:
        log_fn(f"  [{table}] 0 rows")
        return (0, 0)
    placeholders = ", ".join(["%s"] * len(columns))
    insert_sql = (
        f"INSERT INTO {table} ({select_cols}) VALUES ({placeholders}) "
        "ON CONFLICT DO NOTHING"
    )
    inserted = 0
    with pg_conn.cursor() as cur:
        for batch in _chunked(rows, batch_size):
            cur.executemany(insert_sql, [_row_values(r, columns) for r in batch])
            inserted += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
    pg_conn.commit()
    log_fn(f"  [{table}] {len(rows)} read → {inserted} inserted")
    return (len(rows), inserted)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--auth-db", required=True, help="Path to auth SQLite DB")
    parser.add_argument(
        "--billing-db", default="",
        help="Path to billing SQLite DB (optional)",
    )
    parser.add_argument(
        "--dsn", default="",
        help="Postgres DSN. Defaults to DATABASE_URL env var.",
    )
    parser.add_argument(
        "--batch-size", type=int, default=500,
        help="Rows per INSERT batch (default 500)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Read SQLite rows but skip PG writes.",
    )
    args = parser.parse_args(argv)

    dsn = args.dsn or db_layer.get_postgres_dsn()
    if not dsn:
        print("error: no DSN provided and DATABASE_URL unset", file=sys.stderr)
        return 2

    auth_path = Path(args.auth_db)
    if not auth_path.exists():
        print(f"error: auth db not found: {auth_path}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(f"[dry-run] would connect to dsn={dsn[:32]}...")

    # Apply migrations first so the target tables exist.
    if not args.dry_run:
        applied = db_layer.apply_postgres_migrations(dsn)
        if applied:
            print(f"applied migrations: {', '.join(applied)}")

    sqlite_auth = _open_sqlite(auth_path)
    sqlite_billing = (
        _open_sqlite(Path(args.billing_db)) if args.billing_db else None
    )

    total_read = 0
    total_inserted = 0

    if args.dry_run:
        for table, cols in AUTH_TABLES:
            rows = sqlite_auth.execute(f"SELECT count(*) FROM {table}").fetchone()
            print(f"  [{table}] {rows[0]} rows in SQLite")
        return 0

    with db_layer.pg_connection(dsn) as pg_conn:
        print("backfilling auth tables...")
        for table, cols in AUTH_TABLES:
            r, i = backfill_table(
                sqlite_auth, pg_conn, table, cols,
                batch_size=args.batch_size,
            )
            total_read += r
            total_inserted += i
        if sqlite_billing is not None:
            print("backfilling billing tables...")
            for table, cols in BILLING_TABLES:
                r, i = backfill_table(
                    sqlite_billing, pg_conn, table, cols,
                    batch_size=args.batch_size,
                )
                total_read += r
                total_inserted += i

    print(json.dumps({"read": total_read, "inserted": total_inserted}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
