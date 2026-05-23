"""T-040 — SSO (OIDC) callback flow tests.

Covers the deliverables from the T-040 plan:

1. Successful callback flow with a mocked IdP (discovery + JWKS + token).
2. Account linking when the ``email`` claim matches an existing account.
3. New account creation when ``auto_provision=True``.
4. Replay protection — re-using a nonce/state returns 400.
5. Wrong-issuer rejection — ``iss`` claim mismatch returns 400.
6. Provider record encryption at rest (raw DB row is unreadable).
7. The admin route enforces session/role and persists encrypted.

The IdP HTTP egress is mocked end-to-end by monkey-patching
``server_app.services.sso._http_get_json`` and ``_http_post_form``.
No outbound network calls are made.
"""

from __future__ import annotations

import base64
import json
import secrets
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

import server  # noqa: F401  — package import side-effects
from server_app import core as _core
from server_app.services import sso as sso_mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ISSUER_URL = "https://idp.example.test"
CLIENT_ID = "client-acme-001"
CLIENT_SECRET = "super-secret-shhh"
CLIENT_SECRET_ENV = "OIDC_CLIENT_SECRET_ACME"
ORG_ID = "acme"
BASE_URL = "https://app.example.test"
KID = "kid-test-1"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_int(value: int) -> str:
    length = (value.bit_length() + 7) // 8
    return _b64url(value.to_bytes(length, "big"))


def _make_rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwk_from_public(private_key) -> dict[str, str]:
    public_numbers = private_key.public_key().public_numbers()
    return {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": KID,
        "n": _b64url_int(public_numbers.n),
        "e": _b64url_int(public_numbers.e),
    }


