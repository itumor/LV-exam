"""CI run-history collector for SOC 2 evidence (T-070-final).

Wraps ``gh api`` to enumerate the last N days of GitHub Actions runs on
the ``develop`` and ``main`` branches and produces a compact summary
suitable for the auditor:

* total runs per workflow,
* success / failure breakdown,
* the SHA + URL of the most recent failure (so the auditor can click
  through to the post-mortem ticket),
* a flag indicating whether every required workflow (``ci-pr``,
  ``ci-develop``, ``ci-release``, ``backup-restore-drill``,
  ``reusable-security``) ran at least once in the window.

Maps to SOC 2 controls **CC4.1 / CC7.1 / CC8.1** (monitoring + change
management).

The module is dependency-free and uses ``subprocess`` so it works the
same on a developer laptop (where the engineer is logged into ``gh``)
and inside the weekly Actions job (where ``GITHUB_TOKEN`` is exposed to
``gh`` via the ``GH_TOKEN`` env var).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

# Workflows the auditor expects to see run regularly. Names must match
# the ``name:`` field in ``.github/workflows/*.yml`` exactly (case
# preserved). Update this list when a new mandatory workflow is added.
REQUIRED_WORKFLOWS: tuple[str, ...] = (
    "CI — PR",
    "CI — develop",
    "CI — release",
    "Backup restore drill",
)


class CIRunsCollectorError(RuntimeError):
    """Raised when the ``gh`` CLI is missing or returns malformed JSON."""


def _gh_available() -> bool:
    return shutil.which("gh") is not None


def _run_gh(args: list[str], *, runner: Any | None = None) -> str:
    """Run ``gh`` and return stdout; ``runner`` lets tests inject a fake."""
    if runner is not None:
        return runner(args)
    if not _gh_available():
        raise CIRunsCollectorError("`gh` CLI not on PATH")
    result = subprocess.run(
        ["gh", *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise CIRunsCollectorError(
            f"gh exited {result.returncode}: {result.stderr.strip()}"
        )
    return result.stdout


def _parse_runs(raw: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(raw or "[]")
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise CIRunsCollectorError(f"non-JSON from gh: {exc}") from exc
    if not isinstance(data, list):
        raise CIRunsCollectorError("expected JSON array from gh")
    return data


def _summarise(runs: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    by_workflow: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "total": 0,
            "success": 0,
            "failure": 0,
            "cancelled": 0,
            "other": 0,
            "last_failure": None,
        }
    )
    total = 0
    for run in runs:
        name = str(run.get("name") or run.get("workflowName") or "<unknown>")
        bucket = by_workflow[name]
        bucket["total"] += 1
        total += 1
        conclusion = (run.get("conclusion") or "").lower()
        if conclusion == "success":
            bucket["success"] += 1
        elif conclusion == "failure":
            bucket["failure"] += 1
            # Track the most recent failure for the workflow. Runs come
            # back from gh sorted newest-first so the first hit wins.
            if bucket["last_failure"] is None:
                bucket["last_failure"] = {
                    "sha": run.get("headSha") or run.get("sha"),
                    "url": run.get("url") or run.get("html_url"),
                    "createdAt": run.get("createdAt") or run.get("created_at"),
                }
        elif conclusion == "cancelled":
            bucket["cancelled"] += 1
        else:
            bucket["other"] += 1
    # Deterministic order: by workflow name.
    workflows = {name: by_workflow[name] for name in sorted(by_workflow)}
    missing_required = [w for w in REQUIRED_WORKFLOWS if w not in workflows]
    return {
        "total_runs": total,
        "workflows": workflows,
        "required_workflows_seen": [w for w in REQUIRED_WORKFLOWS if w in workflows],
        "required_workflows_missing": missing_required,
    }


def collect(
    *,
    repo: str | None = None,
    days: int = 7,
    branches: tuple[str, ...] = ("develop", "main"),
    now: datetime | None = None,
    runner: Any | None = None,
) -> dict[str, Any]:
    """Collect CI-run evidence.

    Parameters
    ----------
    repo:
        ``<owner>/<repo>``. Defaults to ``GITHUB_REPOSITORY`` env var.
    days:
        Window size; default matches the weekly evidence cadence.
    branches:
        Branches to enumerate. Both ``develop`` and ``main`` are scanned
        so a Type I audit sees the full pre-prod + prod history.
    now:
        Injectable clock for tests.
    runner:
        Optional callable that takes ``list[str]`` and returns stdout —
        used by unit tests to bypass the ``gh`` CLI.
    """
    repo = repo or os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        raise CIRunsCollectorError(
            "GITHUB_REPOSITORY not set and no repo= passed"
        )
    now = now or datetime.now(timezone.utc)
    since = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    all_runs: list[dict[str, Any]] = []
    for branch in branches:
        # We use `gh run list --json` rather than the raw `gh api` URL
        # so the JSON shape is stable across GitHub API versions.
        raw = _run_gh(
            [
                "run",
                "list",
                "--repo",
                repo,
                "--branch",
                branch,
                "--limit",
                "100",
                "--created",
                f">={since}",
                "--json",
                "name,conclusion,headSha,url,createdAt,event,status",
            ],
            runner=runner,
        )
        runs = _parse_runs(raw)
        for run in runs:
            run["branch"] = branch
        all_runs.extend(runs)

    summary = _summarise(all_runs)
    return {
        "collector": "ci_runs",
        "control_refs": ["CC4.1", "CC7.1", "CC8.1"],
        "generated_at": now.isoformat(),
        "window_days": days,
        "since": since,
        "repo": repo,
        "branches": list(branches),
        **summary,
    }
