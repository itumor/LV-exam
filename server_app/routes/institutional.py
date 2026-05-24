"""Institutional seat-licensing routes — T-041.

Re-exports the institutional service surface and documents the public
routes. The actual ``do_GET`` / ``do_POST`` dispatch is installed by
the end-of-file T-041 hook in :mod:`server_app.core`, mirroring the
pattern used by T-024 / T-040 / T-046.

Routes owned here:

* ``POST /api/orgs`` — create an organization (any authenticated session).
* ``GET  /api/orgs/<org_id>/seats`` — list seat usage + roster.
* ``POST /api/orgs/<org_id>/vouchers`` — invite a single member.
* ``POST /api/orgs/<org_id>/vouchers/bulk?count=N`` — issue N vouchers.
* ``POST /api/orgs/<org_id>/subscription`` — open seat-based Stripe checkout.
* ``POST /api/vouchers/redeem`` — redeem a voucher onto the caller.
"""

from __future__ import annotations

from server_app.services.institutional import (  # noqa: F401
    InstitutionalError,
    MAX_BULK_COUNT,
    account_has_active_seat,
    attach_stripe_subscription,
    build_seat_subscription_body,
    create_bulk_vouchers,
    create_org,
    get_org,
    init_institutional_tables,
    invite_member,
    list_seats,
    redeem_voucher,
)

ROUTES: list[tuple[str, str]] = [
    ("POST", "/api/orgs"),
    ("GET", "/api/orgs/<org_id>/seats"),
    ("POST", "/api/orgs/<org_id>/vouchers"),
    ("POST", "/api/orgs/<org_id>/vouchers/bulk"),
    ("POST", "/api/orgs/<org_id>/subscription"),
    ("POST", "/api/vouchers/redeem"),
]

__all__ = [
    "InstitutionalError",
    "MAX_BULK_COUNT",
    "ROUTES",
    "account_has_active_seat",
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
