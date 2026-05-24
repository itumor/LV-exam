"""Tutor dashboard service — T-042.

Adds the *tutor* role on top of the T-041 institutional seat-licensing
substrate so language schools / private tutors can supervise the
progress of the learners on their plan.

Data model extension
--------------------

* ``organizations.plan_tier`` — TEXT, defaults to ``'standard'``. The
  value ``'tutor'`` marks an org whose owner (and any member with
  ``role = 'tutor'``) can read the per-learner readiness rollup of the
  org's *students*. A ``'standard'`` org keeps the T-041 behaviour
  unchanged — no tutor surface, no cross-account reads.

* ``org_members.role`` — the existing TEXT column already accepts
  arbitrary values; we add ``'tutor'`` as a recognised value in
  addition to the existing ``'owner'`` / ``'member'``. A tutor member
  has the same paid-tier entitlements as a normal member (T-024
  extension via :func:`institutional.account_has_active_seat`) plus
  the read-only tutor scope guarded by :func:`assert_tutor`.

Public API
----------

* :func:`init_tutor_extensions` — idempotent ``plan_tier`` migration.
* :func:`is_tutor_for_org` — read-only predicate, ``True`` if
  ``account_id`` is the owner of a tutor-plan org OR an active
  ``role = 'tutor'`` member of such an org.
* :func:`assert_tutor` — raises :class:`TutorError` (HTTP 403) when the
  caller is not a tutor for the requested org.
* :func:`list_students` — return the org's *student* roster
  (``role`` in :data:`STUDENT_ROLES`) plus the per-learner readiness
  summary computed via :mod:`server_app.services.readiness`. Only the
  account id, the role/status, joined_at and the readiness rollup are
  surfaced — emails and other PII columns are deliberately omitted.
* :func:`build_student_report_html` — render a self-contained HTML
  report for one student (used by ``GET /api/tutor/students/{id}/report``).

PII boundary
------------

A tutor can only read the data of accounts they supervise — i.e. the
active members of their own tutor-plan org. The service NEVER returns
the student's email address, password salt/hash, or any other column
that is not strictly required for the readiness UI. The HTML report
exposes the **account id** and the per-skill numeric scores; nothing
else.
"""

from __future__ import annotations

import html
import sqlite3
from typing import Any

from server_app.core import (  # type: ignore[attr-defined]
    db_connection,
    log_event,
    now_iso,
)
from server_app.services import readiness as _readiness


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Plan-tier value that activates the tutor surface on an organization.
PLAN_TIER_TUTOR = "tutor"

#: Default plan-tier for legacy orgs (T-041 created rows without this
#: column). The migration backfills ``'standard'`` so the ``plan_tier``
#: column never carries NULL.
PLAN_TIER_STANDARD = "standard"

#: Org-member roles that represent a *learner* the tutor supervises.
#: The tutor themselves (``role='tutor'``) and the owner (``role='owner'``)
#: are NOT students even though they may technically be learners — they
#: are excluded from the student roster so the tutor dashboard does not
#: list the tutor's own account as a row to be graded.
STUDENT_ROLES: frozenset[str] = frozenset({"member", "student"})

#: Org-member roles that grant the tutor scope (read-only access to
#: ``list_students`` + ``build_student_report_html``).
TUTOR_ROLES: frozenset[str] = frozenset({"owner", "tutor"})


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class TutorError(Exception):
    """Domain error raised by the tutor service.

    Mirrors the shape of :class:`institutional.InstitutionalError` so the
    route layer can use a single error-envelope helper. ``status_code``
    defaults to 403 (the most common failure: caller is not a tutor for
    the requested org).
    """

    def __init__(
        self, code: str, message: str, *, status_code: int = 403
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


# ---------------------------------------------------------------------------
# Schema extension
# ---------------------------------------------------------------------------


def init_tutor_extensions(conn: sqlite3.Connection) -> None:
    """Ensure ``organizations.plan_tier`` exists. Idempotent.

    Called from every public entry point (and from the import-time hook
    in :mod:`server_app.core`) so that test setups that patch
    ``AUTH_DB_PATH`` after module import still see the column.
    """

    # The T-041 service is responsible for creating the base tables —
    # delegate to it so we never race against a fresh AUTH_DB_PATH.
    from server_app.services import institutional as _inst

    _inst.init_institutional_tables(conn)
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(organizations)").fetchall()
    }
    if "plan_tier" not in columns:
        # SQLite ALTER TABLE ADD COLUMN does not support non-constant
        # defaults; ``'standard'`` is a string literal so this is fine.
        conn.execute(
            "ALTER TABLE organizations ADD COLUMN plan_tier TEXT "
            "NOT NULL DEFAULT 'standard'"
        )
        # Backfill rows created before the migration ran. Defensive even
        # though the ADD COLUMN with NOT NULL DEFAULT applies to existing
        # rows on SQLite (>=3.3) — but Postgres rewrites lazily.
        conn.execute(
            "UPDATE organizations SET plan_tier = 'standard' "
            "WHERE plan_tier IS NULL"
        )
    conn.commit()


