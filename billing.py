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


class BillingStore:
    def __init__(self, db_path: str | Path, *, free_exam_id: str = FREE_EXAM_ID) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.free_exam_id = free_exam_id
        self._lock = threading.Lock()
        self._initialize_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
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
        if product.key == "single_exam":
            self.grant_product(
                learner_id,
                product_key=product.key,
                quantity=product.grants_attempts,
                grant_type="exam_attempts",
                customer_id=session.get("customer"),
                source_reference=session.get("payment_intent") or session.get("id"),
                source_event_id=event_id,
                metadata={"checkout_session_id": session.get("id")},
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
                metadata={"checkout_session_id": session.get("id")},
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
                    metadata={"checkout_session_id": session.get("id")},
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
                metadata={"checkout_session_id": session.get("id")},
            )
        return {"status": "granted", "learner_id": learner_id, "product_key": product.key}

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
    ) -> dict[str, Any]:
        if not self.enabled():
            raise RuntimeError("Stripe is not configured.")

        body: dict[str, str] = {
            "mode": product.mode,
            "success_url": success_url,
            "cancel_url": cancel_url,
            "client_reference_id": learner_id,
            "customer_email": email or "",
            "metadata[learner_id]": learner_id,
            "metadata[product_key]": product.key,
        }
        if product.mode == "payment":
            body["line_items[0][price]"] = price_id
            body["line_items[0][quantity]"] = str(max(1, product.quantity))
        else:
            body["line_items[0][price]"] = price_id
            body["line_items[0][quantity]"] = "1"

        for key, value in metadata.items():
            body[f"metadata[{key}]"] = value

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
    ) -> dict[str, Any]:
        session_id = f"cs_test_{uuid.uuid4().hex}"
        return {
            "id": session_id,
            "object": "checkout.session",
            "mode": product.mode,
            "status": "mock",
            "url": success_url,
            "metadata": {"learner_id": learner_id, "product_key": product.key},
            "customer_email": email or "",
            "success_url": success_url,
            "cancel_url": cancel_url,
            "test_mode": True,
        }
