#!/usr/bin/env python3
"""SOC 2 Type I pre-audit pre-flight gate (T-070-final).

Exits non-zero when **any** required artifact for a SOC 2 Type I
engagement is missing. The script is intentionally narrow: it does not
attempt to *evaluate* a control, only to confirm the evidence file
exists, is non-empty, and (where applicable) is recent enough.

It is consumed in three places:

1. ``.github/workflows/soc2-evidence.yml`` — fails the weekly job if
   the auto-collection step produced an incomplete snapshot.
2. The T-minus-90-day audit-prep checklist in
   ``compliance/soc2/README.md``.
3. A developer can run it locally:
   ``python scripts/soc2_preflight.py``.

The required-artifact list is the single source of truth — change it
here and the evidence matrix doc in the same PR.

Usage::

    python scripts/soc2_preflight.py [--evidence-root PATH] [--json] [--quiet]

Exit codes:

* 0 — every required artifact is present and fresh.
* 1 — at least one required artifact is missing / stale.
* 2 — CLI usage error.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE_ROOT = REPO_ROOT / "compliance" / "soc2" / "evidence"


@dataclass(frozen=True)
class RequiredArtifact:
    """A single artifact the pre-flight gate insists on.

    ``path`` is relative to the repo root. ``max_age_days=None`` means
    "presence-only" — the file must exist and be non-empty but its
    mtime is not checked (used for living policy docs that are reviewed
    via their header date, not their mtime).
    """

    path: str
    description: str
    control_refs: tuple[str, ...]
    max_age_days: int | None = None


REQUIRED_ARTIFACTS: tuple[RequiredArtifact, ...] = (
    # ---- T-070 policy + procedure documents ------------------------------
    RequiredArtifact(
        "compliance/soc2/policy-information-security.md",
        "Information-security policy",
        ("CC1.1", "CC1.3"),
    ),
    RequiredArtifact(
        "compliance/soc2/policy-access-control.md",
        "Access-control policy",
        ("CC6.1",),
    ),
    RequiredArtifact(
        "compliance/soc2/policy-incident-response.md",
        "Incident-response policy",
        ("CC7.3", "CC7.4"),
    ),
    RequiredArtifact(
        "compliance/soc2/policy-data-classification.md",
        "Data-classification policy",
        ("C1.1", "CC6.5"),
    ),
    RequiredArtifact(
        "compliance/soc2/policy-vendor-management.md",
        "Vendor / sub-processor policy",
        ("CC9.2",),
    ),
    RequiredArtifact(
        "compliance/soc2/policy-business-continuity.md",
        "Business-continuity policy",
        ("A1.3", "CC7.5"),
    ),
    RequiredArtifact(
        "compliance/soc2/policy-change-management.md",
        "Change-management policy",
        ("CC8.1",),
    ),
    RequiredArtifact(
        "compliance/soc2/procedure-onboarding-offboarding.md",
        "Joiner / leaver procedure",
        ("CC6.2", "CC6.3"),
    ),
    RequiredArtifact(
        "compliance/soc2/procedure-backup-restore.md",
        "Backup / restore procedure + drill log",
        ("A1.3", "PI1.5"),
    ),
    RequiredArtifact(
        "compliance/soc2/evidence-matrix.md",
        "TSC → artifact evidence matrix",
        ("CC5.1",),
    ),
    RequiredArtifact(
        "compliance/soc2/risk-register.md",
        "Risk register",
        ("CC3.2", "CC9.1"),
    ),
    # ---- Operational artifacts produced by other tasks -------------------
    RequiredArtifact(
        "scripts/backup_sqlite.py",
        "T-013 backup script",
        ("A1.3",),
    ),
    RequiredArtifact(
        "scripts/backup_sqlite.sh",
        "T-013 backup wrapper",
        ("A1.3",),
    ),
    RequiredArtifact(
        ".github/workflows/backup-restore-drill.yml",
        "T-013 weekly restore-drill workflow",
        ("A1.3", "PI1.5"),
    ),
    RequiredArtifact(
        "rate_limit.py",
        "T-015 rate-limit middleware",
        ("CC6.1", "CC7.2"),
    ),
    RequiredArtifact(
        "schemas/openapi.yaml",
        "T-029 OpenAPI 3.1 spec for pen-test scoping",
        ("CC4.2",),
    ),
    RequiredArtifact(
        "docs/pentest-scope-of-work.md",
        "T-029 pen-test scope-of-work",
        ("CC4.2",),
    ),
    RequiredArtifact(
        "server_app/services/audit_export.py",
        "T-043 audit-log export service",
        ("CC7.1", "PI1.4"),
    ),
    RequiredArtifact(
        "server_app/metrics.py",
        "T-014 Prometheus metrics surface",
        ("CC4.1", "CC7.1"),
    ),
    RequiredArtifact(
        "server_app/routes/metrics.py",
        "T-014 /metrics route binding",
        ("CC4.1",),
    ),
    # ---- Automation pieces shipped by T-070-final ------------------------
    RequiredArtifact(
        "compliance/soc2/automation/orchestrator.py",
        "Weekly evidence orchestrator",
        ("CC5.2",),
    ),
    RequiredArtifact(
        ".github/workflows/soc2-evidence.yml",
        "Weekly evidence GitHub Actions workflow",
        ("CC5.2",),
    ),
)


@dataclass
class Finding:
    artifact: RequiredArtifact
    kind: str  # "missing" | "empty" | "stale"
    detail: str


@dataclass
class Report:
    repo_root: Path
    findings: list[Finding] = field(default_factory=list)
    checked: int = 0
    latest_evidence_dir: Path | None = None
    evidence_dirs: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.findings

    def to_dict(self) -> dict[str, object]:
        latest_path: str | None = None
        if self.latest_evidence_dir is not None:
            try:
                latest_path = str(
                    self.latest_evidence_dir.relative_to(self.repo_root)
                )
            except ValueError:
                latest_path = str(self.latest_evidence_dir)
        return {
            "ok": self.ok,
            "checked": self.checked,
            "findings": [
                {
                    "path": f.artifact.path,
                    "description": f.artifact.description,
                    "control_refs": list(f.artifact.control_refs),
                    "kind": f.kind,
                    "detail": f.detail,
                }
                for f in self.findings
            ],
            "latest_evidence_dir": latest_path,
            "evidence_dirs": self.evidence_dirs,
        }


def _check_artifact(
    repo_root: Path,
    artifact: RequiredArtifact,
    now: datetime,
) -> Finding | None:
    target = repo_root / artifact.path
    if not target.exists():
        return Finding(artifact, "missing", f"{artifact.path} not found")
    try:
        size = target.stat().st_size
    except OSError as exc:
        return Finding(artifact, "missing", f"{artifact.path}: stat failed: {exc}")
    if size == 0:
        return Finding(artifact, "empty", f"{artifact.path} is zero bytes")
    if artifact.max_age_days is not None:
        mtime = datetime.fromtimestamp(target.stat().st_mtime, tz=timezone.utc)
        age = now - mtime
        if age > timedelta(days=artifact.max_age_days):
            return Finding(
                artifact,
                "stale",
                f"{artifact.path} last modified {age.days}d ago "
                f"(limit {artifact.max_age_days}d)",
            )
    return None


def _evidence_dirs(evidence_root: Path) -> list[Path]:
    if not evidence_root.exists():
        return []
    out: list[Path] = []
    for child in sorted(evidence_root.iterdir()):
        if child.is_dir() and child.name[:4].isdigit():
            out.append(child)
    return out


def run_preflight(
    *,
    repo_root: Path | None = None,
    evidence_root: Path | None = None,
    artifacts: Iterable[RequiredArtifact] | None = None,
    now: datetime | None = None,
    require_recent_evidence_days: int | None = None,
) -> Report:
    """Run the gate and return a :class:`Report`.

    ``require_recent_evidence_days`` defaults to ``None`` for the CLI
    so the gate stays green in a fresh checkout where the weekly cron
    hasn't run yet. The audit-prep README links a separate invocation
    that passes a value here.
    """
    repo_root = repo_root or REPO_ROOT
    evidence_root = evidence_root or (repo_root / "compliance/soc2/evidence")
    now = now or datetime.now(timezone.utc)
    artifacts = list(artifacts or REQUIRED_ARTIFACTS)
    report = Report(repo_root=repo_root)
    for artifact in artifacts:
        report.checked += 1
        finding = _check_artifact(repo_root, artifact, now)
        if finding is not None:
            report.findings.append(finding)

    dirs = _evidence_dirs(evidence_root)
    report.evidence_dirs = [d.name for d in dirs]
    if dirs:
        report.latest_evidence_dir = dirs[-1]
    if require_recent_evidence_days is not None:
        if not dirs:
            try:
                rel_evidence = str(evidence_root.relative_to(repo_root))
            except ValueError:
                rel_evidence = str(evidence_root)
            report.findings.append(
                Finding(
                    RequiredArtifact(
                        rel_evidence,
                        "Weekly evidence directory",
                        ("CC5.2",),
                    ),
                    "missing",
                    "no compliance/soc2/evidence/YYYY-WW directory found",
                )
            )
        else:
            latest = dirs[-1]
            try:
                mtime = datetime.fromtimestamp(latest.stat().st_mtime, tz=timezone.utc)
            except OSError:
                mtime = now - timedelta(days=require_recent_evidence_days + 1)
            age = now - mtime
            if age > timedelta(days=require_recent_evidence_days):
                try:
                    rel_path = str(latest.relative_to(repo_root))
                except ValueError:
                    rel_path = str(latest)
                report.findings.append(
                    Finding(
                        RequiredArtifact(
                            rel_path,
                            "Most recent weekly evidence snapshot",
                            ("CC5.2",),
                        ),
                        "stale",
                        f"latest evidence dir is {age.days}d old "
                        f"(limit {require_recent_evidence_days}d)",
                    )
                )
    return report


def _format_text(report: Report) -> str:
    lines = [
        f"checked {report.checked} required artifacts; "
        f"{len(report.findings)} finding(s)."
    ]
    if report.latest_evidence_dir is not None:
        lines.append(f"latest evidence dir: {report.latest_evidence_dir.name}")
    for f in report.findings:
        controls = ", ".join(f.artifact.control_refs)
        lines.append(f"  [{f.kind.upper():7s}] ({controls}) {f.detail}")
    if report.ok:
        lines.append("OK")
    else:
        lines.append("FAIL")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="soc2_preflight",
        description="Verify every SOC 2 Type I required artifact is present.",
    )
    parser.add_argument(
        "--evidence-root",
        type=Path,
        default=DEFAULT_EVIDENCE_ROOT,
        help="Directory holding per-week evidence snapshots.",
    )
    parser.add_argument(
        "--require-recent-evidence-days",
        type=int,
        default=None,
        help=(
            "If set, also fail when no YYYY-WW evidence directory has "
            "been touched in this many days."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON report.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only emit on failure.",
    )
    args = parser.parse_args(argv)

    report = run_preflight(
        evidence_root=args.evidence_root,
        require_recent_evidence_days=args.require_recent_evidence_days,
    )

    if args.json:
        sys.stdout.write(json.dumps(report.to_dict(), indent=2) + "\n")
    elif not (args.quiet and report.ok):
        sys.stdout.write(_format_text(report) + "\n")
    return 0 if report.ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
