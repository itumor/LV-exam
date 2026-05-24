"""Unit tests for T-030 — A2 readiness dashboard.

Covers the deliverables called out in the T-030 brief:

* Empty history → all four skills surface ``red`` badge,
  ``predicted_pass=False``, ``sample_size=0`` and
  ``overall_pass_predicted=False``.
* All-skills-passing → ``green`` badge per skill,
  ``overall_pass_predicted=True``.
* One skill failing (below 9/15) → that skill ``red``, others ``green``;
  ``overall_pass_predicted=False`` (the 9/15-per-skill rule from
  :mod:`server_app.services.schema_a2`).
* Recency weighting → a streak of recent passes after older fails lifts
  the rolled-up average above the 9/15 threshold even though the
  unweighted mean would still be below.
* ``GET /api/readiness`` route serves the payload to an authenticated
  learner and returns 401 to anonymous callers.
* The route is listed in the modularised ``attempts.ROUTES`` audit list.
"""

from __future__ import annotations

import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import server  # noqa: F401 — runs hook installation side effects
from server_app.services import readiness, schema_a2


# ---------------------------------------------------------------------------
# Helpers — seed accounts + exam_attempt_category_score rows.
# ---------------------------------------------------------------------------


def _seed_account(account_id: str, email: str) -> None:
    with server.db_connection() as conn:
        conn.execute(
            """
            INSERT INTO accounts (id, email, password_salt, password_hash,
                                  status, created_at, deleted_at)
            VALUES (?, ?, 'salt', 'hash', 'active',
                    '2026-05-23T00:00:00Z', NULL)
            """,
            (account_id, email),
        )


def _seed_score(
    *,
    account_id: str,
    attempt_id: str,
    skill: str,
    score: int,
    created_at: str,
) -> None:
    """Insert one (attempt, skill) score row.

    The dashboard reads exclusively from ``exam_attempt_category_score``
    so we do not need to bother building a full attempts row for these
    tests — that's also why we ``INSERT OR IGNORE`` the parent attempts
    row (the FK is enforced by sqlite).
    """

    with server.db_connection() as conn:
        # Parent attempt row — minimum viable fields, FK satisfaction.
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
            INSERT INTO exam_attempt_category_score
            (id, attempt_id, account_id, category, score_0_to_15,
             passed_boolean, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"eacs_{attempt_id}_{skill}",
                attempt_id,
                account_id,
                skill,
                int(score),
                1 if score >= schema_a2.A2_MIN_PER_SKILL else 0,
                created_at,
            ),
        )


def _badges_by_skill(payload: dict) -> dict[str, str]:
    return {row["skill"]: row["badge"] for row in payload["skills"]}


def _avgs_by_skill(payload: dict) -> dict[str, float | None]:
    return {row["skill"]: row["avg_score"] for row in payload["skills"]}


# ---------------------------------------------------------------------------
# Service-level tests — pure logic, no HTTP plumbing.
# ---------------------------------------------------------------------------


