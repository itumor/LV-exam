"""Unit tests for the T-070-final SOC 2 evidence-automation package.

Covers:

1. ``compliance.soc2.automation.ci_runs.collect`` with a mocked ``gh``
   runner — verifies the workflow summary shape, the
   ``required_workflows_missing`` flag, and the "last failure"
   selection logic.
2. ``compliance.soc2.automation.backup_drills.collect`` — verifies
   that an absent R2 lister keeps the collector usable, that a fresh
   snapshot under 9h doesn't fire the stale flag, and that the
   `procedure_last_review` parser pulls the date from the procedure
   doc header.
3. ``compliance.soc2.automation.access_audit.collect`` with an
   in-memory SQLite ``audit_events`` table — verifies joiner/leaver/
   failed-login bucketing and that no raw payloads leak into the
   output.
4. ``compliance.soc2.automation.orchestrator.collect_all`` — writes a
   manifest + per-collector JSON under a tmp evidence root.
5. ``scripts.soc2_preflight.run_preflight`` — fails when an artifact is
   missing, passes against the live repo, and respects the
   ``--require-recent-evidence-days`` knob.
6. ``compliance/soc2/evidence-matrix.md`` completeness — every TSC
   listed in the matrix must reference at least one concrete artifact
   path or task ID.

The tests run under ``python -m unittest`` with no extra deps so they
fit the existing CI matrix.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from compliance.soc2.automation import (  # noqa: E402
    access_audit,
    backup_drills,
    ci_runs,
    orchestrator,
)
from scripts import soc2_preflight  # noqa: E402


_FIXED_NOW = datetime(2026, 5, 24, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# ci_runs
# ---------------------------------------------------------------------------


class CiRunsCollectorTests(unittest.TestCase):
    def _runner(self, payload: list[dict[str, object]]):
        encoded = json.dumps(payload)

        def runner(_args: list[str]) -> str:
            return encoded

        return runner

    def test_collect_aggregates_per_workflow(self) -> None:
        runner = self._runner(
            [
                {
                    "name": "CI — PR",
                    "conclusion": "success",
                    "headSha": "aaa",
                    "url": "https://gh/run/1",
                    "createdAt": "2026-05-22T10:00:00Z",
                },
                {
                    "name": "CI — PR",
                    "conclusion": "failure",
                    "headSha": "bbb",
                    "url": "https://gh/run/2",
                    "createdAt": "2026-05-22T11:00:00Z",
                },
                {
                    "name": "Backup restore drill",
                    "conclusion": "success",
                    "headSha": "ccc",
                    "url": "https://gh/run/3",
                    "createdAt": "2026-05-22T12:00:00Z",
                },
            ]
        )
        result = ci_runs.collect(
            repo="org/repo",
            days=7,
            branches=("main",),
            now=_FIXED_NOW,
            runner=runner,
        )
        # 3 entries in the fake payload, one branch only.
        self.assertEqual(result["total_runs"], 3)
        self.assertEqual(result["workflows"]["CI — PR"]["total"], 2)
        self.assertEqual(result["workflows"]["CI — PR"]["success"], 1)
        self.assertEqual(result["workflows"]["CI — PR"]["failure"], 1)
        self.assertEqual(
            result["workflows"]["CI — PR"]["last_failure"]["sha"], "bbb"
        )
        self.assertIn("CI — PR", result["required_workflows_seen"])
        self.assertIn("Backup restore drill", result["required_workflows_seen"])
        # CI — develop and CI — release weren't in the fake payload.
        self.assertIn("CI — develop", result["required_workflows_missing"])

    def test_collect_handles_empty_payload(self) -> None:
        runner = self._runner([])
        result = ci_runs.collect(
            repo="org/repo",
            days=7,
            branches=("develop",),
            now=_FIXED_NOW,
            runner=runner,
        )
        self.assertEqual(result["total_runs"], 0)
        self.assertEqual(result["workflows"], {})
        self.assertEqual(result["required_workflows_seen"], [])
        self.assertEqual(
            list(result["required_workflows_missing"]),
            list(ci_runs.REQUIRED_WORKFLOWS),
        )

    def test_collect_requires_repo(self) -> None:
        # In CI the GITHUB_REPOSITORY env var is set by the runner, which
        # would otherwise satisfy the fallback chain inside ``collect``.
        # Clear it so we can assert the explicit "no repo" path raises.
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GITHUB_REPOSITORY", None)
            with self.assertRaises(ci_runs.CIRunsCollectorError):
                ci_runs.collect(
                    repo=None, now=_FIXED_NOW, runner=self._runner([])
                )


# ---------------------------------------------------------------------------
# backup_drills
# ---------------------------------------------------------------------------


class BackupDrillCollectorTests(unittest.TestCase):
    def _runner(self, payload: list[dict[str, object]]):
        encoded = json.dumps(payload)
        return lambda _args: encoded

    def test_collect_with_no_r2_lister(self) -> None:
        runner = self._runner(
            [
                {
                    "name": "Backup restore drill",
                    "conclusion": "success",
                    "headSha": "ccc",
                    "url": "https://gh/run/3",
                    "createdAt": "2026-05-19T03:00:00Z",
                },
            ]
        )
        with TemporaryDirectory() as tmp:
            proc = Path(tmp) / "procedure-backup-restore.md"
            proc.write_text(
                "| **Last review** | 2026-04-15 |\n",
                encoding="utf-8",
            )
            result = backup_drills.collect(
                repo="org/repo",
                days=90,
                now=_FIXED_NOW,
                runner=runner,
                r2_lister=None,
                procedure_path=proc,
            )
        self.assertEqual(result["drill_total"], 1)
        self.assertEqual(result["drill_success"], 1)
        self.assertEqual(result["drill_success_rate"], 1.0)
        self.assertEqual(result["procedure_last_review"], "2026-04-15")
        self.assertFalse(result["r2_lister_present"])
        self.assertIsNone(result["r2_object_count"])

    def test_collect_with_fresh_r2_snapshot(self) -> None:
        runner = self._runner([])
        fresh = (_FIXED_NOW - timedelta(hours=4)).isoformat()
        stale = (_FIXED_NOW - timedelta(hours=48)).isoformat()
        result = backup_drills.collect(
            repo="org/repo",
            days=90,
            now=_FIXED_NOW,
            runner=runner,
            r2_lister=lambda: [
                {"key": "snap-1", "lastModified": stale},
                {"key": "snap-2", "lastModified": fresh},
            ],
            procedure_path=Path("/nonexistent"),
        )
        self.assertEqual(result["r2_object_count"], 2)
        self.assertLessEqual(result["r2_latest_object_age_hours"], 4.5)
        self.assertFalse(result["r2_stale_snapshot"])
        self.assertIsNone(result["procedure_last_review"])

    def test_collect_marks_stale_when_oldest_only(self) -> None:
        stale = (_FIXED_NOW - timedelta(hours=48)).isoformat()
        result = backup_drills.collect(
            repo="org/repo",
            days=90,
            now=_FIXED_NOW,
            runner=self._runner([]),
            r2_lister=lambda: [
                {"key": "snap-stale", "lastModified": stale},
            ],
            procedure_path=Path("/nonexistent"),
        )
        self.assertTrue(result["r2_stale_snapshot"])


# ---------------------------------------------------------------------------
# access_audit
# ---------------------------------------------------------------------------


class AccessAuditCollectorTests(unittest.TestCase):
    def _make_db(self, rows: list[tuple[str, str, str | None]]) -> sqlite3.Connection:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            "CREATE TABLE audit_events("
            "id TEXT, org_id TEXT, account_id TEXT, event TEXT, "
            "occurred_at TEXT, source_ip TEXT, user_agent TEXT, "
            "payload_json TEXT)"
        )
        for i, (event, occurred_at, actor) in enumerate(rows):
            conn.execute(
                "INSERT INTO audit_events VALUES(?,?,?,?,?,?,?,?)",
                (
                    f"ae_{i}",
                    "org_test",
                    actor,
                    event,
                    occurred_at,
                    "",
                    "",
                    json.dumps({"secret": "must-not-leak"}),
                ),
            )
        conn.commit()
        return conn

    def test_collect_aggregates_and_redacts(self) -> None:
        rows = [
            ("account.created", "2026-05-20T10:00:00Z", "acct_a"),
            ("account.created", "2026-05-21T10:00:00Z", "acct_b"),
            ("account.deleted", "2026-05-22T10:00:00Z", "acct_a"),
            ("login.failure", "2026-05-22T11:00:00Z", "acct_b"),
            ("login.failure", "2026-05-22T12:00:00Z", "acct_c"),
            # Older than window — must be excluded.
            ("login.failure", "2025-01-01T00:00:00Z", "acct_z"),
        ]
        conn = self._make_db(rows)

        result = access_audit.collect(
            connect=lambda: conn,
            days=30,
            now=_FIXED_NOW,
        )
        self.assertTrue(result["table_present"])
        self.assertEqual(result["joiner_count"], 2)
        self.assertEqual(result["leaver_count"], 1)
        self.assertEqual(result["failed_login_count"], 2)
        # acct_a appears as joiner + leaver but is one actor.
        self.assertEqual(result["unique_actor_count"], 3)
        # The full event types map should have deterministic order.
        self.assertEqual(
            list(result["events_by_type"].keys()),
            sorted(result["events_by_type"].keys()),
        )
        # Crucially: no payload_json leaks anywhere.
        serialised = json.dumps(result)
        self.assertNotIn("must-not-leak", serialised)
        self.assertNotIn("payload", serialised)

    def test_collect_when_table_missing(self) -> None:
        conn = sqlite3.connect(":memory:")
        result = access_audit.collect(
            connect=lambda: conn,
            days=30,
            now=_FIXED_NOW,
        )
        self.assertFalse(result["table_present"])
        self.assertEqual(result["joiner_count"], 0)
        self.assertEqual(result["events_by_type"], {})


# ---------------------------------------------------------------------------
# orchestrator
# ---------------------------------------------------------------------------


class OrchestratorTests(unittest.TestCase):
    def test_collect_all_writes_manifest_and_per_collector_files(self) -> None:
        runner_payload = json.dumps(
            [
                {
                    "name": "CI — PR",
                    "conclusion": "success",
                    "headSha": "x",
                    "url": "u",
                    "createdAt": "2026-05-20T00:00:00Z",
                }
            ]
        )

        def runner(_args: list[str]) -> str:
            return runner_payload

        def db_connect() -> sqlite3.Connection:
            conn = sqlite3.connect(":memory:")
            conn.row_factory = sqlite3.Row
            return conn

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = orchestrator.collect_all(
                out_dir=root,
                now=_FIXED_NOW,
                repo="org/repo",
                runner=runner,
                r2_lister=lambda: [],
                db_connect=db_connect,
            )
            iso_week = _FIXED_NOW.isocalendar()
            week_name = f"{iso_week.year:04d}-W{iso_week.week:02d}"
            week_dir = root / week_name
            self.assertTrue(week_dir.exists())
            self.assertEqual(manifest["error_count"], 0)
            self.assertEqual(manifest["ok_count"], 3)
            for name in ("ci_runs", "backup_drills", "access_audit"):
                self.assertTrue((week_dir / f"{name}.json").exists(), name)
            payload = json.loads((week_dir / "ci_runs.json").read_text())
            # Default branches = (develop, main), runner returns the same
            # payload for each → 2 runs total.
            self.assertEqual(payload["total_runs"], 2)

    def test_collect_all_records_collector_failure_without_aborting(self) -> None:
        def runner(_args: list[str]) -> str:
            raise RuntimeError("gh down")

        def db_connect() -> sqlite3.Connection:
            conn = sqlite3.connect(":memory:")
            conn.row_factory = sqlite3.Row
            return conn

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = orchestrator.collect_all(
                out_dir=root,
                now=_FIXED_NOW,
                repo="org/repo",
                runner=runner,
                r2_lister=None,
                db_connect=db_connect,
            )
            # Two collectors depend on the gh runner; access_audit should
            # still succeed against the empty in-memory DB.
            self.assertEqual(manifest["error_count"], 2)
            self.assertEqual(manifest["ok_count"], 1)
            self.assertEqual(
                manifest["collectors"]["access_audit"]["status"], "ok"
            )
            self.assertEqual(
                manifest["collectors"]["ci_runs"]["status"], "error"
            )


# ---------------------------------------------------------------------------
# soc2_preflight
# ---------------------------------------------------------------------------


class PreflightGateTests(unittest.TestCase):
    def test_live_repo_passes(self) -> None:
        report = soc2_preflight.run_preflight(repo_root=_REPO_ROOT)
        self.assertTrue(
            report.ok,
            f"unexpected findings: {[f.detail for f in report.findings]}",
        )
        self.assertGreater(report.checked, 15)

    def test_missing_artifact_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            fake_root = Path(tmp)
            report = soc2_preflight.run_preflight(
                repo_root=fake_root,
                evidence_root=fake_root / "evidence",
                artifacts=[
                    soc2_preflight.RequiredArtifact(
                        "does/not/exist.md", "Test", ("CC1.1",)
                    ),
                ],
            )
            self.assertFalse(report.ok)
            self.assertEqual(report.findings[0].kind, "missing")
            self.assertEqual(report.findings[0].artifact.path, "does/not/exist.md")

    def test_require_recent_evidence_fails_when_empty(self) -> None:
        with TemporaryDirectory() as tmp:
            fake_root = Path(tmp)
            (fake_root / "compliance/soc2/evidence").mkdir(parents=True)
            report = soc2_preflight.run_preflight(
                repo_root=fake_root,
                evidence_root=fake_root / "compliance/soc2/evidence",
                artifacts=[],
                require_recent_evidence_days=14,
            )
            self.assertFalse(report.ok)
            self.assertEqual(report.findings[0].kind, "missing")

    def test_cli_returns_nonzero_on_missing(self) -> None:
        import io
        from contextlib import redirect_stdout

        with TemporaryDirectory() as tmp:
            buf = io.StringIO()
            with redirect_stdout(buf):
                exit_code = soc2_preflight.main(
                    [
                        "--evidence-root",
                        str(Path(tmp) / "nope"),
                        "--require-recent-evidence-days",
                        "7",
                        "--json",
                    ]
                )
            self.assertEqual(exit_code, 1)
            payload = json.loads(buf.getvalue())
            self.assertFalse(payload["ok"])


# ---------------------------------------------------------------------------
# evidence-matrix.md completeness
# ---------------------------------------------------------------------------


class EvidenceMatrixCompletenessTests(unittest.TestCase):
    """Static checks against compliance/soc2/evidence-matrix.md.

    The auditor expects each TSC row to point at *something* concrete —
    either a file path (`.md`, `.py`, `.yaml`, `.yml`, `.sh`, `.json`)
    or a task ID (``T-NNN``). A bare "TODO" or hand-wavy sentence
    fails this test, which keeps the matrix honest as we evolve the
    artifacts.
    """

    EXPECTED_TSCS: tuple[str, ...] = (
        "CC1.1", "CC1.2", "CC1.3", "CC1.4",
        "CC2.1", "CC2.2", "CC2.3",
        "CC3.1", "CC3.2", "CC3.3", "CC3.4",
        "CC4.1", "CC4.2",
        "CC5.1", "CC5.2", "CC5.3",
        "CC6.1", "CC6.2", "CC6.3", "CC6.5", "CC6.6", "CC6.7", "CC6.8",
        "CC7.1", "CC7.2", "CC7.3", "CC7.4", "CC7.5",
        "CC8.1",
        "CC9.1", "CC9.2",
        "A1.1", "A1.2", "A1.3",
        "C1.1", "C1.2",
        "PI1.1", "PI1.2", "PI1.3", "PI1.4", "PI1.5",
    )

    ARTIFACT_RE = re.compile(
        r"(?:`[^`]+\.(?:md|py|yaml|yml|sh|cjs|json|toml)`)"
        r"|(?:T-\d{3})"
    )

    def setUp(self) -> None:
        path = _REPO_ROOT / "compliance/soc2/evidence-matrix.md"
        self.text = path.read_text(encoding="utf-8")
        self.lines = self.text.splitlines()

    def test_every_expected_tsc_has_a_row(self) -> None:
        for tsc in self.EXPECTED_TSCS:
            with self.subTest(tsc=tsc):
                self.assertRegex(
                    self.text,
                    rf"\b{re.escape(tsc)}\b",
                    f"{tsc} missing from evidence matrix",
                )

    def test_each_tsc_row_references_a_concrete_artifact(self) -> None:
        for tsc in self.EXPECTED_TSCS:
            with self.subTest(tsc=tsc):
                row_lines = [
                    line
                    for line in self.lines
                    if line.startswith("|") and tsc in line and "—" in line
                ]
                self.assertTrue(row_lines, f"no table row for {tsc}")
                row = row_lines[0]
                self.assertRegex(
                    row,
                    self.ARTIFACT_RE,
                    f"{tsc} row does not reference a file path or task ID: {row}",
                )

    def test_matrix_documents_automation_pipeline(self) -> None:
        for token in (
            "ci_runs.json",
            "backup_drills.json",
            "access_audit.json",
            "orchestrator.py",
            "soc2_preflight.py",
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.text)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
