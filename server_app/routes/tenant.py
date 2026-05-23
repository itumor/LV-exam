"""White-label tenant route module (T-044).

Owns the public ``GET /api/tenant`` endpoint that the v2 frontend
(``apps/web-v2``) calls on boot to resolve its theme, logo, support
contact, and CSS-variable block based on the inbound ``Host:`` header.

The handler body lives inline in the end-of-file hook in
:mod:`server_app.core` (mirrors the T-025 / T-037 monkey-patch pattern
so the existing dispatch chain — rate-limit → metrics → debug-gate →
routing — is not disturbed). This module documents the route table for
the modularization audit (``tests/server/test_modularization.py``) and
re-exports the resolver helpers so other modules can import them via
the ``server_app.routes.tenant`` symbol.
"""

from __future__ import annotations

from server_app.services.tenant import (  # noqa: F401
    DEFAULT_TENANT_ID,
    TenantConfig,
    build_css_variables,
    get_tenant,
    register_custom_domain,
    resolve_tenant,
    tenant_to_dict,
)

ROUTES: list[tuple[str, str]] = [
    ("GET", "/api/tenant"),
]

__all__ = [
    "DEFAULT_TENANT_ID",
    "ROUTES",
    "TenantConfig",
    "build_css_variables",
    "get_tenant",
    "register_custom_domain",
    "resolve_tenant",
    "tenant_to_dict",
]