class ReadinessServiceTests(unittest.TestCase):
    """Direct tests of ``server_app.services.readiness.compute_readiness``."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "auth.sqlite3"
        self.auth_db_patch = patch.object(server, "AUTH_DB_PATH", self.db_path)
        self.auth_db_patch.start()
        server.init_auth_store()
        _seed_account("acct_alice", "alice@example.test")

    def tearDown(self) -> None:
        self.auth_db_patch.stop()
        self.tmpdir.cleanup()

    # ------------------------------------------------------------------
    # Empty history.
    # ------------------------------------------------------------------

    def test_empty_history_returns_red_for_every_skill(self) -> None:
        with server.db_connection() as conn:
            payload = readiness.compute_readiness(conn, "acct_alice")
        self.assertEqual(
            [row["skill"] for row in payload["skills"]],
            list(schema_a2.A2_SKILLS),
            "skills must appear in canonical order",
        )
        for row in payload["skills"]:
            self.assertEqual(row["badge"], readiness.BADGE_RED)
            self.assertFalse(row["predicted_pass"])
            self.assertEqual(row["sample_size"], 0)
            self.assertIsNone(row["avg_score"])
        self.assertFalse(payload["overall_pass_predicted"])
        self.assertIn("last_updated", payload)
        self.assertTrue(payload["last_updated"].endswith("Z"))

    def test_unauthenticated_account_id_returns_skeleton(self) -> None:
        with server.db_connection() as conn:
            payload = readiness.compute_readiness(conn, "")
        for row in payload["skills"]:
            self.assertEqual(row["badge"], readiness.BADGE_RED)
            self.assertEqual(row["sample_size"], 0)
        self.assertFalse(payload["overall_pass_predicted"])

    # ------------------------------------------------------------------
    # All four skills above threshold.
    # ------------------------------------------------------------------

    def test_all_skills_passing_returns_green(self) -> None:
        # Three attempts per skill, all comfortably above 12 → green.
        for idx, ts in enumerate(
            ("2026-05-20T00:00:00Z",
             "2026-05-21T00:00:00Z",
             "2026-05-22T00:00:00Z"),
        ):
            for skill in schema_a2.A2_SKILLS:
                _seed_score(
                    account_id="acct_alice",
                    attempt_id=f"att_{idx}_{skill}",
                    skill=skill,
                    score=13,
                    created_at=ts,
                )

        with server.db_connection() as conn:
            payload = readiness.compute_readiness(conn, "acct_alice")
        badges = _badges_by_skill(payload)
        for skill in schema_a2.A2_SKILLS:
            self.assertEqual(badges[skill], readiness.BADGE_GREEN, skill)
        avgs = _avgs_by_skill(payload)
        for skill in schema_a2.A2_SKILLS:
            self.assertEqual(avgs[skill], 13.0, skill)
        self.assertTrue(payload["overall_pass_predicted"])
        for row in payload["skills"]:
            self.assertTrue(row["predicted_pass"])
            self.assertEqual(row["sample_size"], 3)

    # ------------------------------------------------------------------
    # One skill below threshold.
    # ------------------------------------------------------------------

    def test_one_skill_failing_blocks_overall_pass(self) -> None:
        # Listening: 7 (below 9), the rest: 13.
        for ts in ("2026-05-20T00:00:00Z", "2026-05-21T00:00:00Z"):
            for skill, score in (
                ("listening", 7),
                ("reading", 13),
                ("writing", 13),
                ("speaking", 13),
            ):
                _seed_score(
                    account_id="acct_alice",
                    attempt_id=f"att_{ts}_{skill}",
                    skill=skill,
                    score=score,
                    created_at=ts,
                )

        with server.db_connection() as conn:
            payload = readiness.compute_readiness(conn, "acct_alice")
        badges = _badges_by_skill(payload)
        self.assertEqual(badges["listening"], readiness.BADGE_RED)
        self.assertEqual(badges["reading"], readiness.BADGE_GREEN)
        self.assertEqual(badges["writing"], readiness.BADGE_GREEN)
        self.assertEqual(badges["speaking"], readiness.BADGE_GREEN)
        self.assertFalse(payload["overall_pass_predicted"])
        # The failing skill must explicitly carry predicted_pass=False
        # — the dashboard uses this to drive the "needs work" CTA.
        failing = next(
            row for row in payload["skills"] if row["skill"] == "listening"
        )
        self.assertFalse(failing["predicted_pass"])
        self.assertEqual(failing["avg_score"], 7.0)

    def test_borderline_skill_returns_yellow_badge(self) -> None:
        # All four skills at 10 — just above 9 but below 12 → yellow.
        for ts in ("2026-05-20T00:00:00Z", "2026-05-21T00:00:00Z"):
            for skill in schema_a2.A2_SKILLS:
                _seed_score(
                    account_id="acct_alice",
                    attempt_id=f"att_{ts}_{skill}",
                    skill=skill,
                    score=10,
                    created_at=ts,
                )
        with server.db_connection() as conn:
            payload = readiness.compute_readiness(conn, "acct_alice")
        badges = _badges_by_skill(payload)
        for skill in schema_a2.A2_SKILLS:
            self.assertEqual(badges[skill], readiness.BADGE_YELLOW, skill)
        # 10 ≥ 9 → predicted_pass True per-skill, so overall True.
        self.assertTrue(payload["overall_pass_predicted"])

    # ------------------------------------------------------------------
    # Recency weighting.
    # ------------------------------------------------------------------

    def test_recent_passes_lift_rolled_up_average_above_threshold(self) -> None:
        # Older fails: 5, 5, 5. Recent passes: 13, 13, 13.
        # Unweighted mean = 9.0 (exactly at threshold), but weighted
        # mean must come out higher — recent values get bigger weights.
        timeline = (
            ("2026-05-15T00:00:00Z", 5),
            ("2026-05-16T00:00:00Z", 5),
            ("2026-05-17T00:00:00Z", 5),
            ("2026-05-20T00:00:00Z", 13),
            ("2026-05-21T00:00:00Z", 13),
            ("2026-05-22T00:00:00Z", 13),
        )
        for idx, (ts, score) in enumerate(timeline):
            _seed_score(
                account_id="acct_alice",
                attempt_id=f"att_recency_{idx}",
                skill="listening",
                score=score,
                created_at=ts,
            )

        with server.db_connection() as conn:
            payload = readiness.compute_readiness(conn, "acct_alice")
        listening = next(
            row for row in payload["skills"] if row["skill"] == "listening"
        )
        # Weighted average (newest first, weights 6..1):
        # (13*6 + 13*5 + 13*4 + 5*3 + 5*2 + 5*1) / 21
        # = (78 + 65 + 52 + 15 + 10 + 5) / 21
        # = 225 / 21
        # ≈ 10.7  → above 9 (predicted_pass=True) but below 12 (yellow).
        self.assertEqual(listening["avg_score"], 10.7)
        self.assertEqual(listening["badge"], readiness.BADGE_YELLOW)
        self.assertTrue(listening["predicted_pass"])
        self.assertEqual(listening["sample_size"], 6)

    def test_recent_fails_drag_rolled_up_average_below_threshold(self) -> None:
        # Older passes (13s), recent fails (3s) — symmetrical to the
        # previous test. The recent fails MUST drag the weighted mean
        # below 9 even though the unweighted mean is at threshold.
        timeline = (
            ("2026-05-15T00:00:00Z", 13),
            ("2026-05-16T00:00:00Z", 13),
            ("2026-05-17T00:00:00Z", 13),
            ("2026-05-20T00:00:00Z", 3),
            ("2026-05-21T00:00:00Z", 3),
            ("2026-05-22T00:00:00Z", 3),
        )
        for idx, (ts, score) in enumerate(timeline):
            _seed_score(
                account_id="acct_alice",
                attempt_id=f"att_drag_{idx}",
                skill="reading",
                score=score,
                created_at=ts,
            )

        with server.db_connection() as conn:
            payload = readiness.compute_readiness(conn, "acct_alice")
        reading = next(
            row for row in payload["skills"] if row["skill"] == "reading"
        )
        # Newest-first weights: (3*6 + 3*5 + 3*4 + 13*3 + 13*2 + 13*1) / 21
        # = (18 + 15 + 12 + 39 + 26 + 13) / 21
        # = 123 / 21
        # ≈ 5.9 — well below the 9 threshold.
        self.assertEqual(reading["avg_score"], 5.9)
        self.assertEqual(reading["badge"], readiness.BADGE_RED)
        self.assertFalse(reading["predicted_pass"])

    def test_only_last_ten_attempts_are_considered(self) -> None:
        # Twelve attempts on listening: the oldest two are 15s (would
        # otherwise pull the average UP), and the most recent ten are
        # 6s. After windowing the rolled-up score must be 6.0, not the
        # full-history weighted mean.
        for idx in range(2):
            _seed_score(
                account_id="acct_alice",
                attempt_id=f"att_old_{idx}",
                skill="listening",
                score=15,
                created_at=f"2026-04-{idx + 1:02d}T00:00:00Z",
            )
        for idx in range(10):
            _seed_score(
                account_id="acct_alice",
                attempt_id=f"att_recent_{idx}",
                skill="listening",
                score=6,
                created_at=f"2026-05-{idx + 1:02d}T00:00:00Z",
            )
        with server.db_connection() as conn:
            payload = readiness.compute_readiness(conn, "acct_alice")
        listening = next(
            row for row in payload["skills"] if row["skill"] == "listening"
        )
        self.assertEqual(listening["avg_score"], 6.0)
        self.assertEqual(listening["badge"], readiness.BADGE_RED)
        self.assertEqual(listening["sample_size"], 10)

    # ------------------------------------------------------------------
    # last_updated override.
    # ------------------------------------------------------------------

    def test_now_iso_override(self) -> None:
        with server.db_connection() as conn:
            payload = readiness.compute_readiness(
                conn, "acct_alice", now_iso="2026-05-24T07:48:00Z"
            )
        self.assertEqual(payload["last_updated"], "2026-05-24T07:48:00Z")


# ---------------------------------------------------------------------------
# Pure-helper tests (no DB).
# ---------------------------------------------------------------------------


class ReadinessHelperTests(unittest.TestCase):
    """Unit tests for ``classify_badge`` and ``weighted_average``."""

    def test_classify_badge_at_thresholds(self) -> None:
        # 12 → green (≥12 is the comfortable-pass threshold).
        self.assertEqual(
            readiness.classify_badge(12.0, sample_size=1),
            readiness.BADGE_GREEN,
        )
        # 11.99 → yellow.
        self.assertEqual(
            readiness.classify_badge(11.99, sample_size=1),
            readiness.BADGE_YELLOW,
        )
        # 9 → yellow (the 9/15 pass rule is inclusive).
        self.assertEqual(
            readiness.classify_badge(9.0, sample_size=1),
            readiness.BADGE_YELLOW,
        )
        # 8.99 → red.
        self.assertEqual(
            readiness.classify_badge(8.99, sample_size=1),
            readiness.BADGE_RED,
        )

    def test_classify_badge_no_samples_is_red(self) -> None:
        self.assertEqual(
            readiness.classify_badge(15.0, sample_size=0),
            readiness.BADGE_RED,
        )
        self.assertEqual(
            readiness.classify_badge(None, sample_size=5),
            readiness.BADGE_RED,
        )

    def test_weighted_average_empty_returns_none(self) -> None:
        self.assertIsNone(readiness.weighted_average([]))

    def test_weighted_average_single_value(self) -> None:
        self.assertEqual(readiness.weighted_average([12.0]), 12.0)

    def test_weighted_average_linear_weights(self) -> None:
        # newest-first: [10, 5] → (10*2 + 5*1) / 3 = 25/3 ≈ 8.333…
        result = readiness.weighted_average([10, 5])
        assert result is not None
        self.assertAlmostEqual(result, 25 / 3, places=4)

    def test_weighted_average_equal_values_returns_that_value(self) -> None:
        self.assertEqual(readiness.weighted_average([9, 9, 9, 9]), 9.0)


# ---------------------------------------------------------------------------
# HTTP route tests (T-030 hook on AppHandler).
# ---------------------------------------------------------------------------


class _StubHandler:
    """Minimal AppHandler stand-in that records the response."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.command = "GET"
        # Required by the T-015 rate-limit hook.
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

    def body_json(self) -> dict:
        raw = self.wfile.getvalue().decode("utf-8")
        if not raw:
            return {}
        return json.loads(raw)