def _sign_jwt(
    private_key,
    *,
    claims: dict,
    header_kid: str | None = KID,
) -> str:
    header = {"alg": "RS256", "typ": "JWT"}
    if header_kid is not None:
        header["kid"] = header_kid
    header_b64 = _b64url(
        json.dumps(header, separators=(",", ":")).encode("utf-8")
    )
    payload_b64 = _b64url(
        json.dumps(claims, separators=(",", ":")).encode("utf-8")
    )
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{header_b64}.{payload_b64}.{_b64url(signature)}"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class SsoOidcFlowTests(unittest.TestCase):
    """End-to-end coverage of the OIDC callback flow."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "auth.sqlite3"
        # Patch the auth-store DB path module-wide.
        self.auth_db_patch = patch.object(_core, "AUTH_DB_PATH", self.db_path)
        self.auth_db_patch.start()
        _core.init_auth_store()

        # Pin a deterministic encryption key so different test runs are
        # reproducible; otherwise the Fernet key would be derived from
        # the process env which varies between hosts.
        self.encryption_key_patch = patch.dict(
            "os.environ",
            {
                "SSO_ENCRYPTION_KEY": base64.urlsafe_b64encode(
                    b"0" * 32
                ).decode("ascii"),
                "SSO_ALLOW_UNSET_SECRET_ENV": "1",
                CLIENT_SECRET_ENV: CLIENT_SECRET,
            },
        )
        self.encryption_key_patch.start()

        # Make sure the discovery + JWKS caches do not bleed across tests.
        sso_mod._clear_caches_for_tests()

        # Generate a fresh RSA keypair for every test so signatures cannot
        # be replayed across test cases.
        self.private_key = _make_rsa_key()
        self.jwk = _jwk_from_public(self.private_key)

        # Register a provider so /login can resolve it.
        sso_mod.register_provider(
            ORG_ID,
            client_id=CLIENT_ID,
            client_secret_env=CLIENT_SECRET_ENV,
            issuer_url=ISSUER_URL,
            scopes="openid email profile",
        )

    def tearDown(self) -> None:
        self.encryption_key_patch.stop()
        self.auth_db_patch.stop()
        sso_mod._clear_caches_for_tests()
        self.tmpdir.cleanup()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _patch_http(self, *, token_response: dict, discovery_overrides=None):
        """Patch the SSO HTTP egress to deterministic responses.

        Returns the ``captured`` dict; mutate ``captured['token_response']``
        between test phases to inject a freshly-signed id_token after the
        nonce is known.
        """

        discovery = {
            "issuer": ISSUER_URL,
            "authorization_endpoint": f"{ISSUER_URL}/oauth/authorize",
            "token_endpoint": f"{ISSUER_URL}/oauth/token",
            "jwks_uri": f"{ISSUER_URL}/.well-known/jwks.json",
        }
        if discovery_overrides:
            discovery.update(discovery_overrides)
        jwks_doc = {"keys": [self.jwk]}

        captured: dict = {"posts": [], "token_response": token_response}

        def fake_get(url, *, timeout=5.0):
            if url.endswith("/.well-known/openid-configuration"):
                return discovery
            if url.endswith("/.well-known/jwks.json"):
                return jwks_doc
            raise AssertionError(f"unexpected GET to {url}")

        def fake_post(url, data, *, timeout=5.0):
            captured["posts"].append({"url": url, "data": dict(data)})
            return captured["token_response"]

        # Make sure prior cached entries do not bypass our patches.
        sso_mod._clear_caches_for_tests()
        get_patch = patch.object(sso_mod, "_http_get_json", side_effect=fake_get)
        post_patch = patch.object(sso_mod, "_http_post_form", side_effect=fake_post)
        get_patch.start()
        post_patch.start()
        self.addCleanup(get_patch.stop)
        self.addCleanup(post_patch.stop)
        return captured

    def _begin_login(self, return_to: str = "/") -> tuple[str, str, str]:
        """Run the /login leg and return (state, nonce, signed_cookie_value)."""

        authorize_url, signed_state = sso_mod.build_login_redirect(
            ORG_ID, base_url=BASE_URL, return_to=return_to
        )
        # Parse state out of the authorize URL so the caller has it.
        from urllib.parse import parse_qs, urlparse

        params = parse_qs(urlparse(authorize_url).query)
        state = params["state"][0]
        nonce = params["nonce"][0]
        return state, nonce, signed_state

    def _id_token(self, *, nonce: str, claims_overrides=None) -> str:
        now = int(time.time())
        claims = {
            "iss": ISSUER_URL,
            "sub": "user-12345",
            "aud": CLIENT_ID,
            "exp": now + 600,
            "iat": now,
            "nonce": nonce,
            "email": "alice@acme.example",
            "email_verified": True,
            "name": "Alice Anderson",
        }
        if claims_overrides:
            claims.update(claims_overrides)
        return _sign_jwt(self.private_key, claims=claims)

    # ------------------------------------------------------------------
    # 1. Successful callback flow + new-account provisioning
    # ------------------------------------------------------------------

    def test_callback_provisions_new_account_when_email_unknown(self) -> None:
        captured = self._patch_http(token_response={"id_token": "placeholder"})
        state, nonce, signed_cookie = self._begin_login(return_to="/dashboard")
        captured["token_response"] = {
            "id_token": self._id_token(nonce=nonce),
            "token_type": "Bearer",
        }

        result = sso_mod.complete_callback(
            state=state,
            code="authcode-xyz",
            state_cookie_value=signed_cookie,
            base_url=BASE_URL,
        )

        self.assertTrue(result["created"])
        self.assertEqual(result["org_id"], ORG_ID)
        self.assertEqual(result["return_to"], "/dashboard")
        self.assertTrue(result["account_id"].startswith("acct_"))
        self.assertGreater(len(result["session_token"]), 10)

        # Account row exists, profile row exists, session valid.
        with _core.db_connection() as conn:
            account = conn.execute(
                "SELECT id, email, status, role FROM accounts WHERE id = ?",
                (result["account_id"],),
            ).fetchone()
            self.assertIsNotNone(account)
            self.assertEqual(account["email"], "alice@acme.example")
            self.assertEqual(account["status"], "active")
            self.assertEqual(account["role"], "user")

            profile = conn.execute(
                "SELECT full_name FROM profiles WHERE account_id = ?",
                (result["account_id"],),
            ).fetchone()
            self.assertIsNotNone(profile)
            self.assertEqual(profile["full_name"], "Alice Anderson")

    # ------------------------------------------------------------------
    # 2. Account linking when email matches an existing account
    # ------------------------------------------------------------------

    def test_callback_links_existing_account_by_email(self) -> None:
        # Pre-existing password-auth account with the SSO email.
        existing_id = "acct_existing_xyz"
        now = _core.now_iso()
        with _core.db_connection() as conn:
            conn.execute(
                """
                INSERT INTO accounts
                    (id, email, password_salt, password_hash, status,
                     created_at, deleted_at, role)
                VALUES (?, 'alice@acme.example', 'salt', 'hash', 'active',
                        ?, NULL, 'user')
                """,
                (existing_id, now),
            )

        captured = self._patch_http(token_response={"id_token": "placeholder"})
        state, nonce, signed_cookie = self._begin_login()
        captured["token_response"] = {
            "id_token": self._id_token(nonce=nonce),
            "token_type": "Bearer",
        }

        result = sso_mod.complete_callback(
            state=state,
            code="authcode",
            state_cookie_value=signed_cookie,
            base_url=BASE_URL,
        )

        self.assertFalse(result["created"])
        self.assertEqual(result["account_id"], existing_id)
        # Session was opened against the existing account, not a new one.
        with _core.db_connection() as conn:
            session_row = conn.execute(
                "SELECT account_id FROM sessions WHERE token = ?",
                (result["session_token"],),
            ).fetchone()
            self.assertEqual(session_row["account_id"], existing_id)

    # ------------------------------------------------------------------
    # 3. Replay protection — re-using a state/nonce is rejected
    # ------------------------------------------------------------------

    def test_callback_rejects_replayed_state(self) -> None:
        captured = self._patch_http(token_response={"id_token": "placeholder"})
        state, nonce, signed_cookie = self._begin_login()
        captured["token_response"] = {
            "id_token": self._id_token(nonce=nonce),
            "token_type": "Bearer",
        }

        # First call consumes the nonce.
        sso_mod.complete_callback(
            state=state,
            code="authcode",
            state_cookie_value=signed_cookie,
            base_url=BASE_URL,
        )

        # Second call must fail — same state, signed cookie still valid.
        with self.assertRaises(sso_mod.SsoError) as ctx:
            sso_mod.complete_callback(
                state=state,
                code="authcode-2",
                state_cookie_value=signed_cookie,
                base_url=BASE_URL,
            )
        self.assertEqual(ctx.exception.code, "sso_state_replayed")

    # ------------------------------------------------------------------
    # 4. Wrong-issuer rejection
    # ------------------------------------------------------------------

    def test_callback_rejects_wrong_issuer_claim(self) -> None:
        captured = self._patch_http(token_response={"id_token": "placeholder"})
        state, nonce, signed_cookie = self._begin_login()
        captured["token_response"] = {
            "id_token": self._id_token(
                nonce=nonce,
                claims_overrides={"iss": "https://attacker.example"},
            ),
            "token_type": "Bearer",
        }

        with self.assertRaises(sso_mod.SsoError) as ctx:
            sso_mod.complete_callback(
                state=state,
                code="authcode",
                state_cookie_value=signed_cookie,
                base_url=BASE_URL,
            )
        self.assertEqual(ctx.exception.code, "sso_id_token_issuer_mismatch")

    # ------------------------------------------------------------------
    # 5. Wrong-audience rejection
    # ------------------------------------------------------------------

    def test_callback_rejects_wrong_audience_claim(self) -> None:
        captured = self._patch_http(token_response={"id_token": "placeholder"})
        state, nonce, signed_cookie = self._begin_login()
        captured["token_response"] = {
            "id_token": self._id_token(
                nonce=nonce, claims_overrides={"aud": "some-other-client"}
            ),
            "token_type": "Bearer",
        }

        with self.assertRaises(sso_mod.SsoError) as ctx:
            sso_mod.complete_callback(
                state=state,
                code="authcode",
                state_cookie_value=signed_cookie,
                base_url=BASE_URL,
            )
        self.assertEqual(ctx.exception.code, "sso_id_token_audience_mismatch")

    # ------------------------------------------------------------------
    # 6. Tampered state cookie
    # ------------------------------------------------------------------

    def test_callback_rejects_tampered_state_cookie(self) -> None:
        captured = self._patch_http(token_response={"id_token": "placeholder"})
        state, nonce, _signed_cookie = self._begin_login()
        captured["token_response"] = {
            "id_token": self._id_token(nonce=nonce),
            "token_type": "Bearer",
        }

        with self.assertRaises(sso_mod.SsoError) as ctx:
            sso_mod.complete_callback(
                state=state,
                code="authcode",
                state_cookie_value=f"{state}.tampered-signature",
                base_url=BASE_URL,
            )
        self.assertEqual(ctx.exception.code, "sso_state_cookie_mismatch")

    # ------------------------------------------------------------------
    # 7. Auto-provision = False disables learner self-onboarding
    # ------------------------------------------------------------------

    def test_callback_rejects_unknown_email_when_auto_provision_off(self) -> None:
        sso_mod.register_provider(
            ORG_ID,
            client_id=CLIENT_ID,
            client_secret_env=CLIENT_SECRET_ENV,
            issuer_url=ISSUER_URL,
            scopes="openid email profile",
            auto_provision=False,
        )

        captured = self._patch_http(token_response={"id_token": "placeholder"})
        state, nonce, signed_cookie = self._begin_login()
        captured["token_response"] = {
            "id_token": self._id_token(nonce=nonce),
            "token_type": "Bearer",
        }

        with self.assertRaises(sso_mod.SsoError) as ctx:
            sso_mod.complete_callback(
                state=state,
                code="authcode",
                state_cookie_value=signed_cookie,
                base_url=BASE_URL,
            )
        self.assertEqual(ctx.exception.code, "sso_account_not_provisioned")

    # ------------------------------------------------------------------
    # 8. Login redirect contains expected OIDC params
    # ------------------------------------------------------------------

    def test_login_builds_oidc_authorize_url(self) -> None:
        self._patch_http(token_response={"id_token": "unused"})
        authorize_url, signed_cookie = sso_mod.build_login_redirect(
            ORG_ID, base_url=BASE_URL, return_to="/dashboard"
        )

        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(authorize_url)
        self.assertEqual(parsed.scheme + "://" + parsed.netloc, ISSUER_URL)
        params = parse_qs(parsed.query)
        self.assertEqual(params["response_type"], ["code"])
        self.assertEqual(params["client_id"], [CLIENT_ID])
        self.assertEqual(params["scope"], ["openid email profile"])
        self.assertIn("state", params)
        self.assertIn("nonce", params)
        # Signed cookie carries the same state value.
        self.assertTrue(signed_cookie.startswith(params["state"][0] + "."))


class SsoProviderStorageTests(unittest.TestCase):
    """Provider records are encrypted at rest and the secret value is never stored."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "auth.sqlite3"
        self.auth_db_patch = patch.object(_core, "AUTH_DB_PATH", self.db_path)
        self.auth_db_patch.start()
        _core.init_auth_store()
        self.env_patch = patch.dict(
            "os.environ",
            {
                "SSO_ENCRYPTION_KEY": base64.urlsafe_b64encode(
                    b"k" * 32
                ).decode("ascii"),
                "SSO_ALLOW_UNSET_SECRET_ENV": "1",
            },
        )
        self.env_patch.start()

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.auth_db_patch.stop()
        self.tmpdir.cleanup()

    def test_raw_db_row_does_not_contain_plaintext_client_id_or_issuer(self) -> None:
        sso_mod.register_provider(
            "acme",
            client_id="raw-client-id-PLAIN",
            client_secret_env="OIDC_CLIENT_SECRET_ACME_2",
            issuer_url="https://idp.acme.example",
        )
        with _core.db_connection() as conn:
            row = conn.execute(
                "SELECT client_id_encrypted, issuer_url_encrypted, client_secret_env "
                "FROM sso_providers WHERE org_id = ?",
                ("acme",),
            ).fetchone()
        self.assertNotIn("raw-client-id-PLAIN", row["client_id_encrypted"])
        self.assertNotIn(
            "idp.acme.example", row["issuer_url_encrypted"]
        )
        # The env-var NAME is stored as-is (not the secret value).
        self.assertEqual(
            row["client_secret_env"], "OIDC_CLIENT_SECRET_ACME_2"
        )

    def test_register_provider_is_idempotent_on_org_id(self) -> None:
        first = sso_mod.register_provider(
            "acme",
            client_id="cid-1",
            client_secret_env="OIDC_CLIENT_SECRET_ACME_3",
            issuer_url="https://idp.acme.example",
        )
        second = sso_mod.register_provider(
            "acme",
            client_id="cid-2",
            client_secret_env="OIDC_CLIENT_SECRET_ACME_3",
            issuer_url="https://idp.acme.example",
            auto_provision=False,
        )
        # Same provider id; values updated.
        self.assertEqual(first["id"], second["id"])
        loaded = sso_mod.get_provider("acme")
        self.assertEqual(loaded["client_id"], "cid-2")
        self.assertFalse(loaded["auto_provision"])

    def test_register_provider_rejects_missing_env_var_without_override(self) -> None:
        # Drop the override.
        with patch.dict(
            "os.environ", {"SSO_ALLOW_UNSET_SECRET_ENV": ""}, clear=False
        ):
            with self.assertRaises(ValueError):
                sso_mod.register_provider(
                    "acme-2",
                    client_id="cid",
                    client_secret_env="OIDC_CLIENT_SECRET_ACME_NOT_SET",
                    issuer_url="https://idp.example",
                )


