"""Entitlement enforcement service (T-024).

This module is the single, server-side source of truth for "is this
account allowed to perform this paid action?". It reads the
``entitlement_grants`` and ``entitlement_consumptions`` ledger maintained
by :mod:`billing` (``BillingStore``) and offers a small, opinionated API
that route handlers MUST call before performing any paid action:

* :func:`require_entitlement` — raise :class:`EntitlementError` if the
  account does not currently hold a usable entitlement of the requested
  kind. Read-only: never consumes a grant.
* :func:`entitled` — decorator that wraps a route-handler method on
  :class:`server_app.core.AppHandler`. On a failing check it emits a 402
  ``Payment Required`` JSON response and short-circuits the request.

T-022 + T-023 put attempts + identity on the server. T-024's job is to
make sure every paid surface consults the server-side ledger, never the
UI's local copy of ``billing_state``. UI hints (greyed-out buttons,
upgrade prompts) are still allowed - they live in the frontend solely
for affordance, and are documented as non-binding.

Admin + superadmin sessions bypass the gate. Expired (``expires_at <=
now``) and revoked (``revoked_at IS NOT NULL``) grants are ignored by
``BillingStore.get_state``. Concurrent consumption is serialised by
``BillingStore._lock`` + ``BEGIN IMMEDIATE``; ``require_entitlement``
itself is read-only, so two threads can pass it and then race the
write - exactly one wins the consume.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Literal

from server_app.core import (
    ApiError,
    account_role,
    capture_exception,
    current_session_record,
    get_billing_store,
    json_response,
    log_event,
)


logger = logging.getLogger("lvcodex.entitlements")


EntitlementKind = Literal["exam_unlock", "ai_credit", "subscription"]
_ALLOWED_KINDS: tuple[str, ...] = ("exam_unlock", "ai_credit", "subscription")


class EntitlementError(Exception):
    """Raised when an account lacks a usable entitlement."""

    status_code: int = 402

    def __init__(
        self,
        kind: str,
        *,
        reason: str = "missing",
        state: dict[str, Any] | None = None,
        message: str | None = None,
    ) -> None:
        self.kind = kind
        self.reason = reason
        self.state = state or {}
        if message is None:
            message = (
                f"Entitlement '{kind}' is required but not available "
                f"(reason: {reason})."
            )
        super().__init__(message)


def _validate_kind(kind: str) -> EntitlementKind:
    if kind not in _ALLOWED_KINDS:
        raise ValueError(
            f"Unknown entitlement kind {kind!r}. "
            f"Expected one of: {', '.join(_ALLOWED_KINDS)}."
        )
    return kind  # type: ignore[return-value]


def _has_entitlement(state: dict[str, Any], kind: EntitlementKind) -> bool:
    """Pure function: does ``state`` satisfy a ``kind`` requirement?"""

    if state.get("current_plan") == "admin_unlimited":
        return True
    if state.get("frozen"):
        return False
    if kind == "exam_unlock":
        if state.get("subscription_active"):
            return True
        if int(state.get("paid_attempts_remaining") or 0) > 0:
            return True
        if state.get("free_exam_available"):
            return True
        return False
    if kind == "ai_credit":
        if state.get("subscription_active"):
            return True
        if int(state.get("ai_credits_remaining") or 0) > 0:
            return True
        return False
    if kind == "subscription":
        return bool(state.get("subscription_active"))
    return False  # pragma: no cover


def require_entitlement(
    account_id: str,
    kind: EntitlementKind,
    *,
    user_role: str = "user",
) -> bool:
    """Raise :class:`EntitlementError` if ``account_id`` lacks ``kind``.

    Returns ``True`` on success. Failure raises so callers can use it as
    an assertion. Admin / superadmin sessions bypass the check.
    """

    kind = _validate_kind(kind)
    if user_role in {"admin", "superadmin"}:
        return True
    if not account_id:
        raise EntitlementError(kind, reason="account_unknown")
    store = get_billing_store()
    state = store.get_state(account_id, user_role=user_role)
    if state.get("frozen"):
        raise EntitlementError(kind, reason="frozen", state=_safe_state(state))
    if _has_entitlement(state, kind):
        return True
    raise EntitlementError(kind, reason="missing", state=_safe_state(state))


def _safe_state(state: dict[str, Any]) -> dict[str, Any]:
    """Strip the parts of ``get_state`` we never want to expose on a 402."""

    return {
        "current_plan": state.get("current_plan"),
        "frozen": bool(state.get("frozen")),
        "free_exam_available": bool(state.get("free_exam_available")),
        "paid_attempts_remaining": int(state.get("paid_attempts_remaining") or 0),
        "ai_credits_remaining": int(state.get("ai_credits_remaining") or 0),
        "subscription_active": bool(state.get("subscription_active")),
    }


def entitled(*, kind: EntitlementKind) -> Callable[..., Any]:
    """Decorator factory: gate an ``AppHandler`` method on an entitlement."""

    expected_kind = _validate_kind(kind)

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            try:
                session = current_session_record(self)
                if session is None:
                    raise ApiError(401, "auth_required", "Authentication required.")
                role = account_role(session)
                account_id = (session.get("account") or {}).get("id") or ""
                require_entitlement(account_id, expected_kind, user_role=role)
            except EntitlementError as error:
                log_event(
                    "warning",
                    "entitlement_blocked",
                    kind=error.kind,
                    reason=error.reason,
                    account_id=_account_id_for_log(error.state, kwargs),
                )
                json_response(
                    self,
                    error.status_code,
                    {
                        "error": str(error),
                        "kind": error.kind,
                        "reason": error.reason,
                        "billing_state": error.state,
                    },
                )
                return None
            except ApiError:
                raise
            except Exception as error:  # noqa: BLE001
                capture_exception(error)
                log_event(
                    "error",
                    "entitlement_check_error",
                    error=type(error).__name__,
                )
                json_response(
                    self,
                    500,
                    {"error": "Entitlement check failed."},
                )
                return None
            return func(self, *args, **kwargs)

        wrapper.__wrapped__ = func  # type: ignore[attr-defined]
        wrapper.__entitlement_kind__ = expected_kind  # type: ignore[attr-defined]
        wrapper.__name__ = getattr(func, "__name__", "entitled_wrapper")
        wrapper.__doc__ = func.__doc__
        return wrapper

    return decorator


def _account_id_for_log(
    state: dict[str, Any] | None, kwargs: dict[str, Any]
) -> str | None:
    """Best-effort account id extraction for the audit log line."""

    if not state:
        return None
    learner = state.get("learner") if isinstance(state, dict) else None
    if isinstance(learner, dict):
        return learner.get("learner_id")
    return kwargs.get("account_id")


__all__ = [
    "EntitlementError",
    "EntitlementKind",
    "entitled",
    "require_entitlement",
]