def _learner_session(account_id: str = "acct_alice") -> dict:
    return {
        "account": {
            "id": account_id,
            "email": "alice@example.test",
            "status": "active",
            "role": "user",
            "created_at": "2026-05-05T00:00:00Z",
            "deleted_at": None,
        }
    }


class ReadinessRouteTests(unittest.TestCase):
    """End-to-end tests of the T-030 ``GET /api/readiness`` hook."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "auth.sqlite3"
        self.auth_db_patch = patch.object(server, "AUTH_DB_PATH", self.db_path)
        self.auth_db_patch.start()
        server.init_auth_store()
        _seed_account("acct_alice", "alice@example.test")

    def tearDown(self) -> None:
        self.auth_db_patch.stop()
        self.tmpdir.cleanup()

    def test_readiness_route_returns_skeleton_for_new_learner(self) -> None:
        handler = _StubHandler("/api/readiness")
        with patch.object(
            server, "require_session", return_value=_learner_session()
        ):
            server.AppHandler.do_GET(handler)  # type: ignore[arg-type]
        self.assertEqual(handler.get_status(), 200)
        payload = handler.body_json()
        self.assertEqual(
            [row["skill"] for row in payload["skills"]],
            list(schema_a2.A2_SKILLS),
        )
        for row in payload["skills"]:
            self.assertEqual(row["badge"], readiness.BADGE_RED)
            self.assertEqual(row["sample_size"], 0)
        self.assertFalse(payload["overall_pass_predicted"])
        self.assertIn("last_updated", payload)

    def test_readiness_route_returns_real_scores_for_learner_with_history(
        self,
    ) -> None:
        # Seed one passing attempt per skill so the rollup is green.
        for skill in schema_a2.A2_SKILLS:
            _seed_score(
                account_id="acct_alice",
                attempt_id=f"att_route_{skill}",
                skill=skill,
                score=14,
                created_at="2026-05-22T00:00:00Z",
            )
        handler = _StubHandler("/api/readiness")
        with patch.object(
            server, "require_session", return_value=_learner_session()
        ):
            server.AppHandler.do_GET(handler)  # type: ignore[arg-type]
        self.assertEqual(handler.get_status(), 200)
        payload = handler.body_json()
        for row in payload["skills"]:
            self.assertEqual(row["badge"], readiness.BADGE_GREEN)
            self.assertEqual(row["avg_score"], 14.0)
            self.assertTrue(row["predicted_pass"])
        self.assertTrue(payload["overall_pass_predicted"])

    def test_readiness_route_rejects_anonymous_caller(self) -> None:
        handler = _StubHandler("/api/readiness")
        with patch.object(
            server,
            "require_session",
            side_effect=PermissionError("login required"),
        ):
            server.AppHandler.do_GET(handler)  # type: ignore[arg-type]
        self.assertEqual(handler.get_status(), 401)

    def test_readiness_route_is_documented_in_routes_audit_list(self) -> None:
        from server_app.routes import attempts as attempts_routes
        self.assertIn(("GET", "/api/readiness"), attempts_routes.ROUTES)


if __name__ == "__main__":
    unittest.main()
