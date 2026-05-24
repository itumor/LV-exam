"""Institutional seat licensing + bulk vouchers — T-041.

Provides the data model + business logic for institutional customers
(schools, training providers, corporates). An *organization* purchases
a fixed number of *seats*. The owner invites members by issuing
*vouchers* (single-use redemption codes). Each redeemed voucher
consumes one seat, and active members are treated as paid-tier
learners by the T-024 entitlement gates.

Public API
----------

* :func:`create_org` — create an organization + seat allocation.
* :func:`invite_member` — issue a single voucher for one invitee.
* :func:`create_bulk_vouchers` — generate ``N`` unaddressed vouchers
  at once for a sales hand-off.
* :func:`redeem_voucher` — atomically consume a voucher and add the
  redeeming account to the org (under the seat cap).
* :func:`list_seats` — return the seat usage + member roster.
* :func:`account_has_active_seat` — read-only helper used by the
  T-024 entitlement extension at gate-evaluation time.

Storage
-------

Four narrow tables, created lazily by
:func:`init_institutional_tables` and persisted in the same SQLite
file as the rest of the auth store (``AUTH_DB_PATH``):

* ``organizations`` — id, name, owner, Stripe linkage, status.
* ``org_seats`` — one row per org with ``max_seats`` + ``used_seats``.
* ``org_members`` — many-to-one (account_id, org_id) + status.
* ``vouchers`` — single-use code with optional ``expires_at`` +
  ``redeemed_by`` audit columns.

All mutating helpers wrap their work in a ``BEGIN IMMEDIATE``
transaction so concurrent redemptions / invites cannot overshoot the
seat cap. The decision to keep ``used_seats`` denormalised is so
the entitlement-gate read path is one row instead of a COUNT(*) on a
potentially-large ``org_members`` table.
"""

from __future__ import annotations

import secrets
import sqlite3
import string
from typing import Any

