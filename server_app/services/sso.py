"""SSO (OIDC) service — T-040.

Implements an OpenID Connect (OIDC) client for institutional accounts.
SAML is intentionally **out of scope** for this PR — it adds a heavy
``python-saml2`` dependency and the dominant institutional IdPs (Google
Workspace, Azure AD / Entra ID, Okta, Keycloak, Auth0) all speak OIDC.
SAML can be added later via the same ``sso_providers`` table and
parallel route module.

Flow (authorization-code with confidential client):

1. ``GET /sso/oidc/login?org=<org_id>``
   - Look up the org's provider record.
   - Fetch (and cache) the IdP's discovery document.
   - Generate ``state`` and ``nonce``, persist both in ``sso_nonces``.
   - Set a short-lived signed cookie ``sso_state`` carrying the state.
   - 302 to the IdP's ``authorization_endpoint`` with the standard
     OIDC query parameters.

2. ``GET /sso/oidc/callback?code=...&state=...``
   - Verify ``state`` against the cookie + the ``sso_nonces`` ledger.
   - Exchange ``code`` for tokens at the IdP's ``token_endpoint``.
   - Verify the ``id_token``: signature against JWKS, ``iss``, ``aud``,
     ``exp``, and ``nonce``. The ``nonce`` is marked **consumed** on
     successful verification — replay attempts hit the ledger and 400.
   - Look up an existing account by ``email`` claim; if absent and the
     provider has ``auto_provision=1``, create one with a strong random
     password (the learner authenticates via SSO from here on).
   - Issue the standard ``a2_session`` cookie via
     :func:`server_app.core.create_session` so downstream routes see
     the SSO-authenticated user identically to a password-authenticated
     one.

Storage:

* ``sso_providers`` — one row per org. Sensitive columns (``client_id``,
  ``issuer_url``) are Fernet-encrypted at rest using
  ``SSO_ENCRYPTION_KEY``. The client *secret value* is **never** stored —
  only the *name* of the env var that holds it (``client_secret_env``).
* ``sso_nonces`` — short-lived ledger (``state`` + ``nonce``) with a
  10-minute TTL. Enables replay protection across the round-trip.

All HTTP egress (discovery + JWKS + token endpoint) is funnelled through
:func:`_http_get_json` / :func:`_http_post_form`, which are easy to
monkey-patch from tests.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

from server_app.core import (  # type: ignore[attr-defined]
    create_session,
    db_connection,
    log_event,
    normalize_email,
    now_iso,
    upsert_profile,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SSO_STATE_COOKIE = "sso_state"
SSO_NONCE_TTL_SECONDS = 600
JWKS_CACHE_TTL_SECONDS = 24 * 3600
DISCOVERY_CACHE_TTL_SECONDS = 6 * 3600
DEFAULT_OIDC_SCOPES = "openid email profile"
DEFAULT_REDIRECT_PATH = "/sso/oidc/callback"


class SsoError(Exception):
    """Domain error raised by the OIDC client.

    The route layer maps ``SsoError`` to ``400 Bad Request`` with a
    JSON body. ``code`` is a stable machine-readable identifier; the
    English ``message`` is safe to surface in a learner-visible error
    flash. Sensitive details (raw tokens, IdP responses) are never
    embedded — the structured log captures those separately.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# In-process caches
# ---------------------------------------------------------------------------

_DISCOVERY_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_DISCOVERY_LOCK = threading.Lock()

_JWKS_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_JWKS_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Encryption at rest (Fernet)
# ---------------------------------------------------------------------------


def _resolve_encryption_key() -> bytes:
    """Return the Fernet key bytes from ``SSO_ENCRYPTION_KEY``.

    In production this MUST be set in the host environment. In tests
    (and local dev) we derive a deterministic key from a fallback secret
    so the developer can exercise the flow without provisioning anything
    — but we log a warning so accidental production use is visible.
    """

    raw = os.getenv("SSO_ENCRYPTION_KEY", "").strip()
    if raw:
        return raw.encode("ascii")
    fallback_seed = os.getenv("A2_SECRET_KEY", "") or os.getenv(
        "STRIPE_WEBHOOK_SECRET", "lvcodex-sso-dev-only"
    )
    digest = hashlib.sha256(fallback_seed.encode("utf-8")).digest()
    derived = base64.urlsafe_b64encode(digest)
    if os.getenv("APP_ENV", "").strip().lower() == "production":
        log_event(
            "warning",
            "sso_encryption_key_fallback",
            reason="SSO_ENCRYPTION_KEY_not_set_in_production",
        )
    return derived


