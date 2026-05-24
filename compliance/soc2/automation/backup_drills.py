"""Backup-drill evidence collector for SOC 2 (T-070-final).

Cross-references three independent sources to produce audit-ready
evidence for **A1.3 / CC7.5** (recovery) and **PI1.5** (stored-data
integrity):

1. GitHub Actions runs of the ``Backup restore drill`` workflow
   (defined in ``.github/workflows/backup-restore-drill.yml``).
2. The R2 bucket listing for the ``backups/`` prefix — used to verify
   that the 6-hourly ``scripts/backup_sqlite.sh`` cron is actually
   producing artifacts. The lister is injected (``r2_lister``) so tests
   don't need AWS creds.
3. The most recent ``procedure-backup-restore.md`` revision date,
   parsed from the document header. This satisfies the auditor
   requirement that the *procedure* be reviewed alongside the *drill*.

Returns a dict with:

* ``last_drill`` — ``{ "createdAt", "conclusion", "url" }`` for the
  most recent run,
* ``drill_success_rate`` — successes / total over the window,
* ``r2_object_count`` — how many snapshots the lister returned,
* ``r2_latest_object_age_hours`` — age (in hours) of the most recent
  snapshot (None when lister returns nothing),
* ``procedure_last_review`` — ISO date parsed from the procedure doc.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from . import ci_runs

# Tolerated maximum age between snapshots. The cron is 6h so any value
# above this triggers a finding for the auditor. Kept slightly above
# 6h to absorb runner queue time without false positives.
MAX_SNAPSHOT_AGE_HOURS = 9
PROCEDURE_PATH = Path("compliance/soc2/procedure-backup-restore.md")

_LAST_REVIEW_RE = re.compile(
    r"^\|\s*\*\*Last review\*\*\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|",
    re.MULTILINE,
)


class BackupDrillCollectorError(RuntimeError):
    """Raised when neither workflow runs nor R2 evidence can be obtained."""


def _drill_runs(
    *,
    repo: str | None,
    days: int,
    now: datetime,
    runner: Any | None,
) -> dict[str, Any]:
    summary = ci_runs.collect(
        repo=repo,
        days=days,
        branches=("main",),
        now=now,
        runner=runner,
    )
    workflows = summary.get("workflows", {})
    drill = workflows.get("Backup restore drill") or {
        "total": 0,
        "success": 0,
        "failure": 0,
    }
    return drill


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        # GitHub returns "...Z" — datetime.fromisoformat needs +00:00
        normalised = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalised)
    except ValueError:
        return None


def _r2_summary(
    *,
    lister: Callable[[], Iterable[Mapping[str, Any]]] | None,
    now: datetime,
) -> dict[str, Any]:
    if lister is None:
        return {
            "r2_object_count": None,
            "r2_latest_object_age_hours": None,
            "r2_stale_snapshot": None,
            "r2_lister_present": False,
        }
    objects = list(lister())
    if not objects:
        return {
            "r2_object_count": 0,
            "r2_latest_object_age_hours": None,
            "r2_stale_snapshot": True,
            "r2_lister_present": True,
        }
    # objects may carry "lastModified" (ISO) or "LastModified" (boto-style).
    def _ts(obj: Mapping[str, Any]) -> datetime | None:
        return _parse_iso(
            obj.get("lastModified") or obj.get("LastModified") or obj.get("modified")
        )

    ages: list[float] = []
    for obj in objects:
        ts = _ts(obj)
        if ts is None:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age = (now - ts).total_seconds() / 3600.0
        ages.append(age)
    latest = round(min(ages), 2) if ages else None
    return {
        "r2_object_count": len(objects),
        "r2_latest_object_age_hours": latest,
        "r2_stale_snapshot": (
            latest is None or latest > MAX_SNAPSHOT_AGE_HOURS
        ),
        "r2_lister_present": True,
    }


def _read_procedure_last_review(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, IsADirectoryError, OSError):
        return None
    match = _LAST_REVIEW_RE.search(text)
    return match.group(1) if match else None


def collect(
    *,
    repo: str | None = None,
    days: int = 90,
    now: datetime | None = None,
    runner: Any | None = None,
    r2_lister: Callable[[], Iterable[Mapping[str, Any]]] | None = None,
    procedure_path: Path | None = None,
) -> dict[str, Any]:
    """Collect backup-drill evidence.

    ``days`` defaults to 90 so the result captures the rolling
    quarterly window the auditor checks against
    ``procedure-backup-restore.md``.
    """
    now = now or datetime.now(timezone.utc)
    drill = _drill_runs(repo=repo, days=days, now=now, runner=runner)
    total = drill.get("total", 0)
    success = drill.get("success", 0)
    success_rate = (success / total) if total else None
    r2 = _r2_summary(lister=r2_lister, now=now)
    last_review = _read_procedure_last_review(
        procedure_path or PROCEDURE_PATH
    )
    return {
        "collector": "backup_drills",
        "control_refs": ["A1.3", "CC7.5", "PI1.5"],
        "generated_at": now.isoformat(),
        "window_days": days,
        "drill_total": total,
        "drill_success": success,
        "drill_failure": drill.get("failure", 0),
        "drill_success_rate": (
            round(success_rate, 4) if success_rate is not None else None
        ),
        "last_failure": drill.get("last_failure"),
        "procedure_last_review": last_review,
        **r2,
    }


def write_marker(out_dir: Path, payload: Mapping[str, Any]) -> Path:
    """Write a small JSON marker the auditor can grep for. Returns the path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "backup_drills.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n")
    return path
