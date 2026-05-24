"""T-042 — Tutor dashboard tests.

Covers the deliverables called out in the T-042 plan:

* Tutor-scope authorisation:
  - A tutor-plan org owner can list students.
  - A ``role='tutor'`` member can list students.
  - A standard-plan org's owner cannot.
  - An outsider gets 403.
* PII boundary:
  - The roster JSON exposes only ``account_id``, ``role``, ``joined_at``
    and the readiness rollup. Email / password columns are never in
    the response body.
* Report generation:
  - ``GET /api/tutor/students/<id>/report`` renders self-contained HTML
    with the student's per-skill scores when the caller is a tutor.
  - The same call returns 404 for a student that is not in the tutor's
    org (existence-leak guard).
* Route audit:
  - ``GET /api/tutor/students`` and the report path are present in the
    modularization route list.
"""

from __future__ import annotations

import io
import json
import os
import secrets
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import server  # noqa: F401  (package import side-effects install the T-042 hook)
from server_app import core as _core
from server_app.services import institutional as inst_mod
from server_app.services import readiness as readiness_mod
from server_app.services import schema_a2
from server_app.services import tutor as tutor_mod


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return _core.now_iso()


def _insert_account(conn: sqlite3.Connection, *, email: str) -> str:
    account_id = f"acct_{secrets.token_hex(6)}"
    conn.execute(
        """
        INSERT INTO accounts (
            id, email, password_salt, password_hash, status,
            created_at, deleted_at, role
        ) VALUES (?, ?, 'salt', 'hash', 'active', ?, NULL, 'user')
        """,
        (account_id, email, _now_iso()),
    )
    return account_id


def _seed_skill_score(
    account_id: str, skill: str, *, score: int, attempt_id: str | None = None
) -> None:
    """Insert one (attempt, skill) score row.

    Identical shape to the readiness service's expected input — see
    ``tests/server/test_readiness.py`` for the wider docstring.
    """

    attempt_id = attempt_id or f"att_{secrets.token_hex(6)}"
    created_at = _now_iso()
    with _core.db_connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO attempts
            (id, account_id, exam_id, exam_title, status, submitted_at,
             score_total, score_payload, submission_payload,
             created_at, updated_at)
            VALUES (?, ?, 'a2-builtin', 'A2 Mock', 'submitted', ?,
                    NULL, '{}', '{}', ?, ?)
            """,
            (attempt_id, account_id, created_at, created_at, created_at),
        )
        conn.execute(
            """
            INSERT INTO exam_attempt_category_score (
                account_id, attempt_id, category, score_0_to_15,
                passed_boolean, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                account_id,
                attempt_id,
                skill,
                int(score),
                int(score) >= schema_a2.A2_MIN_PER_SKILL,
                created_at,
            ),
        )
        conn.commit()


