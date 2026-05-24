"""Weekly SOC 2 evidence orchestrator (T-070-final).

Invoked by ``.github/workflows/soc2-evidence.yml`` on a weekly cron.
The orchestrator:

1. Runs each collector module (``ci_runs``, ``backup_drills``,
   ``access_audit``).
2. Writes the per-collector JSON into
   ``compliance/soc2/evidence/<YYYY-WW>/`` so each weekly run lands in
   its own directory and the auditor can diff week-over-week.
3. Writes a ``manifest.json`` index summarising what was collected and
   whether every collector succeeded (so a failing collector still
   leaves a breadcrumb instead of vanishing).
4. Returns a non-zero exit code only when **every** collector failed,
   so a missing R2 token doesn't block the rest of the evidence from
   landing — this matches the "best-effort weekly snapshot" auditor
   expectation; the hard gate lives in ``scripts/soc2_preflight.py``.

The module exposes ``main(argv=None)`` so it can be invoked both via
``python -m compliance.soc2.automation.orchestrator`` and from the
tests.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from . import access_audit, backup_drills, ci_runs

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_EVIDENCE_ROOT = REPO_ROOT / "compliance" / "soc2" / "evidence"
DEFAULT_DB = REPO_ROOT / "data" / "lvcodex.db"


def _week_dir(now: datetime, root: Path) -> Path:
    iso_year, iso_week, _ = now.isocalendar()
    return root / f"{iso_year:04d}-W{iso_week:02d}"


def _sqlite_connect(path: Path) -> Callable[[], Any]:
    def _factory() -> Any:
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        return conn

    return _factory


def _safe(name: str, fn: Callable[[], Mapping[str, Any]]) -> dict[str, Any]:
    """Run a collector; on any exception return a structured failure."""
    try:
        return {"status": "ok", "data": dict(fn())}
    except Exception as exc:  # noqa: BLE001 - we want the manifest to record it
        return {
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
            "data": None,
        }


def collect_all(
    *,
    out_dir: Path,
    now: datetime | None = None,
    repo: str | None = None,
    ci_days: int = 7,
    drill_days: int = 90,
    access_days: int = 90,
    db_path: Path | None = None,
    runner: Callable[[list[str]], str] | None = None,
    r2_lister: Callable[[], Any] | None = None,
    db_connect: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    """Run every collector and write outputs under ``out_dir/<YYYY-WW>/``."""
    now = now or datetime.now(timezone.utc)
    week_dir = _week_dir(now, out_dir)
    week_dir.mkdir(parents=True, exist_ok=True)

    results: dict[str, dict[str, Any]] = {}
    results["ci_runs"] = _safe(
        "ci_runs",
        lambda: ci_runs.collect(
            repo=repo,
            days=ci_days,
            now=now,
            runner=runner,
        ),
    )
    results["backup_drills"] = _safe(
        "backup_drills",
        lambda: backup_drills.collect(
            repo=repo,
            days=drill_days,
            now=now,
            runner=runner,
            r2_lister=r2_lister,
        ),
    )
    results["access_audit"] = _safe(
        "access_audit",
        lambda: access_audit.collect(
            connect=(
                db_connect
                if db_connect is not None
                else _sqlite_connect(db_path or DEFAULT_DB)
            ),
            days=access_days,
            now=now,
        ),
    )

    written: dict[str, str] = {}
    for name, result in results.items():
        if result["status"] != "ok":
            continue
        target = week_dir / f"{name}.json"
        target.write_text(json.dumps(result["data"], indent=2) + "\n")
        # Best-effort: report path relative to repo root when out_dir is
        # under the repo (the normal case from the GH Actions runner);
        # fall back to the absolute path otherwise (used by unit tests).
        try:
            rel = target.relative_to(REPO_ROOT)
            written[name] = str(rel)
        except ValueError:
            written[name] = str(target)

    manifest = {
        "generated_at": now.isoformat(),
        "iso_week": f"{now.isocalendar().year:04d}-W{now.isocalendar().week:02d}",
        "collectors": {
            name: {
                "status": r["status"],
                "error": r.get("error"),
                "path": written.get(name),
            }
            for name, r in results.items()
        },
        "ok_count": sum(1 for r in results.values() if r["status"] == "ok"),
        "error_count": sum(1 for r in results.values() if r["status"] == "error"),
    }
    (week_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="soc2-evidence",
        description="Collect weekly SOC 2 Type I evidence artifacts.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_EVIDENCE_ROOT,
        help="Root for compliance/soc2/evidence/.",
    )
    parser.add_argument("--repo", default=None, help="owner/name; defaults to $GITHUB_REPOSITORY")
    parser.add_argument("--ci-days", type=int, default=7)
    parser.add_argument("--drill-days", type=int, default=90)
    parser.add_argument("--access-days", type=int, default=90)
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB,
        help="Path to the SQLite DB hosting audit_events.",
    )
    args = parser.parse_args(argv)

    manifest = collect_all(
        out_dir=args.out_dir,
        repo=args.repo,
        ci_days=args.ci_days,
        drill_days=args.drill_days,
        access_days=args.access_days,
        db_path=args.db_path,
    )
    sys.stdout.write(json.dumps(manifest, indent=2) + "\n")
    # Only fail when *every* collector failed.
    return 1 if manifest["ok_count"] == 0 else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
