"""Smoke tests for scripts/release.sh (task T-019).

We do NOT exercise the destructive paths (branch creation, push, tag, gh).
We only verify:
  - --help exits 0 and prints a usage block.
  - No args prints usage and exits non-zero.
  - Missing required args exits non-zero with a clear error.
  - Invalid --version format is rejected.

The full happy path is covered by manual rehearsal with --dry-run on a real
develop branch, not by this unit test (it would require a fixture git remote
and a working gh CLI, which is overkill for a script-shape smoke).
"""

from __future__ import annotations

import os
import stat
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "release.sh"


class ReleaseScriptSmokeTests(unittest.TestCase):
    """End-to-end shape tests for scripts/release.sh."""

    def setUp(self) -> None:
        self.assertTrue(SCRIPT.exists(), f"missing script: {SCRIPT}")
        mode = SCRIPT.stat().st_mode
        self.assertTrue(
            mode & stat.S_IXUSR,
            f"scripts/release.sh must be executable (mode={oct(mode)})",
        )

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(SCRIPT), *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            check=False,
        )

    def test_help_exits_zero_and_prints_usage(self) -> None:
        result = self._run("--help")
        self.assertEqual(
            result.returncode,
            0,
            f"--help should exit 0; got {result.returncode}\nstderr={result.stderr}",
        )
        self.assertIn("Usage:", result.stdout)
        self.assertIn("--name", result.stdout)
        self.assertIn("--version", result.stdout)
        self.assertIn("--dry-run", result.stdout)

    def test_no_args_prints_usage_and_exits_nonzero(self) -> None:
        result = self._run()
        self.assertNotEqual(
            result.returncode,
            0,
            "release.sh with no args should fail",
        )
        # Usage block is printed before the failure.
        self.assertIn("Usage:", result.stdout)

    def test_missing_version_fails(self) -> None:
        result = self._run("--name", "test")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--version is required", result.stderr)

    def test_missing_name_fails(self) -> None:
        result = self._run("--version", "v0.0.0")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--name is required", result.stderr)

    def test_invalid_version_format_is_rejected(self) -> None:
        result = self._run("--name", "test", "--version", "1.0.0")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("vMAJOR.MINOR.PATCH", result.stderr)

    def test_unknown_argument_is_rejected(self) -> None:
        result = self._run("--bogus")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown argument", result.stderr)


class ReleaseScriptShapeTests(unittest.TestCase):
    """Static checks on the script file itself."""

    def setUp(self) -> None:
        self.body = SCRIPT.read_text(encoding="utf-8")

    def test_uses_set_euo_pipefail(self) -> None:
        self.assertIn("set -euo pipefail", self.body)

    def test_mentions_risk_gates(self) -> None:
        for marker in ("T-011", "T-014", "T-016"):
            self.assertIn(marker, self.body, f"script must reference {marker}")

    def test_references_release_branch_pattern(self) -> None:
        self.assertIn('release/${RELEASE_NAME}', self.body)

    def test_uses_gh_pr_create(self) -> None:
        self.assertIn("gh pr create", self.body)

    def test_has_dry_run_branch(self) -> None:
        self.assertIn("DRY_RUN", self.body)


if __name__ == "__main__":
    unittest.main()