class _TutorTestBase(unittest.TestCase):
    """Shared fixture: isolated SQLite DB pointed at by AUTH_DB_PATH."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "auth.sqlite3"
        self.billing_path = Path(self.tmpdir.name) / "billing.sqlite3"
        self.auth_patch = patch.object(_core, "AUTH_DB_PATH", self.db_path)
        self.env_patch = patch.dict(
            os.environ,
            {
                "AUTH_DB_PATH": str(self.db_path),
                "BILLING_DB_PATH": str(self.billing_path),
            },
        )
        self.auth_patch.start()
        self.env_patch.start()
        _core.init_auth_store()
        with _core.db_connection() as conn:
            inst_mod.init_institutional_tables(conn)
            tutor_mod.init_tutor_extensions(conn)

    def tearDown(self) -> None:
        try:
            _core.get_billing_store.cache_clear()
        except AttributeError:  # pragma: no cover - defensive
            pass
        self.env_patch.stop()
        self.auth_patch.stop()
        self.tmpdir.cleanup()

    def _create_account(self, email: str) -> str:
        with _core.db_connection() as conn:
            return _insert_account(conn, email=email)

    def _create_tutor_org(
        self,
        owner: str,
        *,
        name: str = "Tutor School",
        max_seats: int = 10,
    ) -> dict:
        """Create an org and flip its ``plan_tier`` to ``'tutor'``."""

        org = inst_mod.create_org(name, owner, max_seats=max_seats)
        with _core.db_connection() as conn:
            conn.execute(
                "UPDATE organizations SET plan_tier = 'tutor' WHERE id = ?",
                (org["id"],),
            )
            conn.commit()
        return org

    def _add_student(self, org_id: str, *, email: str) -> str:
        student = self._create_account(email)
        voucher = inst_mod.invite_member(
            org_id,
            actor_account_id=self._lookup_owner(org_id),
        )
        inst_mod.redeem_voucher(voucher["code"], student)
        return student

    def _add_tutor_role(self, org_id: str, account_id: str) -> None:
        """Promote an existing member to ``role='tutor'``."""

        with _core.db_connection() as conn:
            conn.execute(
                "UPDATE org_members SET role = 'tutor' "
                "WHERE org_id = ? AND account_id = ?",
                (org_id, account_id),
            )
            conn.commit()

    def _lookup_owner(self, org_id: str) -> str:
        with _core.db_connection() as conn:
            row = conn.execute(
                "SELECT owner_account_id FROM organizations WHERE id = ?",
                (org_id,),
            ).fetchone()
        assert row is not None
        return str(row["owner_account_id"])


# ---------------------------------------------------------------------------
# Service-layer tests (pure Python, no HTTP).
# ---------------------------------------------------------------------------


class TutorScopeTests(_TutorTestBase):
    """``is_tutor_for_org`` + ``assert_tutor`` — the role/plan gate."""

    def test_tutor_plan_owner_is_recognised(self) -> None:
        owner = self._create_account("owner@school.test")
        org = self._create_tutor_org(owner)
        self.assertTrue(tutor_mod.is_tutor_for_org(org["id"], owner))

    def test_standard_plan_owner_is_not_a_tutor(self) -> None:
        owner = self._create_account("owner2@school.test")
        org = inst_mod.create_org("Standard Org", owner, max_seats=3)
        # Default plan_tier is 'standard' so the tutor scope must reject.
        self.assertFalse(tutor_mod.is_tutor_for_org(org["id"], owner))

    def test_role_tutor_member_is_recognised(self) -> None:
        owner = self._create_account("owner3@school.test")
        org = self._create_tutor_org(owner)
        tutor_acct = self._add_student(org["id"], email="t1@school.test")
        self._add_tutor_role(org["id"], tutor_acct)
        self.assertTrue(tutor_mod.is_tutor_for_org(org["id"], tutor_acct))

    def test_plain_member_is_not_a_tutor(self) -> None:
        owner = self._create_account("owner4@school.test")
        org = self._create_tutor_org(owner)
        student = self._add_student(org["id"], email="s1@school.test")
        # role stays 'member', so they are a student, not a tutor.
        self.assertFalse(tutor_mod.is_tutor_for_org(org["id"], student))

    def test_outsider_is_rejected(self) -> None:
        owner = self._create_account("owner5@school.test")
        org = self._create_tutor_org(owner)
        outsider = self._create_account("outsider@elsewhere.test")
        self.assertFalse(tutor_mod.is_tutor_for_org(org["id"], outsider))

    def test_inactive_org_rejects_tutor(self) -> None:
        owner = self._create_account("owner6@school.test")
        org = self._create_tutor_org(owner)
        with _core.db_connection() as conn:
            conn.execute(
                "UPDATE organizations SET status='suspended' WHERE id = ?",
                (org["id"],),
            )
            conn.commit()
        self.assertFalse(tutor_mod.is_tutor_for_org(org["id"], owner))

    def test_assert_tutor_raises_403_for_outsider(self) -> None:
        owner = self._create_account("owner7@school.test")
        org = self._create_tutor_org(owner)
        outsider = self._create_account("outsider2@elsewhere.test")
        with self.assertRaises(tutor_mod.TutorError) as ctx:
            tutor_mod.assert_tutor(org["id"], outsider)
        self.assertEqual(ctx.exception.code, "tutor_forbidden")
        self.assertEqual(ctx.exception.status_code, 403)

    def test_find_orgs_for_tutor_returns_only_tutor_plans(self) -> None:
        owner = self._create_account("owner8@school.test")
        tutor_org = self._create_tutor_org(owner, name="Tutor Plan Org")
        # A separate standard-plan org owned by the same account must
        # NOT appear — that org has no tutor surface.
        inst_mod.create_org("Standard Org", owner, max_seats=3)
        orgs = tutor_mod.find_orgs_for_tutor(owner)
        self.assertEqual([row["id"] for row in orgs], [tutor_org["id"]])


class TutorListStudentsTests(_TutorTestBase):
    """The roster + readiness rollup returned by ``list_students``."""

    def test_list_students_returns_pii_free_roster(self) -> None:
        owner = self._create_account("owner@school.test")
        org = self._create_tutor_org(owner, max_seats=5)
        student_a = self._add_student(org["id"], email="alice@school.test")
        student_b = self._add_student(org["id"], email="bob@school.test")

        payload = tutor_mod.list_students(
            org["id"], actor_account_id=owner
        )
        self.assertEqual(payload["org"]["id"], org["id"])
        self.assertEqual(payload["org"]["plan_tier"], "tutor")
        ids = sorted(row["account_id"] for row in payload["students"])
        self.assertEqual(ids, sorted([student_a, student_b]))

        # PII guard — neither the email column nor a password column may
        # appear anywhere in the serialised JSON envelope.
        body = json.dumps(payload)
        self.assertNotIn("alice@school.test", body)
        self.assertNotIn("bob@school.test", body)
        self.assertNotIn("password_hash", body)
        self.assertNotIn("password_salt", body)

        # Each row must carry the readiness rollup (per-skill + overall).
        for row in payload["students"]:
            self.assertIn("readiness", row)
            self.assertIn("per_skill", row["readiness"])
            self.assertIn("overall_pass_predicted", row["readiness"])
            for skill in schema_a2.A2_SKILLS:
                self.assertIn(skill, row["readiness"]["per_skill"])

    def test_owner_not_listed_as_student(self) -> None:
        owner = self._create_account("owner@school.test")
        org = self._create_tutor_org(owner)
        student = self._add_student(org["id"], email="s2@school.test")
        payload = tutor_mod.list_students(
            org["id"], actor_account_id=owner
        )
        ids = [row["account_id"] for row in payload["students"]]
        self.assertEqual(ids, [student])
        self.assertNotIn(owner, ids)

    def test_readiness_summary_uses_real_attempt_scores(self) -> None:
        owner = self._create_account("owner@school.test")
        org = self._create_tutor_org(owner)
        student = self._add_student(org["id"], email="learner@school.test")
        for skill in schema_a2.A2_SKILLS:
            _seed_skill_score(student, skill, score=14)
        payload = tutor_mod.list_students(
            org["id"], actor_account_id=owner
        )
        student_row = next(
            row for row in payload["students"] if row["account_id"] == student
        )
        for skill in schema_a2.A2_SKILLS:
            skill_data = student_row["readiness"]["per_skill"][skill]
            self.assertEqual(skill_data["badge"], readiness_mod.BADGE_GREEN)
            self.assertEqual(skill_data["avg_score"], 14.0)
            self.assertTrue(skill_data["predicted_pass"])
        self.assertTrue(student_row["readiness"]["overall_pass_predicted"])

    def test_list_students_rejects_outsider(self) -> None:
        owner = self._create_account("owner@school.test")
        org = self._create_tutor_org(owner)
        outsider = self._create_account("outsider@elsewhere.test")
        with self.assertRaises(tutor_mod.TutorError) as ctx:
            tutor_mod.list_students(org["id"], actor_account_id=outsider)
        self.assertEqual(ctx.exception.code, "tutor_forbidden")


class TutorReportTests(_TutorTestBase):
    """``get_student_report`` + ``build_student_report_html``."""

    def test_report_contains_per_skill_scores(self) -> None:
        owner = self._create_account("owner@school.test")
        org = self._create_tutor_org(owner)
        student = self._add_student(org["id"], email="s3@school.test")
        for skill, score in zip(schema_a2.A2_SKILLS, [12, 10, 8, 14]):
            _seed_skill_score(student, skill, score=score)
        report = tutor_mod.get_student_report(
            org["id"], student, actor_account_id=owner
        )
        html_body = tutor_mod.build_student_report_html(report)
        # The HTML must mention each skill name + the rolled-up score.
        for skill in schema_a2.A2_SKILLS:
            self.assertIn(skill.title(), html_body)
        # The 14 score appears for speaking — surface the float as ``14.0 / 15``.
        self.assertIn("14.0 / 15", html_body)
        self.assertIn("12.0 / 15", html_body)

    def test_report_for_unaffiliated_student_returns_404(self) -> None:
        owner = self._create_account("owner@school.test")
        org = self._create_tutor_org(owner)
        loner = self._create_account("loner@elsewhere.test")
        with self.assertRaises(tutor_mod.TutorError) as ctx:
            tutor_mod.get_student_report(
                org["id"], loner, actor_account_id=owner
            )
        self.assertEqual(ctx.exception.code, "tutor_student_not_found")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_report_html_omits_pii_columns(self) -> None:
        owner = self._create_account("owner@school.test")
        org = self._create_tutor_org(owner)
        student = self._add_student(org["id"], email="pii-check@school.test")
        report = tutor_mod.get_student_report(
            org["id"], student, actor_account_id=owner
        )
        html_body = tutor_mod.build_student_report_html(report)
        # The student's email should NEVER appear in the report. The
        # report only carries the redacted account_id.
        self.assertNotIn("pii-check@school.test", html_body)
        self.assertNotIn("password", html_body.lower())
        self.assertIn(student, html_body)


# ---------------------------------------------------------------------------
# HTTP route tests (T-042 hook on AppHandler).
# ---------------------------------------------------------------------------


class _StubHandler:
    """Minimal AppHandler stand-in — copied from test_readiness.py."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.command = "GET"
        self.client_address = ("127.0.0.1", 0)
        self.headers: dict[str, str] = {}
        self.rfile = io.BytesIO()
        self.wfile = io.BytesIO()
        self.responses: list[int] = []
        self.headers_out: list[tuple[str, str]] = []

    def send_response(self, code, message=None):  # noqa: D401, ANN001
        self.responses.append(int(code))

    def send_header(self, key, value):  # noqa: D401, ANN001
        self.headers_out.append((str(key), str(value)))

    def end_headers(self):  # noqa: D401
        pass

    def get_status(self) -> int:
        return self.responses[0] if self.responses else 0

    def body_bytes(self) -> bytes:
        return self.wfile.getvalue()

    def body_json(self) -> dict:
        raw = self.wfile.getvalue().decode("utf-8")
        if not raw:
            return {}
        return json.loads(raw)

    def header_value(self, key: str) -> str:
        for k, v in self.headers_out:
            if k.lower() == key.lower():
                return v
        return ""