# ---------------------------------------------------------------------------
# Tutor-scope helpers
# ---------------------------------------------------------------------------


def _get_org_plan_tier(conn: sqlite3.Connection, org_id: str) -> str | None:
    row = conn.execute(
        "SELECT plan_tier, status FROM organizations WHERE id = ?",
        (org_id,),
    ).fetchone()
    if row is None:
        return None
    if (row["status"] or "active") != "active":
        return None
    return str(row["plan_tier"] or PLAN_TIER_STANDARD)


def _membership_role(
    conn: sqlite3.Connection, *, org_id: str, account_id: str
) -> str | None:
    row = conn.execute(
        """
        SELECT role, status FROM org_members
        WHERE org_id = ? AND account_id = ?
        """,
        (org_id, account_id),
    ).fetchone()
    if row is None:
        return None
    if (row["status"] or "active") != "active":
        return None
    return str(row["role"] or "member")


def is_tutor_for_org(org_id: str, account_id: str) -> bool:
    """Return True if ``account_id`` can supervise students in ``org_id``.

    The caller must be either the org owner OR an active member with
    ``role = 'tutor'``, AND the org's ``plan_tier`` must equal
    :data:`PLAN_TIER_TUTOR`. Standard-plan orgs return False even for
    the owner — the tutor surface is gated on the plan, not on the
    individual.
    """

    org_id = (org_id or "").strip()
    account_id = (account_id or "").strip()
    if not org_id or not account_id:
        return False
    with db_connection() as conn:
        init_tutor_extensions(conn)
        plan = _get_org_plan_tier(conn, org_id)
        if plan != PLAN_TIER_TUTOR:
            return False
        role = _membership_role(conn, org_id=org_id, account_id=account_id)
        if role is None:
            return False
        return role in TUTOR_ROLES


def find_orgs_for_tutor(account_id: str) -> list[dict[str, Any]]:
    """Return the tutor-plan orgs where ``account_id`` has the tutor scope.

    Used by the route layer when the caller does not pin an explicit
    ``org_id`` — we either return the (single) tutor org or surface an
    ambiguity error.
    """

    account_id = (account_id or "").strip()
    if not account_id:
        return []
    with db_connection() as conn:
        init_tutor_extensions(conn)
        rows = conn.execute(
            """
            SELECT o.id, o.name, o.plan_tier, m.role
            FROM organizations o
            JOIN org_members m ON m.org_id = o.id
            WHERE m.account_id = ?
              AND m.status = 'active'
              AND o.status = 'active'
              AND o.plan_tier = ?
              AND m.role IN ('owner', 'tutor')
            ORDER BY o.created_at ASC
            """,
            (account_id, PLAN_TIER_TUTOR),
        ).fetchall()
    return [
        {"id": r["id"], "name": r["name"], "role": r["role"]} for r in rows
    ]


def assert_tutor(org_id: str, account_id: str) -> None:
    """Raise :class:`TutorError` (HTTP 403) if the caller is not a tutor."""

    org_id = (org_id or "").strip()
    if not org_id:
        raise TutorError(
            "tutor_org_required",
            "org_id is required to read tutor data.",
            status_code=400,
        )
    if not is_tutor_for_org(org_id, account_id):
        raise TutorError(
            "tutor_forbidden",
            "Tutor access is required for this organization.",
            status_code=403,
        )


# ---------------------------------------------------------------------------
# Student roster + readiness rollup
# ---------------------------------------------------------------------------


def _readiness_summary(
    conn: sqlite3.Connection, student_id: str
) -> dict[str, Any]:
    """Return a slim readiness summary suitable for the tutor table.

    We strip out the verbose per-skill structure and keep the four
    numbers + four badges that the dashboard renders, so the response
    payload stays compact even for orgs with hundreds of students.
    """

    full = _readiness.compute_readiness(conn, student_id)
    per_skill: dict[str, dict[str, Any]] = {}
    for row in full["skills"]:
        per_skill[row["skill"]] = {
            "avg_score": row["avg_score"],
            "badge": row["badge"],
            "predicted_pass": row["predicted_pass"],
            "sample_size": row["sample_size"],
        }
    return {
        "per_skill": per_skill,
        "overall_pass_predicted": full["overall_pass_predicted"],
        "last_updated": full["last_updated"],
    }