from server_app.core import (  # type: ignore[attr-defined]
    db_connection,
    log_event,
    normalize_email,
    now_iso,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VOUCHER_CODE_ALPHABET = string.ascii_uppercase + string.digits
"""Alphabet for generated voucher codes — uppercase letters + digits.

The codes are random 12-char strings so the birthday-collision risk is
negligible (~36**12 / 2 ~ 1.5e18 attempts to hit a 50% collision).
Email clients render the codes as-is, and the alphabet keeps them
copy-paste friendly.
"""

VOUCHER_CODE_LENGTH = 12
MAX_BULK_COUNT = 500
"""Hard cap on a single bulk-voucher request. Beyond this the admin
should script multiple calls; the cap keeps a single request bounded
(both for the DB transaction and for the resulting JSON payload)."""


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class InstitutionalError(Exception):
    """Domain error raised by the institutional service.

    The route layer maps ``InstitutionalError`` to a 4xx JSON response;
    ``code`` is a stable machine-readable identifier; ``status_code``
    lets routes pick the right HTTP class without re-implementing the
    mapping. ``message`` is safe to surface to the caller.
    """

    def __init__(
        self, code: str, message: str, *, status_code: int = 400
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def init_institutional_tables(conn: sqlite3.Connection) -> None:
    """Create the institutional tables if missing. Idempotent.

    Called lazily from every public entry point so that test setups
    that patch ``AUTH_DB_PATH`` after module import still work — same
    pattern as :func:`server_app.services.sso.init_sso_tables`.
    """

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS organizations (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            owner_account_id TEXT NOT NULL,
            stripe_customer_id TEXT,
            stripe_subscription_id TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_organizations_owner
        ON organizations (owner_account_id);

        CREATE TABLE IF NOT EXISTS org_seats (
            org_id TEXT PRIMARY KEY REFERENCES organizations(id) ON DELETE CASCADE,
            max_seats INTEGER NOT NULL,
            used_seats INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS org_members (
            id TEXT PRIMARY KEY,
            org_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            account_id TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'member',
            status TEXT NOT NULL DEFAULT 'active',
            joined_at TEXT NOT NULL,
            revoked_at TEXT,
            UNIQUE(org_id, account_id)
        );

        CREATE INDEX IF NOT EXISTS idx_org_members_account
        ON org_members (account_id, status);

        CREATE INDEX IF NOT EXISTS idx_org_members_org
        ON org_members (org_id, status);

        CREATE TABLE IF NOT EXISTS vouchers (
            id TEXT PRIMARY KEY,
            org_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            code TEXT NOT NULL UNIQUE,
            invite_email TEXT,
            created_at TEXT NOT NULL,
            expires_at TEXT,
            redeemed_at TEXT,
            redeemed_by TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_vouchers_org
        ON vouchers (org_id);

        CREATE INDEX IF NOT EXISTS idx_vouchers_code
        ON vouchers (code);
        """
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _new_org_id() -> str:
    return f"org_{secrets.token_hex(8)}"


def _new_member_id() -> str:
    return f"mem_{secrets.token_hex(8)}"


def _new_voucher_id() -> str:
    return f"vch_{secrets.token_hex(8)}"


def _new_voucher_code() -> str:
    """Generate a human-friendly random voucher code.

    12 uppercase-alphanumeric characters separated by a single dash in
    the middle for readability (e.g. ``ABC123-XYZ789``).
    """

    half = VOUCHER_CODE_LENGTH // 2
    chars_a = "".join(secrets.choice(VOUCHER_CODE_ALPHABET) for _ in range(half))
    chars_b = "".join(secrets.choice(VOUCHER_CODE_ALPHABET) for _ in range(half))
    return f"{chars_a}-{chars_b}"


def _begin_immediate(conn: sqlite3.Connection) -> None:
    """Acquire a serialising write lock.

    SQLite's default deferred transaction upgrades on first write; that
    leaves a small window where two concurrent ``invite_member`` /
    ``redeem_voucher`` calls could each read the seat counter, both
    decide a slot is free, and then race to write — overshooting the
    cap. ``BEGIN IMMEDIATE`` acquires the RESERVED lock up front so
    the second caller waits.
    """

    if conn.in_transaction:  # pragma: no cover - defensive
        return
    conn.execute("BEGIN IMMEDIATE")


def _expires_at_ok(row_expires_at: str | None, *, now: str) -> bool:
    """Return True iff the voucher is still within its redemption window."""

    if row_expires_at is None:
        return True
    return row_expires_at > now


# ---------------------------------------------------------------------------
# create_org
# ---------------------------------------------------------------------------


def create_org(
    name: str,
    owner_account_id: str,
    *,
    max_seats: int,
    stripe_customer_id: str | None = None,
    stripe_subscription_id: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Create a new organization with an initial seat allocation.

    The owner is recorded as the first ``active`` member of the org,
    consuming one seat (so ``used_seats`` starts at 1 and ``max_seats``
    must be at least 1). This mirrors the operational model where the
    owner is themselves a learner on the institutional plan.

    ``stripe_customer_id`` / ``stripe_subscription_id`` are optional and
    populated by :mod:`server_app.core` once the seat-based subscription
    is purchased.
    """

    name = (name or "").strip()
    owner_account_id = (owner_account_id or "").strip()
    if not name:
        raise InstitutionalError("org_name_required", "Organization name is required.")
    if not owner_account_id:
        raise InstitutionalError(
            "org_owner_required", "owner_account_id is required."
        )
    if not isinstance(max_seats, int) or max_seats < 1:
        raise InstitutionalError(
            "org_max_seats_invalid",
            "max_seats must be a positive integer (>= 1).",
        )

    now = now_iso()
    org_id = _new_org_id()

    def _do(active: sqlite3.Connection) -> dict[str, Any]:
        init_institutional_tables(active)
        _begin_immediate(active)
        active.execute(
            """
            INSERT INTO organizations (
                id, name, owner_account_id, stripe_customer_id,
                stripe_subscription_id, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'active', ?, ?)
            """,
            (
                org_id,
                name,
                owner_account_id,
                stripe_customer_id,
                stripe_subscription_id,
                now,
                now,
            ),
        )
        active.execute(
            """
            INSERT INTO org_seats (org_id, max_seats, used_seats, updated_at)
            VALUES (?, ?, 0, ?)
            """,
            (org_id, max_seats, now),
        )
        # Add the owner as the first member (consumes 1 seat).
        active.execute(
            """
            INSERT INTO org_members (
                id, org_id, account_id, role, status, joined_at, revoked_at
            ) VALUES (?, ?, ?, 'owner', 'active', ?, NULL)
            """,
            (_new_member_id(), org_id, owner_account_id, now),
        )
        active.execute(
            "UPDATE org_seats SET used_seats = used_seats + 1, updated_at = ? "
            "WHERE org_id = ?",
            (now, org_id),
        )
        active.commit()
        log_event(
            "info",
            "org_created",
            org_id=org_id,
            owner_account_id=owner_account_id,
            max_seats=max_seats,
        )
        return _serialize_org_row(active, org_id)

    if conn is not None:
        return _do(conn)
    with db_connection() as opened:
        return _do(opened)


def _serialize_org_row(conn: sqlite3.Connection, org_id: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT o.id, o.name, o.owner_account_id, o.stripe_customer_id,
               o.stripe_subscription_id, o.status, o.created_at, o.updated_at,
               s.max_seats, s.used_seats
        FROM organizations o
        LEFT JOIN org_seats s ON s.org_id = o.id
        WHERE o.id = ?
        """,
        (org_id,),
    ).fetchone()
    if row is None:
        raise InstitutionalError(
            "org_not_found",
            f"Organization {org_id!r} not found.",
            status_code=404,
        )
    return {
        "id": row["id"],
        "name": row["name"],
        "owner_account_id": row["owner_account_id"],
        "stripe_customer_id": row["stripe_customer_id"],
        "stripe_subscription_id": row["stripe_subscription_id"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "max_seats": int(row["max_seats"] or 0),
        "used_seats": int(row["used_seats"] or 0),
    }


def get_org(org_id: str) -> dict[str, Any] | None:
    """Return the organization record (or None) for ``org_id``."""

    org_id = (org_id or "").strip()
    if not org_id:
        return None
    with db_connection() as conn:
        init_institutional_tables(conn)
        try:
            return _serialize_org_row(conn, org_id)
        except InstitutionalError:
            return None


# ---------------------------------------------------------------------------
# invite_member / create_bulk_vouchers
# ---------------------------------------------------------------------------


def invite_member(
    org_id: str,
    *,
    actor_account_id: str,
    invite_email: str | None = None,
    expires_at: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Create a single voucher for an invitee. Returns the voucher record.

    The voucher does NOT reserve a seat — the seat is consumed only on
    redemption (otherwise a forgotten invite would silently strand
    capacity). The owner is responsible for the redemption window via
    ``expires_at``.

    ``actor_account_id`` is the session account performing the action;
    it must be the org owner (see :func:`assert_owner`). The route
    layer is expected to call :func:`assert_owner` before invoking
    this helper.
    """

    org_id = (org_id or "").strip()
    if not org_id:
        raise InstitutionalError("org_id_required", "org_id is required.")

    email = normalize_email(invite_email) if invite_email else None
    if invite_email and (not email or "@" not in email):
        raise InstitutionalError(
            "invite_email_invalid",
            "invite_email must be a valid email address.",
        )

    now = now_iso()
    voucher_id = _new_voucher_id()
    code = _new_voucher_code()

    def _do(active: sqlite3.Connection) -> dict[str, Any]:
        init_institutional_tables(active)
        _begin_immediate(active)
        assert_owner(active, org_id=org_id, account_id=actor_account_id)
        active.execute(
            """
            INSERT INTO vouchers (
                id, org_id, code, invite_email,
                created_at, expires_at, redeemed_at, redeemed_by
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL)
            """,
            (voucher_id, org_id, code, email, now, expires_at),
        )
        active.commit()
        log_event(
            "info",
            "voucher_issued",
            org_id=org_id,
            voucher_id=voucher_id,
            invite_email=email,
        )
        return {
            "id": voucher_id,
            "org_id": org_id,
            "code": code,
            "invite_email": email,
            "created_at": now,
            "expires_at": expires_at,
            "redeemed_at": None,
            "redeemed_by": None,
        }

    if conn is not None:
        return _do(conn)
    with db_connection() as opened:
        return _do(opened)


def create_bulk_vouchers(
    org_id: str,
    *,
    count: int,
    actor_account_id: str,
    expires_at: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """Issue ``count`` unaddressed vouchers for ``org_id``.

    Used by the sales / enrollment hand-off where the admin wants a
    batch of codes printed on a class roster or emailed in bulk
    externally. Each voucher is independent; redemption rules are the
    same as for single-invite vouchers (single-use, expiry-respecting).

    The seat cap is NOT pre-checked here — issuing more vouchers than
    seats is allowed (e.g. to over-issue against expected attrition);
    the cap is enforced at redemption time. The hard cap
    :data:`MAX_BULK_COUNT` bounds a single request for transaction +
    payload safety.
    """

    if not isinstance(count, int) or count <= 0:
        raise InstitutionalError(
            "bulk_count_invalid", "count must be a positive integer."
        )
    if count > MAX_BULK_COUNT:
        raise InstitutionalError(
            "bulk_count_too_large",
            f"count must be <= {MAX_BULK_COUNT} (was {count}).",
        )

    now = now_iso()
    org_id = (org_id or "").strip()
    if not org_id:
        raise InstitutionalError("org_id_required", "org_id is required.")

    def _do(active: sqlite3.Connection) -> list[dict[str, Any]]:
        init_institutional_tables(active)
        _begin_immediate(active)
        assert_owner(active, org_id=org_id, account_id=actor_account_id)
        records: list[dict[str, Any]] = []
        existing_codes: set[str] = set()
        for _ in range(count):
            code = _new_voucher_code()
            # Local de-dupe guard — the UNIQUE index would catch a
            # collision but the retry costs less than a rolled-back
            # transaction.
            while code in existing_codes:  # pragma: no cover - astronomical
                code = _new_voucher_code()
            existing_codes.add(code)
            voucher_id = _new_voucher_id()
            active.execute(
                """
                INSERT INTO vouchers (
                    id, org_id, code, invite_email,
                    created_at, expires_at, redeemed_at, redeemed_by
                ) VALUES (?, ?, ?, NULL, ?, ?, NULL, NULL)
                """,
                (voucher_id, org_id, code, now, expires_at),
            )
            records.append(
                {
                    "id": voucher_id,
                    "org_id": org_id,
                    "code": code,
                    "invite_email": None,
                    "created_at": now,
                    "expires_at": expires_at,
                    "redeemed_at": None,
                    "redeemed_by": None,
                }
            )
        active.commit()
        log_event(
            "info",
            "vouchers_bulk_issued",
            org_id=org_id,
            count=count,
        )
        return records

    if conn is not None:
        return _do(conn)
    with db_connection() as opened:
        return _do(opened)


# ---------------------------------------------------------------------------
# redeem_voucher
# ---------------------------------------------------------------------------


def redeem_voucher(
    code: str,
    account_id: str,
    *,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Atomically consume a voucher and add the account as an org member.

    The transaction enforces all invariants:

    * voucher exists
    * voucher is not yet redeemed (single-use)
    * voucher is not expired
    * org is active
    * seat cap is not exceeded
    * the same account is not double-added (UNIQUE(org_id, account_id))

    Any violation raises :class:`InstitutionalError` with a stable
    ``code`` the route layer maps to a JSON error envelope.

    Returns a result dict with the org + voucher records on success.
    """

    code = (code or "").strip()
    account_id = (account_id or "").strip()
    if not code:
        raise InstitutionalError("voucher_code_required", "Voucher code is required.")
    if not account_id:
        raise InstitutionalError(
            "account_required",
            "Account is required to redeem a voucher.",
            status_code=401,
        )

    now = now_iso()

    def _do(active: sqlite3.Connection) -> dict[str, Any]:
        init_institutional_tables(active)
        _begin_immediate(active)
        voucher = active.execute(
            "SELECT id, org_id, code, invite_email, created_at, expires_at, "
            "redeemed_at, redeemed_by FROM vouchers WHERE code = ?",
            (code,),
        ).fetchone()
        if voucher is None:
            raise InstitutionalError(
                "voucher_unknown",
                "Voucher code is not recognised.",
                status_code=404,
            )
        if voucher["redeemed_at"] is not None:
            raise InstitutionalError(
                "voucher_already_redeemed",
                "Voucher has already been redeemed.",
                status_code=409,
            )
        if not _expires_at_ok(voucher["expires_at"], now=now):
            raise InstitutionalError(
                "voucher_expired",
                "Voucher has expired.",
                status_code=410,
            )

        org_id = voucher["org_id"]
        org_row = active.execute(
            "SELECT id, name, status FROM organizations WHERE id = ?", (org_id,)
        ).fetchone()
        if org_row is None or org_row["status"] != "active":
            raise InstitutionalError(
                "org_inactive",
                "Organization is not active.",
                status_code=409,
            )

        seat_row = active.execute(
            "SELECT max_seats, used_seats FROM org_seats WHERE org_id = ?",
            (org_id,),
        ).fetchone()
        if seat_row is None:
            raise InstitutionalError(
                "org_seats_missing",
                "Organization has no seat allocation.",
                status_code=409,
            )
        if int(seat_row["used_seats"]) >= int(seat_row["max_seats"]):
            raise InstitutionalError(
                "org_seat_cap_reached",
                "Organization has no seats available.",
                status_code=409,
            )

        existing = active.execute(
            "SELECT id, status FROM org_members WHERE org_id = ? AND account_id = ?",
            (org_id, account_id),
        ).fetchone()
        if existing is not None and existing["status"] == "active":
            raise InstitutionalError(
                "member_already_active",
                "Account is already an active member of this organization.",
                status_code=409,
            )

        # Mark the voucher used + register the member + bump the counter.
        active.execute(
            "UPDATE vouchers SET redeemed_at = ?, redeemed_by = ? WHERE id = ?",
            (now, account_id, voucher["id"]),
        )
        if existing is not None:
            # Reactivate a previously revoked membership.
            active.execute(
                "UPDATE org_members SET status = 'active', revoked_at = NULL, "
                "joined_at = ? WHERE id = ?",
                (now, existing["id"]),
            )
        else:
            active.execute(
                """
                INSERT INTO org_members (
                    id, org_id, account_id, role, status, joined_at, revoked_at
                ) VALUES (?, ?, ?, 'member', 'active', ?, NULL)
                """,
                (_new_member_id(), org_id, account_id, now),
            )
        active.execute(
            "UPDATE org_seats SET used_seats = used_seats + 1, updated_at = ? "
            "WHERE org_id = ?",
            (now, org_id),
        )
        active.commit()
        log_event(
            "info",
            "voucher_redeemed",
            org_id=org_id,
            voucher_id=voucher["id"],
            account_id=account_id,
        )
        return {
            "org_id": org_id,
            "org_name": org_row["name"],
            "voucher_id": voucher["id"],
            "account_id": account_id,
            "redeemed_at": now,
        }

    if conn is not None:
        return _do(conn)
    with db_connection() as opened:
        return _do(opened)


# ---------------------------------------------------------------------------
# list_seats
# ---------------------------------------------------------------------------


def list_seats(org_id: str) -> dict[str, Any]:
    """Return seat usage + active member roster for ``org_id``."""

    org_id = (org_id or "").strip()
    if not org_id:
        raise InstitutionalError("org_id_required", "org_id is required.")

    with db_connection() as conn:
        init_institutional_tables(conn)
        org = _serialize_org_row(conn, org_id)
        members = conn.execute(
            """
            SELECT id, org_id, account_id, role, status, joined_at, revoked_at
            FROM org_members
            WHERE org_id = ?
            ORDER BY joined_at ASC, id ASC
            """,
            (org_id,),
        ).fetchall()
        vouchers = conn.execute(
            """
            SELECT id, org_id, code, invite_email, created_at,
                   expires_at, redeemed_at, redeemed_by
            FROM vouchers
            WHERE org_id = ?
            ORDER BY created_at DESC
            """,
            (org_id,),
        ).fetchall()
    return {
        "org": org,
        "members": [
            {
                "id": r["id"],
                "account_id": r["account_id"],
                "role": r["role"],
                "status": r["status"],
                "joined_at": r["joined_at"],
                "revoked_at": r["revoked_at"],
            }
            for r in members
        ],
        "vouchers": [
            {
                "id": r["id"],
                "code": r["code"],
                "invite_email": r["invite_email"],
                "created_at": r["created_at"],
                "expires_at": r["expires_at"],
                "redeemed_at": r["redeemed_at"],
                "redeemed_by": r["redeemed_by"],
            }
            for r in vouchers
        ],
    }


# ---------------------------------------------------------------------------
# Owner permission check
# ---------------------------------------------------------------------------


def assert_owner(
    conn: sqlite3.Connection, *, org_id: str, account_id: str
) -> None:
    """Raise :class:`InstitutionalError` if ``account_id`` is not the org owner.

    The check uses the ``organizations.owner_account_id`` column rather
    than ``org_members.role = 'owner'`` so it works even if the owner
    has been temporarily revoked (e.g. mid-rotation). Server admins
    (``role in {admin, superadmin}``) are NOT recognised by this helper
    — the route layer is expected to short-circuit the check separately
    for server-side admins.
    """

    row = conn.execute(
        "SELECT id, owner_account_id FROM organizations WHERE id = ?",
        (org_id,),
    ).fetchone()
    if row is None:
        raise InstitutionalError(
            "org_not_found",
            f"Organization {org_id!r} not found.",
            status_code=404,
        )
    if row["owner_account_id"] != account_id:
        raise InstitutionalError(
            "org_owner_required",
            "Only the organization owner can perform this action.",
            status_code=403,
        )


# ---------------------------------------------------------------------------
# T-024 entitlement extension
# ---------------------------------------------------------------------------


def account_has_active_seat(account_id: str) -> bool:
    """Return True if ``account_id`` has an active membership in an active org.

    Read-only fast path used by the T-024 entitlement gate so the
    institutional plan promotes a learner to paid-tier without
    requiring a Stripe ``subscription_attempts`` grant. The gate
    treats an active seat as equivalent to ``subscription_active``.
    """

    account_id = (account_id or "").strip()
    if not account_id:
        return False
    with db_connection() as conn:
        init_institutional_tables(conn)
        row = conn.execute(
            """
            SELECT 1
            FROM org_members m
            JOIN organizations o ON o.id = m.org_id
            WHERE m.account_id = ?
              AND m.status = 'active'
              AND o.status = 'active'
            LIMIT 1
            """,
            (account_id,),
        ).fetchone()
        return row is not None


# ---------------------------------------------------------------------------
# Stripe extension — seat-based subscription helpers
# ---------------------------------------------------------------------------


def build_seat_subscription_body(
    *,
    org_id: str,
    price_id: str,
    quantity: int,
    success_url: str,
    cancel_url: str,
    customer_email: str | None,
    customer_id: str | None = None,
    metadata: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build the form-encoded body for a Stripe seat-based subscription.

    The resulting body is suitable for POSTing to
    ``https://api.stripe.com/v1/checkout/sessions``. ``quantity`` is the
    seat count and is set on ``line_items[0][quantity]`` — Stripe bills
    the customer ``quantity * unit_amount`` per period. Returns a plain
    dict so callers can drop sentinel ``None``s before submitting.

    The companion runtime helper that actually hits Stripe lives in
    :mod:`billing.StripeClient`; this builder is in the institutional
    service because it carries the seat-licensing context (the
    ``metadata[org_id]`` link) and we want it unit-testable without a
    network round-trip.
    """

    org_id = (org_id or "").strip()
    price_id = (price_id or "").strip()
    if not org_id:
        raise InstitutionalError("org_id_required", "org_id is required.")
    if not price_id:
        raise InstitutionalError(
            "price_id_required", "Stripe price_id is required."
        )
    if not isinstance(quantity, int) or quantity < 1:
        raise InstitutionalError(
            "quantity_invalid",
            "quantity must be a positive integer (>= 1).",
        )

    body: dict[str, str] = {
        "mode": "subscription",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": org_id,
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": str(quantity),
        "automatic_tax[enabled]": "true",
        "customer_update[address]": "auto",
        "customer_update[name]": "auto",
        "metadata[product_key]": "institutional_seats",
        "metadata[org_id]": org_id,
        "metadata[seats]": str(quantity),
        "subscription_data[metadata][org_id]": org_id,
        "subscription_data[metadata][seats]": str(quantity),
    }
    if customer_email and not customer_id:
        body["customer_email"] = customer_email
    if customer_id:
        body["customer"] = customer_id
    for key, value in (metadata or {}).items():
        body[f"metadata[{key}]"] = value
    return body


def attach_stripe_subscription(
    org_id: str,
    *,
    stripe_customer_id: str | None,
    stripe_subscription_id: str | None,
    max_seats: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Persist the Stripe customer + subscription IDs onto an org.

    Optionally adjusts the seat cap (when a customer upgrades their
    seat count and the webhook reports the new quantity).
    """

    org_id = (org_id or "").strip()
    if not org_id:
        raise InstitutionalError("org_id_required", "org_id is required.")

    now = now_iso()

    def _do(active: sqlite3.Connection) -> dict[str, Any]:
        init_institutional_tables(active)
        _begin_immediate(active)
        active.execute(
            """
            UPDATE organizations
            SET stripe_customer_id = COALESCE(?, stripe_customer_id),
                stripe_subscription_id = COALESCE(?, stripe_subscription_id),
                updated_at = ?
            WHERE id = ?
            """,
            (stripe_customer_id, stripe_subscription_id, now, org_id),
        )
        if max_seats is not None:
            if not isinstance(max_seats, int) or max_seats < 1:
                raise InstitutionalError(
                    "org_max_seats_invalid",
                    "max_seats must be a positive integer.",
                )
            active.execute(
                "UPDATE org_seats SET max_seats = ?, updated_at = ? "
                "WHERE org_id = ?",
                (max_seats, now, org_id),
            )
        active.commit()
        return _serialize_org_row(active, org_id)

    if conn is not None:
        return _do(conn)
    with db_connection() as opened:
        return _do(opened)


__all__ = [
    "InstitutionalError",
    "MAX_BULK_COUNT",
    "VOUCHER_CODE_ALPHABET",
    "VOUCHER_CODE_LENGTH",
    "account_has_active_seat",
    "assert_owner",
    "attach_stripe_subscription",
    "build_seat_subscription_body",
    "create_bulk_vouchers",
    "create_org",
    "get_org",
    "init_institutional_tables",
    "invite_member",
    "list_seats",
    "redeem_voucher",
]
