"""T-023 — Unified accounts tests.

Covers the merged exam-app + listening-library identity surface:

1. ``resolve_session`` returns the same unified session payload for a
   request originating from either app.
2. Linking a legacy listening-library profile to a unified account is
   idempotent and surfaces in subsequent session resolutions.
3. The migration script (``scripts/link_listening_profiles.py``)
   matches legacy profiles to accounts by email and reports unmatched
   entries without erroring.
4. Anonymous (no-cookie, malformed, expired, or revoked) requests
   resolve to ``None`` on both surfaces.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import server  # noqa: F401  — ensures package import side-effects run
from server_app import core as _core
from server_app.services import auth_store

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import link_listening_profiles  # noqa: E402


def _iso_in(days: int) -> str:
    dt = datetime.now(timezone.utc) + timedelta(days=days)
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def _seed_account(
    conn,
    *,
    account_id: str,
    email: str,
    full_name: str = "Test Learner",
    status: str = "active",
) -> None:
    conn.execute(
        """
        INSERT INTO accounts
            (id, email, password_salt, password_hash, status, created_at, deleted_at, role)
        VALUES (?, ?, 'salt', 'hash', ?, ?, NULL, 'user')
        """,
        (account_id, email, status, _iso_in(-1)),
    )
    conn.execute(
        """
        INSERT INTO profiles
            (account_id, full_name, native_language, exam_target_date,
             exam_pack_status, updated_at)
        VALUES (?, ?, 'en', NULL, 'free', ?)
        """,
        (account_id, full_name, _iso_in(0)),
    )


def _seed_session(
    conn, *, token: str, account_id: str, expires_at: str | None = None
) -> None:
    conn.execute(
        """
        INSERT INTO sessions
            (token, account_id, created_at, expires_at, revoked_at, last_seen_at)
        VALUES (?, ?, ?, ?, NULL, ?)
        """,
        (
            token,
            account_id,
            _iso_in(-1),
            expires_at or _iso_in(30),
            _iso_in(-1),
        ),
    )


class UnifiedAccountsTests(unittest.TestCase):
    """End-to-end coverage of the T-023 unified-accounts surface."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "auth.sqlite3"
        # Patch the auth-store DB path module-wide. Both ``server`` and
        # ``server_app.core`` resolve the same module object, so a single
        # patch is enough.
        self.auth_db_patch = patch.object(_core, "AUTH_DB_PATH", self.db_path)
        self.auth_db_patch.start()
        _core.init_auth_store()

    def tearDown(self) -> None:
        self.auth_db_patch.stop()
        self.tmpdir.cleanup()

    # --- 1. shared session across surfaces -------------------------------

    def test_same_user_session_works_from_either_app(self) -> None:
        token = "tkn_unified_1"
        with _core.db_connection() as conn:
            _seed_account(
                conn, account_id="acct_unified", email="learner@example.test"
            )
            _seed_session(conn, token=token, account_id="acct_unified")

        cookie_header = f"{auth_store.AUTH_SESSION_COOKIE}={token}"

        # Request "from the exam app" — same Cookie header the exam-app
        # JS would send (credentials: same-origin).
        from_exam = auth_store.resolve_session(cookie_header)
        self.assertIsNotNone(from_exam)
        self.assertEqual(from_exam["account"]["email"], "learner@example.test")
        self.assertEqual(from_exam["account"]["id"], "acct_unified")
        self.assertEqual(from_exam["profile"]["full_name"], "Test Learner")
        self.assertEqual(from_exam["listening_profile_links"], [])

        # Request "from the listening library" — the cookie is Path=/ so
        # the browser sends the identical header. The resolver must
        # return the identical account/profile payload.
        from_listening = auth_store.resolve_session(cookie_header)
        self.assertIsNotNone(from_listening)
        self.assertEqual(from_listening["account"], from_exam["account"])
        self.assertEqual(from_listening["profile"], from_exam["profile"])

    def test_resolve_session_handles_extra_cookies(self) -> None:
        token = "tkn_with_neighbours"
        with _core.db_connection() as conn:
            _seed_account(
                conn, account_id="acct_neighbours", email="neighbour@example.test"
            )
            _seed_session(conn, token=token, account_id="acct_neighbours")

        header = (
            f"theme=dark; {auth_store.AUTH_SESSION_COOKIE}={token}; locale=lv"
        )
        session = auth_store.resolve_session(header)
        self.assertIsNotNone(session)
        self.assertEqual(session["account"]["id"], "acct_neighbours")

    # --- 2. link migration -----------------------------------------------

    def test_link_listening_profile_is_idempotent_and_visible(self) -> None:
        with _core.db_connection() as conn:
            _seed_account(
                conn, account_id="acct_link", email="link@example.test"
            )
            _seed_session(conn, token="tkn_link", account_id="acct_link")

        # First link creates the row.
        first = auth_store.link_listening_profile(
            "acct_link", "legacy-listening-uuid-001"
        )
        self.assertTrue(first["created"])
        first_linked_at = first["linked_at"]

        # Re-linking the same pair is a no-op and preserves the original
        # timestamp — important for audit history.
        second = auth_store.link_listening_profile(
            "acct_link", "legacy-listening-uuid-001"
        )
        self.assertFalse(second["created"])
        self.assertEqual(second["linked_at"], first_linked_at)

        # Linking a second legacy id for the same account is allowed —
        # one user may have left multiple devices' worth of localStorage.
        third = auth_store.link_listening_profile(
            "acct_link", "link@example.test"
        )
        self.assertTrue(third["created"])

        # The session resolver returns both links so the front-end can
        # show "merged from listening-library" status.
        session = auth_store.resolve_session(
            f"{auth_store.AUTH_SESSION_COOKIE}=tkn_link"
        )
        self.assertIsNotNone(session)
        ids = sorted(
            link["listening_profile_id"]
            for link in session["listening_profile_links"]
        )
        self.assertEqual(
            ids, ["legacy-listening-uuid-001", "link@example.test"]
        )

    def test_link_listening_profile_requires_known_account(self) -> None:
        with self.assertRaises(LookupError):
            auth_store.link_listening_profile("acct_missing", "anything")

    def test_link_listening_profile_rejects_empty_inputs(self) -> None:
        with _core.db_connection() as conn:
            _seed_account(
                conn, account_id="acct_validate", email="v@example.test"
            )
        with self.assertRaises(ValueError):
            auth_store.link_listening_profile("", "legacy")
        with self.assertRaises(ValueError):
            auth_store.link_listening_profile("acct_validate", "")

    def test_unlink_listening_profile_removes_row(self) -> None:
        with _core.db_connection() as conn:
            _seed_account(
                conn, account_id="acct_unlink", email="u@example.test"
            )
        auth_store.link_listening_profile("acct_unlink", "legacy-x")
        self.assertTrue(
            auth_store.unlink_listening_profile("acct_unlink", "legacy-x")
        )
        self.assertFalse(
            auth_store.unlink_listening_profile("acct_unlink", "legacy-x")
        )

    def test_migration_script_links_by_email_match(self) -> None:
        with _core.db_connection() as conn:
            _seed_account(
                conn, account_id="acct_alice", email="alice@example.test"
            )
            _seed_account(
                conn, account_id="acct_bob", email="bob@example.test"
            )

        records = [
            {
                "listening_profile_id": "alice@example.test",
                "email": "alice@example.test",
            },
            {
                "listening_profile_id": "legacy-uuid-bob",
                "email": "bob@example.test",
            },
            # No matching account — should be reported as unmatched, not
            # raise.
            {
                "listening_profile_id": "legacy-uuid-ghost",
                "email": "ghost@example.test",
            },
        ]
        summary = link_listening_profiles.link_records(records)
        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["linked"], 2)
        self.assertEqual(summary["already_linked"], 0)
        self.assertEqual(summary["unmatched"], 1)
        self.assertEqual(summary["errors"], [])

        # Re-running is safe — every previously-linked record reports as
        # already_linked.
        again = link_listening_profiles.link_records(records)
        self.assertEqual(again["linked"], 0)
        self.assertEqual(again["already_linked"], 2)
        self.assertEqual(again["unmatched"], 1)

    def test_migration_script_dry_run_writes_nothing(self) -> None:
        with _core.db_connection() as conn:
            _seed_account(
                conn, account_id="acct_dry", email="dry@example.test"
            )
        records = [
            {
                "listening_profile_id": "dry@example.test",
                "email": "dry@example.test",
            }
        ]
        summary = link_listening_profiles.link_records(records, dry_run=True)
        self.assertEqual(summary["linked"], 1)
        # No row written.
        with _core.db_connection() as conn:
            auth_store.ensure_listening_profile_links_table(conn)
            count = conn.execute(
                "SELECT COUNT(*) AS n FROM listening_profile_links"
            ).fetchone()["n"]
        self.assertEqual(count, 0)

    def test_migration_script_main_writes_json_summary(self) -> None:
        with _core.db_connection() as conn:
            _seed_account(
                conn, account_id="acct_cli", email="cli@example.test"
            )
        records = [
            {
                "listening_profile_id": "cli@example.test",
                "email": "cli@example.test",
            }
        ]
        input_path = Path(self.tmpdir.name) / "legacy.json"
        input_path.write_text(json.dumps(records), encoding="utf-8")

        import io as _io

        buf = _io.StringIO()
        with patch.object(sys, "stdout", buf):
            rc = link_listening_profiles.main([str(input_path)])
        self.assertEqual(rc, 0)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["linked"], 1)
        self.assertEqual(out["errors"], [])

    # --- 3. anonymous / negative paths -----------------------------------

    def test_anonymous_request_returns_none(self) -> None:
        self.assertIsNone(auth_store.resolve_session(None))
        self.assertIsNone(auth_store.resolve_session(""))
        # No a2_session cookie present.
        self.assertIsNone(auth_store.resolve_session("theme=dark; locale=lv"))

    def test_unknown_token_returns_none(self) -> None:
        cookie = f"{auth_store.AUTH_SESSION_COOKIE}=nope_does_not_exist"
        self.assertIsNone(auth_store.resolve_session(cookie))

    def test_expired_session_returns_none_and_gets_revoked(self) -> None:
        token = "tkn_expired"
        with _core.db_connection() as conn:
            _seed_account(
                conn, account_id="acct_exp", email="exp@example.test"
            )
            _seed_session(
                conn,
                token=token,
                account_id="acct_exp",
                expires_at=_iso_in(-1),
            )
        cookie = f"{auth_store.AUTH_SESSION_COOKIE}={token}"
        self.assertIsNone(auth_store.resolve_session(cookie))
        # Expired sessions should be auto-revoked so they cannot be
        # resurrected by clock skew on a later request.
        with _core.db_connection() as conn:
            row = conn.execute(
                "SELECT revoked_at FROM sessions WHERE token = ?", (token,)
            ).fetchone()
        self.assertIsNotNone(row["revoked_at"])

    def test_revoked_session_returns_none(self) -> None:
        token = "tkn_revoked"
        with _core.db_connection() as conn:
            _seed_account(
                conn, account_id="acct_rev", email="rev@example.test"
            )
            _seed_session(conn, token=token, account_id="acct_rev")
            conn.execute(
                "UPDATE sessions SET revoked_at = ? WHERE token = ?",
                (_iso_in(0), token),
            )
        cookie = f"{auth_store.AUTH_SESSION_COOKIE}={token}"
        self.assertIsNone(auth_store.resolve_session(cookie))

    def test_soft_deleted_account_returns_none(self) -> None:
        token = "tkn_deleted"
        with _core.db_connection() as conn:
            _seed_account(
                conn, account_id="acct_del", email="del@example.test"
            )
            _seed_session(conn, token=token, account_id="acct_del")
            conn.execute(
                "UPDATE accounts SET deleted_at = ?, status = 'deleted' WHERE id = ?",
                (_iso_in(0), "acct_del"),
            )
        cookie = f"{auth_store.AUTH_SESSION_COOKIE}={token}"
        self.assertIsNone(auth_store.resolve_session(cookie))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