def list_students(org_id: str, *, actor_account_id: str) -> dict[str, Any]:
    """Return the org's students plus their readiness rollup.

    Result shape::

        {
          "org": {"id": "...", "name": "...", "plan_tier": "tutor"},
          "students": [
            {
              "account_id": "...",
              "role": "member",
              "joined_at": "...",
              "readiness": {
                "per_skill": {
                  "listening": {"avg_score": 11.4, "badge": "yellow",
                                "predicted_pass": true, "sample_size": 5},
                  ...
                },
                "overall_pass_predicted": false,
                "last_updated": "..."
              }
            },
            ...
          ],
          "generated_at": "..."
        }

    The students are sorted by ``joined_at`` ascending so the tutor's
    "first cohort" appears at the top. PII columns (email, salt, hash)
    are intentionally omitted.
    """

    assert_tutor(org_id, actor_account_id)

    with db_connection() as conn:
        init_tutor_extensions(conn)
        org_row = conn.execute(
            "SELECT id, name, plan_tier FROM organizations WHERE id = ?",
            (org_id,),
        ).fetchone()
        # ``assert_tutor`` already verified the org exists + is active,
        # but the row may have been deleted between calls — defend.
        if org_row is None:
            raise TutorError(
                "tutor_org_not_found",
                "Organization not found.",
                status_code=404,
            )

        members = conn.execute(
            """
            SELECT id, account_id, role, status, joined_at
            FROM org_members
            WHERE org_id = ?
              AND status = 'active'
              AND role IN ('member', 'student')
            ORDER BY joined_at ASC, id ASC
            """,
            (org_id,),
        ).fetchall()

        students: list[dict[str, Any]] = []
        for row in members:
            account_id = str(row["account_id"])
            students.append(
                {
                    "account_id": account_id,
                    "role": str(row["role"] or "member"),
                    "joined_at": row["joined_at"],
                    "readiness": _readiness_summary(conn, account_id),
                }
            )

    log_event(
        "info",
        "tutor_students_listed",
        org_id=org_id,
        actor_account_id=actor_account_id,
        student_count=len(students),
    )
    return {
        "org": {
            "id": org_row["id"],
            "name": org_row["name"],
            "plan_tier": str(org_row["plan_tier"] or PLAN_TIER_STANDARD),
        },
        "students": students,
        "generated_at": now_iso(),
    }


# ---------------------------------------------------------------------------
# Student report (HTML)
# ---------------------------------------------------------------------------


def get_student_report(
    org_id: str, student_account_id: str, *, actor_account_id: str
) -> dict[str, Any]:
    """Return the readiness payload + roster row for a single student.

    Raises :class:`TutorError` ``tutor_forbidden`` (403) if the caller
    cannot supervise the org, and :class:`TutorError` ``tutor_student_not_found``
    (404) if the student is not an active member of the org. The 404 is
    intentionally returned BEFORE we read any data so we never leak the
    existence of an account_id that is unaffiliated with this org.
    """

    assert_tutor(org_id, actor_account_id)
    student_account_id = (student_account_id or "").strip()
    if not student_account_id:
        raise TutorError(
            "tutor_student_required",
            "student account_id is required.",
            status_code=400,
        )

    with db_connection() as conn:
        init_tutor_extensions(conn)
        org_row = conn.execute(
            "SELECT id, name, plan_tier FROM organizations WHERE id = ?",
            (org_id,),
        ).fetchone()
        if org_row is None:
            raise TutorError(
                "tutor_org_not_found",
                "Organization not found.",
                status_code=404,
            )
        member_row = conn.execute(
            """
            SELECT id, account_id, role, status, joined_at
            FROM org_members
            WHERE org_id = ?
              AND account_id = ?
              AND status = 'active'
              AND role IN ('member', 'student')
            """,
            (org_id, student_account_id),
        ).fetchone()
        if member_row is None:
            raise TutorError(
                "tutor_student_not_found",
                "Student not found in this organization.",
                status_code=404,
            )
        readiness_full = _readiness.compute_readiness(conn, student_account_id)

    log_event(
        "info",
        "tutor_student_report",
        org_id=org_id,
        actor_account_id=actor_account_id,
        student_account_id=student_account_id,
    )
    return {
        "org": {
            "id": org_row["id"],
            "name": org_row["name"],
            "plan_tier": str(org_row["plan_tier"] or PLAN_TIER_STANDARD),
        },
        "student": {
            "account_id": member_row["account_id"],
            "role": str(member_row["role"] or "member"),
            "joined_at": member_row["joined_at"],
        },
        "readiness": readiness_full,
        "generated_at": now_iso(),
    }


def _badge_color(badge: str) -> str:
    """Map a readiness badge to a CSS colour. Pure helper for the HTML."""

    return {
        "green": "#2ea043",
        "yellow": "#d4a72c",
        "red": "#da3633",
    }.get(badge, "#94a3b8")