def _fernet():
    """Return a Fernet instance bound to the current key.

    Imported lazily so the rest of the module loads even when
    ``cryptography`` is absent (defence in depth — the calling routes
    surface a clear error).
    """

    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:  # pragma: no cover - exercised via tests
        raise SsoError(
            "sso_crypto_unavailable",
            "Server is missing the 'cryptography' package required for SSO.",
        ) from exc
    return Fernet(_resolve_encryption_key())


def encrypt_value(plaintext: str) -> str:
    """Encrypt ``plaintext`` using the server's SSO key."""

    if plaintext == "":
        return ""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_value(ciphertext: str) -> str:
    """Inverse of :func:`encrypt_value`."""

    if ciphertext == "":
        return ""
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except Exception as exc:  # noqa: BLE001 - any Fernet error means corrupt
        raise SsoError(
            "sso_ciphertext_invalid",
            "Stored SSO provider record is corrupt or the encryption key has rotated.",
        ) from exc


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def init_sso_tables(conn: sqlite3.Connection) -> None:
    """Create the ``sso_providers`` + ``sso_nonces`` tables if missing.

    Idempotent. Called lazily from every public entry point so that
    test setups that mock ``AUTH_DB_PATH`` after module import still
    work, mirroring the pattern used by ``ensure_listening_profile_links_table``.
    """

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sso_providers (
            id TEXT PRIMARY KEY,
            org_id TEXT NOT NULL UNIQUE,
            type TEXT NOT NULL DEFAULT 'oidc',
            client_id_encrypted TEXT NOT NULL,
            client_secret_env TEXT NOT NULL,
            issuer_url_encrypted TEXT NOT NULL,
            scopes TEXT NOT NULL DEFAULT 'openid email profile',
            redirect_path TEXT NOT NULL DEFAULT '/sso/oidc/callback',
            auto_provision INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_sso_providers_org ON sso_providers(org_id);

        CREATE TABLE IF NOT EXISTS sso_nonces (
            state TEXT PRIMARY KEY,
            org_id TEXT NOT NULL,
            nonce TEXT NOT NULL,
            return_to TEXT,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            consumed_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_sso_nonces_expires
        ON sso_nonces(expires_at);
        """
    )


# ---------------------------------------------------------------------------
# Provider CRUD
# ---------------------------------------------------------------------------


def _provider_id() -> str:
    return f"ssop_{secrets.token_hex(8)}"


def register_provider(
    org_id: str,
    *,
    client_id: str,
    client_secret_env: str,
    issuer_url: str,
    scopes: str | None = None,
    redirect_path: str | None = None,
    auto_provision: bool = True,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Register or update an OIDC provider for the given org.

    ``client_secret_env`` MUST be the *name* of an environment variable
    (e.g. ``OIDC_CLIENT_SECRET_ACME``); the value lives in process
    environment, never in the database. We additionally enforce that
    the named env-var is set at registration time so misconfiguration
    surfaces immediately.
    """

    org_id = (org_id or "").strip().lower()
    client_id = (client_id or "").strip()
    client_secret_env = (client_secret_env or "").strip()
    issuer_url = (issuer_url or "").strip().rstrip("/")
    scopes = (scopes or DEFAULT_OIDC_SCOPES).strip() or DEFAULT_OIDC_SCOPES
    redirect_path = (redirect_path or DEFAULT_REDIRECT_PATH).strip()

    if not org_id:
        raise ValueError("org_id is required.")
    if not client_id:
        raise ValueError("client_id is required.")
    if not client_secret_env:
        raise ValueError("client_secret_env is required.")
    if not issuer_url.startswith(("https://", "http://")):
        raise ValueError("issuer_url must be an absolute http(s) URL.")
    if not client_secret_env.replace("_", "").isalnum():
        raise ValueError(
            "client_secret_env must be an env-var name (letters/digits/underscore)."
        )
    if os.getenv(client_secret_env, "") == "" and not os.getenv(
        "SSO_ALLOW_UNSET_SECRET_ENV", ""
    ):
        raise ValueError(
            f"Environment variable '{client_secret_env}' is not set. "
            "Provision it on the host before registering this provider, or set "
            "SSO_ALLOW_UNSET_SECRET_ENV=1 to override during bootstrap."
        )

    now = now_iso()
    client_id_ct = encrypt_value(client_id)
    issuer_url_ct = encrypt_value(issuer_url)

    def _do(active: sqlite3.Connection) -> dict[str, Any]:
        init_sso_tables(active)
        existing = active.execute(
            "SELECT id FROM sso_providers WHERE org_id = ?", (org_id,)
        ).fetchone()
        if existing is None:
            new_id = _provider_id()
            active.execute(
                """
                INSERT INTO sso_providers (
                    id, org_id, type, client_id_encrypted, client_secret_env,
                    issuer_url_encrypted, scopes, redirect_path,
                    auto_provision, created_at, updated_at
                ) VALUES (?, ?, 'oidc', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id,
                    org_id,
                    client_id_ct,
                    client_secret_env,
                    issuer_url_ct,
                    scopes,
                    redirect_path,
                    1 if auto_provision else 0,
                    now,
                    now,
                ),
            )
            provider_id = new_id
        else:
            provider_id = existing["id"]
            active.execute(
                """
                UPDATE sso_providers SET
                    client_id_encrypted = ?,
                    client_secret_env = ?,
                    issuer_url_encrypted = ?,
                    scopes = ?,
                    redirect_path = ?,
                    auto_provision = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    client_id_ct,
                    client_secret_env,
                    issuer_url_ct,
                    scopes,
                    redirect_path,
                    1 if auto_provision else 0,
                    now,
                    provider_id,
                ),
            )
        return {
            "id": provider_id,
            "org_id": org_id,
            "type": "oidc",
            "client_id": client_id,
            "client_secret_env": client_secret_env,
            "issuer_url": issuer_url,
            "scopes": scopes,
            "redirect_path": redirect_path,
            "auto_provision": auto_provision,
        }

    if conn is not None:
        return _do(conn)
    with db_connection() as opened:
        return _do(opened)


def get_provider(org_id: str) -> dict[str, Any] | None:
    """Return the decrypted provider record for the given org, or None."""

    org_id = (org_id or "").strip().lower()
    if not org_id:
        return None
    with db_connection() as conn:
        init_sso_tables(conn)
        row = conn.execute(
            "SELECT * FROM sso_providers WHERE org_id = ?", (org_id,)
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "org_id": row["org_id"],
            "type": row["type"],
            "client_id": decrypt_value(row["client_id_encrypted"]),
            "client_secret_env": row["client_secret_env"],
            "issuer_url": decrypt_value(row["issuer_url_encrypted"]),
            "scopes": row["scopes"],
            "redirect_path": row["redirect_path"],
            "auto_provision": bool(row["auto_provision"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


def list_providers() -> list[dict[str, Any]]:
    """Return all provider records (decrypted). Admin-only callsite."""

    with db_connection() as conn:
        init_sso_tables(conn)
        rows = conn.execute(
            "SELECT * FROM sso_providers ORDER BY org_id ASC"
        ).fetchall()
        return [
            {
                "id": row["id"],
                "org_id": row["org_id"],
                "type": row["type"],
                "client_id": decrypt_value(row["client_id_encrypted"]),
                # NB: never returns the secret VALUE — only the env-var name.
                "client_secret_env": row["client_secret_env"],
                "issuer_url": decrypt_value(row["issuer_url_encrypted"]),
                "scopes": row["scopes"],
                "redirect_path": row["redirect_path"],
                "auto_provision": bool(row["auto_provision"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]


# ---------------------------------------------------------------------------
# Nonce ledger (state + nonce replay protection)
# ---------------------------------------------------------------------------


def _record_nonce(
    conn: sqlite3.Connection, state: str, *, org_id: str, nonce: str, return_to: str
) -> None:
    now_dt = datetime.now(timezone.utc)
    conn.execute(
        """
        INSERT INTO sso_nonces (
            state, org_id, nonce, return_to, created_at, expires_at, consumed_at
        ) VALUES (?, ?, ?, ?, ?, ?, NULL)
        """,
        (
            state,
            org_id,
            nonce,
            return_to,
            now_dt.isoformat(timespec="seconds").replace("+00:00", "Z"),
            (
                now_dt + timedelta(seconds=SSO_NONCE_TTL_SECONDS)
            ).isoformat(timespec="seconds").replace("+00:00", "Z"),
        ),
    )


def _consume_nonce(
    conn: sqlite3.Connection, *, state: str
) -> dict[str, Any]:
    row = conn.execute(
        "SELECT state, org_id, nonce, return_to, expires_at, consumed_at "
        "FROM sso_nonces WHERE state = ?",
        (state,),
    ).fetchone()
    if row is None:
        raise SsoError("sso_state_unknown", "Unknown or expired SSO state.")
    if row["consumed_at"] is not None:
        raise SsoError("sso_state_replayed", "SSO state has already been used.")
    if row["expires_at"] <= now_iso():
        raise SsoError("sso_state_expired", "SSO state has expired; please retry.")
    conn.execute(
        "UPDATE sso_nonces SET consumed_at = ? WHERE state = ?",
        (now_iso(), state),
    )
    return {
        "state": row["state"],
        "org_id": row["org_id"],
        "nonce": row["nonce"],
        "return_to": row["return_to"] or "/",
    }


def purge_expired_nonces() -> int:
    """Best-effort cleanup. Returns the number of rows removed."""

    with db_connection() as conn:
        init_sso_tables(conn)
        cur = conn.execute(
            "DELETE FROM sso_nonces WHERE expires_at <= ?", (now_iso(),)
        )
        return cur.rowcount


# ---------------------------------------------------------------------------
# Signed state cookie
# ---------------------------------------------------------------------------


def _state_signing_key() -> bytes:
    return _resolve_encryption_key()


def _sign_state(state: str) -> str:
    sig = hmac.new(
        _state_signing_key(), state.encode("utf-8"), hashlib.sha256
    ).digest()
    return f"{state}.{base64.urlsafe_b64encode(sig).decode('ascii').rstrip('=')}"


def _verify_state_cookie(value: str, expected_state: str) -> bool:
    if not value or "." not in value:
        return False
    state_part, sig_part = value.rsplit(".", 1)
    if state_part != expected_state:
        return False
    expected = hmac.new(
        _state_signing_key(), expected_state.encode("utf-8"), hashlib.sha256
    ).digest()
    expected_b64 = base64.urlsafe_b64encode(expected).decode("ascii").rstrip("=")
    return hmac.compare_digest(expected_b64, sig_part)


# ---------------------------------------------------------------------------
# Discovery + JWKS fetchers (HTTP egress lives here)
# ---------------------------------------------------------------------------


def _http_get_json(url: str, *, timeout: float = 5.0) -> dict[str, Any]:
    """Tiny stdlib JSON GET. Test code monkey-patches this symbol."""

    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


def _http_post_form(
    url: str, data: dict[str, str], *, timeout: float = 5.0
) -> dict[str, Any]:
    """Tiny stdlib form-encoded POST returning a JSON dict.

    Used for the OIDC token-exchange call. Test code monkey-patches
    this symbol to inject deterministic responses.
    """

    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


def fetch_discovery(issuer_url: str) -> dict[str, Any]:
    """Fetch and cache the OIDC discovery document for ``issuer_url``."""

    issuer_url = issuer_url.rstrip("/")
    now = time.monotonic()
    with _DISCOVERY_LOCK:
        cached = _DISCOVERY_CACHE.get(issuer_url)
        if cached and (now - cached[0]) < DISCOVERY_CACHE_TTL_SECONDS:
            return cached[1]
    try:
        doc = _http_get_json(
            f"{issuer_url}/.well-known/openid-configuration"
        )
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
        raise SsoError(
            "sso_discovery_failed",
            f"Could not fetch OIDC discovery document for {issuer_url}.",
        ) from exc
    if doc.get("issuer", "").rstrip("/") != issuer_url:
        raise SsoError(
            "sso_discovery_issuer_mismatch",
            "OIDC discovery document 'issuer' does not match the configured URL.",
        )
    with _DISCOVERY_LOCK:
        _DISCOVERY_CACHE[issuer_url] = (now, doc)
    return doc


def fetch_jwks(jwks_uri: str) -> list[dict[str, Any]]:
    """Fetch and cache the JWKS keyset at ``jwks_uri``."""

    now = time.monotonic()
    with _JWKS_LOCK:
        cached = _JWKS_CACHE.get(jwks_uri)
        if cached and (now - cached[0]) < JWKS_CACHE_TTL_SECONDS:
            return cached[1]
    try:
        doc = _http_get_json(jwks_uri)
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
        raise SsoError(
            "sso_jwks_fetch_failed",
            "Could not fetch the IdP signing keys (JWKS).",
        ) from exc
    keys = doc.get("keys") or []
    with _JWKS_LOCK:
        _JWKS_CACHE[jwks_uri] = (now, keys)
    return keys


def _clear_caches_for_tests() -> None:
    """Test-only helper: reset the in-process discovery + JWKS caches."""

    with _DISCOVERY_LOCK:
        _DISCOVERY_CACHE.clear()
    with _JWKS_LOCK:
        _JWKS_CACHE.clear()


# ---------------------------------------------------------------------------
# JWT (id_token) verification
# ---------------------------------------------------------------------------


def _b64url_decode(segment: str) -> bytes:
    pad = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode((segment + pad).encode("ascii"))


def _select_jwk(keys: list[dict[str, Any]], kid: str | None) -> dict[str, Any]:
    if kid is not None:
        for key in keys:
            if key.get("kid") == kid:
                return key
    # If there is only one key, fall back to it (some IdPs omit kid in
    # single-key keysets).
    if len(keys) == 1:
        return keys[0]
    raise SsoError(
        "sso_jwk_not_found",
        "No JWKS entry matched the id_token's 'kid' header.",
    )


def _verify_rs256(
    header_b64: str, payload_b64: str, signature: bytes, jwk: dict[str, Any]
) -> None:
    """Verify an RS256-signed JWT segment against an RSA JWK."""

    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding, rsa
        from cryptography.exceptions import InvalidSignature
    except ImportError as exc:  # pragma: no cover - exercised via tests
        raise SsoError(
            "sso_crypto_unavailable",
            "Server is missing the 'cryptography' package required for SSO.",
        ) from exc

    try:
        n_bytes = _b64url_decode(jwk["n"])
        e_bytes = _b64url_decode(jwk["e"])
    except (KeyError, ValueError) as exc:
        raise SsoError(
            "sso_jwk_invalid", "JWKS entry is missing 'n' / 'e' RSA parameters."
        ) from exc
    n = int.from_bytes(n_bytes, "big")
    e = int.from_bytes(e_bytes, "big")
    public_numbers = rsa.RSAPublicNumbers(e=e, n=n)
    public_key = public_numbers.public_key()
    signed_input = f"{header_b64}.{payload_b64}".encode("ascii")
    try:
        public_key.verify(
            signature,
            signed_input,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except InvalidSignature as exc:
        raise SsoError(
            "sso_id_token_signature_invalid",
            "id_token signature did not verify against the IdP's keys.",
        ) from exc


def verify_id_token(
    id_token: str,
    *,
    jwks_keys: list[dict[str, Any]],
    issuer: str,
    audience: str,
    expected_nonce: str,
    leeway_seconds: int = 60,
    now_ts: int | None = None,
) -> dict[str, Any]:
    """Verify an OIDC id_token and return its claims.

    Performs the standard OIDC checks: RS256 signature, ``iss``, ``aud``,
    ``exp``, ``iat``, and ``nonce``. ``leeway_seconds`` allows for small
    clock skew (default 60s). ``now_ts`` is overridable from tests.
    """

    parts = id_token.split(".")
    if len(parts) != 3:
        raise SsoError("sso_id_token_malformed", "id_token is not a JWS triple.")
    header_b64, payload_b64, sig_b64 = parts
    try:
        header = json.loads(_b64url_decode(header_b64))
        claims = json.loads(_b64url_decode(payload_b64))
        signature = _b64url_decode(sig_b64)
    except (ValueError, json.JSONDecodeError) as exc:
        raise SsoError(
            "sso_id_token_malformed", "id_token segments are not base64url JSON."
        ) from exc

    alg = header.get("alg")
    if alg != "RS256":
        raise SsoError(
            "sso_id_token_alg_unsupported",
            f"id_token alg={alg!r} is not supported (only RS256).",
        )

    jwk = _select_jwk(jwks_keys, header.get("kid"))
    _verify_rs256(header_b64, payload_b64, signature, jwk)

    token_iss = str(claims.get("iss", "")).rstrip("/")
    if token_iss != issuer.rstrip("/"):
        raise SsoError(
            "sso_id_token_issuer_mismatch",
            f"id_token 'iss' ({token_iss!r}) does not match configured issuer.",
        )

    aud = claims.get("aud")
    aud_set = set(aud) if isinstance(aud, list) else {aud}
    if audience not in aud_set:
        raise SsoError(
            "sso_id_token_audience_mismatch",
            "id_token 'aud' does not include the configured client_id.",
        )

    now_unix = now_ts if now_ts is not None else int(time.time())
    exp = int(claims.get("exp") or 0)
    if exp <= now_unix - leeway_seconds:
        raise SsoError("sso_id_token_expired", "id_token has expired.")
    iat = int(claims.get("iat") or 0)
    if iat and iat > now_unix + leeway_seconds:
        raise SsoError(
            "sso_id_token_iat_future",
            "id_token 'iat' is unexpectedly in the future — clock skew?",
        )

    if str(claims.get("nonce") or "") != expected_nonce:
        raise SsoError(
            "sso_id_token_nonce_mismatch",
            "id_token 'nonce' does not match the value we issued.",
        )

    return claims


# ---------------------------------------------------------------------------
# /sso/oidc/login — kick off the flow
# ---------------------------------------------------------------------------


def build_login_redirect(
    org_id: str, *, base_url: str, return_to: str | None = None
) -> tuple[str, str]:
    """Return ``(idp_authorize_url, signed_state_cookie_value)``.

    The route layer applies the redirect (302 + ``Location``) and sets
    ``sso_state`` from the signed cookie value.
    """

    provider = get_provider(org_id)
    if provider is None:
        raise SsoError(
            "sso_provider_unknown",
            f"No SSO provider is registered for org '{org_id}'.",
        )
    discovery = fetch_discovery(provider["issuer_url"])
    authorize_url = discovery.get("authorization_endpoint")
    if not authorize_url:
        raise SsoError(
            "sso_discovery_missing_authorize",
            "IdP discovery document is missing 'authorization_endpoint'.",
        )

    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    redirect_uri = base_url.rstrip("/") + (
        provider["redirect_path"] or DEFAULT_REDIRECT_PATH
    )
    safe_return_to = return_to or "/"

    with db_connection() as conn:
        init_sso_tables(conn)
        _record_nonce(
            conn,
            state,
            org_id=org_id.strip().lower(),
            nonce=nonce,
            return_to=safe_return_to,
        )

    params = {
        "response_type": "code",
        "client_id": provider["client_id"],
        "redirect_uri": redirect_uri,
        "scope": provider["scopes"] or DEFAULT_OIDC_SCOPES,
        "state": state,
        "nonce": nonce,
    }
    separator = "&" if "?" in authorize_url else "?"
    final_url = f"{authorize_url}{separator}{urllib.parse.urlencode(params)}"
    return final_url, _sign_state(state)


# ---------------------------------------------------------------------------
# /sso/oidc/callback — finish the flow
# ---------------------------------------------------------------------------


def _resolve_client_secret(env_name: str) -> str:
    value = os.getenv(env_name, "")
    if not value:
        raise SsoError(
            "sso_client_secret_missing",
            f"Configured env var '{env_name}' is not set on this host.",
        )
    return value


def _link_or_create_account(
    claims: dict[str, Any], provider: dict[str, Any]
) -> tuple[str, str, bool]:
    """Return ``(account_id, session_token, created)``.

    ``created`` is True iff a new account row was inserted as a result
    of this SSO login (i.e. the email did not previously exist and
    ``auto_provision=True``).
    """

    email = normalize_email(str(claims.get("email") or ""))
    if not email or "@" not in email:
        raise SsoError(
            "sso_email_claim_missing",
            "IdP did not return a verified 'email' claim required for linking.",
        )
    full_name = (
        str(claims.get("name") or "").strip()
        or str(claims.get("preferred_username") or "").strip()
        or email.split("@", 1)[0]
    )

    with db_connection() as conn:
        existing = conn.execute(
            "SELECT id, status, deleted_at FROM accounts WHERE email = ?", (email,)
        ).fetchone()
        if existing is not None:
            if existing["deleted_at"] is not None:
                raise SsoError(
                    "sso_account_deleted",
                    "Account associated with this email has been deleted.",
                )
            if existing["status"] != "active":
                raise SsoError(
                    "sso_account_inactive",
                    "Account associated with this email is not active.",
                )
            token = create_session(conn, existing["id"])
            log_event(
                "info",
                "sso_login_linked",
                org_id=provider["org_id"],
                account_id=existing["id"],
            )
            return existing["id"], token, False

        if not provider.get("auto_provision", True):
            raise SsoError(
                "sso_account_not_provisioned",
                "Auto-provisioning is disabled for this org; account must exist first.",
            )

        from server_app.core import hash_password as _hash_password

        random_password = secrets.token_urlsafe(24)
        salt_b64, hash_b64 = _hash_password(random_password)
        account_id = f"acct_{secrets.token_hex(8)}"
        now = now_iso()
        conn.execute(
            """
            INSERT INTO accounts (
                id, email, password_salt, password_hash, status,
                created_at, deleted_at, role
            ) VALUES (?, ?, ?, ?, 'active', ?, NULL, 'user')
            """,
            (account_id, email, salt_b64, hash_b64, now),
        )
        upsert_profile(conn, account_id, full_name, None, None)
        token = create_session(conn, account_id)
        log_event(
            "info",
            "sso_login_provisioned",
            org_id=provider["org_id"],
            account_id=account_id,
        )
        return account_id, token, True


def complete_callback(
    *,
    state: str,
    code: str,
    state_cookie_value: str,
    base_url: str,
) -> dict[str, Any]:
    """Drive the callback end-to-end. Returns a result dict.

    Result shape::

        {
            "account_id": str,
            "session_token": str,
            "created": bool,
            "return_to": str,
            "org_id": str,
        }

    Raises :class:`SsoError` on any verification or transport failure.
    """

    if not state or not code:
        raise SsoError(
            "sso_callback_missing_params",
            "SSO callback requires both 'state' and 'code' query parameters.",
        )
    if not _verify_state_cookie(state_cookie_value, state):
        raise SsoError(
            "sso_state_cookie_mismatch",
            "SSO state cookie is missing, tampered, or does not match 'state'.",
        )

    with db_connection() as conn:
        init_sso_tables(conn)
        record = _consume_nonce(conn, state=state)

    provider = get_provider(record["org_id"])
    if provider is None:
        raise SsoError(
            "sso_provider_unknown",
            "Provider record vanished mid-flow (was the org deleted?).",
        )

    discovery = fetch_discovery(provider["issuer_url"])
    token_endpoint = discovery.get("token_endpoint")
    jwks_uri = discovery.get("jwks_uri")
    if not token_endpoint or not jwks_uri:
        raise SsoError(
            "sso_discovery_incomplete",
            "IdP discovery is missing 'token_endpoint' or 'jwks_uri'.",
        )

    client_secret = _resolve_client_secret(provider["client_secret_env"])
    redirect_uri = base_url.rstrip("/") + (
        provider["redirect_path"] or DEFAULT_REDIRECT_PATH
    )
    try:
        token_response = _http_post_form(
            token_endpoint,
            {
                "grant_type": "authorization_code",
                "code": code,
                "client_id": provider["client_id"],
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
            },
        )
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
        raise SsoError(
            "sso_token_exchange_failed",
            "Token-endpoint exchange with the IdP failed.",
        ) from exc

    id_token = token_response.get("id_token")
    if not id_token:
        raise SsoError(
            "sso_token_response_missing_id_token",
            "IdP token response did not include an id_token.",
        )

    jwks_keys = fetch_jwks(jwks_uri)
    claims = verify_id_token(
        id_token,
        jwks_keys=jwks_keys,
        issuer=provider["issuer_url"],
        audience=provider["client_id"],
        expected_nonce=record["nonce"],
    )

    account_id, session_token, created = _link_or_create_account(claims, provider)
    return {
        "account_id": account_id,
        "session_token": session_token,
        "created": created,
        "return_to": record.get("return_to") or "/",
        "org_id": record["org_id"],
    }


__all__ = [
    "DEFAULT_OIDC_SCOPES",
    "DEFAULT_REDIRECT_PATH",
    "SSO_NONCE_TTL_SECONDS",
    "SSO_STATE_COOKIE",
    "SsoError",
    "build_login_redirect",
    "complete_callback",
    "decrypt_value",
    "encrypt_value",
    "fetch_discovery",
    "fetch_jwks",
    "get_provider",
    "init_sso_tables",
    "list_providers",
    "purge_expired_nonces",
    "register_provider",
    "verify_id_token",
]