class SsoNonceLedgerTests(unittest.TestCase):
    """Direct coverage of nonce ledger purge + race-safety guards."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "auth.sqlite3"
        self.auth_db_patch = patch.object(_core, "AUTH_DB_PATH", self.db_path)
        self.auth_db_patch.start()
        _core.init_auth_store()

    def tearDown(self) -> None:
        self.auth_db_patch.stop()
        self.tmpdir.cleanup()

    def test_purge_expired_nonces_drops_only_expired_rows(self) -> None:
        with _core.db_connection() as conn:
            sso_mod.init_sso_tables(conn)
            past = (
                datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            ).replace("+00:00", "Z")
            past_iso = "2020-01-01T00:00:00Z"
            future_iso = "2999-01-01T00:00:00Z"
            for state_value, exp in [
                ("expired-1", past_iso),
                ("expired-2", past_iso),
                ("live-1", future_iso),
            ]:
                conn.execute(
                    """
                    INSERT INTO sso_nonces (
                        state, org_id, nonce, return_to,
                        created_at, expires_at, consumed_at
                    ) VALUES (?, 'o', ?, '/', ?, ?, NULL)
                    """,
                    (state_value, secrets.token_urlsafe(8), past, exp),
                )

        removed = sso_mod.purge_expired_nonces()
        self.assertEqual(removed, 2)
        with _core.db_connection() as conn:
            remaining = [
                row["state"]
                for row in conn.execute(
                    "SELECT state FROM sso_nonces"
                ).fetchall()
            ]
        self.assertEqual(remaining, ["live-1"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