def build_student_report_html(report: dict[str, Any]) -> str:
    """Render the student report dict as a self-contained HTML page.

    The HTML is hand-built (no Jinja, no template engine) so the route
    has no template-discovery dependency — same approach as
    :mod:`server_app.routes.legal`. All user-supplied strings are
    ``html.escape``-d.
    """

    org = report["org"]
    student = report["student"]
    readiness_payload = report["readiness"]

    org_name = html.escape(str(org.get("name") or ""))
    student_id = html.escape(str(student.get("account_id") or ""))
    joined_at = html.escape(str(student.get("joined_at") or ""))
    overall = (
        "On track to pass"
        if readiness_payload.get("overall_pass_predicted")
        else "Not yet predicted to pass"
    )
    last_updated = html.escape(
        str(readiness_payload.get("last_updated") or "")
    )
    generated_at = html.escape(str(report.get("generated_at") or ""))

    skill_rows: list[str] = []
    for skill_row in readiness_payload.get("skills", []):
        skill = html.escape(str(skill_row.get("skill") or ""))
        avg = skill_row.get("avg_score")
        sample = skill_row.get("sample_size") or 0
        badge = str(skill_row.get("badge") or "red")
        predicted = (
            "Predicted pass"
            if skill_row.get("predicted_pass")
            else "Predicted fail"
        )
        avg_label = (
            f"{float(avg):.1f} / 15" if avg is not None else "— / 15"
        )
        skill_rows.append(
            "<tr>"
            f'<td class="skill">{skill.title()}</td>'
            f'<td class="score">{html.escape(avg_label)}</td>'
            f'<td class="sample">{int(sample)} attempt(s)</td>'
            f'<td><span class="badge" style="background:{_badge_color(badge)}">'
            f"{html.escape(badge.upper())}</span></td>"
            f'<td class="predicted">{html.escape(predicted)}</td>'
            "</tr>"
        )
    skill_rows_html = "".join(skill_rows) or (
        '<tr><td colspan="5">No attempts on record yet.</td></tr>'
    )

    return (
        "<!doctype html>\n"
        "<html lang='en'>\n"
        "<head>\n"
        "<meta charset='utf-8' />\n"
        f"<title>Tutor report — {student_id}</title>\n"
        "<meta name='robots' content='noindex,nofollow' />\n"
        "<style>\n"
        "body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;"
        "margin:24px;color:#1f2328;background:#ffffff;}"
        "h1{margin:0 0 4px;font-size:1.4rem;}"
        ".meta{color:#57606a;font-size:0.85rem;margin-bottom:24px;}"
        "table{width:100%;border-collapse:collapse;margin:16px 0;}"
        "th,td{border-bottom:1px solid #d0d7de;padding:8px 12px;text-align:left;font-size:0.9rem;}"
        "th{background:#f6f8fa;font-weight:600;}"
        ".badge{color:#fff;border-radius:4px;padding:3px 8px;font-size:0.7rem;"
        "font-weight:700;letter-spacing:0.05em;}"
        ".predicted{font-weight:600;}"
        ".overall{padding:8px 12px;border-radius:6px;display:inline-block;"
        "background:#ddf4ff;color:#0969da;font-weight:600;}"
        ".footer{margin-top:32px;font-size:0.75rem;color:#57606a;}"
        "</style>\n"
        "</head>\n"
        "<body>\n"
        f"<h1>Tutor report — {org_name}</h1>\n"
        "<div class='meta'>"
        f"Student account ID: <code>{student_id}</code> &middot; "
        f"Joined: {joined_at}"
        "</div>\n"
        f"<p class='overall'>{html.escape(overall)}</p>\n"
        "<h2>Per-skill A2 readiness</h2>\n"
        "<table>\n"
        "<thead><tr>"
        "<th>Skill</th><th>Rolled-up score</th><th>Sample</th>"
        "<th>Risk</th><th>Prediction</th>"
        "</tr></thead>\n"
        f"<tbody>{skill_rows_html}</tbody>\n"
        "</table>\n"
        f"<p class='meta'>Last updated: {last_updated}</p>\n"
        "<div class='footer'>"
        f"Generated {generated_at} &middot; T-042 tutor dashboard "
        "&middot; PII redacted (only account_id + readiness shown)."
        "</div>\n"
        "</body>\n"
        "</html>\n"
    )


__all__ = [
    "PLAN_TIER_TUTOR",
    "PLAN_TIER_STANDARD",
    "STUDENT_ROLES",
    "TUTOR_ROLES",
    "TutorError",
    "assert_tutor",
    "build_student_report_html",
    "find_orgs_for_tutor",
    "get_student_report",
    "init_tutor_extensions",
    "is_tutor_for_org",
    "list_students",
]