def _session_for(account_id: str, *, role: str = "user") -> dict:
    return {
        "account": {
            "id": account_id,
            "email": f"{account_id}@example.test",
            "status": "active",
            "role": role,
            "created_at": "2026-05-05T00:00:00Z",
            "deleted_at": None,
        }
    }


class TutorRouteTests(_TutorTestBase):
    """End-to-end tests of the T-042 ``GET /api/tutor/*`` hooks."""

    def test_list_students_route_serves_tutor(self) -> None:
        owner = self._create_account("owner@school.test")
        org = self._create_tutor_org(owner)
        student = self._add_student(org["id"], email="s@school.test")
        handler = _StubHandler(f"/api/tutor/students?org_id={org['id']}")
        with patch.object(
            _core, "current_session_record", return_value=_session_for(owner)
        ):
            _core.AppHandler.do_GET(handler)  # type: ignore[arg-type]
        self.assertEqual(handler.get_status(), 200)
        payload = handler.body_json()
        self.assertEqual(payload["org"]["id"], org["id"])
        ids = [row["account_id"] for row in payload["students"]]
        self.assertEqual(ids, [student])

    def test_list_students_route_rejects_outsider_with_403(self) -> None:
        owner = self._create_account("owner@school.test")
        org = self._create_tutor_org(owner)
        outsider = self._create_account("outsider@elsewhere.test")
        handler = _StubHandler(f"/api/tutor/students?org_id={org['id']}")
        with patch.object(
            _core,
            "current_session_record",
            return_value=_session_for(outsider),
        ):
            _core.AppHandler.do_GET(handler)  # type: ignore[arg-type]
        self.assertEqual(handler.get_status(), 403)
        self.assertEqual(
            handler.body_json()["error"]["code"], "tutor_forbidden"
        )

    def test_list_students_route_rejects_anonymous_with_401(self) -> None:
        handler = _StubHandler("/api/tutor/students?org_id=org_abc")
        with patch.object(
            _core, "current_session_record", return_value=None
        ):
            _core.AppHandler.do_GET(handler)  # type: ignore[arg-type]
        self.assertEqual(handler.get_status(), 401)

    def test_list_students_route_auto_resolves_single_tutor_org(self) -> None:
        """When ``org_id`` is omitted, the hook picks the caller's only org."""

        owner = self._create_account("owner@school.test")
        org = self._create_tutor_org(owner)
        self._add_student(org["id"], email="s@school.test")
        handler = _StubHandler("/api/tutor/students")
        with patch.object(
            _core, "current_session_record", return_value=_session_for(owner)
        ):
            _core.AppHandler.do_GET(handler)  # type: ignore[arg-type]
        self.assertEqual(handler.get_status(), 200)
        self.assertEqual(handler.body_json()["org"]["id"], org["id"])

    def test_report_route_returns_html_for_known_student(self) -> None:
        owner = self._create_account("owner@school.test")
        org = self._create_tutor_org(owner)
        student = self._add_student(org["id"], email="learner@school.test")
        for skill in schema_a2.A2_SKILLS:
            _seed_skill_score(student, skill, score=12)
        handler = _StubHandler(
            f"/api/tutor/students/{student}/report?org_id={org['id']}"
        )
        with patch.object(
            _core, "current_session_record", return_value=_session_for(owner)
        ):
            _core.AppHandler.do_GET(handler)  # type: ignore[arg-type]
        self.assertEqual(handler.get_status(), 200)
        self.assertEqual(
            handler.header_value("Content-Type"), "text/html; charset=utf-8"
        )
        body = handler.body_bytes().decode("utf-8")
        self.assertIn("<table", body)
        self.assertIn(student, body)
        # The HTML must NOT include the student's email.
        self.assertNotIn("learner@school.test", body)

    def test_report_route_404_for_unaffiliated_student(self) -> None:
        owner = self._create_account("owner@school.test")
        org = self._create_tutor_org(owner)
        loner = self._create_account("loner@elsewhere.test")
        handler = _StubHandler(
            f"/api/tutor/students/{loner}/report?org_id={org['id']}"
        )
        with patch.object(
            _core, "current_session_record", return_value=_session_for(owner)
        ):
            _core.AppHandler.do_GET(handler)  # type: ignore[arg-type]
        self.assertEqual(handler.get_status(), 404)
        self.assertEqual(
            handler.body_json()["error"]["code"], "tutor_student_not_found"
        )

    def test_report_route_rejects_invalid_account_id_segment(self) -> None:
        # Path-traversal style segment must NOT be matched by the T-042
        # report route — ``_t042_match_report_path`` returns ``None``
        # for any segment containing a character outside the
        # ``[A-Za-z0-9_-]`` allow-list (URL-decoded ``..\\/etc`` here
        # contains ``.`` and ``/`` which are both rejected). The
        # function-level assertion below proves the path is rejected
        # before any session check or DB lookup runs.
        match = _core._t042_match_report_path(
            "/api/tutor/students/..%2Fetc/report"
        )
        self.assertIsNone(match)
        # And a well-formed but bogus segment is accepted by the parser
        # (so the route handler can return the canonical 404 envelope).
        self.assertEqual(
            _core._t042_match_report_path(
                "/api/tutor/students/acct_unknown/report"
            ),
            "acct_unknown",
        )


class TutorAuditTests(unittest.TestCase):
    """Audit list — T-042 routes must appear in the modularization registry."""

    def test_routes_are_documented(self) -> None:
        from server_app.routes import tutor as tutor_route
        self.assertIn(("GET", "/api/tutor/students"), tutor_route.ROUTES)
        self.assertIn(
            ("GET", "/api/tutor/students/<account_id>/report"),
            tutor_route.ROUTES,
        )

    def test_routes_visible_in_aggregated_registry(self) -> None:
        from server_app.routes import ROUTES
        patterns = {(method, pattern) for method, pattern, _ in ROUTES}
        self.assertIn(("GET", "/api/tutor/students"), patterns)
        self.assertIn(
            ("GET", "/api/tutor/students/<account_id>/report"), patterns
        )

    def test_hook_install_marker_is_set(self) -> None:
        # The T-042 hook block sets ``_t042_installed`` AFTER the patch
        # is in place, so the v2 SPA static handler is still the
        # outermost wrapper (T-036 audit) while the T-042 hook runs
        # before it on every request.
        self.assertTrue(getattr(_core.AppHandler, "_t042_installed", False))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
