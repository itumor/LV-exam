"""Smoke tests for scripts/backup_sqlite.sh and scripts/restore_sqlite.sh.

These do not hit Cloudflare R2. They only confirm:
  * --help prints usage and exits 0
  * --dry-run executes the planning path and exits 0 without requiring secrets
  * restore_sqlite.sh rejects malformed argument counts

T-013 / BUSINESS_REPORT.md sec 9.2 #2 + App.A #8.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKUP_SCRIPT = ROOT / "scripts" / "backup_sqlite.sh"
RESTORE_SCRIPT = ROOT / "scripts" / "restore_sqlite.sh"
CRON_SCRIPT = ROOT / "docker" / "cron-backup.sh"


def _has_bash() -> bool:
    return shutil.which("bash") is not None


@unittest.skipUnless(_has_bash(), "bash not available")
class BackupScriptTests(unittest.TestCase):
    """The shell scripts must parse args and run dry-run without secrets."""

    def test_backup_script_exists_and_is_executable(self) -> None:
        self.assertTrue(BACKUP_SCRIPT.exists(), f"{BACKUP_SCRIPT} missing")
        mode = BACKUP_SCRIPT.stat().st_mode
        self.assertTrue(
            mode & stat.S_IXUSR,
            f"{BACKUP_SCRIPT} should be executable (chmod +x)",
        )

    def test_restore_script_exists_and_is_executable(self) -> None:
        self.assertTrue(RESTORE_SCRIPT.exists(), f"{RESTORE_SCRIPT} missing")
        mode = RESTORE_SCRIPT.stat().st_mode
        self.assertTrue(
            mode & stat.S_IXUSR,
            f"{RESTORE_SCRIPT} should be executable (chmod +x)",
        )

    def test_cron_script_exists_and_is_executable(self) -> None:
        self.assertTrue(CRON_SCRIPT.exists(), f"{CRON_SCRIPT} missing")
        mode = CRON_SCRIPT.stat().st_mode
        self.assertTrue(
            mode & stat.S_IXUSR,
            f"{CRON_SCRIPT} should be executable (chmod +x)",
        )

    def test_backup_help(self) -> None:
        result = subprocess.run(
            ["bash", str(BACKUP_SCRIPT), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("backup_sqlite.sh", result.stdout)
        self.assertIn("R2_BUCKET", result.stdout)

    def test_backup_unknown_arg_rejected(self) -> None:
        result = subprocess.run(
            ["bash", str(BACKUP_SCRIPT), "--definitely-not-a-flag"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown argument", result.stderr)

    def test_backup_dry_run_without_secrets(self) -> None:
        # Wipe any inherited R2 env so we prove --dry-run does not require them.
        env = {k: v for k, v in os.environ.items() if not k.startswith("R2_")}
        env.setdefault("PATH", os.environ.get("PATH", ""))
        result = subprocess.run(
            ["bash", str(BACKUP_SCRIPT), "--dry-run"],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("dry-run", result.stdout)
        self.assertIn("would upload", result.stdout)

    def test_restore_help(self) -> None:
        result = subprocess.run(
            ["bash", str(RESTORE_SCRIPT), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("--list", result.stdout)
        self.assertIn("--fetch", result.stdout)
        self.assertIn("--latest", result.stdout)

    def test_restore_no_args_fails_with_usage(self) -> None:
        result = subprocess.run(
            ["bash", str(RESTORE_SCRIPT)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Usage", result.stderr)

    def test_restore_fetch_requires_two_positional_args(self) -> None:
        result = subprocess.run(
            ["bash", str(RESTORE_SCRIPT), "--fetch", "only-one"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--fetch requires", result.stderr)


if __name__ == "__main__":
    unittest.main()
