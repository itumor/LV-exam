"""SSO routes (T-040).

Re-exports the OIDC service surface and documents the public routes.
The actual ``do_GET`` / ``do_POST`` dispatch is installed by the
end-of-file T-040 hook in :mod:`server_app.core`, mirroring the pattern
used by T-010 / T-014 / T-015 / T-018 / T-022 / T-036 / T-037.

Routes owned here:

* ``GET  /sso/oidc/login`` — kick off authorization-code flow.
* ``GET  /sso/oidc/callback`` — finish authorization-code flow.
* ``POST /api/admin/sso/providers`` — register / update a provider.
* ``GET  /api/admin/sso/providers`` — list registered providers.
"""

from __future__ import annotations

from server_app.services.sso import (  # noqa: F401
    DEFAULT_OIDC_SCOPES,
    DEFAULT_REDIRECT_PATH,
    SSO_NONCE_TTL_SECONDS,
    SSO_STATE_COOKIE,
    SsoError,
    build_login_redirect,
    complete_callback,
    get_provider,
    init_sso_tables,
    list_providers,
    purge_expired_nonces,
    register_provider,
)

ROUTES: list[tuple[str, str]] = [
    ("GET", "/sso/oidc/login"),
    ("GET", "/sso/oidc/callback"),
    ("GET", "/api/admin/sso/providers"),
    ("POST", "/api/admin/sso/providers"),
]

__all__ = [
    "DEFAULT_OIDC_SCOPES",
    "DEFAULT_REDIRECT_PATH",
    "ROUTES",
    "SSO_NONCE_TTL_SECONDS",
    "SSO_STATE_COOKIE",
    "SsoError",
    "build_login_redirect",
    "complete_callback",
    "get_provider",
    "init_sso_tables",
    "list_providers",
    "purge_expired_nonces",
    "register_provider",
]
