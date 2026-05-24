from __future__ import annotations

import base64
import hashlib
import hmac
import json
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FREE_EXAM_ID = "01"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load_json(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


@dataclass(frozen=True)
class ProductDefinition:
    key: str
    name: str
    mode: str
    price_env: str
    quantity: int
    grants_attempts: int = 0
    grants_ai_credits: int = 0
    grant_type: str = "exam_attempts"
    period_attempts: int = 0
    period_ai_credits: int = 0


DEFAULT_PRODUCTS: tuple[ProductDefinition, ...] = (
    ProductDefinition(
        key="single_exam",
        name="Single Exam Simulation",
        mode="payment",
        price_env="STRIPE_PRICE_SINGLE_EXAM",
        quantity=1,
        grants_attempts=1,
        grants_ai_credits=0,
        grant_type="exam_attempts",
    ),
    ProductDefinition(
        key="exam_pack",
        name="Exam Pack",
        mode="payment",
        price_env="STRIPE_PRICE_EXAM_PACK",
        quantity=1,
        grants_attempts=5,
        grants_ai_credits=5,
        grant_type="exam_attempts",
    ),
    ProductDefinition(
        key="monthly_subscription",
        name="Monthly Subscription",
        mode="subscription",
        price_env="STRIPE_PRICE_MONTHLY_SUBSCRIPTION",
        quantity=1,
        grants_attempts=30,
        grants_ai_credits=30,
        grant_type="subscription_attempts",
        period_attempts=30,
        period_ai_credits=30,
    ),
    ProductDefinition(
        key="ai_credits",
        name="AI Scoring Credits",
        mode="payment",
        price_env="STRIPE_PRICE_AI_CREDITS",
        quantity=1,
        grants_attempts=0,
        grants_ai_credits=10,
        grant_type="ai_credits",
    ),
)


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc, tb) -> bool:
        try:
            return bool(super().__exit__(exc_type, exc, tb))
        finally:
            self.close()


class BillingStore:
    def __init__(self, db_path: str | Path, *, free_exam_id: str = FREE_EXAM_ID) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.free_exam_id = free_exam_id
        self._lock = threading.Lock()
        self._initialize_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30, factory=ClosingConnection)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _initialize_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS learners (
                    learner_id TEXT PRIMARY KEY,
                    email TEXT,
                    name TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS stripe_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    learner_id TEXT,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS entitlement_grants (
                    grant_id TEXT PRIMARY KEY,
                    learner_id TEXT NOT NULL,
                    grant_type TEXT NOT NULL,
                    product_key TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    exam_id TEXT,
                    customer_id TEXT,
                    source_reference TEXT,
                    expires_at TEXT,
                    revoked_at TEXT,
                    source_event_id TEXT,
                    created_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    FOREIGN KEY (learner_id) REFERENCES learners (learner_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS entitlement_consumptions (
                    consumption_id TEXT PRIMARY KEY,
                    learner_id TEXT NOT NULL,
                    consumption_type TEXT NOT NULL,
                    product_key TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    exam_id TEXT,
                    customer_id TEXT,
                    source_reference TEXT,
                    source_event_id TEXT,
                    created_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    FOREIGN KEY (learner_id) REFERENCES learners (learner_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_entitlement_grants_learner ON entitlement_grants (learner_id, grant_type, revoked_at, expires_at);
                CREATE INDEX IF NOT EXISTS idx_entitlement_consumptions_learner ON entitlement_consumptions (learner_id, consumption_type, exam_id);
                CREATE INDEX IF NOT EXISTS idx_stripe_events_learner ON stripe_events (learner_id, created_at DESC);
                """
            )

    def ensure_learner(self, learner_id: str, *, email: str | None = None, name: str | None = None) -> dict[str, Any]:
        now = utc_now_iso()
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT learner_id, email, name, status, created_at, updated_at FROM learners WHERE learner_id = ?", (learner_id,)).fetchone()
            created = row is None
            if row is None:
                conn.execute(
                    """
                    INSERT INTO learners (learner_id, email, name, status, created_at, updated_at)
                    VALUES (?, ?, ?, 'active', ?, ?)
                    """,
                    (learner_id, email, name, now, now),
                )
            else:
                conn.execute(
                    """
                    UPDATE learners
                    SET email = COALESCE(?, email),
                        name = COALESCE(?, name),
                        updated_at = ?
                    WHERE learner_id = ?
                    """,
                    (email, name, now, learner_id),
                )
            free_exam_grant = conn.execute(
                """
                SELECT grant_id
                FROM entitlement_grants
                WHERE learner_id = ? AND grant_type = 'free_exam' AND exam_id = ? AND revoked_at IS NULL
                LIMIT 1
                """,
                (learner_id, self.free_exam_id),
            ).fetchone()
            free_exam_used = conn.execute(
                """
                SELECT consumption_id
                FROM entitlement_consumptions
                WHERE learner_id = ? AND consumption_type = 'free_exam' AND exam_id = ?
                LIMIT 1
                """,
                (learner_id, self.free_exam_id),
            ).fetchone()
            if free_exam_grant is None and free_exam_used is None:
                conn.execute(
                    """
                    INSERT INTO entitlement_grants
                    (grant_id, learner_id, grant_type, product_key, quantity, exam_id, customer_id, source_reference, expires_at, revoked_at, source_event_id, created_at, metadata_json)
                    VALUES (?, ?, 'free_exam', 'free_exam', 1, ?, NULL, 'system-free-exam', NULL, NULL, NULL, ?, ?)
                    """,
                    (
                        new_id("grant"),
                        learner_id,
                        self.free_exam_id,
                        now if created else utc_now_iso(),
                        dump_json({"source": "learner bootstrap"}),
                    ),
                )
            return self.get_learner(learner_id)

    def get_learner(self, learner_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT learner_id, email, name, status, created_at, updated_at FROM learners WHERE learner_id = ?",
                (learner_id,),
            ).fetchone()
        return dict(row) if row else {
            "learner_id": learner_id,
            "email": None,
            "name": None,
            "status": "missing",
            "created_at": None,
            "updated_at": None,
        }

    def list_recent_events(self, learner_id: str, *, limit: int = 10) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT event_id, event_type, created_at, payload_json
                FROM stripe_events
                WHERE learner_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (learner_id, limit),
            ).fetchall()
        return [
            {
                "event_id": row["event_id"],
                "event_type": row["event_type"],
                "created_at": row["created_at"],
                "payload": load_json(row["payload_json"], {}),
            }
            for row in rows
        ]

    def list_recent_activity(self, learner_id: str, *, limit: int = 10) -> list[dict[str, Any]]:
        with self._connect() as conn:
            grants = conn.execute(
                """
                SELECT grant_id AS id, grant_type AS type, product_key, quantity, exam_id, expires_at, revoked_at, source_reference, created_at, metadata_json
                FROM entitlement_grants
                WHERE learner_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (learner_id, limit),
            ).fetchall()
            consumptions = conn.execute(
                """
                SELECT consumption_id AS id, consumption_type AS type, product_key, quantity, exam_id, source_reference, source_event_id, created_at, metadata_json
                FROM entitlement_consumptions
                WHERE learner_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (learner_id, limit),
            ).fetchall()
        rows: list[dict[str, Any]] = []
        for row in grants:
            rows.append(
                {
                    "kind": "grant",
                    "id": row["id"],
                    "type": row["type"],
                    "product_key": row["product_key"],
                    "quantity": row["quantity"],
                    "exam_id": row["exam_id"],
                    "expires_at": row["expires_at"],
                    "revoked_at": row["revoked_at"],
                    "source_reference": row["source_reference"],
                    "created_at": row["created_at"],
                    "metadata": load_json(row["metadata_json"], {}),
                }
            )
        for row in consumptions:
            rows.append(
                {
                    "kind": "consumption",
                    "id": row["id"],
                    "type": row["type"],
                    "product_key": row["product_key"],
                    "quantity": row["quantity"],
                    "exam_id": row["exam_id"],
                    "source_reference": row["source_reference"],
                    "source_event_id": row["source_event_id"],
                    "created_at": row["created_at"],
                    "metadata": load_json(row["metadata_json"], {}),
                }
            )
        rows.sort(key=lambda item: item["created_at"], reverse=True)
        return rows[:limit]

    def learner_ids_for_customer(self, customer_id: str) -> list[str]:
        if not customer_id:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT learner_id
                FROM entitlement_grants
                WHERE customer_id = ?
                """,
                (customer_id,),
            ).fetchall()
        return [row["learner_id"] for row in rows]

    def get_state(self, learner_id: str, *, now: datetime | None = None, user_role: str = "user") -> dict[str, Any]:
        if user_role in {"admin", "superadmin"}:
            return {
                "learner": self.get_learner(learner_id),
                "free_exam_available": True,
                "free_exam_taken": 0,
                "paid_attempts_remaining": -1,
                "ai_credits_remaining": -1,
                "subscription_active": True,
                "frozen": False,
                "current_plan": "admin_unlimited",
                "recent_events": self.list_recent_events(learner_id, limit=10),
                "recent_activity": self.list_recent_activity(learner_id, limit=10),
            }
        current_time = now or utc_now()
        with self._connect() as conn:
            learner = conn.execute(
                "SELECT learner_id, email, name, status, created_at, updated_at FROM learners WHERE learner_id = ?",
                (learner_id,),
            ).fetchone()
            if learner is None:
                return {
                    "learner": self.get_learner(learner_id),
                    "free_exam_available": True,
                    "free_exam_taken": 0,
                    "paid_attempts_remaining": 0,
                    "ai_credits_remaining": 0,
                    "subscription_active": False,
                    "frozen": False,
                    "current_plan": "free",
                    "recent_events": [],
                    "recent_activity": [],
                }

            grants = conn.execute(
                """
                SELECT grant_type, product_key, quantity, exam_id, customer_id, source_reference, expires_at, revoked_at, created_at, metadata_json
                FROM entitlement_grants
                WHERE learner_id = ?
                ORDER BY created_at ASC
                """,
                (learner_id,),
            ).fetchall()
            consumptions = conn.execute(
                """
                SELECT consumption_type, product_key, quantity, exam_id, created_at
                FROM entitlement_consumptions
                WHERE learner_id = ?
                ORDER BY created_at ASC
                """,
                (learner_id,),
            ).fetchall()
            recent_events = conn.execute(
                """
                SELECT event_id, event_type, created_at, payload_json
                FROM stripe_events
                WHERE learner_id = ?
                ORDER BY created_at DESC
                LIMIT 10
                """,
                (learner_id,),
            ).fetchall()

        learner_dict = dict(learner)
        is_frozen = learner_dict.get("status") == "frozen"
        free_exam_available = 0
        paid_attempts = 0
        ai_credits = 0
        subscription_active = False

        for row in grants:
            if row["revoked_at"]:
                continue
            expires_at = parse_iso(row["expires_at"])
            if expires_at and expires_at <= current_time:
                continue
            quantity = int(row["quantity"] or 0)
            if row["grant_type"] == "free_exam" and row["exam_id"] == self.free_exam_id:
                free_exam_available += quantity
            elif row["grant_type"] in {"exam_attempts", "subscription_attempts"}:
                paid_attempts += quantity
                if row["grant_type"] == "subscription_attempts":
                    subscription_active = True
            elif row["grant_type"] == "ai_credits":
                ai_credits += quantity

        free_exam_taken = 0
        paid_attempts_used = 0
        ai_credits_used = 0
        for row in consumptions:
            quantity = int(row["quantity"] or 0)
            if row["consumption_type"] == "free_exam" and row["exam_id"] == self.free_exam_id:
                free_exam_taken += quantity
            elif row["consumption_type"] == "exam_attempt":
                paid_attempts_used += quantity
            elif row["consumption_type"] == "ai_score":
                ai_credits_used += quantity

        free_exam_available = max(0, free_exam_available - free_exam_taken)
        paid_attempts_remaining = max(0, paid_attempts - paid_attempts_used)
        ai_credits_remaining = max(0, ai_credits - ai_credits_used)

        current_plan = "free"
        if subscription_active:
            current_plan = "subscription"
        elif paid_attempts_remaining > 0:
            current_plan = "exam_pack"
        elif not free_exam_available:
            current_plan = "free_exhausted"

        return {
            "learner": learner_dict,
            "free_exam_available": bool(free_exam_available),
            "free_exam_taken": free_exam_taken,
            "paid_attempts_remaining": paid_attempts_remaining,
            "ai_credits_remaining": ai_credits_remaining,
            "subscription_active": subscription_active,
            "frozen": is_frozen,
            "current_plan": current_plan,
            "recent_events": [
                {
                    "event_id": row["event_id"],
                    "event_type": row["event_type"],
                    "created_at": row["created_at"],
                    "payload": load_json(row["payload_json"], {}),
                }
                for row in recent_events
            ],
            "recent_activity": self.list_recent_activity(learner_id, limit=10),
        }

    def can_access_exam(self, learner_id: str, exam_id: str, *, now: datetime | None = None) -> tuple[bool, str]:
        state = self.get_state(learner_id, now=now)
        if state["frozen"]:
            return False, "account_frozen"
        if exam_id == self.free_exam_id and state["free_exam_available"]:
            return True, "free_exam_available"
        if state["paid_attempts_remaining"] > 0:
            return True, "paid_attempt_available"
        return False, "no_attempts_left"

    def consume_exam_access(self, learner_id: str, exam_id: str, *, source_reference: str | None = None, source_event_id: str | None = None, user_role: str = "user") -> dict[str, Any]:
        if user_role in {"admin", "superadmin"}:
            return {"allowed": True, "reason": "admin_unlimited", "state": self.get_state(learner_id, user_role=user_role)}
        allowed = False
        reason = "no_attempts_left"
        with self._lock, self._connect() as conn:
            if source_event_id or source_reference:
                existing = conn.execute(
                    """
                    SELECT consumption_id
                    FROM entitlement_consumptions
                    WHERE learner_id = ?
                      AND consumption_type IN ('free_exam', 'exam_attempt')
                      AND (
                        (? IS NOT NULL AND source_event_id = ?)
                        OR (? IS NOT NULL AND source_reference = ?)
                      )
                    LIMIT 1
                    """,
                    (learner_id, source_event_id, source_event_id, source_reference, source_reference),
                ).fetchone()
                if existing is not None:
                    return {"allowed": True, "reason": "already_consumed", "state": self.get_state(learner_id)}
            state = self.get_state(learner_id)
            if state["frozen"]:
                return {"allowed": False, "reason": "account_frozen", "state": state}
            now = utc_now_iso()
            if exam_id == self.free_exam_id and state["free_exam_available"]:
                conn.execute(
                    """
                    INSERT INTO entitlement_consumptions
                    (consumption_id, learner_id, consumption_type, product_key, quantity, exam_id, source_reference, source_event_id, created_at, metadata_json)
                    VALUES (?, ?, 'free_exam', 'free_exam', 1, ?, ?, ?, ?, ?)
                    """,
                    (
                        new_id("cons"),
                        learner_id,
                        exam_id,
                        source_reference,
                        source_event_id,
                        now,
                        dump_json({"exam_id": exam_id}),
                    ),
                )
                allowed = True
                reason = "free_exam_consumed"
            elif state["paid_attempts_remaining"] > 0:
                conn.execute(
                    """
                    INSERT INTO entitlement_consumptions
                    (consumption_id, learner_id, consumption_type, product_key, quantity, exam_id, source_reference, source_event_id, created_at, metadata_json)
                    VALUES (?, ?, 'exam_attempt', 'paid_exam', 1, ?, ?, ?, ?, ?)
                    """,
                    (
                        new_id("cons"),
                        learner_id,
                        exam_id,
                        source_reference,
                        source_event_id,
                        now,
                        dump_json({"exam_id": exam_id}),
                    ),
                )
                allowed = True
                reason = "paid_attempt_consumed"

            else:
                allowed = False
                reason = "no_attempts_left"
        return {"allowed": allowed, "reason": reason, "state": self.get_state(learner_id)}

    def consume_ai_credit(self, learner_id: str, *, source_reference: str | None = None, source_event_id: str | None = None, user_role: str = "user") -> dict[str, Any]:
        if user_role in {"admin", "superadmin"}:
            return {"allowed": True, "reason": "admin_unlimited", "state": self.get_state(learner_id, user_role=user_role)}
        allowed = False
        reason = "no_ai_credits_left"
        with self._lock, self._connect() as conn:
            if source_event_id or source_reference:
                existing = conn.execute(
                    """
                    SELECT consumption_id
                    FROM entitlement_consumptions
                    WHERE learner_id = ?
                      AND consumption_type = 'ai_score'
                      AND (
                        (? IS NOT NULL AND source_event_id = ?)
                        OR (? IS NOT NULL AND source_reference = ?)
                      )
                    LIMIT 1
                    """,
                    (learner_id, source_event_id, source_event_id, source_reference, source_reference),
                ).fetchone()
                if existing is not None:
                    return {"allowed": True, "reason": "already_consumed", "state": self.get_state(learner_id)}
            state = self.get_state(learner_id)
            if state["frozen"]:
                return {"allowed": False, "reason": "account_frozen", "state": state}
            if state["ai_credits_remaining"] <= 0:
                return {"allowed": False, "reason": "no_ai_credits_left", "state": state}
            now = utc_now_iso()
            conn.execute(
                """
                INSERT INTO entitlement_consumptions
                (consumption_id, learner_id, consumption_type, product_key, quantity, exam_id, source_reference, source_event_id, created_at, metadata_json)
                VALUES (?, ?, 'ai_score', 'ai_credits', 1, NULL, ?, ?, ?, ?)
                """,
                (
                    new_id("cons"),
                    learner_id,
                    source_reference,
                    source_event_id,
                    now,
                    dump_json({}),
                ),
            )
            allowed = True
            reason = "ai_credit_consumed"
        return {"allowed": allowed, "reason": reason, "state": self.get_state(learner_id)}

    def grant_product(
        self,
        learner_id: str,
        *,
        product_key: str,
        quantity: int,
        grant_type: str,
        exam_id: str | None = None,
        expires_at: str | None = None,
        customer_id: str | None = None,
        source_reference: str | None = None,
        source_event_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO entitlement_grants
                (grant_id, learner_id, grant_type, product_key, quantity, exam_id, customer_id, source_reference, expires_at, revoked_at, source_event_id, created_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
                """,
                (
                    new_id("grant"),
                    learner_id,
                    grant_type,
                    product_key,
                    quantity,
                    exam_id,
                    customer_id,
                    source_reference,
                    expires_at,
                    source_event_id,
                    now,
                    dump_json(metadata or {}),
                ),
            )
            return self.get_state(learner_id)

    def freeze_learner(self, learner_id: str) -> None:
        now = utc_now_iso()
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE learners SET status = 'frozen', updated_at = ? WHERE learner_id = ?", (now, learner_id))

    def revoke_grants(self, learner_id: str, *, source_reference: str | None = None, customer_id: str | None = None, grant_types: set[str] | None = None) -> int:
        if not source_reference and not customer_id and not grant_types:
            return 0
        now = utc_now_iso()
        conditions = ["learner_id = ?"]
        params: list[Any] = [learner_id]
        if source_reference:
            conditions.append("source_reference = ?")
            params.append(source_reference)
        if customer_id:
            conditions.append("customer_id = ?")
            params.append(customer_id)
        if grant_types:
            placeholders = ",".join("?" for _ in grant_types)
            conditions.append(f"grant_type IN ({placeholders})")
            params.extend(sorted(grant_types))
        sql = f"UPDATE entitlement_grants SET revoked_at = ? WHERE {' AND '.join(conditions)} AND revoked_at IS NULL"
        with self._lock, self._connect() as conn:
            cursor = conn.execute(sql, [now, *params])
            return cursor.rowcount

    # ------------------------------------------------------------------ #
    # T-016: 7-day self-serve refund flow
    # ------------------------------------------------------------------ #
    def find_grants_by_checkout_session(self, checkout_session_id: str) -> list[dict[str, Any]]:
        """Return all grant rows whose metadata references this checkout session."""
        if not checkout_session_id:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT grant_id, learner_id, grant_type, product_key, quantity, exam_id,
                       customer_id, source_reference, expires_at, revoked_at, source_event_id,
                       created_at, metadata_json
                FROM entitlement_grants
                WHERE metadata_json LIKE ?
                ORDER BY created_at ASC
                """,
                (f"%{checkout_session_id}%",),
            ).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            metadata = load_json(row["metadata_json"], {})
            if metadata.get("checkout_session_id") != checkout_session_id:
                continue
            results.append(
                {
                    "grant_id": row["grant_id"],
                    "learner_id": row["learner_id"],
                    "grant_type": row["grant_type"],
                    "product_key": row["product_key"],
                    "quantity": int(row["quantity"] or 0),
                    "exam_id": row["exam_id"],
                    "customer_id": row["customer_id"],
                    "source_reference": row["source_reference"],
                    "expires_at": row["expires_at"],
                    "revoked_at": row["revoked_at"],
                    "source_event_id": row["source_event_id"],
                    "created_at": row["created_at"],
                    "metadata": metadata,
                }
            )
        return results

    def grants_have_consumption(
        self,
        learner_id: str,
        *,
        source_reference: str | None,
        grant_types: set[str],
        after: str | None = None,
    ) -> bool:
        """Return True if any matching grant has been (partially) consumed.

        Consumption is determined by checking whether the learner has any
        ``entitlement_consumptions`` row of the relevant type since the grant
        was created. This is intentionally conservative: any consumption at
        all (free or paid attempts, AI credits) of the kind granted by the
        purchase invalidates a refund.
        """
        type_map = {
            "exam_attempts": "exam_attempt",
            "subscription_attempts": "exam_attempt",
            "ai_credits": "ai_score",
            "free_exam": "free_exam",
        }
        consumption_types = {type_map[t] for t in grant_types if t in type_map}
        if not consumption_types:
            return False
        placeholders = ",".join("?" for _ in consumption_types)
        params: list[Any] = [learner_id, *sorted(consumption_types)]
        sql = (
            "SELECT 1 FROM entitlement_consumptions "
            f"WHERE learner_id = ? AND consumption_type IN ({placeholders})"
        )
        if after:
            sql += " AND created_at >= ?"
            params.append(after)
        sql += " LIMIT 1"
        with self._connect() as conn:
            row = conn.execute(sql, params).fetchone()
        return row is not None

    def mark_grants_refunded(
        self,
        learner_id: str,
        *,
        checkout_session_id: str,
        refund_id: str | None = None,
        refund_reason: str | None = None,
    ) -> int:
        """Mark all grants associated with a checkout session as refunded.

        Revokes the grants (so consume_* sees zero remaining) and stamps the
        refund context into the grant's metadata for the audit trail.
        """
        grants = self.find_grants_by_checkout_session(checkout_session_id)
        if not grants:
            return 0
        now = utc_now_iso()
        affected = 0
        with self._lock, self._connect() as conn:
            for grant in grants:
                if grant["learner_id"] != learner_id:
                    continue
                if grant["revoked_at"]:
                    continue
                metadata = dict(grant["metadata"] or {})
                metadata["refunded_at"] = now
                if refund_id:
                    metadata["refund_id"] = refund_id
                if refund_reason:
                    metadata["refund_reason"] = refund_reason
                conn.execute(
                    """
                    UPDATE entitlement_grants
                    SET revoked_at = ?, metadata_json = ?
                    WHERE grant_id = ?
                    """,
                    (now, dump_json(metadata), grant["grant_id"]),
                )
                affected += 1
        return affected

    def refund_eligibility(
        self,
        learner_id: str,
        *,
        checkout_session_id: str,
        window_days: int = 7,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Server-side check of whether a checkout session is refundable.

        Returns a dict with ``eligible`` (bool), ``reason`` (machine code),
        ``message`` (human-readable), and the list of matched grants. Callers
        in the HTTP layer MUST use this rather than trusting client claims.
        """
        current_time = now or utc_now()
        grants = self.find_grants_by_checkout_session(checkout_session_id)
        if not grants:
            return {
                "eligible": False,
                "reason": "session_not_found",
                "message": "No purchase found for the supplied checkout session.",
                "grants": [],
            }
        # Ownership check: every grant must belong to the requesting learner.
        owners = {g["learner_id"] for g in grants}
        if owners != {learner_id}:
            return {
                "eligible": False,
                "reason": "wrong_user",
                "message": "This purchase does not belong to the current account.",
                "grants": grants,
            }
        # Window check (7 days by default).
        earliest_created = min(parse_iso(g["created_at"]) or current_time for g in grants)
        age_seconds = (current_time - earliest_created).total_seconds()
        window_seconds = window_days * 86400
        if age_seconds > window_seconds:
            return {
                "eligible": False,
                "reason": "window_expired",
                "message": f"Refund window of {window_days} days has expired.",
                "grants": grants,
            }
        # If anything was already refunded, block.
        if any(g["revoked_at"] for g in grants):
            return {
                "eligible": False,
                "reason": "already_refunded",
                "message": "This purchase has already been refunded or revoked.",
                "grants": grants,
            }
        # Consumption check — any consumption of the granted types disqualifies.
        grant_types = {g["grant_type"] for g in grants}
        source_reference = next(
            (g["source_reference"] for g in grants if g["source_reference"]),
            None,
        )
        earliest_created_iso = min(g["created_at"] for g in grants)
        consumed = self.grants_have_consumption(
            learner_id,
            source_reference=source_reference,
            grant_types=grant_types,
            after=earliest_created_iso,
        )
        if consumed:
            return {
                "eligible": False,
                "reason": "credits_consumed",
                "message": "Refund unavailable: one or more credits from this purchase have already been used.",
                "grants": grants,
            }
        return {
            "eligible": True,
            "reason": "eligible",
            "message": "Eligible for a full refund.",
            "grants": grants,
            "payment_reference": source_reference,
        }

    def record_stripe_event(self, event_id: str, event_type: str, learner_id: str | None, payload: dict[str, Any]) -> bool:
        with self._lock, self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO stripe_events (event_id, event_type, learner_id, created_at, payload_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (event_id, event_type, learner_id, utc_now_iso(), dump_json(payload)),
                )
                return True
            except sqlite3.IntegrityError:
                return False

    def _grant_from_checkout_session(self, session: dict[str, Any], event_id: str) -> dict[str, Any]:
        metadata = session.get("metadata") or {}
        learner_id = metadata.get("learner_id")
        product_key = metadata.get("product_key")
        if not learner_id or not product_key:
            return {"status": "ignored", "reason": "missing_metadata"}

        product = self.product_by_key(product_key)
        if not product:
            return {"status": "ignored", "reason": "unknown_product"}

        self.ensure_learner(learner_id, email=session.get("customer_details", {}).get("email"))

        # T-016: capture B2B context + hosted invoice URL so we can show the
        # buyer their PDF invoice and so the refund flow can audit by session.
        is_b2b = str(metadata.get("b2b", "")).lower() == "true"
        invoice_obj = session.get("invoice") if isinstance(session.get("invoice"), dict) else {}
        hosted_invoice_url = (
            session.get("hosted_invoice_url")
            or invoice_obj.get("hosted_invoice_url")
        )
        invoice_pdf = (
            session.get("invoice_pdf")
            or invoice_obj.get("invoice_pdf")
        )
        invoice_id = (
            session.get("invoice") if isinstance(session.get("invoice"), str) else invoice_obj.get("id")
        )
        grant_meta: dict[str, Any] = {"checkout_session_id": session.get("id")}
        if is_b2b:
            grant_meta["b2b"] = True
        if hosted_invoice_url:
            grant_meta["hosted_invoice_url"] = hosted_invoice_url
        if invoice_pdf:
            grant_meta["invoice_pdf"] = invoice_pdf
        if invoice_id:
            grant_meta["invoice_id"] = invoice_id

        if product.key == "single_exam":
            self.grant_product(
                learner_id,
                product_key=product.key,
                quantity=product.grants_attempts,
                grant_type="exam_attempts",
                customer_id=session.get("customer"),
                source_reference=session.get("payment_intent") or session.get("id"),
                source_event_id=event_id,
                metadata=grant_meta,
            )
        elif product.key == "exam_pack":
            self.grant_product(
                learner_id,
                product_key=product.key,
                quantity=product.grants_attempts,
                grant_type="exam_attempts",
                customer_id=session.get("customer"),
                source_reference=session.get("payment_intent") or session.get("id"),
                source_event_id=event_id,
                metadata=grant_meta,
            )
            if product.grants_ai_credits:
                self.grant_product(
                    learner_id,
                    product_key=product.key,
                    quantity=product.grants_ai_credits,
                    grant_type="ai_credits",
                    customer_id=session.get("customer"),
                    source_reference=session.get("payment_intent") or session.get("id"),
                    source_event_id=event_id,
                    metadata=grant_meta,
                )
        elif product.key == "monthly_subscription":
            return {
                "status": "pending_subscription_activation",
                "learner_id": learner_id,
                "product_key": product.key,
            }
        elif product.key == "ai_credits":
            self.grant_product(
                learner_id,
                product_key=product.key,
                quantity=product.grants_ai_credits,
                grant_type="ai_credits",
                customer_id=session.get("customer"),
                source_reference=session.get("payment_intent") or session.get("id"),
                source_event_id=event_id,
                metadata=grant_meta,
            )
        return {
            "status": "granted",
            "learner_id": learner_id,
            "product_key": product.key,
            "b2b": is_b2b,
            "hosted_invoice_url": hosted_invoice_url,
        }

    def _process_subscription_event(self, subscription: dict[str, Any], event_id: str, *, deleted: bool = False) -> dict[str, Any]:
        metadata = subscription.get("metadata") or {}
        learner_id = metadata.get("learner_id")
        product_key = metadata.get("product_key", "monthly_subscription")
        if not learner_id:
            return {"status": "ignored", "reason": "missing_metadata"}

        self.ensure_learner(learner_id, email=subscription.get("customer_email"))
        if deleted or subscription.get("status") in {"canceled", "incomplete_expired"}:
            self.revoke_grants(
                learner_id,
                source_reference=subscription.get("id"),
                customer_id=subscription.get("customer"),
                grant_types={"subscription_attempts", "ai_credits"},
            )
            return {"status": "revoked", "learner_id": learner_id, "product_key": product_key}

        current_period_end = subscription.get("current_period_end")
        expires_at = None
        if current_period_end:
            expires_at = datetime.fromtimestamp(int(current_period_end), tz=timezone.utc).isoformat().replace("+00:00", "Z")
        self.revoke_grants(
            learner_id,
            source_reference=subscription.get("id"),
            customer_id=subscription.get("customer"),
            grant_types={"subscription_attempts", "ai_credits"},
        )
        self.grant_product(
            learner_id,
            product_key=product_key,
            quantity=30,
            grant_type="subscription_attempts",
            expires_at=expires_at,
            customer_id=subscription.get("customer"),
            source_reference=subscription.get("id"),
            source_event_id=event_id,
            metadata={"subscription_status": subscription.get("status")},
        )
        self.grant_product(
            learner_id,
            product_key=product_key,
            quantity=30,
            grant_type="ai_credits",
            expires_at=expires_at,
            customer_id=subscription.get("customer"),
            source_reference=subscription.get("id"),
            source_event_id=event_id,
            metadata={"subscription_status": subscription.get("status")},
        )
        return {"status": "updated", "learner_id": learner_id, "product_key": product_key}

    def _process_refund_or_dispute(self, object_data: dict[str, Any], event_type: str, event_id: str) -> dict[str, Any]:
        customer_id = object_data.get("customer")
        payment_intent = object_data.get("payment_intent")
        charge = object_data.get("charge")
        target_reference = payment_intent or charge or object_data.get("id")
        learner_id = object_data.get("metadata", {}).get("learner_id")
        learner_ids = [learner_id] if learner_id else self.learner_ids_for_customer(customer_id)
        for item in learner_ids:
            self.freeze_learner(item)
            if target_reference or customer_id:
                self.revoke_grants(
                    item,
                    source_reference=target_reference,
                    customer_id=customer_id,
                    grant_types={"exam_attempts", "subscription_attempts", "ai_credits", "free_exam"},
                )
        return {
            "status": "frozen" if event_type == "charge.dispute.created" else "revoked",
            "learner_id": learner_id or learner_ids,
            "reference": target_reference,
        }

    def process_stripe_event(self, event: dict[str, Any]) -> dict[str, Any]:
        event_id = event.get("id")
        event_type = event.get("type")
        object_data = (event.get("data") or {}).get("object") or {}
        learner_id = None
        if isinstance(object_data, dict):
            metadata = object_data.get("metadata") or {}
            learner_id = metadata.get("learner_id")
        if not event_id or not event_type:
            return {"status": "ignored", "reason": "missing_event_fields"}

        if not self.record_stripe_event(event_id, event_type, learner_id, event):
            return {"status": "duplicate", "event_id": event_id}

        if event_type == "checkout.session.completed" and isinstance(object_data, dict):
            return self._grant_from_checkout_session(object_data, event_id)
        if event_type in {"customer.subscription.created", "customer.subscription.updated"} and isinstance(object_data, dict):
            return self._process_subscription_event(object_data, event_id)
        if event_type == "customer.subscription.deleted" and isinstance(object_data, dict):
            return self._process_subscription_event(object_data, event_id, deleted=True)
        if event_type in {"invoice.paid"} and isinstance(object_data, dict):
            subscription_id = object_data.get("subscription")
            if subscription_id:
                return self._process_subscription_event(
                    {
                        "id": subscription_id,
                        "customer": object_data.get("customer"),
                        "metadata": object_data.get("metadata") or {},
                        "status": "active",
                        "current_period_end": (object_data.get("lines") or {}).get("data", [{}])[0].get("period", {}).get("end"),
                        "customer_email": object_data.get("customer_email"),
                    },
                    event_id,
                )
        if event_type in {"charge.refunded", "charge.dispute.created", "charge.dispute.funds_withdrawn", "charge.dispute.closed"} and isinstance(object_data, dict):
            return self._process_refund_or_dispute(object_data, event_type, event_id)
        return {"status": "recorded", "event_type": event_type}

    def verify_webhook_signature(self, payload: bytes, signature_header: str | None, secret: str, *, tolerance_seconds: int = 300) -> bool:
        if not signature_header:
            return False
        try:
            items = {}
            for segment in signature_header.split(","):
                key, value = segment.split("=", 1)
                items.setdefault(key.strip(), []).append(value.strip())
            timestamp_raw = items.get("t", [None])[0]
            signatures = items.get("v1", [])
            if not timestamp_raw or not signatures:
                return False
            timestamp = int(timestamp_raw)
        except (ValueError, TypeError):
            return False

        if abs(int(time.time()) - timestamp) > tolerance_seconds:
            return False

        signed_payload = f"{timestamp}.{payload.decode('utf-8')}".encode("utf-8")
        expected = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
        return any(hmac.compare_digest(expected, signature) for signature in signatures)

    def handle_webhook(self, payload: bytes, signature_header: str | None, secret: str) -> dict[str, Any]:
        if not self.verify_webhook_signature(payload, signature_header, secret):
            raise ValueError("Invalid Stripe webhook signature.")
        event = json.loads(payload.decode("utf-8"))
        return self.process_stripe_event(event)

    def product_by_key(self, product_key: str) -> ProductDefinition | None:
        for product in DEFAULT_PRODUCTS:
            if product.key == product_key:
                return product
        return None

    def catalog(self) -> list[dict[str, Any]]:
        items = []
        for product in DEFAULT_PRODUCTS:
            items.append(
                {
                    "key": product.key,
                    "name": product.name,
                    "mode": product.mode,
                    "price_env": product.price_env,
                    "quantity": product.quantity,
                    "grants_attempts": product.grants_attempts,
                    "grants_ai_credits": product.grants_ai_credits,
                    "grant_type": product.grant_type,
                    "period_attempts": product.period_attempts,
                    "period_ai_credits": product.period_ai_credits,
                }
            )
        return items

    def checkout_config(self, env: dict[str, str]) -> dict[str, Any]:
        catalog = []
        for product in DEFAULT_PRODUCTS:
            catalog.append(
                {
                    **self.product_by_key(product.key).__dict__,
                    "price_id": env.get(product.price_env) or "",
                }
            )
        return {
            "free_exam_id": self.free_exam_id,
            "catalog": catalog,
        }


class StripeClient:
    def __init__(self, secret_key: str, *, api_base: str = "https://api.stripe.com") -> None:
        self.secret_key = secret_key
        self.api_base = api_base.rstrip("/")

    def enabled(self) -> bool:
        return bool(self.secret_key.strip())

    def build_checkout_session_body(
        self,
        *,
        product: ProductDefinition,
        price_id: str,
        learner_id: str,
        email: str | None,
        success_url: str,
        cancel_url: str,
        metadata: dict[str, str],
        b2b: bool = False,
        business_address: dict[str, str] | None = None,
        vat_id: str | None = None,
        vat_id_type: str = "eu_vat",
    ) -> dict[str, str]:
        """Build the form-encoded body for a Stripe checkout session.

        Always enables Stripe Tax (`automatic_tax`) and address/name auto-resolution
        so the customer's billing country is captured for EU VAT compliance.

        When ``b2b`` is true, also enables:
          - hosted PDF invoice generation via ``invoice_creation``
          - VAT-ID collection via ``tax_id_collection`` (and optional pre-filled
            ``tax_id_data`` when the caller supplied a ``vat_id``)
        """
        body: dict[str, str] = {
            "mode": product.mode,
            "success_url": success_url,
            "cancel_url": cancel_url,
            "client_reference_id": learner_id,
            "metadata[learner_id]": learner_id,
            "metadata[product_key]": product.key,
            # T-016: Stripe Tax for EU VAT compliance.
            "automatic_tax[enabled]": "true",
            # `customer_update` requires that Checkout creates/attaches a customer.
            # When a customer_email is provided, Stripe creates a Customer for the
            # session automatically; for `payment` mode without a saved customer
            # we explicitly request `customer_creation=always` so the
            # `customer_update[address]` parameter is accepted.
            "customer_update[address]": "auto",
            "customer_update[name]": "auto",
        }
        if email:
            body["customer_email"] = email
        if product.mode == "payment":
            body["line_items[0][price]"] = price_id
            body["line_items[0][quantity]"] = str(max(1, product.quantity))
            body["customer_creation"] = "always"
        else:
            body["line_items[0][price]"] = price_id
            body["line_items[0][quantity]"] = "1"

        for key, value in metadata.items():
            body[f"metadata[{key}]"] = value

        if b2b:
            body["metadata[b2b]"] = "true"
            # Always issue a hosted PDF invoice for B2B transactions; the URL
            # is recorded in the entitlement grant ledger when the webhook
            # confirms the purchase.
            body["invoice_creation[enabled]"] = "true"
            # Collect a VAT/Tax ID from the buyer at checkout.
            body["tax_id_collection[enabled]"] = "true"
            if vat_id:
                # Pre-fill the buyer's VAT/Tax ID so Stripe issues a
                # VAT-compliant invoice without manual entry.
                body["customer_data[tax_id_data][0][type]"] = vat_id_type
                body["customer_data[tax_id_data][0][value]"] = vat_id
            if business_address:
                for field, value in business_address.items():
                    if value:
                        body[f"metadata[business_address_{field}]"] = str(value)
        return body

    def create_checkout_session(
        self,
        *,
        product: ProductDefinition,
        price_id: str,
        learner_id: str,
        email: str | None,
        success_url: str,
        cancel_url: str,
        metadata: dict[str, str],
        b2b: bool = False,
        business_address: dict[str, str] | None = None,
        vat_id: str | None = None,
        vat_id_type: str = "eu_vat",
    ) -> dict[str, Any]:
        if not self.enabled():
            raise RuntimeError("Stripe is not configured.")

        body = self.build_checkout_session_body(
            product=product,
            price_id=price_id,
            learner_id=learner_id,
            email=email,
            success_url=success_url,
            cancel_url=cancel_url,
            metadata=metadata,
            b2b=b2b,
            business_address=business_address,
            vat_id=vat_id,
            vat_id_type=vat_id_type,
        )

        request = urllib.request.Request(
            f"{self.api_base}/v1/checkout/sessions",
            data=urllib.parse.urlencode({key: value for key, value in body.items() if value}).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.secret_key}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Stripe-Version": "2024-06-20",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))

    def create_mock_checkout_session(
        self,
        *,
        product: ProductDefinition,
        learner_id: str,
        email: str | None,
        success_url: str,
        cancel_url: str,
        b2b: bool = False,
        business_address: dict[str, str] | None = None,
        vat_id: str | None = None,
    ) -> dict[str, Any]:
        session_id = f"cs_test_{uuid.uuid4().hex}"
        meta: dict[str, str] = {"learner_id": learner_id, "product_key": product.key}
        if b2b:
            meta["b2b"] = "true"
        session: dict[str, Any] = {
            "id": session_id,
            "object": "checkout.session",
            "mode": product.mode,
            "status": "mock",
            "url": success_url,
            "metadata": meta,
            "customer_email": email or "",
            "success_url": success_url,
            "cancel_url": cancel_url,
            "test_mode": True,
            # Mirror the real Stripe payload so frontend + tests can assert on it.
            "automatic_tax": {"enabled": True, "status": "complete"},
            "customer_update": {"address": "auto", "name": "auto"},
        }
        if b2b:
            session["invoice_creation"] = {"enabled": True}
            session["tax_id_collection"] = {"enabled": True}
            if vat_id:
                session["customer_data"] = {
                    "tax_id_data": [{"type": "eu_vat", "value": vat_id}]
                }
            if business_address:
                session["business_address"] = dict(business_address)
        return session

    def retrieve_checkout_session(self, session_id: str) -> dict[str, Any]:
        """Fetch a checkout session from Stripe (used by the refund flow)."""
        if not self.enabled():
            raise RuntimeError("Stripe is not configured.")
        request = urllib.request.Request(
            f"{self.api_base}/v1/checkout/sessions/{urllib.parse.quote(session_id, safe='')}",
            headers={
                "Authorization": f"Bearer {self.secret_key}",
                "Stripe-Version": "2024-06-20",
            },
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))

    def create_refund(
        self,
        *,
        payment_intent: str | None = None,
        charge: str | None = None,
        reason: str = "requested_by_customer",
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Issue a full Stripe refund for the given payment_intent or charge."""
        if not self.enabled():
            raise RuntimeError("Stripe is not configured.")
        if not payment_intent and not charge:
            raise ValueError("Refund requires payment_intent or charge.")
        body: dict[str, str] = {"reason": reason}
        if payment_intent:
            body["payment_intent"] = payment_intent
        elif charge:
            body["charge"] = charge
        for key, value in (metadata or {}).items():
            body[f"metadata[{key}]"] = value
        request = urllib.request.Request(
            f"{self.api_base}/v1/refunds",
            data=urllib.parse.urlencode({k: v for k, v in body.items() if v}).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.secret_key}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Stripe-Version": "2024-06-20",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
